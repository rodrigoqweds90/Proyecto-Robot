// =====================================================================
// ROBOT CONTROL — firmware ESP32 + PCA9685
// El PC habla por Serial en el formato:  canal,pulso_us,velocidad
// Busca "SEGMENTO:" para saltar directo a cada parte del codigo.
// =====================================================================

#include <Wire.h>
#include <WiFi.h>
#include <Adafruit_PWMServoDriver.h>
#include <Adafruit_SSD1306.h>
#include <Adafruit_MPU6050.h>
#include <Adafruit_Sensor.h>
#include <Preferences.h>
#include <lwip/sockets.h> // socket crudo: WiFiClient::write() bloquea, ver enviarLinea()
#include <errno.h>

Adafruit_PWMServoDriver pwm = Adafruit_PWMServoDriver(0x40);
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

// us que el balance le sumo a cada canal en la ultima escritura al PCA9685
// (0 con el balance apagado). Vive aparte de pulsoActual a proposito: ver
// SEGMENTO: BALANCE.
float ultimaCorreccion[NUM_CANALES] = {0};
bool  mpuDisponible = false;
float correccionBalance(uint8_t canal); // definida en SEGMENTO: BALANCE
void cancelarAutoajuste(const String &motivo);
void cancelarNivelado(const String &motivo); // definida en SEGMENTO: NIVELAR EL TORSO
void guardarHome();                          // definida en SEGMENTO: POSICION DE INICIO

// =====================================================================
// SEGMENTO: CONTROL DE SERVOS (PULSOS Y RAMPAS)
// =====================================================================
uint16_t usATicks(uint16_t us) {
  float periodo_us = 1000000.0 / SERVO_FREQ;
  float ticks = (us / periodo_us) * 4096.0;
  return (uint16_t) round(ticks);
}

