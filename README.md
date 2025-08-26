# Vepexpert EMG - Dual Channel EMG with Posture Analysis

Sistema de monitoreo EMG de dos canales con análisis de postura utilizando ESP32 y sensor MPU6050.

## Características

-  Monitoreo EMG dual channel en tiempo real
-  Filtrado digital avanzado (notch, paso bajo, paso alto)
-  Análisis de postura usando MPU6050 (pitch y roll)
-  Sistema de calibración y scoring de postura
-  Visualización web interactiva con Chart.js
-  Exportación de datos a CSV
-  Soporte para Docker

## Componentes del Sistema

### Hardware
- **ESP32-WROOM**: Microcontrolador principal
- **Sensores EMG**: Dos canales de entrada analógica
- **MPU6050**: Sensor de 6-axis (acelerómetro + giroscopio)

### Software
- **Servidor Python**: WebSocket server con filtrado digital
- **Interface Web**: Dashboard interactivo HTML5/JavaScript
- **Firmware ESP32**: Código Arduino para adquisición de datos

## Estructura del Proyecto

```
vepexpert-emg/
├── server.py              # Servidor WebSocket principal
├── static/
│   └── index.html         # Interface web
├── sketch_apr10a.ino      # Firmware ESP32
├── Dockerfile             # Configuración Docker
├── requirements.txt       # Dependencias Python
└── README.md             # Este archivo
```

## Requisitos

### Python
```bash
pip install -r requirements.txt
```

### Hardware
- ESP32-WROOM-32
- Sensores EMG compatibles con ADC
- MPU6050 (opcional para análisis de postura)
- WiFi network

## Configuración

### 1. ESP32 Configuration
Edita las siguientes variables en `sketch_apr10a.ino`:
```cpp
const char* ssid = "TU_RED_WIFI";
const char* password = "TU_PASSWORD";
const char* ws_server = "IP_DEL_SERVIDOR";
```

### 2. Pines ESP32
- EMG Channel 1: GPIO34
- EMG Channel 2: GPIO35
- I2C SDA: GPIO21
- I2C SCL: GPIO22

### 3. Servidor
```bash
python server.py
```

Puertos por defecto:
- WebSocket (Web clients): 8080
- WebSocket (ESP32): 8081
- HTTP (Interface): 8000

## Uso con Docker

```bash
# Build
docker build -t vepexpert-emg .

# Run
docker run -p 8000:8000 -p 8080:8080 -p 8081:8081 vepexpert-emg
```

## Uso

1. **Conectar Hardware**: Ensambla el ESP32 con sensores EMG y MPU6050
2. **Cargar Firmware**: Sube `sketch_apr10a.ino` al ESP32
3. **Iniciar Servidor**: Ejecuta `python server.py`
4. **Acceder Interface**: Ve a `http://localhost:8000`
5. **Conectar**: Usa el botón "Connect" en la interface web
6. **Calibrar Postura**: Establece postura baseline cuando sea necesario

## Características Técnicas

### Filtrado Digital
- **Notch Filter**: 60Hz (eliminación de interferencia de línea)
- **Bandpass Filter**: 20-330Hz (configurable)
- **Sample Rate**: 1650Hz

### Análisis de Postura
- **Pitch**: Ángulo de inclinación forward/backward
- **Roll**: Ángulo de inclinación side-to-side
- **Scoring**: Sistema de puntuación 0-100

### Exportación de Datos
- Formatos: CSV
- Rangos: 10min, 30min, 1hora, sesión completa
- Datos incluidos: RMS, Mean, Imbalance, Ángulos, Posture Score

## API WebSocket

### Mensajes del ESP32 al Servidor
```
# Datos EMG con MPU
"EMG1,EMG2,pitch,roll"

# Datos EMG sin MPU
"EMG1,EMG2"

# Estadísticas
"STATS,rms1,rms2,mean1,mean2,imbalance[,pitch,roll]"
```

### Mensajes del Cliente Web
```json
{
  "type": "filter_settings",
  "notch_enabled": true,
  "low_pass_cutoff": 330.0,
  "high_pass_cutoff": 20.0
}
```

## Contribuir

1. Fork el proyecto
2. Crea una feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit tus cambios (`git commit -m 'Add some AmazingFeature'`)
4. Push a la branch (`git push origin feature/AmazingFeature`)
5. Abre un Pull Request

## Licencia

The GNU General Public License v3.0

## Contacto

Esteban León Treviño Martínez - estebanman03@hotmail.com
