#include <Arduino.h>
#include <ctype.h>

// ── PUENTES H MOTORES DC (Tracción 4WD) ──
const int M1_A = 2; const int M1_B = 3;
const int M3_A = 4; const int M3_B = 5;
const int M2_A = 6; const int M2_B = 7;
const int M4_A = 8; const int M4_B = 9;

// ── MOTOR PASO A PASO (Paneo Cámara 28BYJ-48 con ULN2003) ──
// Pines físicos en Arduino Uno
const int PIN_IN1 = 10;
const int PIN_IN2 = 11;
const int PIN_IN3 = 12;
const int PIN_IN4 = 13;

const int SWITCH_PIN      = A5;
const int MAX_PAN_STEPS   = 450;  // Límite seguro (~79° a cada lado, 11° antes del tope de 180° y 0°)
const int BUSQUEDA_HOMING = 250;  // Búsqueda suave de homing: ±250 pasos (~44° de ventana)
const int MAX_TRACK_STEP  = 40;   // Límite de pasos por comando individual

// Secuencia de 8 medios pasos para 28BYJ-48 (máximo torque, movimiento ultra suave, sin vibración)
const uint8_t halfStepLUT[8] = {
  0b1000, // Paso 0: IN1
  0b1100, // Paso 1: IN1 + IN2
  0b0100, // Paso 2: IN2
  0b0110, // Paso 3: IN2 + IN3
  0b0010, // Paso 4: IN3
  0b0011, // Paso 5: IN3 + IN4
  0b0001, // Paso 6: IN4
  0b1001  // Paso 7: IN4 + IN1
};

int  stepIndex    = 0;
bool autoPan      = false;
int  panDirection = -1;
int  currentPos   = 0; // Posición actual en pasos (-450 a +450, 0 = 90° centro)

String inputBuffer = "";

// ── FUNCIONES DE MOTORES DC ──
void actualizarMotores(bool m1a, bool m1b, bool m2a, bool m2b, bool m3a, bool m3b, bool m4a, bool m4b) {
  digitalWrite(M1_A, m1a); digitalWrite(M1_B, m1b);
  digitalWrite(M2_A, m2a); digitalWrite(M2_B, m2b);
  digitalWrite(M3_A, m3a); digitalWrite(M3_B, m3b);
  digitalWrite(M4_A, m4a); digitalWrite(M4_B, m4b);
}

void procesarComando(char tecla) {
  switch (tolower(tecla)) {
    case 'w': actualizarMotores(LOW, HIGH, LOW, HIGH, HIGH, LOW, HIGH, LOW); break;
    case 's': actualizarMotores(HIGH, LOW, HIGH, LOW, LOW, HIGH, LOW, HIGH); break;
    case 'a': actualizarMotores(LOW, HIGH, HIGH, LOW, HIGH, LOW, LOW, HIGH); break;
    case 'd': actualizarMotores(HIGH, LOW, LOW, HIGH, LOW, HIGH, HIGH, LOW); break;
    case ' ': actualizarMotores(LOW, LOW, LOW, LOW, LOW, LOW, LOW, LOW);     break;
  }
}

// ── CONTROL NATIVO HALF-STEP MOTOR STEPPER 28BYJ-48 ──
void setCoils(uint8_t mask) {
  digitalWrite(PIN_IN1, (mask & 0b1000) ? HIGH : LOW);
  digitalWrite(PIN_IN2, (mask & 0b0100) ? HIGH : LOW);
  digitalWrite(PIN_IN3, (mask & 0b0010) ? HIGH : LOW);
  digitalWrite(PIN_IN4, (mask & 0b0001) ? HIGH : LOW);
}

void apagarBobinas() {
  digitalWrite(PIN_IN1, LOW);
  digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, LOW);
  digitalWrite(PIN_IN4, LOW);
}

bool switchPressed() {
  return digitalRead(SWITCH_PIN) == LOW;
}

// Ejecuta un medio paso individual
void doOneHalfStep(int dir, unsigned int delayMicros) {
  if (dir > 0) {
    stepIndex = (stepIndex + 1) & 0x07;
  } else {
    stepIndex = (stepIndex + 7) & 0x07; // (stepIndex - 1) mod 8
  }
  setCoils(halfStepLUT[stepIndex]);
  delayMicroseconds(delayMicros);
}

