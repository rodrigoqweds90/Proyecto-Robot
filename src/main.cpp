// =====================================================================
// ROBOT CONTROL — firmware ESP32 + PCA9685
// El PC habla por Serial en el formato:  canal,pulso_us,velocidad
// Busca "SEGMENTO:" para saltar directo a cada parte del codigo.
// =====================================================================

#include <Wire.h>
#include <WiFi.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_SSD1306.h>
#include <Bluepad32.h>
#include <bt/uni_bt_le.h>
#include <Preferences.h>
#include <lwip/sockets.h> // socket crudo: WiFiClient::write() bloquea, ver enviarLinea()
#include <errno.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);
Preferences prefs;

// =====================================================================
// SEGMENTO: MODO DE ARRANQUE — MANDO (Bluetooth) o WIFI, nunca los dos
// Bluepad32 con WiFi prendido a la vez tiene cuelgues reportados y sin
// solucion (ver el vault, "Bluetooth del mando"). El modo se guarda en la
// flash (clave "modo" del espacio "robot") y se elige UNA vez al prender:
// este app_main reemplaza al del paquete Bluepad32, que prendia el
// Bluetooth siempre. Para cambiar de modo: comando MODO,WIFI o MODO,MANDO
// (por USB funciona en los dos modos) y el ESP32 se reinicia solo.
// Por USB (Serial) se puede hablar con el robot en cualquiera de los dos.
// =====================================================================
extern "C" {
#include <arduino_bootstrap.h>
#include <arduino_platform.h>
#include <btstack_port_esp32.h>
#include <btstack_run_loop.h>
#include <nvs.h>
#include <nvs_flash.h>
#include <platform/uni_platform.h>
#include <uni_init.h>
}

#define MODO_MANDO 0   // default: un ESP32 recien flasheado arranca con el mando
#define MODO_WIFI  1
bool modoMando = true;

uint8_t leerModoArranque() {
  uint8_t modo = MODO_MANDO;
  nvs_handle_t h;
  // Solo se lee: si la flash da error se arranca con el mando, nunca se borra
  // (ahi tambien vive la pose de Inicio guardada).
  if (nvs_flash_init() == ESP_OK && nvs_open("robot", NVS_READONLY, &h) == ESP_OK) {
    nvs_get_u8(h, "modo", &modo);
    nvs_close(h);
  }
  return modo;
}

extern "C" void app_main() {
  modoMando = leerModoArranque() != MODO_WIFI;
  if (!modoMando) {
    arduino_bootstrap();  // solo Arduino (setup/loop): el Bluetooth no se toca
    return;
  }
  // Lo mismo que hace el app_main original de Bluepad32
  btstack_init();
  uni_platform_set_custom(get_arduino_platform());
  uni_init(0, nullptr);
  btstack_run_loop_execute();
}

// =====================================================================
// SEGMENTO: WIFI (RED PROPIA DEL ROBOT)
// El ESP32 crea su propia red — no depende de un router. Se conecta como
// respaldo/alternativa al cable USB: los dos canales funcionan a la vez,
// hablan el mismo protocolo de texto por linea.
// =====================================================================
const char* WIFI_SSID     = "RobotControl";
const char* WIFI_PASSWORD = "robot1234"; // minimo 8 caracteres (WPA2)
const uint16_t PUERTO_TCP = 8888;

WiFiServer servidorTCP(PUERTO_TCP);
WiFiClient clienteTCP;

// Manda una linea por los dos canales a la vez (el que no tenga a nadie
// escuchando simplemente no hace nada). Todo el resto del programa usa
// esta funcion en vez de Serial.print directo, para no tener que acordarse
// de duplicar cada mensaje.
void enviarLinea(const String &texto) {
  Serial.println(texto);
  if (!clienteTCP || !clienteTCP.connected()) return;

  // NO se usa clienteTCP.println(). El write() de WiFiClient hace select()
  // de 1 segundo y reintenta hasta 10 veces, o sea que un solo println()
  // puede dejar clavado el loop() hasta 10 segundos si la cola de envio de
  // TCP esta llena -- y mientras el loop() esta clavado no avanza ninguna
  // rampa, los servos se congelan a mitad de camino. Ademas println() son
  // dos write() (el texto y el "\r\n"), o sea dos paquetes TCP por linea
  // con TCP_NODELAY puesto.
  //
  // Aca se manda todo de una sola vez y con MSG_DONTWAIT: si no entra, la
  // linea se descarta y seguimos. Es telemetria para la consola de la app;
  // vale mucho menos que mantener el movimiento fluido.
  int descriptor = clienteTCP.fd();
  if (descriptor < 0) return;
  String conSalto = texto + "\n";
  int enviados = lwip_send(descriptor, conSalto.c_str(), conSalto.length(), MSG_DONTWAIT);
  if (enviados < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
    clienteTCP.stop(); // el socket murio de verdad, se libera para reconectar
  }
}

