#include <Arduino.h>
#include <SoftwareSerial.h>

SoftwareSerial serialMotores(2, 3); // RX=2, TX=3 (Hacia Motores)

// Pines Sensores
const int trigPinFrente = 9;  const int echoPinFrente = 8;
const int linePinIzq = A0; 
const int linePinCen = A1; 
const int linePinDer = A2;

const unsigned long TIMEOUT_US = 5000; 

// Variables de estado
int16_t distFrente = 999;
uint8_t lineaIzquierda = 0;
uint8_t lineaCentro = 0;
uint8_t lineaDerecha = 0;

int16_t calcular_distancia(unsigned long duracion) {
  if (duracion == 0) return 999;
  // Optimización AVR: División entera (58.3 us/cm ida y vuelta) para evitar FPU por software
  return (int16_t)(duracion / 58);
}

void medir_distancias() {
  unsigned long duracion = 0;

  digitalWrite(trigPinFrente, LOW); delayMicroseconds(2);
  digitalWrite(trigPinFrente, HIGH); delayMicroseconds(10); digitalWrite(trigPinFrente, LOW);
  duracion = pulseIn(echoPinFrente, HIGH, TIMEOUT_US); 
  
  if (duracion == 0) {
    pinMode(echoPinFrente, OUTPUT); digitalWrite(echoPinFrente, LOW);
    delayMicroseconds(50); pinMode(echoPinFrente, INPUT);
  }
  distFrente = calcular_distancia(duracion);
}

void leer_entorno() {
  lineaIzquierda = digitalRead(linePinIzq);
  lineaCentro = digitalRead(linePinCen); 
  lineaDerecha = digitalRead(linePinDer);
}

void evaluar_y_transmitir() {
  char comandoMotor = ' '; 

  // 1. LÓGICA DE EVASIÓN FRONTAL
  if (distFrente < 30) {
    comandoMotor = ' '; 
  } else {
    
    // 2. LÓGICA DE SEGUIMIENTO (Reducción Booleana)
    uint8_t I = lineaIzquierda;
    uint8_t C = lineaCentro; 
    uint8_t D = lineaDerecha;
    
    static char ultimaCurva = 'w';

    if (I && C && D) {
      comandoMotor = 'w'; // Intersección
      ultimaCurva = 'w';
    } 
    else if (!I && C && !D) {
      comandoMotor = 'w'; // Centrado
      ultimaCurva = 'w';
    } 
    // Correcciones Izquierda (Abarca estados con o sin sensor central)
    else if (I && !D) {
      comandoMotor = 'a'; 
      ultimaCurva = 'a'; 
    } 
    // Correcciones Derecha (Abarca estados con o sin sensor central)
    else if (!I && D) {
      comandoMotor = 'd'; 
      ultimaCurva = 'd'; 
    } 
    // PÉRDIDA TOTAL DE LÍNEA (!I && !C && !D)
    else { 
      if (ultimaCurva == 'a' || ultimaCurva == 'd') {
        comandoMotor = ultimaCurva; // Girar hasta reenganchar pista
      } else {
        comandoMotor = ' '; // Freno por salida de pista imprevista
      }
    }
  }

  // 3. ENVÍO UART CONDICIONAL
  static char ultimoComandoMotor = 'x';
  if (comandoMotor != ultimoComandoMotor) {
    ultimoComandoMotor = comandoMotor;
    serialMotores.print(comandoMotor); 
  }
  
  // 4. VOLCADO DE DEPURACIÓN (500ms)
  static unsigned long ultimaTransmision = 0;
  if (millis() - ultimaTransmision >= 500) {
    ultimaTransmision = millis();
    
    Serial.println("=========================================");
    Serial.println("      DEBUG NAVBOT (NODO CEREBRO)        ");
    Serial.println("=========================================");
    Serial.print("ODOMETRÍA   | Frente: "); Serial.print(distFrente); Serial.println(" cm");
    
    Serial.print("INFRARROJOS | I: "); Serial.print(lineaIzquierda); 
    Serial.print(" \t C: "); Serial.print(lineaCentro);
    Serial.print(" \t D: "); Serial.println(lineaDerecha);
    
    Serial.print("ESTADO UART | Cmd hacia motores: [ "); 
    Serial.print(comandoMotor); Serial.println(" ]");
    Serial.println("=========================================\n");
  }
}

void setup() {
  serialMotores.begin(9600);
  Serial.begin(115200); 
  
  pinMode(trigPinFrente, OUTPUT);
  pinMode(echoPinFrente, INPUT);
  pinMode(linePinIzq, INPUT); pinMode(linePinCen, INPUT); pinMode(linePinDer, INPUT);
}

void loop() {
  medir_distancias();
  leer_entorno();
  evaluar_y_transmitir(); 
}