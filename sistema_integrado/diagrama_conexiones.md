# Diagrama de Conexiones Físicas y Seriales

Al utilizar la Raspberry Pi como **Cerebro Central**, ya **NO** se necesitan cables ni puentes de comunicación serial entre ambos Arduinos. Todo se comunica de manera directa y limpia por cables USB.

---

## 1. Mapa de Conexiones entre Componentes

```
                   ┌────────────────────────────────────────┐
                   │             RASPBERRY PI               │
                   │    (Cerebro Central Coordinador)       │
                   │  - controlador_central.py              │
                   │  - alert_sound.py (Bluetooth al Altavoz)│
                   └───────┬────────────────────────┬───────┘
                           │ Cable USB              │ Cable USB
                           │ (/dev/ttyACM0)         │ (/dev/ttyUSB0)
                           │ 115200 baud            │ 9600 baud
                           ▼                        ▼
         ┌───────────────────────────┐    ┌───────────────────────────┐
         │    ARDUINO 1: SENSORES    │    │    ARDUINO 2: MOTORES     │
         │    (Ultrasonido + Línea)  │    │   (Tracción 4WD + Paneo)  │
         └─────────────┬─────────────┘    └─────────────┬─────────────┘
                       │                                │
                       ▼                                ▼
              [SENSORES]                       [ACTUADORES]
              - Trig: Pin 9                    - M1: Pines 2, 3
              - Echo: Pin 8                    - M3: Pines 4, 5
              - IR Izq: Pin A0                 - M2: Pines 6, 7
              - IR Cen: Pin A1                 - M4: Pines 8, 9
              - IR Der: Pin A2                 - Stepper: 10, 11, 12, 13
                                               - Final carrera: Pin A5
```

---

## 2. Detalle de Conexiones

### Arduino 1: Sensores (Ultrasonido y Línea)
* **Sensor Ultrasonido HC-SR04:**
  * `VCC` -> 5V de Arduino 1
  * `GND` -> GND de Arduino 1
  * `Trig` -> Pin 9
  * `Echo` -> Pin 8
* **Sensores Infrarrojos de Línea (TCRT5000):**
  * Sensor Izquierdo -> Pin A0
  * Sensor Central -> Pin A1
  * Sensor Derecho -> Pin A2
* **Conexión a Raspberry Pi:**
  * Cable USB estándar (Puerto `/dev/ttyACM0` a 115200 baudios).
  * **Sin cables hacia el otro Arduino.**

---

### Arduino 2: Motores y Paneo de Cámara
* **Puente H L298N 1 (Lado Izquierdo):**
  * `IN1`, `IN2` -> Pines 2, 3
  * `IN3`, `IN4` -> Pines 4, 5
* **Puente H L298N 2 (Lado Derecho):**
  * `IN1`, `IN2` -> Pines 6, 7
  * `IN3`, `IN4` -> Pines 8, 9
* **Motor Paso a Paso 28BYJ-48 (Controlador ULN2003):**
  * `IN1`, `IN2`, `IN3`, `IN4` -> Pines 11, 13, 12, 10
* **Final de Carrera (Switch Homing):**
  * Pin A5 y GND
* **Conexión a Raspberry Pi:**
  * Cable USB estándar (Puerto `/dev/ttyUSB0` a 9600 baudios).
  * **Sin cables hacia el otro Arduino.**
