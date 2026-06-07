#include <Arduino.h>
#include <ctype.h>

// PUENTE H 1 (IZQUIERDA)
const int M1_A = 2; const int M1_B = 3;
const int M3_A = 4; const int M3_B = 5;

// PUENTE H 2 (DERECHA)
const int M2_A = 6; const int M2_B = 7;
const int M4_A = 8; const int M4_B = 9;

void setup() {
  const int pinesMotores[] = {M1_A, M1_B, M2_A, M2_B, M3_A, M3_B, M4_A, M4_B};
  for (int i = 0; i < 8; i++) {
    pinMode(pinesMotores[i], OUTPUT);
  }
  Serial.begin(9600); // Lee desde Pin 0 (RX)
}

void actualizarMotores(bool m1a, bool m1b, bool m2a, bool m2b, bool m3a, bool m3b, bool m4a, bool m4b) {
  digitalWrite(M1_A, m1a); digitalWrite(M1_B, m1b);
  digitalWrite(M2_A, m2a); digitalWrite(M2_B, m2b);
  digitalWrite(M3_A, m3a); digitalWrite(M3_B, m3b);
  digitalWrite(M4_A, m4a); digitalWrite(M4_B, m4b);
}

void procesarComando() {
  char tecla = Serial.read();
  switch (tolower(tecla)) {
    case 'w': actualizarMotores(LOW, HIGH, LOW, HIGH, HIGH, LOW, HIGH, LOW); break;
    case 's': actualizarMotores(HIGH, LOW, HIGH, LOW, LOW, HIGH, LOW, HIGH); break;
    case 'a': actualizarMotores(LOW, HIGH, HIGH, LOW, HIGH, LOW, LOW, HIGH); break;
    case 'd': actualizarMotores(HIGH, LOW, LOW, HIGH, LOW, HIGH, HIGH, LOW); break;
    case ' ': actualizarMotores(LOW, LOW, LOW, LOW, LOW, LOW, LOW, LOW); break;
  }
}

void loop() {
  if (Serial.available() > 0) {
    procesarComando();
  }
}