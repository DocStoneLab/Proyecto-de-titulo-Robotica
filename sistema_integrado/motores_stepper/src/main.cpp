#include <Arduino.h>
#include <Stepper.h>
#include <ctype.h>

// ── PUENTES H MOTORES DC (Tracción 4WD) ──
const int M1_A = 2; const int M1_B = 3;
const int M3_A = 4; const int M3_B = 5;
const int M2_A = 6; const int M2_B = 7;
const int M4_A = 8; const int M4_B = 9;

// ── MOTOR PASO A PASO (Paneo Cámara 28BYJ-48) ──
const int STEPS_PER_REV = 2048;
const int HALF_REV      = 1024;
const int QUARTER_REV   = 512;
const int SWITCH_PIN    = A5;
const int SWITCH_OFFSET = 100;

// Ajustes de seguimiento (Tracking)
const int TRACK_SPEED_RPM = 12;  // Velocidad para respuesta rápida
const int MAX_TRACK_STEP  = 40;  // Límite de pasos por comando

Stepper stepper(STEPS_PER_REV, 11, 13, 12, 10);

bool autoPan      = false;
int  panDirection = -1;
int  currentPos   = 0; // Posición actual en pasos (-512 a +512)

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

// ── FUNCIONES DEL STEPPER ──
bool switchPressed() {
  return digitalRead(SWITCH_PIN) == LOW;
}

void goHome() {
  Serial.println(F("Homing..."));
  stepper.setSpeed(5);

  for (int i = 0; i < QUARTER_REV; i++) {
    if (switchPressed()) {
      Serial.println(F("Switch encontrado desde la izquierda."));
      currentPos = 0;
      return;
    }
    stepper.step(-1);
  }

  for (int i = 0; i < HALF_REV; i++) {
    if (switchPressed()) {
      Serial.println(F("Switch encontrado desde la derecha (aplicando offset)."));
      stepper.step(SWITCH_OFFSET);
      currentPos = 0;
      return;
    }
    stepper.step(1);
  }

  Serial.println(F("ADVERTENCIA: Switch no encontrado."));
}

void moveSteps(int steps) {
  stepper.step(steps);
  currentPos += steps;
}

void runAutoPan() {
  stepper.setSpeed(5);
  stepper.step(panDirection);
  currentPos += panDirection;

  if (currentPos <= -QUARTER_REV) {
    currentPos = -QUARTER_REV;
    panDirection = +1;
  }
  if (currentPos >= QUARTER_REV) {
    currentPos = QUARTER_REV;
    panDirection = -1;
  }
}

void trackStep(int steps) {
  autoPan = false;

  if (steps > MAX_TRACK_STEP)  steps = MAX_TRACK_STEP;
  if (steps < -MAX_TRACK_STEP) steps = -MAX_TRACK_STEP;

  int target = currentPos + steps;
  if (target > QUARTER_REV)  steps = QUARTER_REV - currentPos;
  if (target < -QUARTER_REV) steps = -QUARTER_REV - currentPos;

  if (steps != 0) {
    stepper.setSpeed(TRACK_SPEED_RPM);
    moveSteps(steps);
  }
}

// ── DESPACHO DE COMANDOS SIMPLES ──
bool trackingMode = false;

void ejecutarComandoSimple(char c) {
  switch (toupper(c)) {
    case 'W': case 'S': case 'A': case 'D': case ' ':
      procesarComando(c);
      break;

    case 'L':
      autoPan = false;
      moveSteps(-QUARTER_REV);
      break;

    case 'R':
      autoPan = false;
      moveSteps(QUARTER_REV);
      break;

    case 'P':
      autoPan = !autoPan;
      if (autoPan) {
        goHome();
        panDirection = -1;
      } else {
        goHome();
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
  stepper.setSpeed(5);

  Serial.println(F("Iniciando Arduino Motores y Stepper..."));
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
