#include <Arduino.h>
#include <SoftwareSerial.h>

SoftwareSerial serialMotores(2, 3); // RX=2, TX=3 (Hacia Arduino de Motores)

// ==========================================
// PINES DE SENSORES (Arduino Cerebro)
// ==========================================
const int trigPinFrente = 9;  
const int echoPinFrente = 8;
const int linePinIzq    = A0; 
const int linePinCen    = A1; 
const int linePinDer    = A2;

const unsigned long TIMEOUT_US = 6000; // ~100 cm de alcance maximo en ultrasonido

// ==========================================
// PARÁMETROS CALIBRABLES DE NAVEGACIÓN
// ==========================================
const int16_t       DIST_OBJETIVO_CM       = 10;   // Frenar a 10 cm del objetivo
const unsigned long TIEMPO_GIRO_DEFAULT_MS = 450;  // Duración estimada para girar hacia el ángulo del objeto
const unsigned long TIMEOUT_AVANCE_MS      = 6000; // Límite de seguridad para el avance frontal
const unsigned long MARGEN_SEGURIDAD_REV_MS= 2000; // Margen extra sobre el tiempo de avance para reversa

// ==========================================
// MÁQUINA DE ESTADOS FINITOS (FSM)
// ==========================================
enum EstadoRobot {
  SEGUIR_LINEA,           // Seguimiento normal de cinta
  GIRAR_HACIA_OBJETIVO,   // Gira hacia el ángulo detectado por la cámara
  AVANZAR_A_OBJETIVO,     // Avanza hasta ultrasonido <= 10 cm
  ESPERA_EN_OBJETIVO,     // Freno total, notifica para sonido, espera "listo" / "pare"
  RETORNO_REVERSA,        // Retroceso en línea recta hasta tocar cinta
  REALINEAR_CON_PISTA     // Contragiro inverso para continuar en el sentido del circuito
};

EstadoRobot estadoActual = SEGUIR_LINEA;

// Variables de sensado
int16_t distFrente   = 999;
uint8_t lineaIzquierda = 0;
uint8_t lineaCentro    = 0;
uint8_t lineaDerecha   = 0;

// Variables de memoria de maniobra (Cinemática simétrica reversible)
char          direccionGiroActual  = ' '; // 'a' (izquierda), 'd' (derecha), ' ' (sin giro)
unsigned long duracionGiroActual   = 0;   // Duración en ms del giro realizado
unsigned long tiempoAvanceEfectivo = 0;   // Duración en ms que avanzó hacia el objetivo
unsigned long t_inicio_estado      = 0;   // Timestamp de inicio del sub-estado actual
uint8_t       confirmacionesUS     = 0;   // Filtro de rebote: 2 lecturas consecutivas <= 10 cm

// Seguimiento de pista
char ultimaCurva = 'w';
char ultimoComandoEnviado = 'x';

// ==========================================
// FUNCIONES DE CONTROL DE MOTORES
// ==========================================
void enviarComandoMotor(char comando) {
  if (comando != ultimoComandoEnviado) {
    ultimoComandoEnviado = comando;
    serialMotores.print(comando);
  }
}

// ==========================================
// LECTURA DE SENSORES
// ==========================================
int16_t calcular_distancia(unsigned long duracion) {
  if (duracion == 0) return 999;
  return (int16_t)(duracion / 58); // 58 us/cm ida y vuelta
}

void medir_distancias() {
  unsigned long duracion = 0;
  digitalWrite(trigPinFrente, LOW);  delayMicroseconds(2);
  digitalWrite(trigPinFrente, HIGH); delayMicroseconds(10); 
  digitalWrite(trigPinFrente, LOW);
  
  duracion = pulseIn(echoPinFrente, HIGH, TIMEOUT_US); 
  if (duracion == 0) {
    pinMode(echoPinFrente, OUTPUT); digitalWrite(echoPinFrente, LOW);
    delayMicroseconds(50); pinMode(echoPinFrente, INPUT);
  }
  distFrente = calcular_distancia(duracion);
}

