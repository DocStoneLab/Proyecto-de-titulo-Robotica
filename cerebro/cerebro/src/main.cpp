#include <Arduino.h>
// #include <SoftwareSerial.h> // COMENTADO PARA PRUEBAS
// #include <SPI.h>            // COMENTADO PARA PRUEBAS
// #include <nRF24L01.h>       // COMENTADO PARA PRUEBAS
// #include <RF24.h>           // COMENTADO PARA PRUEBAS

// 1. Configuración de Comunicación
// SoftwareSerial serialMotores(2, 3); // COMENTADO PARA PRUEBAS
// RF24 radio(4, 5);                   // COMENTADO PARA PRUEBAS
// const byte direccionBase[6] = "00001"; // COMENTADO PARA PRUEBAS

// 2. Asignación de Pines
const int trigPin1 = 9;
const int echoPin1 = 8;  // Mantenemos el pin 8 para evitar conflicto futuro
const int trigPin2 = 7;
const int echoPin2 = 6;  

const int linePinIzq = A0;
const int linePinCen = A1;
const int linePinDer = A2;

// const int pinGasMQ5 = A3;  // COMENTADO PARA PRUEBAS
const int pinHumedad = A4; // COMENTADO PARA PRUEBAS

const unsigned long TIMEOUT_US = 3000000;

// 3. Estructura de Telemetría
struct __attribute__((packed)) Telemetria {
  int16_t distIzquierda;
  int16_t distDerecha;
  uint8_t lineaIzquierda;
  uint8_t lineaCentro;
  uint8_t lineaDerecha;
  // int16_t nivelGas;      // COMENTADO PARA PRUEBAS
  int16_t nivelHumedad;  // COMENTADO PARA PRUEBAS
};
Telemetria datosRobot;

// Función para calcular distancia
int16_t calcular_distancia(unsigned long duracion) {
  if (duracion == 0) return 999;
  return (duracion * 0.034) / 2;
}

// Lectura acústica bloqueante optimizada por Timeout
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

// Actualización de estado del entorno
void leer_entorno() {
  datosRobot.lineaIzquierda = digitalRead(linePinIzq);
  datosRobot.lineaCentro = digitalRead(linePinCen);
  datosRobot.lineaDerecha = digitalRead(linePinDer);
  
  // COMENTADO PARA PRUEBAS
  // datosRobot.nivelGas = analogRead(pinGasMQ5);
  datosRobot.nivelHumedad = analogRead(pinHumedad);
}

// Lógica central y transmisión de datos
void evaluar_y_transmitir() {
  char comandoMotor = 'S'; 
  
  // A. Evasión de colisiones
  if (datosRobot.distIzquierda < 30 || datosRobot.distDerecha < 30) {
    comandoMotor = 'S'; // Stop
  } else {
    // B. Odometría de 3 Sensores
    uint8_t I = datosRobot.lineaIzquierda;
    uint8_t C = datosRobot.lineaCentro;
    uint8_t D = datosRobot.lineaDerecha;

    if (I && C && D) {
      comandoMotor = 'X'; 
    } else if (!I && C && !D) {
      comandoMotor = 'A'; 
    } else if (I && !D) {
      comandoMotor = 'I'; 
    } else if (!I && D) {
      comandoMotor = 'D'; 
    } else {
      comandoMotor = 'S'; 
    }
  }

  // C. Transmisión Serial (COMENTADO PARA PRUEBAS)
  // serialMotores.println(comandoMotor);
  
  // D. Transmisión RF (COMENTADO PARA PRUEBAS)
  // radio.write(&datosRobot, sizeof(datosRobot));

  // E. Monitoreo por Serial Hardware para el Test (PC)
  static unsigned long ultimoPrint = 0;
  if (millis() - ultimoPrint >= 500) { 
    ultimoPrint = millis();
    Serial.print("[TEST SENSORES] Dist: Izq="); Serial.print(datosRobot.distIzquierda);
    Serial.print("cm, Der="); Serial.print(datosRobot.distDerecha);
    Serial.print("cm | Linea (Izq-Cen-Der): ");
    Serial.print(datosRobot.lineaIzquierda ? "1" : "0");
    Serial.print(datosRobot.lineaCentro ? "1" : "0");
    Serial.print(datosRobot.lineaDerecha ? "1" : "0");
    
    // COMENTADO PARA PRUEBAS
    // Serial.print(" | Gas: "); Serial.print(datosRobot.nivelGas);
    Serial.print(" | Hum: "); Serial.print(datosRobot.nivelHumedad);
    
    Serial.print(" | Cmd Calculado: "); Serial.println(comandoMotor);
  }
}

void setup() {
  Serial.begin(115200); 
  // serialMotores.begin(9600); // COMENTADO PARA PRUEBAS
  
  pinMode(trigPin1, OUTPUT); pinMode(trigPin2, OUTPUT);
  pinMode(echoPin1, INPUT); pinMode(echoPin2, INPUT);
  
  pinMode(linePinIzq, INPUT);
  pinMode(linePinCen, INPUT);
  pinMode(linePinDer, INPUT);
  
  // Configuración RF (COMENTADO PARA PRUEBAS)
  /*
  if (radio.begin()) {
    radio.openWritingPipe(direccionBase);
    radio.setPALevel(RF24_PA_MIN);
    radio.setDataRate(RF24_1MBPS); 
    radio.stopListening(); 
  }
  */
  
  Serial.println("--- Modo Prueba: Sensores Ultrasónicos y de Línea Inicializados ---");
}

void loop() {
  medir_distancias();
  leer_entorno();
  evaluar_y_transmitir();
  delay(10); 
}