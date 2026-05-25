#include <Arduino.h>

// Definición de los pines
const int trigPin = 9;
const int echoPin = 10;
const int linePin = 8;

// Variables para calcular la distancia
long duracion;
int distancia;
bool Linea;

int medir_distancia(){
  // 1. Limpiar el pin Trig
  digitalWrite(trigPin, LOW);
  delayMicroseconds(2);
  
  // 2. Emitir un pulso ultrasónico de 10 microsegundos
  digitalWrite(trigPin, HIGH);
  delayMicroseconds(10);
  digitalWrite(trigPin, LOW);
  
  // 3. Leer el tiempo que tarda el eco en regresar
  duracion = pulseIn(echoPin, HIGH);
  
  // 4. Calcular la distancia (la velocidad del sonido es aprox. 340 m/s o 0.034 cm/µs)
  // Como el sonido va y vuelve, dividimos el tiempo entre 2.
  distancia = duracion * 0.034 / 2;
  
  // 5. Mostrar el resultado en el Monitor Serial
  //Serial.print("Distancia: ");
  //Serial.print(distancia);
  //Serial.println(" cm");
  
  delay(500); // Espera medio segundo antes de la siguiente medición

  return distancia;
}

void avanzar(int distancia){

  if (distancia < 30)
  {
    Serial.println("No avanzar");
  }
  else
  {
    Serial.println("avanzar");
  }
  
}

void setup() {
  pinMode(trigPin, OUTPUT); // El pin Trig emite el pulso
  pinMode(echoPin, INPUT);  // El pin Echo recibe el rebote
  pinMode(linePin, INPUT);  // EL pin de el Sensor de linea
  Serial.begin(9600);       // Inicializa la comunicación serial
}

void loop() {
  Serial.println(medir_distancia());
  avanzar(medir_distancia());
  Linea = digitalRead(linePin);
  Serial.println(Linea);

}