void leer_entorno() {
  lineaIzquierda = digitalRead(linePinIzq);
  lineaCentro    = digitalRead(linePinCen); 
  lineaDerecha   = digitalRead(linePinDer);
}

// ==========================================
// RECEPCIÓN DE DISPARADORES (CÁMARA / VOZ)
// ==========================================
void procesarComandosSerial() {
  while (Serial.available() > 0) {
    char cmd = Serial.read();

    switch (cmd) {
      // Disparadores de Cámara (Objeto detectado):
      case 'I':
      case 'i':
        if (estadoActual == SEGUIR_LINEA) {
          Serial.println(F("TRIGGER: Objeto detectado a la IZQUIERDA. Iniciando giro."));
          direccionGiroActual = 'a';
          duracionGiroActual  = TIEMPO_GIRO_DEFAULT_MS;
          t_inicio_estado     = millis();
          estadoActual        = GIRAR_HACIA_OBJETIVO;
          enviarComandoMotor('a');
        }
        break;

      case 'D':
      case 'd':
        if (estadoActual == SEGUIR_LINEA) {
          Serial.println(F("TRIGGER: Objeto detectado a la DERECHA. Iniciando giro."));
          direccionGiroActual = 'd';
          duracionGiroActual  = TIEMPO_GIRO_DEFAULT_MS;
          t_inicio_estado     = millis();
          estadoActual        = GIRAR_HACIA_OBJETIVO;
          enviarComandoMotor('d');
        }
        break;

      case 'F':
      case 'f':
        if (estadoActual == SEGUIR_LINEA) {
          Serial.println(F("TRIGGER: Objeto detectado al FRENTE. Avanzando directo."));
          direccionGiroActual = ' ';
          duracionGiroActual  = 0;
          t_inicio_estado     = millis();
          confirmacionesUS    = 0;
          estadoActual        = AVANZAR_A_OBJETIVO;
          enviarComandoMotor('w');
        }
        break;

      // Disparador de Voz (Usuario dice "listo" o "pare"):
      case 'R':
      case 'r':
        if (estadoActual == ESPERA_EN_OBJETIVO) {
          Serial.println(F("TRIGGER: Comando 'Listo/Pare' recibido. Iniciando reversa hacia pista."));
          t_inicio_estado = millis();
          estadoActual    = RETORNO_REVERSA;
          enviarComandoMotor('s');
        }
        break;

      // Parada de emergencia manual
      case ' ':
        Serial.println(F("MANUAL: Parada forzada."));
        enviarComandoMotor(' ');
        estadoActual = ESPERA_EN_OBJETIVO;
        break;

      default:
        break;
    }
  }
}

// ==========================================
// CONTROL DE SEGUIMIENTO DE LÍNEA
// ==========================================
void ejecutarSeguimientoLinea() {
  // 1. Evasión de seguridad frontal en pista normal
  if (distFrente < 20) {
    enviarComandoMotor(' ');
    return;
  }

  // 2. Lógica booleana de centrado en pista
  uint8_t I = lineaIzquierda;
  uint8_t C = lineaCentro; 
  uint8_t D = lineaDerecha;

  if ((I && C && D) || (!I && C && !D)) {
    enviarComandoMotor('w');
    ultimaCurva = 'w';
  } 
  else if (I && !D) {
    enviarComandoMotor('a');
    ultimaCurva = 'a';
  } 
  else if (!I && D) {
    enviarComandoMotor('d');
    ultimaCurva = 'd';
  } 
  else { 
    // Pérdida momentánea de línea
    if (ultimaCurva == 'a' || ultimaCurva == 'd') {
      enviarComandoMotor(ultimaCurva);
    } else {
      enviarComandoMotor(' ');
    }
  }
}