// Escribe el pulso pedido MAS la correccion de balance vigente. pulsoActual
// guarda solo lo pedido: las rampas y HOMESET no deben ver el ajuste.
void escribirSalida(uint8_t canal) {
  long salida = lround(canales[canal].pulsoActual + ultimaCorreccion[canal]);
  pwm.setPWM(canal, 0, usATicks((uint16_t) constrain(salida, (long) PULSO_MIN_ABS, (long) PULSO_MAX_ABS)));
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
  // El autoajuste y el nivelado miden contra la pose quieta: cualquier movimiento los invalida.
  cancelarAutoajuste("se movio un servo a mitad del autoajuste");
  cancelarNivelado("se movio un servo a mitad del nivelado");
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

// Avanza todas las rampas activas y aplica la correccion de balance vigente.
// Se llama en cada vuelta de loop().
void actualizarRampas() {
  unsigned long ahora = millis();
  if (ahora - ultimoTickRampa < TICK_RAMPA_MS) return;
  ultimoTickRampa = ahora;

  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    if (!canales[canal].activo) continue;
    float diff = canales[canal].pulsoObjetivo - canales[canal].pulsoActual;
    bool enRampa = fabs(diff) >= 1.0f;
    // Un canal quieto igual se reescribe si su correccion cambio: parado
    // sobre un pie es justo cuando mas tiene que corregir.
    float correccion = correccionBalance(canal);
    bool cambioCorreccion = fabs(correccion - ultimaCorreccion[canal]) >= 1.0f ||
                            (correccion == 0 && ultimaCorreccion[canal] != 0);
    if (!enRampa && !cambioCorreccion) continue;

    if (enRampa && canales[canal].duracionMs > 0) {
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
    } else if (enRampa) {
      float paso = canales[canal].pasoPorTick;
      if (paso <= 0) paso = 40; // respaldo por si se pidio rampa sin velocidad definida
      canales[canal].pulsoActual += (diff > 0 ? min(paso, diff) : max(-paso, diff));
    }
    ultimaCorreccion[canal] = correccion;
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
// SEGMENTO: BALANCE CON MPU6050 (se calibra y se autoajusta solo)
// Las poses y secuencias se mandan igual que siempre; esto les suma un
// ajuste en vivo para frenar el torso cuando se va de lado. No importa como
// este pegado el sensor ni hay que decirle nada: todo se aprende solo.
//  - Sesgo del giroscopio: cada vez que el robot queda quieto 1 s.
//  - "Derecho": la direccion de la gravedad, quieto en la pose de Inicio.
//    Todo se mide contra ese vector, asi que sirve cualquier montaje.
//  - Autoajuste (una vez, al pedir el balance): mueve caderas, pies y
//    femures unos grados y mide cuanto y hacia donde se inclina el torso.
//    De ahi sale cual es el eje lateral y hacia donde corrige cada grupo.
//
// Mismo bus I2C que el PCA9685 (21/22): 0x68 no choca con 0x40.
// =====================================================================
Adafruit_MPU6050 mpu;

#define MPU_DIRECCION          0x68
#define TICK_IMU_MS            10      // ~100 Hz
#define INTERVALO_ACT_MS       100     // telemetria para la app, 10 Hz
#define ANGULO_CAIDA           45.0f   // mas inclinado que esto: caido, no se corrige
#define SEGUNDOS_ENTRADA       0.5f    // lo que tarda el balance en entrar/salir del todo
#define VENTANA_QUIETO_MS      1000
#define RUIDO_QUIETO_GRADOS    4.0f    // variacion max del giroscopio en la ventana para "quieto" (margen para el zumbido de servos cargados)
// La correccion no apunta a "derecho" sino a una referencia que sigue la
// inclinacion lentamente: asi no pelea con las poses que inclinan el robot
// a proposito para pasar el peso, y si frena los tirones rapidos (el pie
// que baja y se va de lado).
#define SEGUNDOS_REFERENCIA    1.5f
#define TAU_COMPLEMENTARIO     0.49f   // equivale a alfa 0.98 a 100 Hz, pero no cambia si el loop se atrasa
#define CAMBIO_MONTAJE_GRADOS  15.0f   // un "derecho" nuevo tan distinto invalida el autoajuste

// Servos del balance. Cada grupo se mueve en paralelo (una pierna hacia
// adentro y la otra hacia afuera), asi nunca se juntan las dos caderas ni
// los dos pies. Signos segun hacia donde va cada servo a mayor pwm:
//   Caderas: izq abre a la izquierda, der va adentro   -> +,+ = pies a la izquierda
//   Pies:    izq se inclina adentro, der afuera         -> +,+ = pies inclinados a la derecha
//   Femures: izq pie atras, der pie adelante            -> -,+ = pies adelante
#define CANAL_CADERA_IZQ 0
#define CANAL_FEMUR_IZQ  1
#define CANAL_PIE_IZQ    3
#define CANAL_PIE_DER    12
#define CANAL_FEMUR_DER  14
#define CANAL_CADERA_DER 15
enum GrupoBalance { GRUPO_CADERAS, GRUPO_PIES, GRUPO_FEMURES, NUM_GRUPOS };
const char* NOMBRE_GRUPO[NUM_GRUPOS] = {"caderas", "pies", "femures"};

bool grupoDelCanal(uint8_t canal, int &grupo, float &signo) {
  switch (canal) {
    case CANAL_CADERA_IZQ: grupo = GRUPO_CADERAS; signo = 1;  return true;
    case CANAL_CADERA_DER: grupo = GRUPO_CADERAS; signo = 1;  return true;
    case CANAL_PIE_IZQ:    grupo = GRUPO_PIES;    signo = 1;  return true;
    case CANAL_PIE_DER:    grupo = GRUPO_PIES;    signo = 1;  return true;
    case CANAL_FEMUR_IZQ:  grupo = GRUPO_FEMURES; signo = -1; return true;
    case CANAL_FEMUR_DER:  grupo = GRUPO_FEMURES; signo = 1;  return true;
  }
  return false;
}

// Autoajuste: cuanto se mueve cada grupo y cuanto tiene que notarse.
#define AMPLITUD_AUTO_US       50.0f   // ~4.6 grados de servo
#define EFECTO_MINIMO_CADERAS  1.0f    // grados de torso con AMPLITUD_AUTO_US
#define EFECTO_MINIMO_OTROS    0.7f

bool  balanceActivo    = false; // lo que pidio el usuario (se guarda al apagar)
bool  telemetriaActiva = false;
bool  caidaDetectada   = false;
bool  enPoseHome       = false; // true mientras el robot siga en la pose de Inicio
float mezclaBalance    = 0;     // 0..1: cuanto de la correccion se aplica ahora

float gEst[3] = {0, 0, 1};           // hacia donde queda "arriba" visto desde el sensor (unitario)
bool  gEstIniciado = false;
float roll = 0, pitch = 0;           // grados respecto a "derecho": + a su derecha / + adelante
float rollVel = 0, pitchVel = 0;     // grados/s
float rumbo = 0;                     // grados girados desde el ultimo RUMBO,0
float refRoll = 0, refPitch = 0;     // inclinacion "de la pose", sigue a roll/pitch con SEGUNDOS_REFERENCIA
bool  referenciaIniciada = false;
bool  nivelGuardadoEnEstaHome = false;
float salidaGrupo[NUM_GRUPOS] = {0}; // us de correccion por grupo, antes de mezclar
unsigned long ultimaMuestraIMU = 0, ultimoEnvioACT = 0;

struct CalibracionIMU {
  float   sesgo[3];                // rad/s, ejes X Y Z del giroscopio
  float   arriba[3];               // gravedad en la pose de Inicio (unitario)
  float   ejeLateral[3];           // hacia donde se mueve la gravedad con el torso a su derecha
  float   ganancia[NUM_GRUPOS];    // grados de torso por us; 0 = el grupo no corrige
  uint8_t giroListo, nivelListo, autoListo, reservado;
};
const CalibracionIMU CALIBRACION_INICIAL = {{0, 0, 0}, {0, 0, 1}, {1, 0, 0}, {0, 0, 0}, 0, 0, 0, 0};
CalibracionIMU calib = CALIBRACION_INICIAL;

// kp: que parte de la desviacion corrige (0.5 = la mitad). kd: en segundos.
// Adimensionales porque el autoajuste ya midio cuantos grados mueve cada us.
struct AjustesBalance { float kpRoll, kdRoll, kpPitch, kdPitch, maxUs; };
AjustesBalance ajustes = {0.5f, 0.08f, 0.5f, 0.08f, 150.0f};

// ---- Vectores ---------------------------------------------------------------
float punto(const float a[3], const float b[3]) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }

void cruz(const float a[3], const float b[3], float r[3]) {
  r[0] = a[1] * b[2] - a[2] * b[1];
  r[1] = a[2] * b[0] - a[0] * b[2];
  r[2] = a[0] * b[1] - a[1] * b[0];
}

bool normalizar(float v[3]) {
  float n = sqrt(punto(v, v));
  if (n < 1e-6f) return false;
  for (int i = 0; i < 3; i++) v[i] /= n;
  return true;
}

void quitarComponente(float v[3], const float p[3]) {
  float d = punto(v, p);
  for (int i = 0; i < 3; i++) v[i] -= d * p[i];
}

float anguloEntre(const float a[3], const float b[3]) {
  return acos(constrain(punto(a, b), -1.0f, 1.0f)) * RAD_TO_DEG;
}

// Ejes horizontales para medir roll y pitch: lateral (a su derecha) y
// frontal (adelante), perpendiculares a "arriba". Antes del autoajuste el
// lateral es provisorio (solo para mostrar algo y detectar caidas).
void baseHorizontal(float lateral[3], float frontal[3]) {
  for (int i = 0; i < 3; i++) lateral[i] = calib.ejeLateral[i];
  quitarComponente(lateral, calib.arriba);
  if (!normalizar(lateral)) {
    float x[3] = {1, 0, 0}, y[3] = {0, 1, 0};
    const float* candidato = fabs(calib.arriba[0]) < 0.9f ? x : y;
    for (int i = 0; i < 3; i++) lateral[i] = candidato[i];
    quitarComponente(lateral, calib.arriba);
    normalizar(lateral);
  }
  cruz(calib.arriba, lateral, frontal);
}

// ---- Persistencia -----------------------------------------------------------
bool cargarBloque(const char* clave, void* destino, size_t tamano) {
  if (!prefs.isKey(clave) || prefs.getBytesLength(clave) != tamano) return false;
  prefs.getBytes(clave, destino, tamano);
  return true;
}

void guardarCalibracion() {
  prefs.putBytes("imucal3", &calib, sizeof(calib));
}

void cargarBalance() {
  cargarBloque("imucal3", &calib, sizeof(calib));
  cargarBloque("balaj2", &ajustes, sizeof(ajustes));
  balanceActivo = mpuDisponible && prefs.getBool("balon", false);
}

bool iniciarMPU() {
  bool encontrado = mpu.begin(MPU_DIRECCION);
  if (!encontrado) {
    // mpu.begin() exige que el registro WHO_AM_I diga exactamente 0x68.
    // Algunos MPU6050 "clon" responden bien por I2C pero ese registro trae
    // otro valor, y la libreria los rechaza aunque el sensor funcione
    // igual. Si el chip SI responde en el bus, se ignora ese chequeo y se
    // saca a mano del modo sleep (lo que mpu.begin() se salta al rechazarlo).
    Wire.beginTransmission(MPU_DIRECCION);
    if (Wire.endTransmission() == 0) {
      Wire.beginTransmission(MPU_DIRECCION);
      Wire.write(0x75); // registro WHO_AM_I
      Wire.endTransmission(false);
      Wire.requestFrom((uint8_t) MPU_DIRECCION, (uint8_t) 1);
      uint8_t whoAmI = Wire.available() ? Wire.read() : 0xFF;
      Serial.print("MPU6050 responde en el bus con WHO_AM_I=0x");
      Serial.print(whoAmI, HEX);
      Serial.println(" (distinto al 0x68 esperado) - se inicializa de todas formas.");

      Wire.beginTransmission(MPU_DIRECCION);
      Wire.write(0x6B); // PWR_MGMT_1
      Wire.write(0x00); // sacarlo del modo sleep de fabrica
      Wire.endTransmission();
      encontrado = true;
    }
  }
  if (!encontrado) {
    Serial.println("Aviso: MPU6050 no encontrado. El robot funciona sin balance.");
    return false;
  }
  mpu.setAccelerometerRange(MPU6050_RANGE_8_G);
  mpu.setGyroRange(MPU6050_RANGE_500_DEG);
  mpu.setFilterBandwidth(MPU6050_BAND_21_HZ);
  return true;
}

bool rampasEnCurso() {
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    if (canales[canal].activo && fabs(canales[canal].pulsoObjetivo - canales[canal].pulsoActual) >= 1.0f) return true;
  }
  return false;
}