// Ejecuta N pasos completos (cada paso son 2 medios pasos) con rampa de aceleración
void stepMotorHalf(int steps) {
  if (steps == 0) return;
  int dir = (steps > 0) ? 1 : -1;
  int totalHalfSteps = abs(steps) * 2;

  for (int i = 0; i < totalHalfSteps; i++) {
    // Rampa suave de arranque: los primeros medios pasos arrancan lento para no perder pasos
    unsigned int d = 1400; // ~1400 µs por medio paso (~10 RPM, torque masivo)
    if (i < 8) {
      d = 2500 - (i * 120);
    }
    doOneHalfStep(dir, d);
  }
  apagarBobinas();
  currentPos += steps;
}

void goHome() {
  Serial.println(F("Homing: calibrando camara al frente (switch 90 deg)..."));

  // Si ya arranca presionado en el centro
  if (switchPressed()) {
    Serial.println(F("Switch ya presionado al inicio (centro 90 deg OK)."));
    currentPos = 0;
    Serial.println(F("POS:0"));
    apagarBobinas();
    return;
  }

  int pasos_dados = 0;

  // 1. Buscar hacia un lado suavemente (hasta BUSQUEDA_HOMING = 250 pasos = ~44°)
  for (int i = 0; i < BUSQUEDA_HOMING; i++) {
    if (switchPressed()) {
      Serial.println(F("Switch encontrado (calibrado en centro 90 deg)."));
      currentPos = 0;
      Serial.println(F("POS:0"));
      apagarBobinas();
      return;
    }
    doOneHalfStep(1, 1600);
    doOneHalfStep(1, 1600);
    pasos_dados++;
  }

  // 2. Buscar hacia el lado contrario (hasta BUSQUEDA_HOMING * 2 = 500 pasos = ~88° totales)
  for (int i = 0; i < (BUSQUEDA_HOMING * 2); i++) {
    if (switchPressed()) {
      Serial.println(F("Switch encontrado en barrido opuesto (calibrado en centro 90 deg)."));
      currentPos = 0;
      Serial.println(F("POS:0"));
      apagarBobinas();
      return;
    }
    doOneHalfStep(-1, 1600);
    doOneHalfStep(-1, 1600);
    pasos_dados--;
  }

  // 3. Si NO se detectó el switch dentro del rango seguro: regresar al inicio
  Serial.println(F("⚠️ Switch no detectado en rango +-250 pasos. Regresando a posicion inicial."));
  if (pasos_dados > 0) {
    for (int i = 0; i < pasos_dados; i++) {
      doOneHalfStep(-1, 1600);
      doOneHalfStep(-1, 1600);
    }
  } else if (pasos_dados < 0) {
    for (int i = 0; i < -pasos_dados; i++) {
      doOneHalfStep(1, 1600);
      doOneHalfStep(1, 1600);
    }
  }
  currentPos = 0;
  Serial.println(F("Posicion actual asumida como centro (0 pasos / 90 deg)."));
  Serial.println(F("POS:0"));
  apagarBobinas();
}

void runAutoPan() {
  doOneHalfStep(panDirection, 1800);
  doOneHalfStep(panDirection, 1800);
  currentPos += panDirection;

  if (currentPos <= -MAX_PAN_STEPS) {
    currentPos = -MAX_PAN_STEPS;
    panDirection = +1;
  }
  if (currentPos >= MAX_PAN_STEPS) {
    currentPos = MAX_PAN_STEPS;
    panDirection = -1;
  }
}

void trackStep(int steps) {
  autoPan = false;

  // Limitar incremento individual
  if (steps > MAX_TRACK_STEP)  steps = MAX_TRACK_STEP;
  if (steps < -MAX_TRACK_STEP) steps = -MAX_TRACK_STEP;

  // Clampear para no superar nunca el límite físico seguro [-MAX_PAN_STEPS, MAX_PAN_STEPS]
  int targetPos = constrain(currentPos + steps, -MAX_PAN_STEPS, MAX_PAN_STEPS);
  int effectiveSteps = targetPos - currentPos;

  if (effectiveSteps != 0) {
    stepMotorHalf(effectiveSteps);
    Serial.print(F("STEP:"));
    Serial.print(effectiveSteps);
    Serial.print(F(" POS:"));
    Serial.println(currentPos);
  } else {
    Serial.print(F("LIMITE POS:"));
    Serial.println(currentPos);
  }
}

