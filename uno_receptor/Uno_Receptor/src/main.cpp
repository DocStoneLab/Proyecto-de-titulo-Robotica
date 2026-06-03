#include <Arduino.h>
#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>

// 1. Configuración Radiofrecuencia nRF24L01
RF24 radio(4, 5); // CE en pin 4, CSN en pin 5
const byte direccionBase[6] = "00001"; // Debe coincidir exactamente con el transmisor

// 2. Configuración de Alertas (Buzzer de Seguridad)
const int pinBuzzer = 8;
const int UMBRAL_GAS = 400; // Valor analógico de calibración para disparar la alarma

// 3. Estructura de Telemetría (Idéntica al transmisor)
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

void setup() {
  Serial.begin(9600); // Salida al Monitor Serie
  
  pinMode(pinBuzzer, OUTPUT);
  digitalWrite(pinBuzzer, LOW);
  
  // Inicialización del hardware RF
  if (!radio.begin()) {
    Serial.println("Error crítico: Módulo nRF24L01 no detectado en el bus SPI.");
    while (1); // Bloqueo de seguridad si el hardware no responde
  }
  
  // Configuración de la tubería de recepción
  radio.openReadingPipe(0, direccionBase);
  radio.setPALevel(RF24_PA_MIN);
  radio.startListening(); // Conmutar el chip a modo receptor
  
  Serial.println("Estación Base en línea. Escuchando telemetría...");
}

void evaluar_seguridad() {
  // Activación del buzzer físico local según umbrales de concentración
  if (datosRobot.nivelGas > UMBRAL_GAS) {
    digitalWrite(pinBuzzer, HIGH);
    Serial.println("¡ALERTA CRÍTICA: Límite de gas excedido!");
  } else {
    digitalWrite(pinBuzzer, LOW);
  }
}

void loop() {
  // Evalúa el registro FIFO del módulo RF para detectar paquetes entrantes
  if (radio.available()) {
    
    // Mapeo directo del flujo de bytes a la estructura de telemetría
    radio.read(&datosRobot, sizeof(datosRobot));
    
    // Formateo de datos en consola
    Serial.println("\n--- TELEMETRÍA NAVBOT ---");
    Serial.print("Odometría (cm)   -> Izq: "); Serial.print(datosRobot.distIzquierda);
    Serial.print(" | Der: "); Serial.println(datosRobot.distDerecha);
    
    Serial.print("Estado Línea     -> I: "); Serial.print(datosRobot.lineaIzquierda);
    Serial.print(" | C: "); Serial.print(datosRobot.lineaCentro);
    Serial.print(" | D: "); Serial.println(datosRobot.lineaDerecha);
    
    Serial.print("Datos Ambientales-> Humedad: "); Serial.print(datosRobot.nivelHumedad);
    Serial.print(" | Gas MQ-5: "); Serial.println(datosRobot.nivelGas);
    
    // Ejecutar lógica de alarmas locales
    evaluar_seguridad();
  }
}