// =====================================================================
// SEGMENTO: CONFIGURACION Y VARIABLES GLOBALES
// =====================================================================
#define SERVO_FREQ      50      // Frecuencia PWM para servos (50 Hz -> periodo de 20000 us)
#define PULSO_MIN_ABS   500     // Limite absoluto de seguridad, ningun canal puede salir de aqui
#define PULSO_MAX_ABS   2450
#define PULSO_CENTRO    1475
#define NUM_CANALES     16
#define TICK_RAMPA_MS   15      // Cada cuanto se actualiza el movimiento suave

bool  pcaDisponible    = false;
bool  emergenciaActiva = false;

unsigned long ultimoTickRampa  = 0;

struct CanalServo {
  float pulsoActual;
  float pulsoObjetivo;
  float pasoPorTick; // us que avanza cada TICK_RAMPA_MS. 0 = todavia no seteado
  bool  activo;       // false tras STOP/RELAX hasta el proximo comando de movimiento
  // Movimiento por tiempo (POSET): sale de pulsoInicio en tInicio y llega a pulsoObjetivo
  // justo a los duracionMs, con arranque y frenado suaves. duracionMs = 0 => rampa por
  // velocidad de siempre (pasoPorTick).
  float pulsoInicio;
  unsigned long tInicio;
  uint32_t duracionMs;
  bool lineal;        // POSET con modo 1: velocidad pareja, sin frenar (tramos cortos de una curva continua)
};
CanalServo canales[NUM_CANALES];

// =====================================================================
// SEGMENTO: CONTROL DE SERVOS (PULSOS Y RAMPAS)
// =====================================================================
uint16_t usATicks(uint16_t us) {
  float periodo_us = 1000000.0 / SERVO_FREQ;
  float ticks = (us / periodo_us) * 4096.0;
  return (uint16_t) round(ticks);
}

void escribirSalida(uint8_t canal) {
  pwm.setPWM(canal, 0, usATicks((uint16_t) lround(canales[canal].pulsoActual)));
}

void aplicarPulso(uint8_t canal, uint16_t us) {
  canales[canal].pulsoActual = constrain(us, PULSO_MIN_ABS, PULSO_MAX_ABS);
  escribirSalida(canal);
}

// Mueve un canal hacia un pulso objetivo. velocidad=0 => salto inmediato,
// velocidad>0 => avanza esa cantidad de us cada TICK_RAMPA_MS (no bloqueante).
// 'avisar' en false: mueve el canal sin mandar el eco "M,...". Lo usan POSE
// y HOME, que tocan los 16 canales de una sola vez: devolver 16 ecos por cada
// paso llenaba el buffer de salida (USB o WiFi) y dejaba a loop() bloqueado
// escribiendo justo cuando tenia que estar avanzando las rampas. Se sentia
// como que el robot caminaba, se trababa, se lentiaba y terminaba quieto.
void comandoMover(uint8_t canal, uint16_t pulsoUs, uint16_t velocidad, bool avisar = true) {
  if (canal >= NUM_CANALES) {
    enviarLinea("Canal invalido (0-15)");
    return;
  }
  if (emergenciaActiva) {
    enviarLinea("STOP activo. Envia RESUME antes de mover.");
    return;
  }
  pulsoUs = constrain(pulsoUs, PULSO_MIN_ABS, PULSO_MAX_ABS);
  canales[canal].activo = true;
  canales[canal].pulsoObjetivo = pulsoUs;
  canales[canal].duracionMs = 0;   // cualquier comando por velocidad corta un POSET en curso

  if (velocidad == 0) {
    aplicarPulso(canal, pulsoUs);
  } else {
    canales[canal].pasoPorTick = velocidad;
  }

  if (avisar) {
    enviarLinea("M," + String(canal) + "," + String(pulsoUs) + "," + String(velocidad));
  }
}

// Avanza todas las rampas activas. Se llama en cada vuelta de loop().
void actualizarRampas() {
  unsigned long ahora = millis();
  if (ahora - ultimoTickRampa < TICK_RAMPA_MS) return;
  ultimoTickRampa = ahora;

  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    if (!canales[canal].activo) continue;
    float diff = canales[canal].pulsoObjetivo - canales[canal].pulsoActual;
    if (fabs(diff) < 1.0f) continue;

    if (canales[canal].duracionMs > 0) {
      // POSET: posicion segun el tiempo transcurrido (todos los canales de la pose llegan juntos)
      float f = (float) (ahora - canales[canal].tInicio) / (float) canales[canal].duracionMs;
      if (f >= 1.0f) {
        canales[canal].pulsoActual = canales[canal].pulsoObjetivo;
        canales[canal].duracionMs = 0;
      } else {
        float s = canales[canal].lineal ? f : f * f * (3.0f - 2.0f * f);   // lineal o con arranque y frenado suaves
        canales[canal].pulsoActual = canales[canal].pulsoInicio +
                                     (canales[canal].pulsoObjetivo - canales[canal].pulsoInicio) * s;
      }
    } else {
      float paso = canales[canal].pasoPorTick;
      if (paso <= 0) paso = 40; // respaldo por si se pidio rampa sin velocidad definida
      canales[canal].pulsoActual += (diff > 0 ? min(paso, diff) : max(-paso, diff));
    }
    escribirSalida(canal);
  }
}