bool servosConFuerza() {
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    if (canales[canal].activo) return true;
  }
  return false;
}

// ---- Autocalibrado: sesgo del giroscopio y "derecho" ------------------------
struct VentanaQuieto {
  unsigned long inicio;
  int   muestras;
  float suma[3];              // giroscopio crudo, rad/s
  float minimo[3], maximo[3]; // giroscopio crudo, grados/s
  float sumaAcel[3];          // m/s2
};
VentanaQuieto ventana;
unsigned long ultimoMovimiento = 0; // ultima vez que el robot NO estaba quieto

void reiniciarVentana(unsigned long ahora) {
  memset(&ventana, 0, sizeof(ventana));
  ventana.inicio = ahora;
  for (int i = 0; i < 3; i++) {
    ventana.minimo[i] = 1e6f;
    ventana.maximo[i] = -1e6f;
  }
}

// Si el robot estuvo quieto toda la ventana, el promedio del giroscopio es
// su sesgo puro; y si ademas esta en la pose de Inicio, el promedio del
// acelerometro es "derecho". Se mide por la variacion (max-min) y no por el
// valor, porque el sesgo todavia desconocido puede ser de varios grados/s.
void revisarQuietud(const float giroCrudo[3], const float acel[3], float modAccel, unsigned long ahora) {
  if (fabs(modAccel - SENSORS_GRAVITY_EARTH) > 0.8f || rampasEnCurso()) {
    ultimoMovimiento = ahora;
    reiniciarVentana(ahora);
    return;
  }
  for (int i = 0; i < 3; i++) {
    float gradosPorSeg = giroCrudo[i] * RAD_TO_DEG;
    ventana.suma[i] += giroCrudo[i];
    ventana.minimo[i] = min(ventana.minimo[i], gradosPorSeg);
    ventana.maximo[i] = max(ventana.maximo[i], gradosPorSeg);
    ventana.sumaAcel[i] += acel[i];
  }
  ventana.muestras++;
  if (ahora - ventana.inicio < VENTANA_QUIETO_MS) return;

  bool quieto = ventana.muestras >= 50;
  for (int i = 0; i < 3; i++) {
    if (ventana.maximo[i] - ventana.minimo[i] > RUIDO_QUIETO_GRADOS) quieto = false;
  }
  if (!quieto) ultimoMovimiento = ahora;
  if (quieto) {
    for (int i = 0; i < 3; i++) calib.sesgo[i] = ventana.suma[i] / ventana.muestras;
    calib.giroListo = 1;

    float nuevoArriba[3] = {ventana.sumaAcel[0], ventana.sumaAcel[1], ventana.sumaAcel[2]};
    if (enPoseHome && normalizar(nuevoArriba)) {
      float cambio = calib.nivelListo ? anguloEntre(nuevoArriba, calib.arriba) : 0;
      // Una sola vez por cada llegada a Inicio: si el ruido oscila alrededor
      // del umbral no se reescribe la flash cada segundo.
      if ((!calib.nivelListo || cambio > 0.5f) && !nivelGuardadoEnEstaHome) {
        nivelGuardadoEnEstaHome = true;
        if (calib.nivelListo && calib.autoListo && cambio > CAMBIO_MONTAJE_GRADOS) {
          // Otro Inicio muy distinto o el sensor se volvio a pegar: lo aprendido ya no vale.
          calib.autoListo = 0;
          enviarLinea("AUTOAJUSTE,pendiente,el Inicio cambio " + String(cambio, 0) + " grados: se repite al pedir el balance");
        }
        for (int i = 0; i < 3; i++) calib.arriba[i] = nuevoArriba[i];
        calib.nivelListo = 1;
        referenciaIniciada = false; // el roll/pitch salta: sin esto daria un tiron
        // Solo se guarda si cambio: la flash del ESP32 tiene escrituras limitadas
        // (por eso el sesgo, que se reaprende en 1 s, no se guarda solo).
        guardarCalibracion();
        enviarLinea("NIVEL,ok," + String(cambio, 1));
      }
    }
  }
  reiniciarVentana(ahora);
}

