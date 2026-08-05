#include <Stepper.h>
#include <Arduino.h>

const int STEPS_PER_REV = 2048;
const int HALF_REV      = 1024; // 180 degrees
const int QUARTER_REV   = 512;  // 90 degrees
const int SWITCH_PIN    = 6;
// Offset to compensate for switch triggering earlier from the left
// Increase this value if still off-center, decrease if overcorrecting
const int SWITCH_OFFSET = 100;

Stepper stepper(STEPS_PER_REV, 2, 4, 3, 5);

bool autoPan      = false;
int  panDirection = -1;
int  currentPos   = 0;

bool switchPressed() {
  return digitalRead(SWITCH_PIN) == LOW;
}

void goHome() {
  Serial.println("Homing...");
  stepper.setSpeed(5);

  // First try going left (90 degrees) — no offset needed
  for (int i = 0; i < QUARTER_REV; i++) {
    if (switchPressed()) {
      Serial.println("Switch found from left.");
      currentPos = 0;
      return;
    }
    stepper.step(-1);
  }

  // Try going right (180 degrees total) — apply offset
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

void printMenu() {
  Serial.println("---------------------------");
  Serial.println("L  - Pan left  90 degrees");
  Serial.println("R  - Pan right 90 degrees");
  Serial.println("A  - Toggle auto-pan");
  Serial.println("H  - Re-home");
  Serial.println("?  - Show this menu");
  Serial.println("---------------------------");
  Serial.print("Auto-pan : ");
  Serial.println(autoPan ? "ON" : "OFF");
  Serial.print("Switch   : ");
  Serial.println(switchPressed() ? "PRESSED" : "open");
}

void setup() {
  Serial.begin(9600);
  pinMode(SWITCH_PIN, INPUT_PULLUP);
  stepper.setSpeed(5);

  Serial.println("Booting - homing...");
  goHome();
  Serial.println("Ready. Send ? for commands.");
  printMenu();
}

void handleSerial() {
  if (!Serial.available()) return;

  char cmd = Serial.read();
  if (cmd == '\n' || cmd == '\r') return;
  cmd = toupper(cmd);

  switch (cmd) {

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

    case 'A':
      autoPan = !autoPan;
      if (autoPan) {
        goHome();
        panDirection = -1;
        Serial.println("Auto-pan ON. Send A to stop.");
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
      Serial.println("Send ? for the command list.");
      break;
  }
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

void loop() {
  handleSerial();
  if (autoPan) runAutoPan();
}