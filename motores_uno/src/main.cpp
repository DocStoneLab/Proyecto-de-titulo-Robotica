#include <Arduino.h>
#include <ctype.h>

// --- MAPEO DE LOS 8 PINES DIGITALES DIRECTOS ---
// PUENTE H 1 - LADO IZQUIERDO
const int M1_A = 2;  // Motor 1 (Delantero Izquierdo) -> IN1
const int M1_B = 3;  // Motor 1 (Delantero Izquierdo) -> IN2
const int M3_A = 4;  // Motor 3 (Trasero Izquierdo)   -> IN3
const int M3_B = 5;  // Motor 3 (Trasero Izquierdo)   -> IN4

// PUENTE H 2 - LADO DERECHO
const int M2_A = 6;  // Motor 2 (Delantero Derecho)   -> IN1
const int M2_B = 7;  // Motor 2 (Delantero Derecho)   -> IN2
const int M4_A = 8;  // Motor 4 (Trasero Derecho)     -> IN3
const int M4_B = 9;  // Motor 4 (Trasero Derecho)     -> IN4

void setup()
{
  // Inicialización masiva de pines como salidas
  const int pinesMotores[] = {M1_A, M1_B, M2_A, M2_B, M3_A, M3_B, M4_A, M4_B};
  for (int i = 0; i < 8; i++)
  {
    pinMode(pinesMotores[i], OUTPUT);
  }

  Serial.begin(9600);
  Serial.println("Controlador de Tracción (8 Pines Dedicados) Listo.");
}

// Función maestra para escribir el estado digital de los 8 canales simultáneamente
void actualizarMotores(bool m1a, bool m1b, bool m2a, bool m2b, bool m3a, bool m3b, bool m4a, bool m4b)
{
  digitalWrite(M1_A, m1a); digitalWrite(M1_B, m1b);
  digitalWrite(M2_A, m2a); digitalWrite(M2_B, m2b);
  digitalWrite(M3_A, m3a); digitalWrite(M3_B, m3b);
  digitalWrite(M4_A, m4a); digitalWrite(M4_B, m4b);
}

void ControlTeclado()
{
  char tecla = Serial.read();

  switch (tolower(tecla))
  {
    case 'w': // AVANZAR (Todos los motores giran adelante)
      actualizarMotores(LOW, HIGH, LOW, HIGH, HIGH, LOW, HIGH, LOW);
      Serial.println("Estado: Avanzar");
      break;

    case 's': // RETROCEDER (Todos los motores giran atrás)
      actualizarMotores(HIGH, LOW, HIGH, LOW, LOW, HIGH, LOW, HIGH);
      Serial.println("Estado: Retroceder");
      break;

    case 'a': // ROTAR IZQUIERDA (Bloque izquierdo atrás, Bloque derecho adelante)
      actualizarMotores(LOW, HIGH, HIGH, LOW, HIGH, LOW, LOW, HIGH);
      Serial.println("Estado: Rotar Izquierda en el eje");
      break;

    case 'd': // ROTAR DERECHA (Bloque izquierdo adelante, Bloque derecho atrás)
      actualizarMotores(HIGH, LOW, LOW, HIGH, LOW, HIGH, HIGH, LOW);
      Serial.println("Estado: Rotar Derecha en el eje");
      break;

    case ' ': // DETENER (Freno por software poniendo todas las líneas a masa)
      actualizarMotores(LOW, LOW, LOW, LOW, LOW, LOW, LOW, LOW);
      Serial.println("Estado: DETENIDO");
      break;
  }
}

void loop()
{
  if (Serial.available() > 0)
  {
    ControlTeclado();
  }
} 