// ---- Autoajuste: cuanto inclina el torso cada grupo de servos --------------
enum FaseAutoajuste { FASE_SUBIR, FASE_ESPERAR, FASE_MEDIR, FASE_BAJAR, FASE_REPOSO, NUM_FASES };
const float DURACION_FASE[NUM_FASES] = {0.4f, 0.8f, 0.6f, 0.4f, 0.6f}; // ~17 s en total

struct Autoajuste {
  bool    activo;
  uint8_t paso;                           // 0..5: grupo = paso/2, signo + en pares y - en impares
  uint8_t fase;
  float   t;
  float   suma[3];
  int     muestras;
  float   media[NUM_GRUPOS][2][3];
  float   salida[NUM_GRUPOS];             // us que suma ahora cada grupo
};
Autoajuste autoajuste;

bool listoParaAutoajuste(String &motivo) {
  if (!calib.giroListo || !calib.nivelListo) { motivo = "falta calibrar: llevalo a Inicio y dejalo quieto 2 s"; return false; }
  if (emergenciaActiva)                       { motivo = "STOP activo"; return false; }
  if (!servosConFuerza())                     { motivo = "servos sueltos (RELAX): manda HOME"; return false; }
  if (!enPoseHome || rampasEnCurso())         { motivo = "tiene que estar en la pose de Inicio"; return false; }
  if (caidaDetectada)                         { motivo = "esta caido"; return false; }
  if (millis() - ultimoMovimiento < 1500)     { motivo = "se esta moviendo: dejalo quieto"; return false; }
  return true;
}

void iniciarAutoajuste() {
  memset(&autoajuste, 0, sizeof(autoajuste));
  autoajuste.activo = true;
  enviarLinea("AUTOAJUSTE,inicio,no lo toques unos 17 s");
}

void cancelarAutoajuste(const String &motivo) {
  if (!autoajuste.activo) return;
  autoajuste.activo = false;
  for (int g = 0; g < NUM_GRUPOS; g++) autoajuste.salida[g] = 0;
  enviarLinea("AUTOAJUSTE,error," + motivo);
  if (balanceActivo && !calib.autoListo) {
    balanceActivo = false;
    prefs.putBool("balon", false);
    enviarLinea("BALANCE,OFF");
  }
}

void terminarAutoajuste() {
  autoajuste.activo = false;
  float efecto[NUM_GRUPOS][3]; // rad de torso por us, solo la parte horizontal
  for (int g = 0; g < NUM_GRUPOS; g++) {
    autoajuste.salida[g] = 0;
    for (int i = 0; i < 3; i++) {
      efecto[g][i] = (autoajuste.media[g][0][i] - autoajuste.media[g][1][i]) / (2 * AMPLITUD_AUTO_US);
    }
    quitarComponente(efecto[g], calib.arriba);
  }

  float gradosCaderas = sqrt(punto(efecto[GRUPO_CADERAS], efecto[GRUPO_CADERAS])) * AMPLITUD_AUTO_US * RAD_TO_DEG;
  if (gradosCaderas < EFECTO_MINIMO_CADERAS) {
    autoajuste.activo = true; // para que cancelarAutoajuste() informe y apague
    cancelarAutoajuste("las caderas casi no inclinan el torso (" + String(gradosCaderas, 1) +
                       " grados): tiene que estar parado en el piso");
    return;
  }
  // Caderas + llevan los pies a la izquierda: con los pies apoyados el torso
  // se va a su derecha. Esa direccion pasa a ser el eje lateral positivo.
  for (int i = 0; i < 3; i++) calib.ejeLateral[i] = efecto[GRUPO_CADERAS][i];
  float lateral[3], frontal[3];
  baseHorizontal(lateral, frontal);

  calib.ganancia[GRUPO_CADERAS] = punto(efecto[GRUPO_CADERAS], lateral) * RAD_TO_DEG;
  // Pies (lateral) y femures (frontal) solo corrigen si su efecto se nota y
  // va sobre todo en su eje: si no, empujarian para cualquier lado.
  float pl = punto(efecto[GRUPO_PIES], lateral), pf = punto(efecto[GRUPO_PIES], frontal);
  calib.ganancia[GRUPO_PIES] =
      (fabs(pl) * AMPLITUD_AUTO_US * RAD_TO_DEG >= EFECTO_MINIMO_OTROS && fabs(pl) > fabs(pf)) ? pl * RAD_TO_DEG : 0;
  float fl = punto(efecto[GRUPO_FEMURES], lateral), ff = punto(efecto[GRUPO_FEMURES], frontal);
  calib.ganancia[GRUPO_FEMURES] =
      (fabs(ff) * AMPLITUD_AUTO_US * RAD_TO_DEG >= EFECTO_MINIMO_OTROS && fabs(ff) > fabs(fl)) ? ff * RAD_TO_DEG : 0;

  calib.autoListo = 1;
  referenciaIniciada = false;
  guardarCalibracion();
  String linea = "AUTOAJUSTE,ok";
  for (int g = 0; g < NUM_GRUPOS; g++) {
    linea += "," + String(NOMBRE_GRUPO[g]) + "=" + String(calib.ganancia[g] * AMPLITUD_AUTO_US, 1);
  }
  enviarLinea(linea); // grados de torso con AMPLITUD_AUTO_US; 0 = ese grupo no corrige
  if (balanceActivo) enviarLinea("BALANCE,ON");
}

