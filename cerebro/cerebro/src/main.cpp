#include <Arduino.h>
#include <SoftwareSerial.h>
#include <RH_ASK.h> // NUEVA LIBRERÍA: RadioHead ASK
#include <SPI.h>    // Requerido por la arquitectura interna de RadioHead

SoftwareSerial serialMotores(2, 3); // RX=2, TX=3 (Hacia Motores)

// Configuración RadioHead: Velocidad 2000 bps, RX pin (no usado)=11, TX pin=12, PTT pin (no usado, fijado a pin 10 libre)=10
RH_ASK radio(2000, 11, 12, 10);

// Asignación de Pines de Sensores
const int trigPin1 = 9;
const int echoPin1 = 8;
const int trigPin2 = 7;
const int echoPin2 = 6;  

const int linePinIzq = A0;
const int linePinCen = A1;
const int linePinDer = A2;

const int pinGasMQ5 = A3;
const int pinHumedad = A4;

const unsigned long TIMEOUT_US = 5000; // 5ms equivale a ~85 cm (suficiente para detectar obstáculo a <30cm sin esperar de más)

// Estructura empaquetada para transmisión
struct __attribute__((packed)) Telemetria {
  int16_t distIzquierda;
  int16_t distDerecha;
  uint8_t lineaIzquierda;
  uint8_t lineaCentro;
  uint8_t lineaDerecha;
  int16_t nivelGas;
  int16_t nivelHumedad;
};
Telemetria datosRobot;

int16_t calcular_distancia(unsigned long duracion) {
  if (duracion == 0) return 999;
  return (duracion * 0.034) / 2;
}

void medir_distancias() {
  unsigned long dur1, dur2;
  
  // Guardamos el estado y desactivamos la interrupción del Timer 1 (RadioHead)
  // para evitar que interfiera con la precisión de pulseIn() y cause jitter en las lecturas
  byte oldTIMSK1 = TIMSK1;
  TIMSK1 &= ~_BV(OCIE1A);

  // Sensor 1 (Izquierda)
  digitalWrite(trigPin1, LOW); delayMicroseconds(2);
  digitalWrite(trigPin1, HIGH); delayMicroseconds(10); digitalWrite(trigPin1, LOW);
  dur1 = pulseIn(echoPin1, HIGH, TIMEOUT_US); 
  
  // Si dur1 es 0, el sensor pudo haber quedado en timeout.
  // Realizamos un reset físico/eléctrico momentáneo del pin Echo.
  if (dur1 == 0) {
    pinMode(echoPin1, OUTPUT);
    digitalWrite(echoPin1, LOW);
    delayMicroseconds(50);
    pinMode(echoPin1, INPUT);
  }
  
  // Pausa corta de 15ms para evitar rebote acústico (cross-talk) entre sensores
  delay(15);
  
  // Sensor 2 (Derecha)
  digitalWrite(trigPin2, LOW); delayMicroseconds(2);
  digitalWrite(trigPin2, HIGH); delayMicroseconds(10); digitalWrite(trigPin2, LOW);
  dur2 = pulseIn(echoPin2, HIGH, TIMEOUT_US);

  // Reset físico/eléctrico si hay timeout
  if (dur2 == 0) {
    pinMode(echoPin2, OUTPUT);
    digitalWrite(echoPin2, LOW);
    delayMicroseconds(50);
    pinMode(echoPin2, INPUT);
  }

  // Restauramos la interrupción de la radio
  TIMSK1 = oldTIMSK1;

  datosRobot.distIzquierda = calcular_distancia(dur1);
  datosRobot.distDerecha = calcular_distancia(dur2);
}


void leer_entorno() {
  
  datosRobot.lineaIzquierda = digitalRead(linePinIzq);
  datosRobot.lineaCentro = digitalRead(linePinCen);
  datosRobot.lineaDerecha = digitalRead(linePinDer);
  datosRobot.nivelGas = analogRead(pinGasMQ5);
  datosRobot.nivelHumedad = analogRead(pinHumedad);

  // ===============================Eliminar
  // SIMULACIÓN DE LÍNEA CENTRAL PARA PRUEBA DE AVANCE ('w')
  // Forzamos las condiciones ideales: No hay línea a los lados (0), pero sí al centro (1)
  datosRobot.lineaCentro = 1;    // Simulamos que el sensor del medio siempre detecta la línea
  // ===============================Eliminar
}

