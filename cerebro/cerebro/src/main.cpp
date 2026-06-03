#include <Arduino.h>
#include <SoftwareSerial.h>
#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>

// 1. Configuración de Comunicación
SoftwareSerial serialMotores(2, 3); // RX en 2, TX en 3 (Hacia Arduino Motores)
RF24 radio(4, 5);                   // CE en 4, CSN en 5 (Bus SPI en 11, 12, 13)
const byte direccionBase[6] = "00001";

// 2. Asignación de Pines
const int trigPin1 = 9;
const int echoPin1 = 10;
const int trigPin2 = 7;
const int echoPin2 = 6;  // Modificado (Evitar conflicto SPI)

const int linePinIzq = A0;
const int linePinCen = A1;
const int linePinDer = A2;

const int pinGasMQ5 = A3;
const int pinHumedad = A4;

const unsigned long TIMEOUT_US = 3000;

// 3. Estructura de Telemetría (Debe ser idéntica en el Arduino receptor)
struct Telemetria {
  int distIzquierda;
  int distDerecha;
  bool lineaIzquierda;
  bool lineaCentro;
  bool lineaDerecha;
  int nivelGas;
  int nivelHumedad;
};
Telemetria datosRobot;

// Función para calcular distancia
int calcular_distancia(long duracion) {
  if (duracion == 0) return 999;
  return (duracion * 0.034) / 2;
}

// Lectura acústica bloqueante optimizada por Timeout
void medir_distancias() {
  long dur1, dur2;
  
  digitalWrite(trigPin1, LOW); delayMicroseconds(2);
  digitalWrite(trigPin1, HIGH); delayMicroseconds(10); digitalWrite(trigPin1, LOW);
  dur1 = pulseIn(echoPin1, HIGH, TIMEOUT_US); 
  
  digitalWrite(trigPin2, LOW); delayMicroseconds(2);
  digitalWrite(trigPin2, HIGH); delayMicroseconds(10); digitalWrite(trigPin2, LOW);
  dur2 = pulseIn(echoPin2, HIGH, TIMEOUT_US);

  datosRobot.distIzquierda = calcular_distancia(dur1);
  datosRobot.distDerecha = calcular_distancia(dur2);
}

// Actualización de estado del entorno
void leer_entorno() {
  datosRobot.lineaIzquierda = digitalRead(linePinIzq);
  datosRobot.lineaCentro = digitalRead(linePinCen);
  datosRobot.lineaDerecha = digitalRead(linePinDer);
  
  datosRobot.nivelGas = analogRead(pinGasMQ5);
  datosRobot.nivelHumedad = analogRead(pinHumedad);
}

// Lógica central y transmisión de datos
void evaluar_y_transmitir() {
  char comandoMotor = 'S'; 
  
  // A. Evasión de colisiones (Seguridad Activa)
  if (datosRobot.distIzquierda < 30 || datosRobot.distDerecha < 30) {
    comandoMotor = 'S'; // Stop
  } else {
    // B. Odometría de 3 Sensores (1 = Línea Negra, 0 = Fondo Claro)
    bool I = datosRobot.lineaIzquierda;
    bool C = datosRobot.lineaCentro;
    bool D = datosRobot.lineaDerecha;

    if (I && C && D) {
      comandoMotor = 'X'; // Intersección completa
    } else if (!I && C && !D) {
      comandoMotor = 'A'; // Centrado -> Avanzar Recto
    } else if (I && !D) {
      comandoMotor = 'I'; // Desvío detectado a la derecha -> Girar Izquierda
    } else if (!I && D) {
      comandoMotor = 'D'; // Desvío detectado a la izquierda -> Girar Derecha
    } else {
      comandoMotor = 'S'; // Fuera de línea -> Stop o Búsqueda
    }
  }

  // C. Transmisión Serial al Arduino Motores
  serialMotores.println(comandoMotor);
  
  // D. Transmisión RF a la Estación Base
  radio.write(&datosRobot, sizeof(datosRobot));
}

void setup() {
  serialMotores.begin(9600);
  
  pinMode(trigPin1, OUTPUT); pinMode(trigPin2, OUTPUT);
  pinMode(echoPin1, INPUT); pinMode(echoPin2, INPUT);
  
  pinMode(linePinIzq, INPUT);
  pinMode(linePinCen, INPUT);
  pinMode(linePinDer, INPUT);
  
  // Configuración RF
  if (radio.begin()) {
    radio.openWritingPipe(direccionBase);
    radio.setPALevel(RF24_PA_MIN);
    radio.stopListening(); 
  }
}

void loop() {
  medir_distancias();
  leer_entorno();
  evaluar_y_transmitir();
  delay(10); 
}