void pasoAutoajuste(float dt) {
  if (emergenciaActiva || !servosConFuerza() || caidaDetectada) {
    cancelarAutoajuste("se detuvo o se cayo a mitad del autoajuste");
    return;
  }
  int grupo = autoajuste.paso / 2;
  float signo = (autoajuste.paso % 2 == 0) ? 1 : -1;
  float duracion = DURACION_FASE[autoajuste.fase];
  autoajuste.t += dt;
  float avance = min(autoajuste.t / duracion, 1.0f);

  if (autoajuste.fase == FASE_SUBIR) autoajuste.salida[grupo] = signo * AMPLITUD_AUTO_US * avance;
  else if (autoajuste.fase == FASE_BAJAR) autoajuste.salida[grupo] = signo * AMPLITUD_AUTO_US * (1 - avance);
  else if (autoajuste.fase == FASE_MEDIR) {
    for (int i = 0; i < 3; i++) autoajuste.suma[i] += gEst[i];
    autoajuste.muestras++;
  }
  if (autoajuste.t < duracion) return;

  autoajuste.t = 0;
  if (autoajuste.fase == FASE_MEDIR && autoajuste.muestras > 0) {
    int indice = signo > 0 ? 0 : 1;
    for (int i = 0; i < 3; i++) autoajuste.media[grupo][indice][i] = autoajuste.suma[i] / autoajuste.muestras;
    memset(autoajuste.suma, 0, sizeof(autoajuste.suma));
    autoajuste.muestras = 0;
  }
  if (++autoajuste.fase < NUM_FASES) return;
  autoajuste.fase = 0;
  if (++autoajuste.paso < 2 * NUM_GRUPOS) return;
  terminarAutoajuste();
}

// =====================================================================
// SEGMENTO: NIVELAR EL TORSO (ajusta la pose de Inicio hasta dejarlo derecho)
// El GY-521 va plano sobre la cubierta del torso con los componentes hacia
// arriba, asi que su eje Z es la vertical del torso. Con el robot parado en
// piso plano, NIVELAR mueve las caderas (costado) y los femures (adelante /
// atras) en pasos chicos, mide de nuevo, y repite hasta que la gravedad
// quede alineada con ese eje. Al terminar guarda la pose como Inicio.
// Usa lo que midio el autoajuste (grados de torso por us): si falta, lo
// corre antes, solo.
// =====================================================================
#define NIVEL_TOLERANCIA_GRADOS 0.5f
#define NIVEL_MAX_ITERACIONES   8
#define NIVEL_MAX_US            200.0f  // lo maximo que puede cambiar cada grupo en total
#define NIVEL_ASENTAR_MS        1500    // quieto despues de cada paso antes de medir
#define NIVEL_VELOCIDAD         4       // us por tick de rampa: pasos suaves
#define NIVEL_FACTOR            0.8f    // corrige un poco menos de lo medido para no pasarse
#define NIVEL_MONTAJE_MAX_GRADOS 30.0f  // si "arriba" queda mas lejos del eje Z, el sensor no esta plano
const float EJE_TORSO_SENSOR[3] = {0, 0, 1};

struct Nivelado {
  bool          activo;
  bool          esperandoAutoajuste;
  uint8_t       iteracion;
  unsigned long desde;                  // ultimo paso aplicado (o ultima rampa en curso)
  float         acumulado[NUM_GRUPOS];  // us que ya se sumaron a cada grupo
};
Nivelado nivelado;

// Inclinacion del torso respecto a la vertical real, en grados: + a su derecha / + adelante.
bool inclinacionTorso(float &rollTorso, float &pitchTorso) {
  float lateral[3] = {calib.ejeLateral[0], calib.ejeLateral[1], calib.ejeLateral[2]};
  quitarComponente(lateral, EJE_TORSO_SENSOR);
  if (!normalizar(lateral)) return false;
  float frontal[3];
  cruz(EJE_TORSO_SENSOR, lateral, frontal);
  rollTorso = asin(constrain(punto(gEst, lateral), -1.0f, 1.0f)) * RAD_TO_DEG;
  pitchTorso = asin(constrain(punto(gEst, frontal), -1.0f, 1.0f)) * RAD_TO_DEG;
  return true;
}

void cancelarNivelado(const String &motivo) {
  if (!nivelado.activo) return;
  nivelado.activo = false;
  enviarLinea("NIVELAR,error," + motivo);
}

void iniciarNivelado() {
  String motivo;
  if (!mpuDisponible)            { enviarLinea("NIVELAR,error,MPU6050 no detectado"); return; }
  if (nivelado.activo)           { enviarLinea("NIVELAR,error,ya esta en curso"); return; }
  if (autoajuste.activo)         { enviarLinea("NIVELAR,error,hay un autoajuste en curso"); return; }
  if (!listoParaAutoajuste(motivo)) { enviarLinea("NIVELAR,error," + motivo); return; }
  if (anguloEntre(gEst, EJE_TORSO_SENSOR) > NIVEL_MONTAJE_MAX_GRADOS) {
    enviarLinea("NIVELAR,error,el sensor no esta plano con los componentes hacia arriba (o el robot esta muy torcido)");
    return;
  }
  memset(&nivelado, 0, sizeof(nivelado));
  nivelado.activo = true;
  nivelado.desde = millis();
  if (!calib.autoListo) {
    nivelado.esperandoAutoajuste = true;
    iniciarAutoajuste();
  }
  enviarLinea("NIVELAR,inicio,no lo toques; tiene que estar en piso plano");
}

// Suma 'us' a los dos canales de un grupo, con rampa lenta y el signo de cada lado.
void moverGrupoNivelado(int grupo, float us) {
  for (uint8_t canal = 0; canal < NUM_CANALES; canal++) {
    int g;
    float signo;
    if (!grupoDelCanal(canal, g, signo) || g != grupo) continue;
    canales[canal].pulsoObjetivo = constrain(canales[canal].pulsoObjetivo + signo * us, (float) PULSO_MIN_ABS, (float) PULSO_MAX_ABS);
    canales[canal].pasoPorTick = NIVEL_VELOCIDAD;
    canales[canal].duracionMs = 0;
  }
  nivelado.acumulado[grupo] += us;
}