void evaluar_y_transmitir() {
  char comandoMotor = ' '; 

  // 1. LÓGICA AUTÓNOMA (Cálculo base)
  if (datosRobot.distIzquierda < 30 || datosRobot.distDerecha < 30) {
    comandoMotor = ' '; // Prioridad absoluta: Evasión (Stop)
  } else {
    uint8_t I = datosRobot.lineaIzquierda;
    uint8_t C = datosRobot.lineaCentro;
    uint8_t D = datosRobot.lineaDerecha;

    if (I && C && D) {
      comandoMotor = ' '; // Intersección
    } else if (!I && C && !D) {
      comandoMotor = 'w'; // Avanzar
    } else if (I && !D) {
      comandoMotor = 'a'; // Corrección Izquierda
    } else if (!I && D) {
      comandoMotor = 'd'; // Corrección Derecha
    } else {
      comandoMotor = ' '; // Fuera de línea
    }
  }

  // 2. INTERRUPCIÓN POR TECLADO (Sobrescribe la lógica autónoma si estás en PC)
  if (Serial.available() > 0) {
    char tecla = Serial.read();
    if (tecla != '\n' && tecla != '\r') {
      comandoMotor = tolower(tecla); 
    }
  }

  // 3. ENVÍO DE DATOS A NODO DE TRACCIÓN (UART) - Solo si hay un cambio de comando para no saturar con interrupciones
  static char ultimoComandoMotor = 'x';
  if (comandoMotor != ultimoComandoMotor) {
    ultimoComandoMotor = comandoMotor;
    serialMotores.print(comandoMotor); // Usar print en lugar de println para ahorrar bytes e interrupciones bloqueadas
  }
  
  // 4. TRANSMISIÓN RF Y DEPURACIÓN EN PANTALLA (Temporizado a 500ms)
  static unsigned long ultimaTransmision = 0;
  if (millis() - ultimaTransmision >= 500) {
    ultimaTransmision = millis();
    
    // Transmisión inalámbrica 433 MHz a la Estación Base
    radio.send((uint8_t *)&datosRobot, sizeof(datosRobot));
    radio.waitPacketSent();
    
    // Volcado de Depuración Visual (Monitor Serie a 115200 baudios)
    Serial.println("=========================================");
    Serial.println("      DEBUG NAVBOT (NODO CEREBRO)        ");
    Serial.println("=========================================");
    Serial.print("ODOMETRÍA   | Izq: "); Serial.print(datosRobot.distIzquierda); 
    Serial.print(" cm \t Der: "); Serial.print(datosRobot.distDerecha); Serial.println(" cm");
    
    Serial.print("INFRARROJOS | I: "); Serial.print(datosRobot.lineaIzquierda); 
    Serial.print(" \t C: "); Serial.print(datosRobot.lineaCentro);
    Serial.print(" \t D: "); Serial.println(datosRobot.lineaDerecha);
    
    Serial.print("AMBIENTAL   | Gas: "); Serial.print(datosRobot.nivelGas); 
    Serial.print(" \t Hum: "); Serial.println(datosRobot.nivelHumedad);
    
    Serial.print("ESTADO UART | Cmd hacia motores: [ "); 
    Serial.print(comandoMotor); Serial.println(" ]");
    Serial.println("=========================================\n");
  }
}

void setup() {
  serialMotores.begin(9600);
  Serial.begin(115200);
  
  pinMode(trigPin1, OUTPUT); pinMode(trigPin2, OUTPUT);
  pinMode(echoPin1, INPUT);  pinMode(echoPin2, INPUT);
  pinMode(linePinIzq, INPUT); pinMode(linePinCen, INPUT); pinMode(linePinDer, INPUT);
  
  // Inicializar hardware 433MHz
  if (!radio.init()) {
    Serial.println("Fallo critico: Modulo 433MHz no inicializado.");
  } else {
    Serial.println("Transmisor 433MHz en linea.");
  }
}

void loop() {
  medir_distancias();
  leer_entorno();
  evaluar_y_transmitir();
  delay(10); 
}