void mostrarPulsos() {
  enviarLinea("---- Pulsos actuales (us) ----");
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    enviarLinea("Canal " + String(canal) + ": " + String((int) canales[canal].pulsoActual));
  }
  enviarLinea("-------------------------------");
}

// =====================================================================
// SEGMENTO: PANTALLA OLED (CARAS) — mismo bus I2C que el PCA9685 (21/22).
// La cara queda fija y solo se redibuja cuando se cambia. Mandar la
// pantalla entera de una vez tarda ~25 ms y congelaria los servos ese
// tiempo, asi que se manda de a una pagina (1/8 de pantalla, ~3.5 ms)
// por vuelta de loop(), intercalada con las rampas.
// =====================================================================
#define PANTALLA_ANCHO    128
#define PANTALLA_ALTO     64
#define PANTALLA_PAGINAS  (PANTALLA_ALTO / 8)

// 400 kHz durante Y despues de cada envio: con el valor por defecto
// (100 kHz despues) la libreria dejaria el bus lento para el PCA9685.
Adafruit_SSD1306 pantalla(PANTALLA_ANCHO, PANTALLA_ALTO, &Wire, -1, 400000UL, 400000UL);
bool pantallaDisponible = false;
// Los OLED vienen en 0x3C (la mayoria) o 0x3D segun el puente de atras:
// se busca al arrancar. begin() de Adafruit no avisa si no hay nadie.
uint8_t pantallaDir = 0;
uint8_t paginaPendiente = PANTALLA_PAGINAS; // PANTALLA_PAGINAS = nada por mandar

enum Expresion { CARA_NEUTRAL, CARA_FELIZ, CARA_TRISTE, CARA_SORPRESA };

// Traza un arco (para la boca) sumando pequenos segmentos de recta.
// angulos en grados, convencion de pantalla (0=derecha, 90=abajo).
void dibujarArco(int cx, int cy, int radio, float anguloInicioGrados, float anguloFinGrados) {
  float rad0 = radians(anguloInicioGrados);
  int xAnt = cx + radio * cos(rad0);
  int yAnt = cy + radio * sin(rad0);
  for (float g = anguloInicioGrados + 5; g <= anguloFinGrados; g += 5) {
    float rad = radians(g);
    int x = cx + radio * cos(rad);
    int y = cy + radio * sin(rad);
    pantalla.drawLine(xAnt, yAnt, x, y, SSD1306_WHITE);
    xAnt = x; yAnt = y;
  }
}

void dibujarCara(Expresion expresion) {
  if (!pantallaDisponible) return;
  pantalla.clearDisplay();

  const int ojoIzqX = 40, ojoDerX = 88, ojoY = 26;
  int radioOjo = (expresion == CARA_SORPRESA) ? 15 : 12;
  pantalla.fillCircle(ojoIzqX, ojoY, radioOjo, SSD1306_WHITE);
  pantalla.fillCircle(ojoDerX, ojoY, radioOjo, SSD1306_WHITE);

  const int bocaX = 64, bocaY = 44;
  switch (expresion) {
    case CARA_FELIZ:
      dibujarArco(bocaX, bocaY - 6, 16, 20, 160);  // arco de abajo: sonrisa
      break;
    case CARA_TRISTE:
      dibujarArco(bocaX, bocaY + 10, 16, 200, 340); // arco de arriba: tristeza
      break;
    case CARA_SORPRESA:
      pantalla.drawCircle(bocaX, bocaY + 4, 5, SSD1306_WHITE); // boca en "O"
      break;
    case CARA_NEUTRAL:
    default:
      pantalla.drawLine(bocaX - 14, bocaY, bocaX + 14, bocaY, SSD1306_WHITE);
      break;
  }

  paginaPendiente = 0; // la manda actualizarPantalla() de a poco
}

// Manda una pagina pendiente de la cara (128 bytes) por llamada.
void actualizarPantalla() {
  if (!pantallaDisponible || paginaPendiente >= PANTALLA_PAGINAS) return;
  pantalla.ssd1306_command(SSD1306_COLUMNADDR);
  pantalla.ssd1306_command(0);
  pantalla.ssd1306_command(PANTALLA_ANCHO - 1);
  pantalla.ssd1306_command(SSD1306_PAGEADDR);
  pantalla.ssd1306_command(paginaPendiente);
  pantalla.ssd1306_command(paginaPendiente);
  const uint8_t *datos = pantalla.getBuffer() + paginaPendiente * PANTALLA_ANCHO;
  for (uint8_t i = 0; i < PANTALLA_ANCHO; i += 32) {
    Wire.beginTransmission(pantallaDir);
    Wire.write(0x40); // lo que sigue son pixeles, no comandos
    Wire.write(datos + i, 32);
    Wire.endTransmission();
  }
  paginaPendiente++;
}

