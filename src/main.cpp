// =====================================================================
// ROBOT CONTROL — firmware ESP32 + PCA9685 + MPU6050
// El PC habla por Serial en el formato:  canal,pulso_us,velocidad
// Busca "SEGMENTO:" para saltar directo a cada parte del codigo.
// =====================================================================

#include <Wire.h>
#include <WiFi.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_SSD1306.h>
#include <Preferences.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);
Adafruit_MPU6050 mpu;
Preferences prefs;

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
  if (clienteTCP && clienteTCP.connected()) {
    clienteTCP.println(texto);
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
bool  imuDisponible    = false;
bool  imuStreamActivo  = false;
bool  emergenciaActiva = false;

unsigned long ultimoTickRampa  = 0;
unsigned long ultimoEnvioIMU   = 0;
unsigned long ultimaMuestraIMU = 0;
const unsigned long INTERVALO_IMU_MS = 100; // 10 Hz

float pitch = 0, roll = 0;

// El MPU6050 esta montado con el lado de los componentes mirando hacia
// abajo (el eje Z del sensor apunta al piso, no al cielo), asi que hay que
// invertir Z al calcular el Roll para que la lectura en reposo caiga cerca
// de 0 grados en vez del punto donde atan2 salta entre +180/-180. Si en
// algun momento se vuelve a montar con los componentes hacia arriba, cambiar
// esto a 1.
#define SIGNO_Z_ACCEL -1

// Offsets de calibracion (ver SEGMENTO: GIROSCOPIO)
float offsetGyroX = 0, offsetGyroY = 0;
float offsetAccelPitch = 0, offsetAccelRoll = 0;

struct CanalServo {
  float pulsoActual;
  float pulsoObjetivo;
  float pasoPorTick; // us que avanza cada TICK_RAMPA_MS. 0 = todavia no seteado
  bool  activo;       // false tras STOP/RELAX hasta el proximo comando de movimiento
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

void aplicarPulso(uint8_t canal, uint16_t us) {
  us = constrain(us, PULSO_MIN_ABS, PULSO_MAX_ABS);
  pwm.setPWM(canal, 0, usATicks(us));
  canales[canal].pulsoActual = us;
}

// Mueve un canal hacia un pulso objetivo. velocidad=0 => salto inmediato,
// velocidad>0 => avanza esa cantidad de us cada TICK_RAMPA_MS (no bloqueante).
void comandoMover(uint8_t canal, uint16_t pulsoUs, uint16_t velocidad) {
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

  if (velocidad == 0) {
    aplicarPulso(canal, pulsoUs);
  } else {
    canales[canal].pasoPorTick = velocidad;
  }

  enviarLinea("M," + String(canal) + "," + String(pulsoUs) + "," + String(velocidad));
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

    float paso = canales[canal].pasoPorTick;
    if (paso <= 0) paso = 40; // respaldo por si se pidio rampa sin velocidad definida
    float nuevo = canales[canal].pulsoActual + (diff > 0 ? min(paso, diff) : max(-paso, diff));
    aplicarPulso(canal, (uint16_t) round(nuevo));
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
// SEGMENTO: PANTALLA OLED (CARAS) — bus I2C aparte, NO comparte con
// servos/giroscopio. Un refresco de pantalla es lento (~20 ms) y si
// compartiera bus con el PCA9685 congelaria el control de los servos
// justo ese tiempo cada vez que la cara cambia.
// =====================================================================
#define PANTALLA_SDA_PIN 25
#define PANTALLA_SCL_PIN 26
#define PANTALLA_ANCHO    128
#define PANTALLA_ALTO     64
#define PANTALLA_DIR_I2C  0x3D

TwoWire WirePantalla = TwoWire(1);
Adafruit_SSD1306 pantalla(PANTALLA_ANCHO, PANTALLA_ALTO, &WirePantalla, -1);
bool pantallaDisponible = false;

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

  pantalla.display();
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
    comandoMover(canal, home[canal], 10);
    reporte += "," + String(home[canal]);
  }
  enviarLinea(reporte);
}

// =====================================================================
// SEGMENTO: GIROSCOPIO (MPU6050) — fusion y calibracion
// =====================================================================

// Calibrar: promedia varias muestras con el robot quieto y parado derecho.
// Elimina tanto el sesgo del giroscopio como el desalineado de montaje del
// sensor, para que "0,0" represente esa pose de referencia.
void calibrarIMU() {
  if (!imuDisponible) {
    enviarLinea("CALIBRAR,error - MPU6050 no detectado");
    return;
  }
  enviarLinea("Calibrando giroscopio, no muevas el robot...");

  const int MUESTRAS = 200;
  float sumaGX = 0, sumaGY = 0, sumaAccelPitch = 0, sumaAccelRoll = 0;

  for (int i = 0; i < MUESTRAS; i++) {
    sensors_event_t a, g, temp;
    mpu.getEvent(&a, &g, &temp);
    sumaGX += g.gyro.x;
    sumaGY += g.gyro.y;
    sumaAccelPitch += atan2(-a.acceleration.x, sqrt(a.acceleration.y * a.acceleration.y + a.acceleration.z * a.acceleration.z)) * 180.0 / PI;
    sumaAccelRoll  += atan2(a.acceleration.y, SIGNO_Z_ACCEL * a.acceleration.z) * 180.0 / PI;
    delay(3);
  }

  offsetGyroX = sumaGX / MUESTRAS;
  offsetGyroY = sumaGY / MUESTRAS;
  offsetAccelPitch = sumaAccelPitch / MUESTRAS;
  offsetAccelRoll  = sumaAccelRoll / MUESTRAS;
  pitch = 0;
  roll = 0;
  ultimaMuestraIMU = millis();

  enviarLinea("CALIBRAR,ok");
}

void actualizarIMU() {
  // Si nadie esta viendo el giroscopio en la app, no vale la pena gastar
  // tiempo del bus I2C (que tambien usan los servos) leyendo el sensor.
  if (!imuDisponible || !imuStreamActivo) return;

  unsigned long ahora = millis();
  float dt = (ultimaMuestraIMU == 0) ? 0 : (ahora - ultimaMuestraIMU) / 1000.0f;
  ultimaMuestraIMU = ahora;

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  float accelPitch = atan2(-a.acceleration.x, sqrt(a.acceleration.y * a.acceleration.y + a.acceleration.z * a.acceleration.z)) * 180.0 / PI - offsetAccelPitch;
  float accelRoll  = atan2(a.acceleration.y, SIGNO_Z_ACCEL * a.acceleration.z) * 180.0 / PI - offsetAccelRoll;
  float gyroPitchRate = (g.gyro.x - offsetGyroX) * 180.0 / PI;
  float gyroRollRate  = (g.gyro.y - offsetGyroY) * 180.0 / PI;

  const float ALPHA = 0.98f;
  if (dt > 0 && dt < 1.0f) {
    pitch = ALPHA * (pitch + gyroPitchRate * dt) + (1 - ALPHA) * accelPitch;
    roll  = ALPHA * (roll  + gyroRollRate  * dt) + (1 - ALPHA) * accelRoll;
  } else {
    pitch = accelPitch;
    roll = accelRoll;
  }

  if (imuStreamActivo && (ahora - ultimoEnvioIMU >= INTERVALO_IMU_MS)) {
    ultimoEnvioIMU = ahora;
    enviarLinea("IMU," + String(a.acceleration.x, 3) + "," + String(a.acceleration.y, 3) + "," +
                String(a.acceleration.z, 3) + "," + String(g.gyro.x, 3) + "," + String(g.gyro.y, 3) + "," +
                String(g.gyro.z, 3) + "," + String(pitch, 2) + "," + String(roll, 2));
  }
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
    enviarLinea(String(encontrados) + " dispositivo(s) encontrado(s). PCA9685 deberia ser 0x40, MPU6050 deberia ser 0x68 (o 0x69).");
  }
}

