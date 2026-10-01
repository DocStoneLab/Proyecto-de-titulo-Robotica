# Diagrama de Conexiones Físicas y Seriales

Este documento muestra cómo deben quedar conectados físicamente los dos Arduinos y la Raspberry Pi para que el sistema opere coordinadamente.

---

## 1. Mapa de Conexiones entre Componentes

```
                   ┌────────────────────────────────────────┐
                   │             RASPBERRY PI               │
                   │  - send_feed.py (Cámara / YOLO)        │
                   │  - comando_voz_v2.py (Micrófono)       │
                   └───────┬────────────────────────┬───────┘
                           │ USB                    │ USB
                           │ (/dev/ttyACM0)         │ (/dev/ttyUSB0)
                           │ 115200 baud            │ 9600 baud
                           ▼                        ▼
         ┌───────────────────────────┐    ┌───────────────────────────┐
         │      ARDUINO CEREBRO      │    │  ARDUINO MOTORES/STEPPER  │
         │ (Navegación FSM / Lógica) │    │   (Tracción 4WD + Paneo)  │
         └─────────────┬─────────────┘    └─────────────▲─────────────┘
                       │                                │
                       │    Línea Serial Software       │
                       │    Pin 3 (TX) ────────────────►│ Pin A0 (RX)
                       │    GND        ────────────────►│ GND
                       │    (9600 baud)                 │
                       │                                │
                       ▼                                ▼
              [SENSORES CEREBRO]              [ACTUADORES MOTORES]
              - Trig: Pin 9                   - M1: Pines 2, 3
              - Echo: Pin 8                   - M3: Pines 4, 5
              - IR Izq: Pin A0                - M2: Pines 6, 7
              - IR Cen: Pin A1                - M4: Pines 8, 9
              - IR Der: Pin A2                - Stepper: 10, 11, 12, 13
                                              - Final carrera: Pin A5
```

---

## 2. Detalle de Pines

### Arduino Cerebro (Navegación FSM)
* **Sensor Ultrasonido HC-SR04:**
  * `VCC` -> 5V
  * `GND` -> GND
  * `Trig` -> Pin 9
  * `Echo` -> Pin 8
* **Sensores de Línea TCRT5000 (3x):**
  * Sensor Izquierdo -> Pin A0
  * Sensor Central -> Pin A1
  * Sensor Derecho -> Pin A2
* **Conexión hacia Arduino Motores:**
  * Pin 3 (SoftwareSerial TX) -> Pin A0 (SoftwareSerial RX) de Arduino Motores
  * GND -> GND común con Arduino Motores
* **Conexión hacia Raspberry Pi:**
  * Cable USB (Puerto `/dev/ttyACM0` a 115200 baudios)

---

### Arduino Motores y Stepper
* **Puente H L298N 1 (Lado Izquierdo):**
  * `IN1`, `IN2` -> Pines 2, 3
  * `IN3`, `IN4` -> Pines 4, 5
* **Puente H L298N 2 (Lado Derecho):**
  * `IN1`, `IN2` -> Pines 6, 7
  * `IN3`, `IN4` -> Pines 8, 9
* **Motor Paso a Paso 28BYJ-48 (Controlador ULN2003):**
  * `IN1`, `IN2`, `IN3`, `IN4` -> Pines 11, 13, 12, 10
* **Final de Carrera:**
  * Pin A5 (con pullup interno activado) y GND
* **Recepción desde Arduino Cerebro:**
  * Pin A0 (SoftwareSerial RX) conectado al Pin 3 de Cerebro
* **Conexión hacia Raspberry Pi:**
  * Cable USB (Puerto `/dev/ttyUSB0` a 9600 baudios)