// =====================================================================
// SEGMENTO: PARADA DE EMERGENCIA Y RELAJAR
// =====================================================================
void pararEmergencia() {
  emergenciaActiva = true;
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    pwm.setPin(canal, 0, false); // fuerza la salida a "siempre apagada", sin PWM
    canales[canal].activo = false;
  }
  dibujarCara(CARA_TRISTE);
  enviarLinea("STOP,activado");
}

void reanudar() {
  emergenciaActiva = false;
  dibujarCara(CARA_NEUTRAL);
  enviarLinea("STOP,desactivado. Envia HOME o posiciones para mover.");
}

void relajar() {
  if (emergenciaActiva) {
    enviarLinea("STOP activo. Envia RESUME primero.");
    return;
  }
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    pwm.setPin(canal, 0, false);
    canales[canal].activo = false;
  }
  enviarLinea("RELAX,ok");
}

// =====================================================================
// SEGMENTO: POSICION DE INICIO (HOME) — persiste al apagar el robot
// =====================================================================
bool cargarHome(uint16_t* destino) {
  size_t esperado = sizeof(uint16_t) * NUM_CANALES;
  if (prefs.isKey("home") && prefs.getBytesLength("home") == esperado) {
    prefs.getBytes("home", destino, esperado);
    return true;
  }
  return false;
}

void guardarHome() {
  uint16_t valores[NUM_CANALES];
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    valores[canal] = (uint16_t) canales[canal].pulsoActual;
  }
  prefs.putBytes("home", valores, sizeof(valores));
  enviarLinea("HOMESET,ok");
}

void irAHome() {
  if (emergenciaActiva) {
    enviarLinea("STOP activo. Envia RESUME primero.");
    return;
  }
  uint16_t home[NUM_CANALES];
  if (!cargarHome(home)) {
    for (uint8_t canal = 0; canal < NUM_CANALES; canal++) home[canal] = PULSO_CENTRO;
  }
  // Un solo mensaje con los 16 pulsos de destino, para que la app sincronice
  // los sliders de una vez -- HOME es el unico caso donde la app no sabe de
  // antemano a que pulso va cada canal (eso vive guardado aca, no en la app).
  String reporte = "HOME,ok";
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    comandoMover(canal, home[canal], 10, false);
    reporte += "," + String(home[canal]);
  }
  enviarLinea(reporte);
}

// Lleva los 16 servos al centro (90 grados) sin mirar la calibracion: es la posicion con la que se
// colocan los horns usando los soportes de armado (piernas rectas). Mismo formato de respuesta que HOME
// para que la app sincronice los sliders.
void centrarTodos() {
  if (emergenciaActiva) {
    enviarLinea("STOP activo. Envia RESUME primero.");
    return;
  }
  String reporte = "HOME,ok";
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    comandoMover(canal, PULSO_CENTRO, 10, false);
    reporte += "," + String(PULSO_CENTRO);
  }
  enviarLinea(reporte);
  enviarLinea("CENTRAR,ok - todos en 90 grados: pon los horns con el robot en los soportes de armado");
}

// =====================================================================
// SEGMENTO: DIAGNOSTICO I2C
// =====================================================================
void escanearI2C() {
  enviarLinea("Escaneando bus I2C (SDA=21, SCL=22)...");
  int encontrados = 0;
  for (uint8_t direccion = 1; direccion < 127; direccion++) {
    Wire.beginTransmission(direccion);
    if (Wire.endTransmission() == 0) {
      String hex = String(direccion, HEX);
      if (direccion < 16) hex = "0" + hex;
      enviarLinea("  Dispositivo encontrado en 0x" + hex);
      encontrados++;
    }
  }
  if (encontrados == 0) {
    enviarLinea("Nada respondio en el bus. Revisa alimentacion (3V3/GND) y que SDA/SCL no esten al reves.");
  } else {
    enviarLinea(String(encontrados) + " dispositivo(s) encontrado(s). PCA9685 deberia ser 0x40.");
  }
}

void reportarEstado(); // definida despues de setup(), la usan setup() y loop()

// =====================================================================
// SEGMENTO: MANDO (BLUEPAD32) — solo en modo MANDO
// El EasySMX D10 va en modo Switch (Bluetooth clasico): Bluepad32 lo ve
// como Switch Pro. Por ahora solo avisa que boton cambia, con las mismas
// claves de la pestana Mando de la app (MANDO_BOTON,<clave>,presionado|soltado).
// =====================================================================
#define UMBRAL_PALANCA 250   // de -511 a 512: mas que esto cuenta como direccion apretada