void reportarEstado(); // definida despues de setup(), la usan setup() y loop()

// =====================================================================
// SEGMENTO: SETUP
// =====================================================================
void setup() {
  Serial.begin(115200);
  delay(500);

  Wire.begin(); // ESP32: SDA=21, SCL=22 por defecto. PCA9685 y MPU6050 comparten este bus.

  // Adafruit_PWMServoDriver::begin() no devuelve si encontro el chip o no,
  // asi que se comprueba a mano por I2C antes de usarlo (igual que con el
  // MPU6050 mas abajo), para no reportar "listo" cuando en realidad no esta.
  Wire.beginTransmission(0x40);
  pcaDisponible = (Wire.endTransmission() == 0);

  pwm.begin();
  pwm.setPWMFreq(SERVO_FREQ);
  delay(10);

  prefs.begin("robot", false);

  imuDisponible = mpu.begin();
  if (!imuDisponible) {
    // mpu.begin() exige que el registro WHO_AM_I diga exactamente 0x68.
    // Algunos MPU6050 "clon" responden bien por I2C pero ese registro trae
    // otro valor, y la libreria los rechaza aunque el sensor funcione
    // igual. Si el chip SI responde en el bus, se ignora ese chequeo y se
    // saca a mano del modo sleep (lo que mpu.begin() se salta al rechazarlo).
    Wire.beginTransmission(0x68);
    if (Wire.endTransmission() == 0) {
      Wire.beginTransmission(0x68);
      Wire.write(0x75); // registro WHO_AM_I
      Wire.endTransmission(false);
      Wire.requestFrom((uint8_t)0x68, (uint8_t)1);
      uint8_t whoAmI = Wire.available() ? Wire.read() : 0xFF;
      Serial.print("MPU6050 responde en el bus con WHO_AM_I=0x");
      Serial.print(whoAmI, HEX);
      Serial.println(" (distinto al 0x68 esperado) - se inicializa de todas formas.");

      Wire.beginTransmission(0x68);
      Wire.write(0x6B); // PWR_MGMT_1
      Wire.write(0x00); // sacarlo del modo sleep de fabrica
      Wire.endTransmission();
      imuDisponible = true;
    }
  }
  if (imuDisponible) {
    mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
    mpu.setGyroRange(MPU6050_RANGE_500_DEG);
    mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  } else {
    Serial.println("Aviso: MPU6050 no encontrado. El robot funciona sin giroscopio.");
  }

  WirePantalla.begin(PANTALLA_SDA_PIN, PANTALLA_SCL_PIN);
  pantallaDisponible = pantalla.begin(SSD1306_SWITCHCAPVCC, PANTALLA_DIR_I2C);
  if (pantallaDisponible) {
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

  WiFi.softAP(WIFI_SSID, WIFI_PASSWORD);
  WiFi.setSleep(false); // sin esto el modo ahorro de energia mete latencia extra a cada paquete
  servidorTCP.begin();
  Serial.print("WiFi AP \""); Serial.print(WIFI_SSID); Serial.print("\" activo. IP: ");
  Serial.println(WiFi.softAPIP());

  reportarEstado();
}

// Resumen de que hardware detecto el robot, mas la lista de comandos. Se
// manda una vez al arrancar (por Serial, WiFi todavia no tiene a nadie
// conectado tan rapido) y de nuevo cada vez que un cliente WiFi se conecta,
// porque para ese momento el setup() original ya paso hace rato.
void reportarEstado() {
  enviarLinea(String("PCA9685: ") + (pcaDisponible ? "detectado" : "no detectado - los servos no van a responder"));
  enviarLinea(String("MPU6050: ") + (imuDisponible ? "detectado" : "no detectado"));
  enviarLinea("Comandos disponibles:");
  enviarLinea("  canal,pulso_us,velocidad  -> mover un servo (velocidad 0 = instantaneo)");
  enviarLinea("  STOP      -> corta el PWM de todos los servos (emergencia)");
  enviarLinea("  RESUME    -> reactiva tras un STOP");
  enviarLinea("  RELAX     -> suelta el torque de todos los servos (para posar a mano)");
  enviarLinea("  HOME      -> mueve a la posicion de inicio guardada");
  enviarLinea("  HOMESET   -> guarda la posicion actual como inicio (persiste al apagar)");
  enviarLinea("  CALIBRAR  -> calibra el giroscopio (robot quieto y parado derecho)");
  enviarLinea("  CARA,nombre -> FELIZ / TRISTE / SORPRESA / NEUTRAL en la pantalla OLED");
  enviarLinea("  IMUON / IMUOFF -> activa/desactiva el streaming del giroscopio");
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
  if (tipo.equalsIgnoreCase("CALIBRAR")) { calibrarIMU(); return; }
  if (tipo.equalsIgnoreCase("PING")) { enviarLinea("PONG"); return; }
  if (tipo.equalsIgnoreCase("SCAN")) { escanearI2C(); return; }
  if (tipo.equalsIgnoreCase("IMUON")) {
    imuStreamActivo = true;
    enviarLinea("IMUSTREAM,ON");
    return;
  }
  if (tipo.equalsIgnoreCase("IMUOFF")) {
    imuStreamActivo = false;
    enviarLinea("IMUSTREAM,OFF");
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
      comandoMover(canal, pulsos[canal], velocidad);
    }
    enviarLinea("POSE,ok");
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
// mientras loop() esta bloqueado, no se actualizan ni rampas ni giroscopio,
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
  actualizarIMU();

  // Acepta un cliente WiFi nuevo (uno a la vez, como con el cable USB).
  if (!clienteTCP || !clienteTCP.connected()) {
    WiFiClient nuevo = servidorTCP.available();
    if (nuevo) {
      clienteTCP = nuevo;
      clienteTCP.setNoDelay(true); // manda cada linea al toque, sin esperar a juntar varias (Nagle) - menos latencia
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
