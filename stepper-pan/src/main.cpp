#include <Arduino.h>
#include <Stepper.h>
#include <ctype.h>

// ── DC MOTORS (H-BRIDGE) ──
const int M1_A = 2; const int M1_B = 3;
const int M3_A = 4; const int M3_B = 5;
const int M2_A = 6; const int M2_B = 7;
const int M4_A = 8; const int M4_B = 9;

// ── STEPPER MOTOR ──
const int STEPS_PER_REV = 2048;
const int HALF_REV      = 1024;
const int QUARTER_REV   = 512;
const int SWITCH_PIN    = A5;
const int SWITCH_OFFSET = 100;

Stepper stepper(STEPS_PER_REV, 11, 13, 12, 10);

bool autoPan      = false;
int  panDirection = -1;
int  currentPos   = 0;

// ── DC MOTOR FUNCTIONS ──
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

// ── STEPPER FUNCTIONS ──
bool switchPressed() {
  return digitalRead(SWITCH_PIN) == LOW;
}

void goHome() {
  Serial.println("Homing...");
  stepper.setSpeed(5);

  for (int i = 0; i < QUARTER_REV; i++) {
    if (switchPressed()) {
      Serial.println("Switch found from left.");
      currentPos = 0;
      return;
    }
    stepper.step(-1);
  }

  for (int i = 0; i < HALF_REV; i++) {
    if (switchPressed()) {
      Serial.println("Switch found from right — applying offset.");
      stepper.step(SWITCH_OFFSET);
      currentPos = 0;
      return;
    }
    stepper.step(1);
  }

  Serial.println("WARNING: switch not found. Check wiring.");
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
    Serial.println("Auto: reached left - going right");
  }

  if (currentPos >= QUARTER_REV) {
    currentPos = QUARTER_REV;
    panDirection = -1;
    Serial.println("Auto: reached right - going left");
  }
}

void printMenu() {
  Serial.println("---------------------------");
  Serial.println("W/S/A/D - move robot");
  Serial.println("SPACE   - stop robot");
  Serial.println("L       - pan left  90°");
  Serial.println("R       - pan right 90°");
  Serial.println("P       - toggle auto-pan");
  Serial.println("H       - re-home");
  Serial.println("?       - show this menu");
  Serial.println("---------------------------");
  Serial.print("Auto-pan : ");
  Serial.println(autoPan ? "ON" : "OFF");
  Serial.print("Switch   : ");
  Serial.println(switchPressed() ? "PRESSED" : "open");
}

// ── SETUP ──
void setup() {
  Serial.begin(9600);

  // DC motor pins
  const int pinesMotores[] = {M1_A, M1_B, M2_A, M2_B, M3_A, M3_B, M4_A, M4_B};
  for (int i = 0; i < 8; i++) pinMode(pinesMotores[i], OUTPUT);

  // Stepper + switch
  pinMode(SWITCH_PIN, INPUT_PULLUP);
  stepper.setSpeed(5);

  Serial.println("Booting - homing...");
  goHome();
  Serial.println("Ready. Send ? for commands.");
  printMenu();
}

// ── LOOP ──
void loop() {
  if (Serial.available()) {
    char cmd = Serial.read();
    if (cmd == '\n' || cmd == '\r') return;

    switch (toupper(cmd)) {

      // DC motor commands (lowercase handled by procesarComando)
      case 'W': case 'S': case 'A': case 'D': case ' ':
        procesarComando(cmd);
        break;

      // Stepper commands
      case 'L':
        autoPan = false;
        Serial.println("Panning left 90 degrees...");
        moveSteps(-QUARTER_REV);
        Serial.print("Done. Position: ");
        Serial.print((currentPos * 360) / STEPS_PER_REV);
        Serial.println(" degrees");
        break;

      case 'R':
        autoPan = false;
        Serial.println("Panning right 90 degrees...");
        moveSteps(QUARTER_REV);
        Serial.print("Done. Position: ");
        Serial.print((currentPos * 360) / STEPS_PER_REV);
        Serial.println(" degrees");
        break;

      case 'P':
        autoPan = !autoPan;
        if (autoPan) {
          goHome();
          panDirection = -1;
          Serial.println("Auto-pan ON. Send P to stop.");
        } else {
          Serial.println("Auto-pan OFF. Returning to center...");
          goHome();
          Serial.println("Done.");
        }
        break;

      case 'H':
        autoPan = false;
        goHome();
        break;

      case '?':
        printMenu();
        break;

      default:
        Serial.print("Unknown command: ");
        Serial.println(cmd);
        break;
    }
  }

  if (autoPan) runAutoPan();
}