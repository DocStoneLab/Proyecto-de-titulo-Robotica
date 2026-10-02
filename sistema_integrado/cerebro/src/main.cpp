#include <Arduino.h>

// ==========================================
// ARDUINO 1: NODO DE SENSORES (US + LÍNEA)
// Conectado directamente por USB a la Raspberry Pi (115200 baudios)
// ==========================================

// Pines Sensores
const int trigPinFrente = 9;
const int echoPinFrente = 8;
const int linePinIzq    = A0;
const int linePinCen    = A1;
const int linePinDer    = A2;

const unsigned long TIMEOUT_US = 6000; // ~100 cm de alcance maximo en ultrasonido

// Variables de sensado
int16_t distFrente     = 999;
uint8_t lineaIzquierda = 0;
uint8_t lineaCentro    = 0;
uint8_t lineaDerecha   = 0;

// Lectura de distancia ultrasónica
int16_t calcular_distancia(unsigned long duracion) {
  if (duracion == 0) return 999;
  return (int16_t)(duracion / 58); // 58 us/cm ida y vuelta
}

void medir_distancias() {
  unsigned long duracion = 0;
  digitalWrite(trigPinFrente, LOW);  delayMicroseconds(2);
  digitalWrite(trigPinFrente, HIGH); delayMicroseconds(10); 
  digitalWrite(trigPinFrente, LOW);
  
  duracion = pulseIn(echoPinFrente, HIGH, TIMEOUT_US); 
  if (duracion == 0) {
    pinMode(echoPinFrente, OUTPUT); digitalWrite(echoPinFrente, LOW);
    delayMicroseconds(50); pinMode(echoPinFrente, INPUT);
  }
  distFrente = calcular_distancia(duracion);
}

void leer_entorno() {
  lineaIzquierda = digitalRead(linePinIzq);
  lineaCentro    = digitalRead(linePinCen);
  lineaDerecha   = digitalRead(linePinDer);
}

// Envío de telemetría a Raspberry Pi cada 50 ms (20 Hz)
void transmitirTelemetria() {
  static unsigned long ultimaTransmision = 0;
  if (millis() - ultimaTransmision >= 50) {
    ultimaTransmision = millis();

    // Formato de telemetría: TLM:<distancia_cm>,<izq>,<cen>,<der>
    Serial.print(F("TLM:"));
    Serial.print(distFrente);     Serial.print(',');
    Serial.print(lineaIzquierda); Serial.print(',');
    Serial.print(lineaCentro);    Serial.print(',');
    Serial.println(lineaDerecha);
  }
}

void setup() {
  Serial.begin(115200); // UART Hardware hacia Raspberry Pi por USB
  
  pinMode(trigPinFrente, OUTPUT);
  pinMode(echoPinFrente, INPUT);
  
  pinMode(linePinIzq, INPUT);
  pinMode(linePinCen, INPUT);
  pinMode(linePinDer, INPUT);

  Serial.println(F("Arduino Sensores Iniciado (USB 115200 baud)."));
}

void loop() {
  medir_distancias();
  leer_entorno();
  transmitirTelemetria();
}
