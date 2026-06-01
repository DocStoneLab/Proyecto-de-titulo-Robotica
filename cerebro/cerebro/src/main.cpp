#include <Arduino.h>

// Definición de pines - Sensores de Ultrasonido
const int trigPin1 = 9;
const int echoPin1 = 10;
const int trigPin2 = 7;
const int echoPin2 = 11;

// Definición de pines - Sensores de Línea (TCRT5000)
const int linePinIzq = 8;
const int linePinDer = 12; // Pin adicional requerido para cuadrícula

// Variables de estado
int distancia1 = 0;
int distancia2 = 0;
bool estadoLineaIzq = false;
bool estadoLineaDer = false;

// Timeout para 50 cm (aprox 3000 microsegundos)
const unsigned long TIMEOUT_US = 3000; 

int calcular_distancia(long duracion) {
  // Retorna 0 si la duración es 0 (ocurre cuando pulseIn alcanza el timeout)
  if (duracion == 0) return 999; // 999 representa "vía libre"
  return (duracion * 0.034) / 2;
}

void medir_distancias(int &dist1, int &dist2) {
  long duracion1, duracion2;

  // Medición Sensor 1
  digitalWrite(trigPin1, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin1, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin1, LOW);
  duracion1 = pulseIn(echoPin1, HIGH, TIMEOUT_US); 
  
  // Medición Sensor 2
  digitalWrite(trigPin2, LOW);
  delayMicroseconds(2);
  digitalWrite(trigPin2, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin2, LOW);
  duracion2 = pulseIn(echoPin2, HIGH, TIMEOUT_US);

  dist1 = calcular_distancia(duracion1);
  dist2 = calcular_distancia(duracion2);
}

void evaluar_entorno() {
  // Lectura de los dos sensores de línea
  estadoLineaIzq = digitalRead(linePinIzq);
  estadoLineaDer = digitalRead(linePinDer);

  // Lógica de prioridad: La seguridad (ultrasonido) anula la odometría (infrarrojo)
  if (distancia1 < 30 || distancia2 < 30) {
    Serial.println("EVASIÓN: Obstáculo detectado. Detener motores.");
    // Aquí invocarás: detenerMotores();
  } else {
    // Lógica de seguimiento de línea (Ejemplo discreto)
    if (estadoLineaIzq == HIGH && estadoLineaDer == HIGH) {
      Serial.println("INTERSECCIÓN: Evaluar giro.");
    } else if (estadoLineaIzq == HIGH) {
      Serial.println("DESVÍO DERECHA: Corrigiendo a la izquierda.");
    } else if (estadoLineaDer == HIGH) {
      Serial.println("DESVÍO IZQUIERDA: Corrigiendo a la derecha.");
    } else {
      Serial.println("VÍA LIBRE: Avanzando recto.");
    }
  }
}

void setup() {
  pinMode(trigPin1, OUTPUT);
  pinMode(trigPin2, OUTPUT);
  pinMode(echoPin1, INPUT);
  pinMode(echoPin2, INPUT);
  pinMode(linePinIzq, INPUT);
  pinMode(linePinDer, INPUT);
  Serial.begin(9600);
}

void loop() {
  medir_distancias(distancia1, distancia2);
  evaluar_entorno();
  
  // Pausa mínima de estabilidad del ciclo (no interfiere con la odometría local)
  delay(10); 
}