void pasoNivelado() {
  if (emergenciaActiva || !servosConFuerza() || caidaDetectada) {
    cancelarNivelado("se detuvo o se cayo a mitad del nivelado");
    return;
  }
  unsigned long ahora = millis();
  if (nivelado.esperandoAutoajuste) {
    if (autoajuste.activo) return;
    if (!calib.autoListo) {
      cancelarNivelado("no se pudo hacer el autoajuste");
      return;
    }
    nivelado.esperandoAutoajuste = false;
    nivelado.desde = ahora;
  }
  if (rampasEnCurso()) {
    nivelado.desde = ahora;
    return;
  }
  if (ahora - nivelado.desde < NIVEL_ASENTAR_MS || ahora - ultimoMovimiento < NIVEL_ASENTAR_MS) return;

  float rollTorso, pitchTorso;
  if (!inclinacionTorso(rollTorso, pitchTorso)) {
    cancelarNivelado("no hay eje lateral: repeti el AUTOAJUSTE");
    return;
  }
  bool corregirPitch = calib.ganancia[GRUPO_FEMURES] != 0;
  if (fabs(rollTorso) <= NIVEL_TOLERANCIA_GRADOS && (!corregirPitch || fabs(pitchTorso) <= NIVEL_TOLERANCIA_GRADOS)) {
    nivelado.activo = false;
    guardarHome();                    // la pose nivelada pasa a ser la de Inicio
    nivelGuardadoEnEstaHome = false;  // y el "derecho" del balance se vuelve a aprender quieto en ella
    referenciaIniciada = false;
    enviarLinea("NIVELAR,ok," + String(rollTorso, 1) + "," + String(pitchTorso, 1) + "," + String(nivelado.iteracion) +
                (corregirPitch ? "" : ",los femures no inclinan el torso: adelante/atras no se corrigio"));
    return;
  }
  if (nivelado.iteracion >= NIVEL_MAX_ITERACIONES) {
    cancelarNivelado("no llego a menos de " + String(NIVEL_TOLERANCIA_GRADOS, 1) + " grados (queda " +
                     String(rollTorso, 1) + " / " + String(pitchTorso, 1) + ")");
    return;
  }
  // Mismo convenio que el balance: us = inclinacion deseada / grados por us del grupo.
  float usCaderas = -NIVEL_FACTOR * rollTorso / calib.ganancia[GRUPO_CADERAS];
  usCaderas = constrain(usCaderas, -NIVEL_MAX_US - nivelado.acumulado[GRUPO_CADERAS], NIVEL_MAX_US - nivelado.acumulado[GRUPO_CADERAS]);
  float usFemures = 0;
  if (corregirPitch) {
    usFemures = -NIVEL_FACTOR * pitchTorso / calib.ganancia[GRUPO_FEMURES];
    usFemures = constrain(usFemures, -NIVEL_MAX_US - nivelado.acumulado[GRUPO_FEMURES], NIVEL_MAX_US - nivelado.acumulado[GRUPO_FEMURES]);
  }
  if (fabs(usCaderas) < 1.0f && fabs(usFemures) < 1.0f) {
    cancelarNivelado("llego al limite de " + String(NIVEL_MAX_US, 0) + " us sin nivelar: revisa la pose de Inicio");
    return;
  }
  moverGrupoNivelado(GRUPO_CADERAS, usCaderas);
  if (corregirPitch) moverGrupoNivelado(GRUPO_FEMURES, usFemures);
  nivelado.iteracion++;
  nivelado.desde = ahora;
  enviarLinea("NIVELAR,paso," + String(nivelado.iteracion) + "," + String(rollTorso, 1) + "," + String(pitchTorso, 1));
}

// ---- Lectura, filtro y control -------------------------------------------
float limitarUs(float us) { return constrain(us, -ajustes.maxUs, ajustes.maxUs); }