ControllerPtr mando = nullptr;
uint32_t botonesAnteriores = 0;

const char* CLAVES_MANDO[] = {
  "A", "B", "X", "Y", "LB", "RB", "LT", "RT", "VIEW", "HOME", "MENU",
  "DPAD_ARRIBA", "DPAD_ABAJO", "DPAD_IZQUIERDA", "DPAD_DERECHA",
  "LS_ARRIBA", "LS_ABAJO", "LS_IZQUIERDA", "LS_DERECHA", "LS_CLICK",
  "RS_ARRIBA", "RS_ABAJO", "RS_IZQUIERDA", "RS_DERECHA", "RS_CLICK",
};
const uint8_t NUM_CLAVES_MANDO = sizeof(CLAVES_MANDO) / sizeof(CLAVES_MANDO[0]);

void alConectarMando(ControllerPtr ctl) {
  if (mando != nullptr) {
    ctl->disconnect(); // uno solo: el robot no sabria a cual hacerle caso
    return;
  }
  mando = ctl;
  botonesAnteriores = 0;
  enviarLinea("MANDO_EMPAREJADO," + String(ctl->getModelName().c_str()));
}

void alDesconectarMando(ControllerPtr ctl) {
  if (ctl != mando) return;
  mando = nullptr;
  enviarLinea("MANDO_DESCONECTADO");
}

void iniciarMando() {
  BP32.setup(&alConectarMando, &alDesconectarMando);
  BP32.enableVirtualDevice(false);
  // El D10 ademas intenta conectarse por BLE: ese intento falla en bucle
  // ("Failed to disconnect HIDS client") y congela la entrada unos segundos.
  uni_bt_le_set_enabled(false);
  Serial.println("Modo MANDO: Bluetooth activo, WiFi apagado. Mando D10 en modo Switch.");
}

// Un bit por clave de CLAVES_MANDO, en el mismo orden.
uint32_t leerBotonesMando(ControllerPtr c) {
  uint8_t d = c->dpad(), m = c->miscButtons();
  bool b[] = {
    c->a(), c->b(),
    c->y(), c->x(),   // el D10 en modo Switch manda X e Y cruzados
    c->l1(), c->r1(), c->l2(), c->r2(),
    (bool) (m & MISC_BUTTON_SELECT), (bool) (m & MISC_BUTTON_SYSTEM), (bool) (m & MISC_BUTTON_START),
    (bool) (d & DPAD_UP), (bool) (d & DPAD_DOWN), (bool) (d & DPAD_LEFT), (bool) (d & DPAD_RIGHT),
    c->axisY() < -UMBRAL_PALANCA, c->axisY() > UMBRAL_PALANCA,
    c->axisX() < -UMBRAL_PALANCA, c->axisX() > UMBRAL_PALANCA, c->thumbL(),
    c->axisRY() < -UMBRAL_PALANCA, c->axisRY() > UMBRAL_PALANCA,
    c->axisRX() < -UMBRAL_PALANCA, c->axisRX() > UMBRAL_PALANCA, c->thumbR(),
  };
  uint32_t bits = 0;
  for (uint8_t i = 0; i < NUM_CLAVES_MANDO; i++) bits |= (uint32_t) b[i] << i;
  return bits;
}

void actualizarMando() {
  BP32.update();
  if (mando == nullptr || !mando->isConnected()) return;
  uint32_t ahora = leerBotonesMando(mando);
  uint32_t cambios = ahora ^ botonesAnteriores;
  for (uint8_t i = 0; i < NUM_CLAVES_MANDO; i++) {
    if (cambios >> i & 1) {
      enviarLinea(String("MANDO_BOTON,") + CLAVES_MANDO[i] + (ahora >> i & 1 ? ",presionado" : ",soltado"));
    }
  }
  botonesAnteriores = ahora;
}

// MODO,WIFI o MODO,MANDO: lo guarda y reinicia para aplicarlo limpio.
void cambiarModoArranque(const String &valor) {
  bool wifi = valor.equalsIgnoreCase("WIFI");
  if (!wifi && !valor.equalsIgnoreCase("MANDO")) {
    enviarLinea(String("MODO,") + (modoMando ? "MANDO" : "WIFI") + " (uso: MODO,WIFI o MODO,MANDO)");
    return;
  }
  prefs.putUChar("modo", wifi ? MODO_WIFI : MODO_MANDO);
  enviarLinea(String("MODO,") + (wifi ? "WIFI" : "MANDO") + ",reiniciando");
  Serial.flush();
  delay(200);
  esp_restart();
}

