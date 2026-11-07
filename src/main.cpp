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
#include <LittleFS.h>
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

// Los 16 canales llegan juntos a 'pulsos' en ms (0 = salto inmediato). La usan
// POSET y las secuencias que el robot reproduce solo con el mando.
void moverPoseEnMs(const uint16_t *pulsos, uint32_t ms, bool lineal) {
  unsigned long ahora = millis();
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    comandoMover(canal, pulsos[canal], ms == 0 ? 0 : 1, false);   // velocidad 0 = salto inmediato
    if (ms > 0) {
      canales[canal].pulsoInicio = canales[canal].pulsoActual;
      canales[canal].tInicio = ahora;
      canales[canal].duracionMs = ms;
      canales[canal].lineal = lineal;
    }
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

// Solo ojos, sin boca: toda la expresion esta en la forma de los ojos.
// Cada forma se arma pintando en blanco y recortando en negro.
void dibujarOjo(int cx, int lado, Expresion expresion) { // lado: -1 ojo izquierdo, +1 derecho
  const int cy = PANTALLA_ALTO / 2;
  switch (expresion) {
    case CARA_FELIZ: // arco "^": circulo blanco menos uno negro corrido abajo, sin la mitad de abajo
      pantalla.fillCircle(cx, cy + 8, 19, SSD1306_WHITE);
      pantalla.fillCircle(cx, cy + 15, 15, SSD1306_BLACK);
      pantalla.fillRect(cx - 20, cy + 9, 41, PANTALLA_ALTO - cy - 9, SSD1306_BLACK);
      break;
    case CARA_TRISTE: { // mas bajo, con el parpado caido hacia afuera
      pantalla.fillRoundRect(cx - 16, cy - 10, 32, 32, 10, SSD1306_WHITE);
      int afuera = cx + 18 * lado, adentro = cx - 18 * lado;
      pantalla.fillTriangle(afuera, cy - 12, adentro, cy - 12, afuera, cy + 4, SSD1306_BLACK);
      break;
    }
    case CARA_SORPRESA: // grandes y redondos
      pantalla.fillCircle(cx, cy, 21, SSD1306_WHITE);
      break;
    case CARA_NEUTRAL:
    default:
      pantalla.fillRoundRect(cx - 16, cy - 20, 32, 40, 10, SSD1306_WHITE);
      break;
  }
}

void dibujarCara(Expresion expresion) {
  if (!pantallaDisponible) return;
  pantalla.clearDisplay();
  dibujarOjo(36, -1, expresion);
  dibujarOjo(92, 1, expresion);
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
// como Switch Pro. Avisa que boton cambia, con las mismas claves de la
// pestana Mando de la app (MANDO_BOTON,<clave>,presionado|soltado), y
// ejecuta lo que la app le asigno (ver PROGRAMA DEL MANDO).
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

// =====================================================================
// SEGMENTO: PROGRAMA DEL MANDO — secuencias guardadas en el robot
// La app (pestana Mando > "Enviar al robot") manda las secuencias ya
// convertidas a pulsos y que hace cada boton. Queda en la flash (LittleFS,
// /mando.txt), asi el robot camina con el mando sin la PC. Una linea por cosa:
//   S,<nombre>                   empieza una secuencia
//   P,<ms>,<p0>,...,<p15>        un paso de la ultima secuencia
//   B,<clave>,S,<sec>,<repetir>  boton -> secuencia (repetir 1: en bucle mientras se mantiene)
//   B,<clave>,P,<sec>            boton -> pose (secuencia de 1 paso; se queda ahi)
//   B,<clave>,C,<comando>        boton -> comando (HOME, RELAX, CARA,FELIZ...)
// Al soltar el boton la secuencia termina su vuelta y el robot vuelve a Inicio.
// =====================================================================
#define ARCHIVO_MANDO  "/mando.txt"
#define ARCHIVO_CARGA  "/mando.tmp"
#define MAX_SECUENCIAS 40
#define MAX_PASOS      500

struct PasoMando { uint16_t ms; uint16_t pulsos[NUM_CANALES]; };
struct SecuenciaMando { uint16_t primerPaso; uint16_t numPasos; };
enum TipoBoton : uint8_t { BOTON_NADA, BOTON_SECUENCIA, BOTON_POSE, BOTON_COMANDO };
struct BotonMando { TipoBoton tipo; uint8_t secuencia; bool repetir; String comando; };

PasoMando pasosMando[MAX_PASOS];   // 34 B x 500 = 17 KB
SecuenciaMando secuenciasMando[MAX_SECUENCIAS];
BotonMando botonesMando[NUM_CLAVES_MANDO];
uint16_t numPasosMando = 0;
uint8_t numSecuenciasMando = 0;
bool littleFsListo = false;

int8_t botonReproduciendo = -1;    // clave cuya secuencia esta corriendo, -1 = ninguna
uint8_t secReproduciendo = 0;
uint16_t pasoReproduciendo = 0;
unsigned long tPasoMando = 0;

File archivoCarga;
uint16_t lineasCarga = 0;

void procesarLinea(String linea); // los botones con comando usan el mismo interprete que la app

// Lee hasta n enteros separados por coma. Devuelve cuantos leyo.
int leerEnteros(const char *texto, long *destino, int n) {
  int leidos = 0;
  while (leidos < n && *texto) {
    char *fin;
    destino[leidos++] = strtol(texto, &fin, 10);
    if (*fin != ',') break;
    texto = fin + 1;
  }
  return leidos;
}

bool interpretarLineaMando(const String &linea) {
  if (linea.startsWith("S,")) {
    if (numSecuenciasMando >= MAX_SECUENCIAS) return false;
    secuenciasMando[numSecuenciasMando++] = {numPasosMando, 0};
    return true;
  }
  if (linea.startsWith("P,")) {
    long v[1 + NUM_CANALES];
    if (numSecuenciasMando == 0 || numPasosMando >= MAX_PASOS) return false;
    if (leerEnteros(linea.c_str() + 2, v, 1 + NUM_CANALES) != 1 + NUM_CANALES) return false;
    PasoMando &paso = pasosMando[numPasosMando++];
    paso.ms = constrain(v[0], 50, 60000);
    for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
      paso.pulsos[canal] = constrain(v[1 + canal], PULSO_MIN_ABS, PULSO_MAX_ABS);
    }
    secuenciasMando[numSecuenciasMando - 1].numPasos++;
    return true;
  }
  if (linea.startsWith("B,")) {
    int coma1 = linea.indexOf(',', 2), coma2 = linea.indexOf(',', coma1 + 1);
    if (coma1 < 0 || coma2 < 0) return false;
    String clave = linea.substring(2, coma1);
    int indice = -1;
    for (uint8_t i = 0; i < NUM_CLAVES_MANDO; i++) if (clave == CLAVES_MANDO[i]) indice = i;
    if (indice < 0) return false;
    char tipo = linea[coma1 + 1];
    String resto = linea.substring(coma2 + 1);
    BotonMando &boton = botonesMando[indice];
    if (tipo == 'C') {
      boton.tipo = BOTON_COMANDO;
      boton.comando = resto;
      return true;
    }
    long v[2];
    int leidos = leerEnteros(resto.c_str(), v, 2);
    if (leidos < 1 || v[0] < 0 || v[0] >= numSecuenciasMando) return false;
    boton.tipo = tipo == 'P' ? BOTON_POSE : BOTON_SECUENCIA;
    boton.secuencia = v[0];
    boton.repetir = leidos == 2 && v[1] == 1;
    return true;
  }
  return false;
}

bool cargarProgramaMando(const char *ruta) {
  botonReproduciendo = -1;
  numPasosMando = 0;
  numSecuenciasMando = 0;
  for (uint8_t i = 0; i < NUM_CLAVES_MANDO; i++) botonesMando[i] = {BOTON_NADA, 0, false, ""};
  File archivo = LittleFS.open(ruta, "r");
  if (!archivo) return false;
  bool ok = true;
  while (archivo.available()) {
    String linea = archivo.readStringUntil('\n');
    linea.trim();
    if (linea.length() > 0 && !interpretarLineaMando(linea)) ok = false;
  }
  archivo.close();
  return ok;
}

// MANDO_CARGA,INICIO / MANDO_CARGA,<linea del archivo> / MANDO_CARGA,FIN
// Cada linea se contesta (listo/ok/error) y la app espera esa respuesta antes
// de mandar la siguiente: el buffer de entrada del Serial es de solo 256 bytes.
void recibirCargaMando(const String &resto) {
  if (!littleFsListo) { enviarLinea("MANDO_CARGA,error,no hay memoria flash para guardar"); return; }
  if (resto == "INICIO") {
    if (archivoCarga) archivoCarga.close();
    archivoCarga = LittleFS.open(ARCHIVO_CARGA, "w");
    lineasCarga = 0;
    enviarLinea(archivoCarga ? "MANDO_CARGA,listo,0" : "MANDO_CARGA,error,no se pudo abrir el archivo");
    return;
  }
  if (!archivoCarga) { enviarLinea("MANDO_CARGA,error,falta MANDO_CARGA,INICIO"); return; }
  if (resto == "FIN") {
    archivoCarga.close();
    // Se prueba lo recibido antes de reemplazar lo que ya estaba guardado
    if (!cargarProgramaMando(ARCHIVO_CARGA)) {
      cargarProgramaMando(ARCHIVO_MANDO);
      enviarLinea("MANDO_CARGA,error,lo recibido no es valido; el robot sigue con lo anterior");
      return;
    }
    LittleFS.remove(ARCHIVO_MANDO);
    LittleFS.rename(ARCHIVO_CARGA, ARCHIVO_MANDO);
    enviarLinea("MANDO_CARGA,ok," + String(numSecuenciasMando) + "," + String(numPasosMando));
    return;
  }
  archivoCarga.println(resto);
  enviarLinea("MANDO_CARGA,listo," + String(++lineasCarga));
}

void empezarPasoMando() {
  const PasoMando &paso = pasosMando[secuenciasMando[secReproduciendo].primerPaso + pasoReproduciendo];
  // como la app: el movimiento termina 30 ms (2 ticks) antes que el paso, asi siempre llega
  moverPoseEnMs(paso.pulsos, max(50, (int) paso.ms - 30), false);
  tPasoMando = millis();
}

void alApretarBotonMando(uint8_t indice) {
  const BotonMando &boton = botonesMando[indice];
  if (boton.tipo == BOTON_NADA) return;
  if (boton.tipo == BOTON_COMANDO) {
    botonReproduciendo = -1;   // un comando (STOP, RELAX...) corta lo que se este haciendo
    procesarLinea(boton.comando);
    return;
  }
  // Mientras corre una secuencia los demas botones esperan a que termine
  if (botonReproduciendo >= 0 || emergenciaActiva) return;
  if (secuenciasMando[boton.secuencia].numPasos == 0) return;
  botonReproduciendo = indice;
  secReproduciendo = boton.secuencia;
  pasoReproduciendo = 0;
  empezarPasoMando();
}

void actualizarSecuenciaMando(uint32_t botones) {
  if (botonReproduciendo < 0) return;
  if (emergenciaActiva) { botonReproduciendo = -1; return; }
  const PasoMando &paso = pasosMando[secuenciasMando[secReproduciendo].primerPaso + pasoReproduciendo];
  if (millis() - tPasoMando < paso.ms) return;
  if (++pasoReproduciendo < secuenciasMando[secReproduciendo].numPasos) {
    empezarPasoMando();
    return;
  }
  // Termino una vuelta entera: otra si el boton sigue apretado, si no a Inicio
  const BotonMando &boton = botonesMando[botonReproduciendo];
  if (boton.tipo == BOTON_SECUENCIA && boton.repetir && (botones >> botonReproduciendo & 1)) {
    pasoReproduciendo = 0;
    empezarPasoMando();
    return;
  }
  botonReproduciendo = -1;
  if (boton.tipo == BOTON_SECUENCIA) irAHome();   // una pose se queda donde llego
}

void actualizarMando() {
  BP32.update();
  // Sin mando cuenta como todo suelto: si se desconecta caminando, termina la vuelta y va a Inicio
  uint32_t ahora = (mando != nullptr && mando->isConnected()) ? leerBotonesMando(mando) : 0;
  uint32_t cambios = ahora ^ botonesAnteriores;
  for (uint8_t i = 0; i < NUM_CLAVES_MANDO; i++) {
    if (cambios >> i & 1) {
      enviarLinea(String("MANDO_BOTON,") + CLAVES_MANDO[i] + (ahora >> i & 1 ? ",presionado" : ",soltado"));
      if (ahora >> i & 1) alApretarBotonMando(i);
    }
  }
  botonesAnteriores = ahora;
  actualizarSecuenciaMando(ahora);
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

  // true: la primera vez formatea la particion (tarda unos segundos, una sola vez)
  littleFsListo = LittleFS.begin(true);
  if (littleFsListo) cargarProgramaMando(ARCHIVO_MANDO);

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
  uint8_t asignados = 0;
  for (uint8_t i = 0; i < NUM_CLAVES_MANDO; i++) asignados += botonesMando[i].tipo != BOTON_NADA;
  enviarLinea("Programa del mando: " + String(numSecuenciasMando) + " secuencias, " +
              String(asignados) + " botones asignados");
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
  enviarLinea("  MANDO_CARGA,...  -> lo usa la app (pestana Mando > Enviar al robot) para guardar secuencias");
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
  if (tipo.equalsIgnoreCase("MANDO_CARGA")) {
    recibirCargaMando(primeraComa == -1 ? String() : linea.substring(primeraComa + 1));
    return;
  }
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
    moverPoseEnMs(pulsos, (uint32_t) ms, lineal);
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
