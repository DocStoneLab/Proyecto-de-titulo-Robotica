#include <Arduino.h>

// Definición de los pines - CORRECCIÓN: Se requiere un Trigger por sensor
const int trigPin1 = 9;
const int trigPin2 = 7; // Asignar a un nuevo pin en el Arduino
const int echoPin1 = 10;
const int echoPin2 = 11;
const int linePin = 8;

// Variables globales limpias
int distancia1;
int distancia2;
bool estadoLinea;

// Función para calcular la distancia
int calcular_distancia(long duracion) {
  // Velocidad del sonido 0.034 cm/µs. Dividido por 2 por el rebote.
  return (duracion * 0.034) / 2;
}

// CORRECCIÓN: Paso de variables por referencia para modificar ambas variables globales/locales
void medir_distancias(int &dist1, int &dist2) {
  long duracion1, duracion2;

  // Medición Sensor 1
  digitalWrite(trigPin1, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin1, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin1, LOW);
  duracion1 = pulseIn(echoPin1, HIGH);
  
  // Medición Sensor 2 (Debe ser secuencial debido al bloqueo de pulseIn)
  digitalWrite(trigPin2, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin2, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin2, LOW);
  duracion2 = pulseIn(echoPin2, HIGH);

  // Cálculos
  dist1 = calcular_distancia(duracion1);
  dist2 = calcular_distancia(duracion2);
}

// CORRECCIÓN: Ahora recibe ambas distancias o las evalúa según la lógica del robot
void avanzar(int dist1, int dist2) {
  // Si cualquiera de los dos sensores detecta un obstáculo a menos de 30cm
  if (dist1 < 30 || dist2 < 30) {
    Serial.println("No avanzar");
  } else {
    Serial.println("Avanzar");
  }
}

void setup() {
  pinMode(trigPin1, OUTPUT);
  pinMode(trigPin2, OUTPUT);
  pinMode(echoPin1, INPUT);
  pinMode(echoPin2, INPUT);
  pinMode(linePin, INPUT);
  Serial.begin(9600);
}

void loop() {
  // 1. Ejecutar la medición una sola vez por ciclo
  medir_distancias(distancia1, distancia2);
  
  // 2. Imprimir distancias
  Serial.print("D1: "); Serial.print(distancia1);
  Serial.print(" cm | D2: "); Serial.print(distancia2); Serial.println(" cm");
  
  // 3. Tomar decisión de movimiento
  avanzar(distancia1, distancia2);
  
  // 4. Leer sensor de línea
  estadoLinea = digitalRead(linePin);
  Serial.print("Sensor de Linea: ");
  Serial.println(estadoLinea);
  
  delay(500); // Retraso unificado al final del ciclo
}