// ── DESPACHO DE COMANDOS SIMPLES ──
bool trackingMode = false;

void ejecutarComandoSimple(char c) {
  switch (toupper(c)) {
    case 'W': case 'S': case 'A': case 'D': case ' ':
      procesarComando(c);
      break;

    case '<': // Girar 30 pasos a la izquierda
      trackStep(-30);
      break;

    case '>': // Girar 30 pasos a la derecha
      trackStep(30);
      break;

    case 'C': // Centrar cámara al frente (0)
      autoPan = false;
      if (currentPos != 0) {
        stepMotorHalf(-currentPos);
      }
      currentPos = 0;
      Serial.println(F("POS:0"));
      break;

    case 'L': { // Ir al extremo izquierdo seguro (-MAX_PAN_STEPS)
      autoPan = false;
      int delta = -MAX_PAN_STEPS - currentPos;
      if (delta != 0) {
        stepMotorHalf(delta);
      }
      Serial.print(F("POS:"));
      Serial.println(currentPos);
      break;
    }

    case 'R': { // Ir al extremo derecho seguro (+MAX_PAN_STEPS)
      autoPan = false;
      int delta = MAX_PAN_STEPS - currentPos;
      if (delta != 0) {
        stepMotorHalf(delta);
      }
      Serial.print(F("POS:"));
      Serial.println(currentPos);
      break;
    }

    case 'P':
      autoPan = !autoPan;
      if (autoPan) {
        panDirection = -1;
      } else {
        apagarBobinas();
      }
      break;

    case 'H':
      autoPan = false;
      goHome();
      break;

    case 'Q': // Query de posición actual
      Serial.print(F("POS:"));
      Serial.println(currentPos);
      break;

    case 'K': // Diagnóstico de switch
      Serial.print(F("SWITCH:"));
      Serial.println(digitalRead(SWITCH_PIN) == LOW ? F("PRESIONADO_LOW") : F("LIBRE_HIGH"));
      break;

    case 'Z': // Diagnóstico secuencial de bobinas / LEDs del ULN2003
      Serial.println(F("TEST_COILS: Probando LEDs A->B->C->D..."));
      apagarBobinas();
      digitalWrite(PIN_IN1, HIGH); delay(400); digitalWrite(PIN_IN1, LOW);
      digitalWrite(PIN_IN2, HIGH); delay(400); digitalWrite(PIN_IN2, LOW);
      digitalWrite(PIN_IN3, HIGH); delay(400); digitalWrite(PIN_IN3, LOW);
      digitalWrite(PIN_IN4, HIGH); delay(400); digitalWrite(PIN_IN4, LOW);
      apagarBobinas();
      Serial.println(F("TEST_COILS_FIN"));
      break;

    case '\n': case '\r':
      break;

    default:
      break;
  }
}

// ── SETUP ──
void setup() {
  Serial.begin(9600); // UART Hardware hacia Raspberry Pi (USB)

  const int pinesMotores[] = {M1_A, M1_B, M2_A, M2_B, M3_A, M3_B, M4_A, M4_B};
  for (int i = 0; i < 8; i++) pinMode(pinesMotores[i], OUTPUT);

  pinMode(SWITCH_PIN, INPUT_PULLUP);
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
  apagarBobinas();

  Serial.println(F("Iniciando Arduino Motores y Stepper Half-Step..."));
  Serial.print(F("Estado inicial Switch A5: "));
  Serial.println(digitalRead(SWITCH_PIN) == LOW ? F("PRESIONADO (LOW)") : F("LIBRE (HIGH)"));

  goHome();
  Serial.println(F("Listo para recibir comandos desde Raspberry Pi (USB)."));
}

// ── LOOP ──
void loop() {
  // Lectura directa desde Raspberry Pi por USB Serial
  while (Serial.available()) {
    char c = Serial.read();

    if (trackingMode) {
      if (c == '\n' || c == '\r') {
        if (inputBuffer.length() > 0) {
          trackStep(inputBuffer.toInt());
          inputBuffer = "";
        }
        trackingMode = false;
      } else {
        inputBuffer += c;
      }
      continue;
    }

    if (toupper(c) == 'T') {
      trackingMode = true;
      inputBuffer = "";
      continue;
    }

    ejecutarComandoSimple(c);
  }

  // Paneo automático si está activo
  if (autoPan) runAutoPan();
}