// =====================================================================
// SEGMENTO: SETUP
// =====================================================================
void setup() {
  // Buffer de salida propio antes de abrir el puerto. Sin esto, una rafaga
  // como reportarEstado() o SCAN (que mandan mas de 20 lineas seguidas) llena
  // el FIFO del UART y Serial.println bloquea el loop() hasta que se vacie.
  Serial.setTxBufferSize(2048);
  Serial.begin(115200);
  delay(500);

  Wire.begin(); // ESP32: SDA=21, SCL=22 por defecto. El PCA9685 vive en este bus.
  // 400 kHz en vez de los 100 kHz por defecto. Cada tick de rampa escribe los
  // 16 canales del PCA9685; a 100 kHz eso son ~10 ms de los 15 ms del tick, y
  // el loop() no alcanzaba a hacer nada mas. A 400 kHz baja a ~2.5 ms.
  Wire.setClock(400000);

  // Adafruit_PWMServoDriver::begin() no devuelve si encontro el chip o no,
  // asi que se comprueba a mano por I2C antes de usarlo, para no reportar
  // "listo" cuando en realidad no esta.
  Wire.beginTransmission(0x40);
  pcaDisponible = (Wire.endTransmission() == 0);

  pwm.begin();
  pwm.setPWMFreq(SERVO_FREQ);
  delay(10);

  prefs.begin("robot", false);

  // false al final: no volver a iniciar Wire, ya lo inicio el PCA9685
  for (uint8_t dir : {0x3C, 0x3D}) {
    Wire.beginTransmission(dir);
    if (Wire.endTransmission() == 0) { pantallaDir = dir; break; }
  }
  pantallaDisponible = pantallaDir && pantalla.begin(SSD1306_SWITCHCAPVCC, pantallaDir, true, false);
  if (pantallaDisponible) {
    Serial.println("Pantalla OLED en 0x" + String(pantallaDir, HEX));
    dibujarCara(CARA_FELIZ);
  } else {
    Serial.println("Aviso: pantalla OLED no encontrada. El robot funciona sin caras.");
  }

  // Al arrancar: ir directo (sin rampa, la posicion fisica real se desconoce)
  // a la posicion de HOME guardada, o al centro si nunca se guardo una.
  uint16_t home[NUM_CANALES];
  bool hayHome = cargarHome(home);
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    uint16_t destino = hayHome ? home[canal] : PULSO_CENTRO;
    canales[canal].pulsoActual = destino;
    canales[canal].pulsoObjetivo = destino;
    canales[canal].pasoPorTick = 0;
    canales[canal].activo = true;
    aplicarPulso(canal, destino);
    delay(15); // evita el pico de corriente de mover los 16 servos de golpe
  }

  if (modoMando) {
    iniciarMando();
  } else {
    WiFi.softAP(WIFI_SSID, WIFI_PASSWORD);
    WiFi.setSleep(false); // sin esto el modo ahorro de energia mete latencia extra a cada paquete
    servidorTCP.begin();
    Serial.print("WiFi AP \""); Serial.print(WIFI_SSID); Serial.print("\" activo. IP: ");
    Serial.println(WiFi.softAPIP());
  }

  reportarEstado();
}

// Resumen de que hardware detecto el robot, mas la lista de comandos. Se
// manda una vez al arrancar (por Serial, WiFi todavia no tiene a nadie
// conectado tan rapido) y de nuevo cada vez que un cliente WiFi se conecta,
// porque para ese momento el setup() original ya paso hace rato.
void reportarEstado() {
  enviarLinea(String("PCA9685: ") + (pcaDisponible ? "detectado" : "no detectado - los servos no van a responder"));
  enviarLinea(String("MODO,") + (modoMando ? "MANDO (Bluetooth, sin WiFi)" : "WIFI (sin Bluetooth)"));
  enviarLinea("Comandos disponibles:");
  enviarLinea("  canal,pulso_us,velocidad  -> mover un servo (velocidad 0 = instantaneo)");
  enviarLinea("  STOP      -> corta el PWM de todos los servos (emergencia)");
  enviarLinea("  RESUME    -> reactiva tras un STOP");
  enviarLinea("  RELAX     -> suelta el torque de todos los servos (para posar a mano)");
  enviarLinea("  POSET,p0..p15,ms[,1] -> los 16 servos llegan juntos a la pose en ms (,1 = velocidad pareja)");
  enviarLinea("  HOME      -> mueve a la posicion de inicio guardada");
  enviarLinea("  HOMESET   -> guarda la posicion actual como inicio (persiste al apagar)");
  enviarLinea("  CENTRAR   -> los 16 servos a 90 grados (para poner los horns con los soportes de armado)");
  enviarLinea("  CARA,nombre -> FELIZ / TRISTE / SORPRESA / NEUTRAL en la pantalla OLED");
  enviarLinea("  MODO,WIFI / MODO,MANDO -> elige el radio al arrancar (WiFi o mando Bluetooth) y reinicia");
  enviarLinea("  PING      -> responde PONG (para probar la conexion)");
  enviarLinea("  SCAN      -> escanea el bus I2C y lista direcciones encontradas");
  enviarLinea("  S         -> muestra los pulsos actuales de todos los canales");
  enviarLinea("Ejemplo: 0,1475,10");
}