// ==========================================
// MÁQUINA DE ESTADOS PRINCIPAL
// ==========================================
void actualizarNavegacion() {
  unsigned long t_actual = millis();

  switch (estadoActual) {

    case SEGUIR_LINEA:
      ejecutarSeguimientoLinea();
      break;

    case GIRAR_HACIA_OBJETIVO:
      // Gira hacia el ángulo del objeto por el tiempo asignado
      if (t_actual - t_inicio_estado >= duracionGiroActual) {
        Serial.println(F("INFO: Giro hacia objeto completado. Avanzando hacia el objetivo..."));
        enviarComandoMotor('w');
        t_inicio_estado  = millis();
        confirmacionesUS = 0;
        estadoActual     = AVANZAR_A_OBJETIVO;
      }
      break;

    case AVANZAR_A_OBJETIVO:
      enviarComandoMotor('w');

      // Verificación de distancia ultrasónica <= 10 cm con filtro de confirmación
      if (distFrente > 0 && distFrente <= DIST_OBJETIVO_CM) {
        confirmacionesUS++;
      } else {
        confirmacionesUS = 0;
      }

      if (confirmacionesUS >= 2) {
        // Frenado exacto a 10 cm del objeto
        enviarComandoMotor(' ');
        tiempoAvanceEfectivo = t_actual - t_inicio_estado;
        estadoActual = ESPERA_EN_OBJETIVO;

        Serial.println(F("====================================="));
        Serial.print(F("EVT:OBJETIVO_10CM - Distancia: "));
        Serial.print(distFrente);
        Serial.println(F(" cm"));
        Serial.println(F("Esperando sonido y comando de voz ('r')"));
        Serial.println(F("====================================="));
      }
      else if (t_actual - t_inicio_estado >= TIMEOUT_AVANCE_MS) {
        // Timeout de seguridad en avance
        enviarComandoMotor(' ');
        tiempoAvanceEfectivo = TIMEOUT_AVANCE_MS;
        estadoActual = ESPERA_EN_OBJETIVO;
        Serial.println(F("ALERTA: Timeout en avance sin confirmar 10 cm. Freno por seguridad."));
        Serial.println(F("EVT:OBJETIVO_10CM"));
      }
      break;

    case ESPERA_EN_OBJETIVO:
      enviarComandoMotor(' '); // Mantener freno total
      // Permanece en este estado hasta recibir 'R' en procesarComandosSerial()
      break;

    case RETORNO_REVERSA:
      enviarComandoMotor('s'); // Retroceso recto

      // Verificar si cualquiera de los sensores IR tocó la cinta
      if (lineaCentro || lineaIzquierda || lineaDerecha) {
        enviarComandoMotor(' ');
        Serial.println(F("INFO: Pista de cinta detectada en reversa. Deteniendo reversa."));

        // Si hubo giro inicial, ejecutar contragiro para recuperar orientación de circuito
        if (direccionGiroActual == 'a') {
          // Si salió hacia la izquierda, contragira a la derecha
          enviarComandoMotor('d');
          t_inicio_estado = millis();
          estadoActual    = REALINEAR_CON_PISTA;
          Serial.println(F("INFO: Iniciando contragiro a la DERECHA..."));
        } 
        else if (direccionGiroActual == 'd') {
          // Si salió hacia la derecha, contragira a la izquierda
          enviarComandoMotor('a');
          t_inicio_estado = millis();
          estadoActual    = REALINEAR_CON_PISTA;
          Serial.println(F("INFO: Iniciando contragiro a la IZQUIERDA..."));
        } 
        else {
          // Si salió recto, ya está orientado con la pista
          estadoActual = SEGUIR_LINEA;
          Serial.println(F("EVT:EN_PISTA - Retomando seguimiento normal de circuito."));
        }
      }
      else if (t_actual - t_inicio_estado >= (tiempoAvanceEfectivo + MARGEN_SEGURIDAD_REV_MS)) {
        // Timeout de seguridad de reversa
        enviarComandoMotor(' ');
        Serial.println(F("ALERTA: Timeout de reversa alcanzado. Deteniendo para evitar desvío."));
        estadoActual = SEGUIR_LINEA;
        Serial.println(F("EVT:EN_PISTA"));
      }
      break;

    case REALINEAR_CON_PISTA:
      // Finaliza el contragiro por tiempo o en cuanto el sensor central quede sobre la cinta
      if ((t_actual - t_inicio_estado >= duracionGiroActual) || 
          (lineaCentro && !lineaIzquierda && !lineaDerecha)) {
        enviarComandoMotor(' ');
        estadoActual = SEGUIR_LINEA;
        ultimaCurva  = 'w';
        Serial.println(F("EVT:EN_PISTA - Realineación completada. Reanudando circuito hacia adelante."));
      }
      break;
  }
}

