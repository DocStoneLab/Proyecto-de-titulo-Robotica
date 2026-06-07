#include <Arduino.h>
#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>

RF24 radio(4, 5); 
const byte direccionBase[6] = "00001"; 

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
  
  if (!radio.begin()) {
    Serial.println("Error RF");
    while (1); 
  }
  
  radio.openReadingPipe(0, direccionBase);
  radio.setPALevel(RF24_PA_MIN);
  radio.setDataRate(RF24_1MBPS);
  radio.startListening(); 
  Serial.println("Estacion Base Lista.");
}

void loop() {
  if (radio.available()) {
    radio.read(&datosRobot, sizeof(datosRobot));
    
    Serial.print("Dist[I-D]: "); Serial.print(datosRobot.distIzquierda); Serial.print("-"); Serial.print(datosRobot.distDerecha);
    Serial.print(" | Gas: "); Serial.print(datosRobot.nivelGas);
    Serial.print(" | Hum: "); Serial.println(datosRobot.nivelHumedad);

    if (datosRobot.nivelGas > UMBRAL_GAS) {
      digitalWrite(pinBuzzer, HIGH);
    } else {
      digitalWrite(pinBuzzer, LOW);
    }
  }
}