// =====================================================================
// SEGMENTO: LOOP PRINCIPAL Y COMANDOS (SERIAL + WIFI)
// =====================================================================

// Interpreta una linea de comando venga de donde venga (USB o WiFi).
void procesarLinea(String linea) {
  linea.trim();
  if (linea.length() == 0) return;

  int primeraComa = linea.indexOf(',');
  String tipo = (primeraComa == -1) ? linea : linea.substring(0, primeraComa);
  tipo.trim();

  if (tipo.equalsIgnoreCase("S")) { mostrarPulsos(); return; }
  if (tipo.equalsIgnoreCase("STOP")) { pararEmergencia(); return; }
  if (tipo.equalsIgnoreCase("RESUME")) { reanudar(); return; }
  if (tipo.equalsIgnoreCase("RELAX")) { relajar(); return; }
  if (tipo.equalsIgnoreCase("HOME")) { irAHome(); return; }
  if (tipo.equalsIgnoreCase("HOMESET")) { guardarHome(); return; }
  if (tipo.equalsIgnoreCase("CENTRAR")) { centrarTodos(); return; }
  if (tipo.equalsIgnoreCase("PING")) { enviarLinea("PONG"); return; }
  if (tipo.equalsIgnoreCase("MODO")) {
    String valor = (primeraComa == -1) ? String() : linea.substring(primeraComa + 1);
    valor.trim();
    cambiarModoArranque(valor);
    return;
  }
  if (tipo.equalsIgnoreCase("SCAN")) { escanearI2C(); return; }
  if (tipo.equalsIgnoreCase("CARA")) {
    String nombre = linea.substring(primeraComa + 1);
    nombre.trim();
    if (nombre.equalsIgnoreCase("FELIZ")) dibujarCara(CARA_FELIZ);
    else if (nombre.equalsIgnoreCase("TRISTE")) dibujarCara(CARA_TRISTE);
    else if (nombre.equalsIgnoreCase("SORPRESA")) dibujarCara(CARA_SORPRESA);
    else dibujarCara(CARA_NEUTRAL);
    enviarLinea("CARA," + nombre);
    return;
  }

  if (tipo.equalsIgnoreCase("POSE")) {
    // Formato: POSE,p0,p1,...,p15,velocidad -> mueve los 16 canales de una
    // sola vez, en un solo mensaje (mas confiable que mandar 16 comandos
    // sueltos: por WiFi, cualquiera de esos 16 podria llegar tarde o
    // perderse y dejar la pose a medio aplicar).
    uint16_t pulsos[NUM_CANALES];
    int cursor = primeraComa + 1;
    bool formatoValido = true;
    for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
      int coma = linea.indexOf(',', cursor);
      if (coma == -1) { formatoValido = false; break; }
      pulsos[canal] = (uint16_t) linea.substring(cursor, coma).toInt();
      cursor = coma + 1;
    }
    if (!formatoValido) {
      enviarLinea("POSE invalida: se esperan 16 pulsos + velocidad.");
      return;
    }
    int velocidadLeida = linea.substring(cursor).toInt();
    uint16_t velocidad = (uint16_t) max(0, velocidadLeida);
    if (emergenciaActiva) {
      enviarLinea("STOP activo. Envia RESUME antes de mover.");
      return;
    }
    for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
      comandoMover(canal, pulsos[canal], velocidad, false);
    }
    enviarLinea("POSE,ok");
    return;
  }

  if (tipo.equalsIgnoreCase("POSET")) {
    // Formato: POSET,p0,p1,...,p15,ms[,modo] -> como POSE, pero en vez de una velocidad igual
    // para todos, cada canal se mueve a su ritmo para que los 16 lleguen JUNTOS a los ms pedidos.
    // modo 0 (o sin modo): arranque y frenado suaves. modo 1: velocidad pareja, para que la app
    // mande una curva continua en tramos cortos sin que el robot frene en cada tramo.
    // POSE sigue igual que siempre.
    uint16_t pulsos[NUM_CANALES];
    int cursor = primeraComa + 1;
    bool formatoValido = true;
    for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
      int coma = linea.indexOf(',', cursor);
      if (coma == -1) { formatoValido = false; break; }
      pulsos[canal] = (uint16_t) linea.substring(cursor, coma).toInt();
      cursor = coma + 1;
    }
    long ms = formatoValido ? linea.substring(cursor).toInt() : 0;   // toInt() corta en la coma del modo
    int comaModo = formatoValido ? linea.indexOf(',', cursor) : -1;
    bool lineal = comaModo != -1 && linea.substring(comaModo + 1).toInt() == 1;
    if (!formatoValido || ms < 0 || ms > 60000) {
      enviarLinea("POSET invalida: se esperan 16 pulsos + ms (0-60000).");
      return;
    }
    if (emergenciaActiva) {
      enviarLinea("STOP activo. Envia RESUME antes de mover.");
      return;
    }
    unsigned long ahora = millis();
    for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
      comandoMover(canal, pulsos[canal], ms == 0 ? 0 : 1, false);   // velocidad 0 = salto inmediato
      if (ms > 0) {
        canales[canal].pulsoInicio = canales[canal].pulsoActual;
        canales[canal].tInicio = ahora;
        canales[canal].duracionMs = (uint32_t) ms;
        canales[canal].lineal = lineal;
      }
    }
    enviarLinea("POSET,ok");
    return;
  }

  // Formato de movimiento: canal,pulso_us,velocidad
  int segundaComa = linea.indexOf(',', primeraComa + 1);
  if (primeraComa == -1 || segundaComa == -1) {
    enviarLinea("Comando no reconocido. Usa: canal,pulso_us,velocidad");
    return;
  }
  int canal = linea.substring(0, primeraComa).toInt();
  int pulso = linea.substring(primeraComa + 1, segundaComa).toInt();
  int velocidad = linea.substring(segundaComa + 1).toInt();

  if (canal < 0 || canal >= NUM_CANALES) {
    enviarLinea("Canal invalido (0-15)");
    return;
  }
  comandoMover((uint8_t) canal, (uint16_t) pulso, (uint16_t) max(0, velocidad));
}

