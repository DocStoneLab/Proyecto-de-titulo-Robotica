#include <Arduino.h>
#include <RH_ASK.h>
#include <SPI.h>

// Configuración RadioHead: Velocidad 2000 bps, RX pin=11, TX pin(no usado)=12, PTT pin (no usado, fijado a pin 10 libre)=10
RH_ASK radio(2000, 11, 12, 10);

const int pinBuzzer = 8;
const int UMBRAL_GAS = 400; 

// Estructura idéntica al Maestro
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

void setup() {
  Serial.begin(9600); 
  pinMode(pinBuzzer, OUTPUT);
  digitalWrite(pinBuzzer, LOW);
  
  if (!radio.init()) {
    Serial.println("Fallo crítico: Receptor 433MHz no inicializado.");
    while(1);
  }
  Serial.println("Estacion Base 433MHz Lista. Esperando datos...");
}

void loop() {
  uint8_t longitudBuffer = sizeof(datosRobot);
  
  // Si se recibe un paquete y la longitud coincide con nuestra estructura
  if (radio.recv((uint8_t*)&datosRobot, &longitudBuffer)) {
    if (longitudBuffer == sizeof(datosRobot)) {
      
      Serial.println("\n--- TELEMETRÍA RECIBIDA ---");
      Serial.print("Dist[I-D]: "); Serial.print(datosRobot.distIzquierda); Serial.print("-"); Serial.print(datosRobot.distDerecha);
      Serial.print(" | Líneas[I-C-D]: "); 
      Serial.print(datosRobot.lineaIzquierda); Serial.print("-");
      Serial.print(datosRobot.lineaCentro); Serial.print("-");
      Serial.print(datosRobot.lineaDerecha);
      Serial.print(" | Gas: "); Serial.print(datosRobot.nivelGas);
      Serial.print(" | Hum: "); Serial.println(datosRobot.nivelHumedad);

      // Evaluación del sensor
      if (datosRobot.nivelGas > UMBRAL_GAS) {
        digitalWrite(pinBuzzer, HIGH);
        Serial.println("¡ALERTA CRÍTICA: GAS DETECTADO!");
      } else {
        digitalWrite(pinBuzzer, LOW);
      }
      
    }
  }
}