// ==========================================
// VOLCADO DE DEPURACIÓN SERIAL (Cada 500 ms)
// ==========================================
void reportarDebug() {
  static unsigned long ultimaTransmision = 0;
  if (millis() - ultimaTransmision >= 500) {
    ultimaTransmision = millis();
    
    Serial.println(F("-----------------------------------------"));
    Serial.print(F("ESTADO FSM: "));
    switch (estadoActual) {
      case SEGUIR_LINEA:         Serial.println(F("SEGUIR_LINEA")); break;
      case GIRAR_HACIA_OBJETIVO: Serial.println(F("GIRAR_HACIA_OBJETIVO")); break;
      case AVANZAR_A_OBJETIVO:   Serial.println(F("AVANZAR_A_OBJETIVO")); break;
      case ESPERA_EN_OBJETIVO:   Serial.println(F("ESPERA_EN_OBJETIVO")); break;
      case RETORNO_REVERSA:      Serial.println(F("RETORNO_REVERSA")); break;
      case REALINEAR_CON_PISTA:  Serial.println(F("REALINEAR_CON_PISTA")); break;
    }
    Serial.print(F("ULTRASONIDO | Frente: ")); Serial.print(distFrente); Serial.println(F(" cm"));
    Serial.print(F("LÍNEA (IR)  | I: ")); Serial.print(lineaIzquierda); 
    Serial.print(F("  C: ")); Serial.print(lineaCentro);
    Serial.print(F("  D: ")); Serial.println(lineaDerecha);
    Serial.print(F("CMD MOTORES | [ ")); Serial.print(ultimoComandoEnviado); Serial.println(F(" ]"));
    Serial.println(F("-----------------------------------------\n"));
  }
}

// ==========================================
// SETUP & LOOP
// ==========================================
void setup() {
  serialMotores.begin(9600);   // UART software hacia Arduino de Motores
  Serial.begin(115200);        // UART hardware (USB / Raspberry Pi)
  
  pinMode(trigPinFrente, OUTPUT);
  pinMode(echoPinFrente, INPUT);
  
  pinMode(linePinIzq, INPUT); 
  pinMode(linePinCen, INPUT); 
  pinMode(linePinDer, INPUT);

  Serial.println(F("========================================="));
  Serial.println(F("   CEREBRO NAVBOT - INICIALIZADO         "));
  Serial.println(F("   Comandos de prueba disponibles:       "));
  Serial.println(F("   'i' = Detectar objeto a la izquierda  "));
  Serial.println(F("   'd' = Detectar objeto a la derecha    "));
  Serial.println(F("   'f' = Detectar objeto al frente       "));
  Serial.println(F("   'r' = Listo / Regresar a la pista     "));
  Serial.println(F("   ' ' = Freno manual                    "));
  Serial.println(F("========================================="));
}

void loop() {
  medir_distancias();
  leer_entorno();
  procesarComandosSerial();
  actualizarNavegacion();
  reportarDebug();
}