void actualizarIMU() {
  if (!mpuDisponible) return;
  unsigned long ahora = millis();
  if (ahora - ultimaMuestraIMU < TICK_IMU_MS) return;
  float dt = (ultimaMuestraIMU == 0) ? 0 : (ahora - ultimaMuestraIMU) / 1000.0f;
  ultimaMuestraIMU = ahora;
  // Primera muestra, o loop() estuvo trabado: no integrar un salto enorme.
  if (dt <= 0 || dt > 0.5f) dt = TICK_IMU_MS / 1000.0f;
  if (!enPoseHome) nivelGuardadoEnEstaHome = false;

  sensors_event_t a, g, temp;
  mpu.getEvent(&a, &g, &temp);

  float acel[3] = {a.acceleration.x, a.acceleration.y, a.acceleration.z};
  float modAccel = sqrt(punto(acel, acel));
  const float giroCrudo[3] = {g.gyro.x, g.gyro.y, g.gyro.z};
  revisarQuietud(giroCrudo, acel, modAccel, ahora);

  // Sin sesgo conocido el giroscopio deriva: hasta calibrarlo se usa solo el acelerometro.
  float w[3] = {0, 0, 0};
  if (calib.giroListo) for (int i = 0; i < 3; i++) w[i] = giroCrudo[i] - calib.sesgo[i];

  float acelUnit[3] = {acel[0], acel[1], acel[2]};
  bool acelValida = normalizar(acelUnit);
  if (!gEstIniciado) {
    if (!acelValida) return;
    for (int i = 0; i < 3; i++) gEst[i] = acelUnit[i];
    gEstIniciado = true;
  }
  // Filtro complementario sobre el vector gravedad: el giroscopio dice como
  // se movio (d/dt = -w x g) y el acelerometro lo corrige de a poco. Con
  // golpes fuertes el acelerometro miente y, si se puede, se ignora.
  float giroXg[3];
  cruz(w, gEst, giroXg);
  bool acelConfiable = acelValida && (fabs(modAccel - SENSORS_GRAVITY_EARTH) < 3.0f || !calib.giroListo);
  const float ALFA = acelConfiable ? TAU_COMPLEMENTARIO / (TAU_COMPLEMENTARIO + dt) : 1.0f;
  for (int i = 0; i < 3; i++) {
    gEst[i] = ALFA * (gEst[i] - giroXg[i] * dt) + (1 - ALFA) * (acelConfiable ? acelUnit[i] : 0);
  }
  normalizar(gEst);

  bool caido = false;
  if (calib.nivelListo) {
    float lateral[3], frontal[3];
    baseHorizontal(lateral, frontal);
    roll = asin(constrain(punto(gEst, lateral), -1.0f, 1.0f)) * RAD_TO_DEG;
    pitch = asin(constrain(punto(gEst, frontal), -1.0f, 1.0f)) * RAD_TO_DEG;
    rollVel = -punto(giroXg, lateral) * RAD_TO_DEG;
    pitchVel = -punto(giroXg, frontal) * RAD_TO_DEG;
    if (calib.giroListo) rumbo += punto(w, calib.arriba) * RAD_TO_DEG * dt;
    caido = anguloEntre(gEst, calib.arriba) > ANGULO_CAIDA;
  } else {
    roll = pitch = rollVel = pitchVel = 0;
  }
  if (caido != caidaDetectada) {
    caidaDetectada = caido;
    enviarLinea(caido ? "BALANCE,caida" : "BALANCE,recuperado");
  }

  if (!referenciaIniciada) {
    refRoll = roll;
    refPitch = pitch;
    referenciaIniciada = true;
  }
  float seguir = dt / (SEGUNDOS_REFERENCIA + dt);
  refRoll += seguir * (roll - refRoll);
  refPitch += seguir * (pitch - refPitch);

  // Balance pedido pero sin autoajuste: se hace solo en cuanto el robot
  // este quieto en Inicio.
  String motivo;
  if (balanceActivo && !calib.autoListo && !autoajuste.activo && listoParaAutoajuste(motivo)) {
    iniciarAutoajuste();
  }
  if (autoajuste.activo) pasoAutoajuste(dt);
  if (nivelado.activo) pasoNivelado();

  // Correccion en grados de torso, repartida en us segun lo que midio el autoajuste.
  float deseoRoll = -(ajustes.kpRoll * (roll - refRoll) + ajustes.kdRoll * rollVel);
  float deseoPitch = -(ajustes.kpPitch * (pitch - refPitch) + ajustes.kdPitch * pitchVel);
  bool usaPies = calib.ganancia[GRUPO_PIES] != 0;
  salidaGrupo[GRUPO_CADERAS] = calib.ganancia[GRUPO_CADERAS] != 0
      ? limitarUs((usaPies ? 0.5f : 1.0f) * deseoRoll / calib.ganancia[GRUPO_CADERAS]) : 0;
  salidaGrupo[GRUPO_PIES] = usaPies ? limitarUs(0.5f * deseoRoll / calib.ganancia[GRUPO_PIES]) : 0;
  salidaGrupo[GRUPO_FEMURES] = calib.ganancia[GRUPO_FEMURES] != 0
      ? limitarUs(deseoPitch / calib.ganancia[GRUPO_FEMURES]) : 0;

  // Entra y sale de a poco: sin tirones al activarlo, al reanudar tras un
  // STOP/RELAX o al levantar el robot caido.
  bool aplicar = balanceActivo && calib.autoListo && calib.giroListo && !autoajuste.activo && !nivelado.activo &&
                 !caidaDetectada && !emergenciaActiva && servosConFuerza();
  float pasoMezcla = dt / SEGUNDOS_ENTRADA;
  mezclaBalance = constrain(mezclaBalance + (aplicar ? pasoMezcla : -pasoMezcla), 0.0f, 1.0f);

  if (telemetriaActiva && ahora - ultimoEnvioACT >= INTERVALO_ACT_MS) {
    ultimoEnvioACT = ahora;
    const char* estado = autoajuste.activo ? "AUTO" : caidaDetectada ? "CAIDA" : (mezclaBalance > 0 ? "ON" : "OFF");
    float corrLateral = autoajuste.activo ? autoajuste.salida[GRUPO_CADERAS] : mezclaBalance * salidaGrupo[GRUPO_CADERAS];
    float corrFrontal = autoajuste.activo ? autoajuste.salida[GRUPO_FEMURES] : mezclaBalance * salidaGrupo[GRUPO_FEMURES];
    char linea[96];
    snprintf(linea, sizeof(linea), "ACT,%.1f,%.1f,%.1f,%.0f,%.0f,%s,%d,%d,%d", roll, pitch, rumbo,
             corrLateral, corrFrontal, estado, calib.giroListo, calib.nivelListo, calib.autoListo);
    enviarLinea(linea);
  }
}

// Cuanto sumarle a la salida fisica de un canal. 0 para los canales que no
// participan o con el balance apagado: ahi todo queda identico a antes.
float correccionBalance(uint8_t canal) {
  int grupo;
  float signo;
  if (!grupoDelCanal(canal, grupo, signo)) return 0;
  if (autoajuste.activo) return signo * autoajuste.salida[grupo];
  if (mezclaBalance <= 0) return 0;
  return signo * mezclaBalance * salidaGrupo[grupo];
}

void mostrarActitud() {
  if (!mpuDisponible) {
    enviarLinea("MPU6050 no detectado.");
    return;
  }
  enviarLinea("Roll " + String(roll, 1) + " | Pitch " + String(pitch, 1) + " | Rumbo " + String(rumbo, 1) +
              " | Balance " + (balanceActivo ? "ON" : "OFF") +
              " | Giro " + (calib.giroListo ? "calibrado" : "sin calibrar (dejarlo quieto 1 s)") +
              " | Nivel " + (calib.nivelListo ? "ok" : "pendiente (quieto en Inicio)") +
              " | Autoajuste " + (autoajuste.activo ? "en curso" : calib.autoListo ? "ok" : "pendiente"));
}

void reportarConfigBalance() {
  char linea[160];
  snprintf(linea, sizeof(linea), "BALCONF,%.2f,%.2f,%.2f,%.2f,%.0f,%d,%.1f,%.1f,%.1f,%d",
           ajustes.kpRoll, ajustes.kdRoll, ajustes.kpPitch, ajustes.kdPitch, ajustes.maxUs, calib.autoListo,
           calib.ganancia[GRUPO_CADERAS] * AMPLITUD_AUTO_US, calib.ganancia[GRUPO_PIES] * AMPLITUD_AUTO_US,
           calib.ganancia[GRUPO_FEMURES] * AMPLITUD_AUTO_US, balanceActivo ? 1 : 0);
  enviarLinea(linea);
}

// Lee hasta 'cantidad' numeros separados por coma desde la posicion 'desde'.
int leerNumeros(const String &linea, int desde, float* salida, int cantidad) {
  int leidos = 0;
  int cursor = desde;
  while (leidos < cantidad) {
    int coma = linea.indexOf(',', cursor);
    String trozo = (coma == -1) ? linea.substring(cursor) : linea.substring(cursor, coma);
    trozo.trim();
    if (trozo.length() == 0) break;
    salida[leidos++] = trozo.toFloat();
    if (coma == -1) break;
    cursor = coma + 1;
  }
  return leidos;
}

