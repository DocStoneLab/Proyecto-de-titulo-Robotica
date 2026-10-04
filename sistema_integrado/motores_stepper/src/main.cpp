#include <Arduino.h>
#include <Stepper.h>
#include <ctype.h>

// ── PUENTES H MOTORES DC (Tracción 4WD) ──
const int M1_A = 2; const int M1_B = 3;
const int M3_A = 4; const int M3_B = 5;
const int M2_A = 6; const int M2_B = 7;
const int M4_A = 8; const int M4_B = 9;

// ── MOTOR PASO A PASO (Paneo Cámara 28BYJ-48) ──
// Secuencia estándar para ULN2003 en pines 10, 11, 12, 13:
// La librería Stepper requiere el orden IN1, IN3, IN2, IN4:
// IN1=10, IN3=12, IN2=11, IN4=13 -> (10, 12, 11, 13)
// Con esto el motor tiene torque pleno y gira simétricamente en AMBAS direcciones.
const int STEPS_PER_REV   = 2048;
const int HALF_REV        = 1024;
const int QUARTER_REV     = 512;
const int SWITCH_PIN      = A5;
const int SWITCH_OFFSET   = 0;    // El switch está exactamente en 90° (centro frontal)
const int MAX_PAN_STEPS   = 450;  // Límite seguro (~79° a cada lado, 11° antes del tope de 180° y 0°)
const int BUSQUEDA_HOMING = 250;  // Búsqueda suave de homing: ±250 pasos (~44° de ventana)

// Ajustes de seguimiento (Tracking)
const int TRACK_SPEED_RPM = 7;   // Velocidad con torque óptimo para no trabarse con la cámara
const int MAX_TRACK_STEP  = 40;  // Límite de pasos por comando individual

Stepper stepper(STEPS_PER_REV, 10, 12, 11, 13);

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

// ── FUNCIONES DEL STEPPER ──
void apagarBobinas() {
  digitalWrite(10, LOW);
  digitalWrite(11, LOW);
  digitalWrite(12, LOW);
  digitalWrite(13, LOW);
}

bool switchPressed() {
  return digitalRead(SWITCH_PIN) == LOW;
}

void goHome() {
  Serial.println(F("Homing: calibrando camara al frente (switch 90 deg)..."));
  stepper.setSpeed(6);

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
    stepper.step(1);
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
    stepper.step(-1);
    pasos_dados--;
  }

  // 3. Si NO se detectó el switch dentro del rango seguro:
  // Regresar suavemente a la posición de inicio para no quedar desfasado
  Serial.println(F("⚠️ Switch no detectado en rango +-250 pasos. Regresando a posicion inicial."));
  if (pasos_dados != 0) {
    stepper.step(-pasos_dados);
  }
  currentPos = 0;
  Serial.println(F("Posicion actual asumida como centro (0 pasos / 90 deg)."));
  Serial.println(F("POS:0"));
  apagarBobinas();
}

void moveSteps(int steps) {
  stepper.step(steps);
  currentPos += steps;
}

void runAutoPan() {
  stepper.setSpeed(5);
  stepper.step(panDirection);
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
    stepper.setSpeed(TRACK_SPEED_RPM);
    moveSteps(effectiveSteps);
    apagarBobinas();
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
        stepper.setSpeed(TRACK_SPEED_RPM);
        moveSteps(-currentPos);
        apagarBobinas();
      }
      currentPos = 0;
      Serial.println(F("POS:0"));
      break;

    case 'L': { // Ir al extremo izquierdo seguro (-MAX_PAN_STEPS)
      autoPan = false;
      int delta = -MAX_PAN_STEPS - currentPos;
      if (delta != 0) {
        stepper.setSpeed(TRACK_SPEED_RPM);
        moveSteps(delta);
        apagarBobinas();
      }
      Serial.print(F("POS:"));
      Serial.println(currentPos);
      break;
    }

    case 'R': { // Ir al extremo derecho seguro (+MAX_PAN_STEPS)
      autoPan = false;
      int delta = MAX_PAN_STEPS - currentPos;
      if (delta != 0) {
        stepper.setSpeed(TRACK_SPEED_RPM);
        moveSteps(delta);
        apagarBobinas();
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
  pinMode(10, OUTPUT);
  pinMode(11, OUTPUT);
  pinMode(12, OUTPUT);
  pinMode(13, OUTPUT);
  apagarBobinas();

  Serial.println(F("Iniciando Arduino Motores y Stepper..."));
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
