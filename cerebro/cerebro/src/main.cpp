#include <Arduino.h>
#include <SoftwareSerial.h>
#include <RH_ASK.h> 
#include <SPI.h>    

SoftwareSerial serialMotores(2, 3); // RX=2, TX=3 (Hacia Motores)

// Configuración RadioHead: 2000 bps, RX=11(NC), TX=12, PTT=10
RH_ASK radio(2000, 11, 12, 10);

// Pines Sensores
const int trigPinFrente = 9;  const int echoPinFrente = 8;
const int trigPinAtras = 7;   const int echoPinAtras = 6;  
const int linePinIzq = A0; 
const int linePinCen = A1; 
const int linePinDer = A2;
const int pinGasMQ5 = A3;
const int pinHumedad = A4;

const unsigned long TIMEOUT_US = 5000; 

struct __attribute__((packed)) Telemetria {
  int16_t distFrente;
  int16_t distAtras;
  uint8_t lineaIzquierda;
  uint8_t lineaCentro;
  uint8_t lineaDerecha;
  int16_t nivelGas;
  int16_t nivelHumedad;
};
Telemetria datosRobot;

int16_t calcular_distancia(unsigned long duracion) {
  if (duracion == 0) return 999;
  // Optimización AVR: División entera (58.3 us/cm ida y vuelta) para evitar FPU por software
  return (int16_t)(duracion / 58);
}

void medir_distancias() {
  static bool turnoFrente = true; 
  unsigned long duracion = 0;

  if (turnoFrente) {
    digitalWrite(trigPinFrente, LOW); delayMicroseconds(2);
    digitalWrite(trigPinFrente, HIGH); delayMicroseconds(10); digitalWrite(trigPinFrente, LOW);
    duracion = pulseIn(echoPinFrente, HIGH, TIMEOUT_US); 
    
    if (duracion == 0) {
      pinMode(echoPinFrente, OUTPUT); digitalWrite(echoPinFrente, LOW);
      delayMicroseconds(50); pinMode(echoPinFrente, INPUT);
    }
    datosRobot.distFrente = calcular_distancia(duracion);
  } else {
    digitalWrite(trigPinAtras, LOW); delayMicroseconds(2);
    digitalWrite(trigPinAtras, HIGH); delayMicroseconds(10); digitalWrite(trigPinAtras, LOW);
    duracion = pulseIn(echoPinAtras, HIGH, TIMEOUT_US);

    if (duracion == 0) {
      pinMode(echoPinAtras, OUTPUT); digitalWrite(echoPinAtras, LOW);
      delayMicroseconds(50); pinMode(echoPinAtras, INPUT);
    }
    datosRobot.distAtras = calcular_distancia(duracion);
  }

  turnoFrente = !turnoFrente; 
}

void leer_entorno() {
  datosRobot.lineaIzquierda = digitalRead(linePinIzq);
  datosRobot.lineaCentro = digitalRead(linePinCen); 
  datosRobot.lineaDerecha = digitalRead(linePinDer);
  datosRobot.nivelGas = analogRead(pinGasMQ5);
  datosRobot.nivelHumedad = analogRead(pinHumedad);
}

void evaluar_y_transmitir() {
  char comandoMotor = ' '; 

  // 1. LÓGICA DE EVASIÓN FRONTAL
  if (datosRobot.distFrente < 30) {
    comandoMotor = ' '; 
  } else {
    
    // 2. LÓGICA DE SEGUIMIENTO (Reducción Booleana)
    uint8_t I = datosRobot.lineaIzquierda;
    uint8_t C = datosRobot.lineaCentro; 
    uint8_t D = datosRobot.lineaDerecha;
    
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
  
  // 4. TRANSMISIÓN RF ASÍNCRONA Y VOLCADO DE DEPURACIÓN (500ms)
  static unsigned long ultimaTransmision = 0;
  if (millis() - ultimaTransmision >= 500) {
    ultimaTransmision = millis();
    
    // Envio no bloqueante: la interrupción del Timer 1 maneja la modulación en segundo plano
    radio.send((uint8_t *)&datosRobot, sizeof(datosRobot));
    
    Serial.println("=========================================");
    Serial.println("      DEBUG NAVBOT (NODO CEREBRO)        ");
    Serial.println("=========================================");
    Serial.print("ODOMETRÍA   | Frente: "); Serial.print(datosRobot.distFrente); 
    Serial.print(" cm \t Atras: "); Serial.print(datosRobot.distAtras); Serial.println(" cm");
    
    Serial.print("INFRARROJOS | I: "); Serial.print(datosRobot.lineaIzquierda); 
    Serial.print(" \t C: "); Serial.print(datosRobot.lineaCentro);
    Serial.print(" \t D: "); Serial.println(datosRobot.lineaDerecha);
    
    Serial.print("ESTADO UART | Cmd hacia motores: [ "); 
    Serial.print(comandoMotor); Serial.println(" ]");
    Serial.println("=========================================\n");
  }
}

void setup() {
  serialMotores.begin(9600);
  Serial.begin(115200); 
  
  pinMode(trigPinFrente, OUTPUT); pinMode(trigPinAtras, OUTPUT);
  pinMode(echoPinFrente, INPUT);  pinMode(echoPinAtras, INPUT);
  pinMode(linePinIzq, INPUT); pinMode(linePinCen, INPUT); pinMode(linePinDer, INPUT);
  
  if (!radio.init()) {
    Serial.println("Error critico: Modulo RF no inicializado");
  }
}

void loop() {
  medir_distancias();
  leer_entorno();
  evaluar_y_transmitir(); 
}