// =====================================================================
// SEGMENTO: PANTALLA OLED (CARAS) — bus I2C aparte, NO comparte con
// los servos. Un refresco de pantalla es lento (~20 ms) y si
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
    ultimaCorreccion[canal] = 0;
  }
  enPoseHome = false;
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
    ultimaCorreccion[canal] = 0;
  }
  enPoseHome = false;
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
  // La pose actual pasa a ser la de Inicio, pero si hay rampas en curso el
  // robot va a terminar en otra pose: ahi no sirve como referencia de nivel.
  enPoseHome = !rampasEnCurso();
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
  enPoseHome = true;
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
  enPoseHome = false;          // no es la pose de Inicio guardada: el balance no se activa aca
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

  mpuDisponible = iniciarMPU();
  cargarBalance(); // despues de prefs.begin() y de saber si hay sensor

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
  enPoseHome = true;

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
  enviarLinea(String("MPU6050: ") + (mpuDisponible ? "detectado" : "no detectado - el balance no va a funcionar"));
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
  enviarLinea("  BALANCE,ON/OFF -> balance automatico con el MPU6050 (se recuerda al apagar)");
  enviarLinea("  AUTOAJUSTE -> mide hacia donde corrige cada grupo de servos (~17 s, en Inicio)");
  enviarLinea("  NIVELAR   -> deja el torso derecho ajustando caderas/femures y lo guarda como Inicio (piso plano)");
  enviarLinea("  IMUON / IMUOFF -> manda la inclinacion en vivo a la app (ACT,...)");
  enviarLinea("  BALCONF   -> muestra ganancias y resultado del autoajuste");
  enviarLinea("  BALGAIN,kpR,kdR,kpP,kdP,maxUs -> cambia cuanto corrige");
  enviarLinea("  RUMBO,0   -> pone en cero el desvio de rumbo");
  enviarLinea("  ACTITUD   -> inclinacion y estado del autocalibrado");
  enviarLinea("  IMURESET  -> olvida lo aprendido (si se remonta el sensor)");
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
  if (tipo.equalsIgnoreCase("SCAN")) { escanearI2C(); return; }
  if (tipo.equalsIgnoreCase("ACTITUD")) { mostrarActitud(); return; }
  if (tipo.equalsIgnoreCase("BALCONF")) { reportarConfigBalance(); return; }
  if (tipo.equalsIgnoreCase("RUMBO")) { rumbo = 0; enviarLinea("RUMBO,0"); return; }
  if (tipo.equalsIgnoreCase("IMURESET")) {
    cancelarAutoajuste("IMURESET");
    calib = CALIBRACION_INICIAL;
    guardarCalibracion();
    enviarLinea("IMURESET,ok - se vuelve a aprender solo");
    return;
  }
  if (tipo.equalsIgnoreCase("AUTOAJUSTE")) {
    String motivo;
    if (!mpuDisponible) enviarLinea("AUTOAJUSTE,error,MPU6050 no detectado");
    else if (autoajuste.activo) enviarLinea("AUTOAJUSTE,error,ya esta en curso");
    else if (!listoParaAutoajuste(motivo)) enviarLinea("AUTOAJUSTE,error," + motivo);
    else iniciarAutoajuste();
    return;
  }
  if (tipo.equalsIgnoreCase("NIVELAR")) { iniciarNivelado(); return; }
  if (tipo.equalsIgnoreCase("IMUON") || tipo.equalsIgnoreCase("IMUOFF")) {
    if (!mpuDisponible) {
      enviarLinea("IMUSTREAM,error - MPU6050 no detectado");
      return;
    }
    telemetriaActiva = tipo.equalsIgnoreCase("IMUON");
    enviarLinea(telemetriaActiva ? "IMUSTREAM,ON" : "IMUSTREAM,OFF");
    return;
  }
  if (tipo.equalsIgnoreCase("BALANCE")) {
    String valor = (primeraComa == -1) ? String() : linea.substring(primeraComa + 1);
    valor.trim();
    bool encender = valor.equalsIgnoreCase("ON");
    if (!encender && !valor.equalsIgnoreCase("OFF")) {
      enviarLinea("Uso: BALANCE,ON o BALANCE,OFF");
      return;
    }
    if (encender && !mpuDisponible) {
      enviarLinea("BALANCE,error - MPU6050 no detectado");
      return;
    }
    balanceActivo = encender;
    prefs.putBool("balon", balanceActivo);
    if (!encender) {
      cancelarAutoajuste("se apago el balance");
      enviarLinea("BALANCE,OFF");
    } else if (calib.autoListo) {
      enviarLinea("BALANCE,ON");
    } else {
      // actualizarIMU() arranca el autoajuste solo en cuanto se pueda.
      String motivo;
      enviarLinea(listoParaAutoajuste(motivo) ? "BALANCE,autoajustando"
                                              : "BALANCE,esperando," + motivo + " (despues se autoajusta solo)");
    }
    return;
  }
  if (tipo.equalsIgnoreCase("BALGAIN")) {
    float v[5];
    bool valido = primeraComa != -1 && leerNumeros(linea, primeraComa + 1, v, 5) == 5 &&
                  v[0] >= 0 && v[0] <= 2 && v[1] >= 0 && v[1] <= 0.5f &&
                  v[2] >= 0 && v[2] <= 2 && v[3] >= 0 && v[3] <= 0.5f && v[4] >= 0 && v[4] <= 400;
    if (!valido) {
      enviarLinea("BALGAIN invalido. Usa: kpRoll(0-2),kdRoll(0-0.5),kpPitch(0-2),kdPitch(0-0.5),maxUs(0-400)");
      return;
    }
    ajustes = {v[0], v[1], v[2], v[3], v[4]};
    prefs.putBytes("balaj2", &ajustes, sizeof(ajustes));
    reportarConfigBalance();
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
    enPoseHome = false;
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
    enPoseHome = false;
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
  enPoseHome = false;
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
  actualizarIMU();
  actualizarRampas();

  // Acepta un cliente WiFi nuevo (uno a la vez, como con el cable USB). Se
  // acepta SIEMPRE, no solo cuando el cliente viejo ya se dio por muerto: si
  // el PC pierde el WiFi de golpe y vuelve, abre un socket nuevo mientras el
  // ESP32 todavia cree que el viejo sigue vivo, y ese socket nuevo quedaria
  // esperando en la cola sin que nadie lo acepte -- la app diria "Conectado"
  // y el robot no responderia hasta reiniciarlo. Gana el ultimo que llega.
  {
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