// Arma lineas de a poco leyendo solo lo que ya llego, sin esperar nunca:
// readStringUntil() bloquearia el loop() (hasta 1 segundo por defecto) si
// una linea larga como POSE llega partida en varios paquetes de WiFi -- y
// mientras loop() esta bloqueado, no se actualizan las rampas de movimiento,
// lo que se sentia como trabones. bufferLinea es el acumulado de esa fuente
// entre llamadas; devuelve true y llena 'linea' recien cuando aparece '\n'.
bool leerLineaDisponible(Stream &origen, String &bufferLinea, String &linea) {
  while (origen.available()) {
    char c = (char) origen.read();
    if (c == '\n') {
      linea = bufferLinea;
      linea.trim();
      bufferLinea = "";
      return true;
    }
    if (c != '\r') {
      bufferLinea += c;
      if (bufferLinea.length() > 300) bufferLinea = ""; // linea corrupta/gigante, se descarta
    }
  }
  return false;
}

String bufferLineaSerial;
String bufferLineaWifi;

void loop() {
  actualizarRampas();
  actualizarPantalla();
  if (modoMando) actualizarMando();

  // Acepta un cliente WiFi nuevo (uno a la vez, como con el cable USB). Se
  // acepta SIEMPRE, no solo cuando el cliente viejo ya se dio por muerto: si
  // el PC pierde el WiFi de golpe y vuelve, abre un socket nuevo mientras el
  // ESP32 todavia cree que el viejo sigue vivo, y ese socket nuevo quedaria
  // esperando en la cola sin que nadie lo acepte -- la app diria "Conectado"
  // y el robot no responderia hasta reiniciarlo. Gana el ultimo que llega.
  if (!modoMando) {
    WiFiClient nuevo = servidorTCP.accept();
    if (nuevo) {
      if (clienteTCP) clienteTCP.stop(); // echa al anterior, vivo o zombi
      clienteTCP = nuevo;
      clienteTCP.setNoDelay(true); // manda cada linea al toque, sin esperar a juntar varias (Nagle) - menos latencia
      // Keepalive rapido. LwIP trae SO_KEEPALIVE activado por el servidor,
      // pero con un TCP_KEEPIDLE de 2 horas: si el PC se apaga o se sale del
      // alcance del WiFi, el ESP32 seguiria creyendo que hay alguien del otro
      // lado y no aceptaria una reconexion. Con estos valores lo nota en ~12 s.
      int activo = 1, ocioso = 3, intervalo = 3, intentos = 3;
      int descriptorNuevo = clienteTCP.fd();
      lwip_setsockopt(descriptorNuevo, SOL_SOCKET, SO_KEEPALIVE, &activo, sizeof(activo));
      lwip_setsockopt(descriptorNuevo, IPPROTO_TCP, TCP_KEEPIDLE, &ocioso, sizeof(ocioso));
      lwip_setsockopt(descriptorNuevo, IPPROTO_TCP, TCP_KEEPINTVL, &intervalo, sizeof(intervalo));
      lwip_setsockopt(descriptorNuevo, IPPROTO_TCP, TCP_KEEPCNT, &intentos, sizeof(intentos));
      bufferLineaWifi = "";
      reportarEstado(); // el setup() ya paso hace rato, este cliente no lo vio
    }
  }

  String linea;
  if (leerLineaDisponible(Serial, bufferLineaSerial, linea)) {
    procesarLinea(linea);
  }
  if (clienteTCP && clienteTCP.connected() && leerLineaDisponible(clienteTCP, bufferLineaWifi, linea)) {
    procesarLinea(linea);
  }
}
