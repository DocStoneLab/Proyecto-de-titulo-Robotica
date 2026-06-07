#include <Arduino.h>
#include <SoftwareSerial.h>
#include <SPI.h>
#include <nRF24L01.h>
#include <RF24.h>

SoftwareSerial serialMotores(2, 3); // RX=2, TX=3 (Hacia Motores)
RF24 radio(4, 5);                   // CE=4, CSN=5 (Hacia Estación Base)
const byte direccionBase[6] = "00001";

// Asignación de Pines
const int trigPin1 = 9;
const int echoPin1 = 8;
const int trigPin2 = 7;
const int echoPin2 = 6;  

const int linePinIzq = A0;
const int linePinCen = A1;
const int linePinDer = A2;

const int pinGasMQ5 = A3;
const int pinHumedad = A4;

const unsigned long TIMEOUT_US = 3000; // ~50cm max

// Estructura empaquetada para RF
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
  
  digitalWrite(trigPin1, LOW); delayMicroseconds(2);
  digitalWrite(trigPin1, HIGH); delayMicroseconds(10); digitalWrite(trigPin1, LOW);
  dur1 = pulseIn(echoPin1, HIGH, TIMEOUT_US); 
  
  digitalWrite(trigPin2, LOW); delayMicroseconds(2);
  digitalWrite(trigPin2, HIGH); delayMicroseconds(10); digitalWrite(trigPin2, LOW);
  dur2 = pulseIn(echoPin2, HIGH, TIMEOUT_US);

  datosRobot.distIzquierda = calcular_distancia(dur1);
  datosRobot.distDerecha = calcular_distancia(dur2);
}

void leer_entorno() {
  datosRobot.lineaIzquierda = digitalRead(linePinIzq);
  datosRobot.lineaCentro = digitalRead(linePinCen);
  datosRobot.lineaDerecha = digitalRead(linePinDer);
  datosRobot.nivelGas = analogRead(pinGasMQ5);
  datosRobot.nivelHumedad = analogRead(pinHumedad);
}

void evaluar_y_transmitir() {
  //========================Eliminar
  // INICIO DE DEBUG POR TECLADO (PC)
  if (Serial.available() > 0) {
    char tecla = Serial.read();
    
    // Ignorar caracteres de salto de línea (\n) o retorno de carro (\r) del Monitor Serie
    if (tecla != '\n' && tecla != '\r') {
      char comandoManual = tolower(tecla); // Forzar a minúscula para compatibilidad
      
      // Enviar instrucción al Arduino Esclavo
      serialMotores.println(comandoManual);
      
      // Confirmación visual en la PC
      Serial.print("[DEBUG TECLADO] Instruccion enviada al puente H: [");
      Serial.print(comandoManual);
      Serial.println("]");
    }
  }
  //===========================Eliminar
  /*
  char comandoMotor = ' '; 
  
  // A. Seguridad Activa (Ultrasonido)
  if (datosRobot.distIzquierda < 30 || datosRobot.distDerecha < 30) {
    comandoMotor = ' '; // Stop
  } else {
    // B. Odometría (Infrarrojo)
    uint8_t I = datosRobot.lineaIzquierda;
    uint8_t C = datosRobot.lineaCentro;
    uint8_t D = datosRobot.lineaDerecha;

    if (I && C && D) {
      comandoMotor = ' '; // Intersección (Stop preventivo)
    } else if (!I && C && !D) {
      comandoMotor = 'w'; // Avanzar
    } else if (I && !D) {
      comandoMotor = 'a'; // Girar Izquierda
    } else if (!I && D) {
      comandoMotor = 'd'; // Girar Derecha
    } else {
      comandoMotor = ' '; // Fuera de línea
    }
  }

  // C. Transmitir UART a Motores
  serialMotores.println(comandoMotor);
  
  // D. Transmitir SPI/RF a Estación Base
  radio.write(&datosRobot, sizeof(datosRobot));
*/
}

void setup() {
  //Inicializacion del puerto Serie por Hardware (Para debug)
  Serial.begin(115200);

  //Inicializacion del puerto Serie por software (Hacia Arduino Morotes)
  serialMotores.begin(9600);
  
  pinMode(trigPin1, OUTPUT); pinMode(trigPin2, OUTPUT);
  pinMode(echoPin1, INPUT);  pinMode(echoPin2, INPUT);
  pinMode(linePinIzq, INPUT); pinMode(linePinCen, INPUT); pinMode(linePinDer, INPUT);
  
  if (radio.begin()) {
    radio.openWritingPipe(direccionBase);
    radio.setPALevel(RF24_PA_MIN);
    radio.setDataRate(RF24_1MBPS); 
    radio.stopListening(); 
  }

  Serial.println("Arduino Maestro Iniciado. Iniciando telemetria...");
}

void loop() {
  medir_distancias();
  leer_entorno();
  evaluar_y_transmitir();
  delay(10); 
}