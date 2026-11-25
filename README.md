# Vepexpert EMG – Dual-Channel EMG with Posture Analysis

Vepexpert is a wearable system for **remote rehabilitation monitoring of the lower back**. It was designed for older adults and people with chronic low back pain (LBP), so that a therapist can follow their muscle activity and posture at a distance.

A vest carries two EMG sensors and an MPU6050 motion sensor, connected to an ESP32. The ESP32 streams the signals over Wi-Fi to a Python server, which filters them in real time and serves a web dashboard for visualization, posture scoring and data export.

Developed at Universidad de Guadalajara as a graduation project.

> **Note:** Vepexpert is a research prototype. It is not a certified medical device and is not intended for diagnosis.

## Features

- Real-time dual-channel EMG monitoring (1650 Hz sample rate)
- Digital filtering: notch (mains noise), low-pass and high-pass, adjustable from the dashboard
- Posture analysis with the MPU6050 (pitch and roll)
- Baseline calibration and a 0–100 posture score
- Interactive web dashboard (Chart.js)
- CSV export (last 10 min, 30 min, 1 h, or the full session)
- Docker support for easy deployment

## System Components

### Hardware

| Component | Role |
|---|---|
| ESP32-WROOM-32 | Main microcontroller, Wi-Fi |
| 2 × EMG sensors (analog output) | Muscle activity, two channels |
| MPU6050 | 6-axis accelerometer + gyroscope for posture (optional) |

**Pinout**

| Signal | ESP32 pin |
|---|---|
| EMG channel 1 | GPIO34 |
| EMG channel 2 | GPIO35 |
| I2C SDA (MPU6050) | GPIO21 |
| I2C SCL (MPU6050) | GPIO22 |

### Software

- **ESP32 firmware** (`sketch_apr10a.ino`) – Arduino-based data acquisition and Wi-Fi/WebSocket streaming
- **Python server** (`server.py`) – WebSocket server with real-time digital filtering
- **Web dashboard** (`static/index.html`) – HTML5/JavaScript interface

## Project Structure

```
Vepexpert/
├── server.py              # WebSocket server and filtering
├── static/
│   └── index.html         # Web dashboard
├── sketch_apr10a.ino      # ESP32 firmware
├── Dockerfile             # Docker configuration
├── requirements.txt       # Python dependencies
├── LICENSE                # GPL-3.0
└── README.md
```

## Installation & Setup

### 1. Configure the ESP32

Edit `sketch_apr10a.ino` with your own network and the IP address of the computer running the server:

```cpp
const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_WIFI_PASSWORD";
const char* ws_server = "SERVER_IP";
```

Never commit real credentials to the repository.

Then upload the sketch to the ESP32 with the Arduino IDE (the `WebSockets` library by Markus Sattler is required).

### 2. Set the mains frequency

The notch filter removes power-line noise. It is set to **60 Hz** (Americas). In Europe and most of the world the mains frequency is **50 Hz**, so change this line in `server.py`:

```python
notch_b, notch_a = design_notch_filter(60.0, SAMPLE_RATE, Q_FACTOR)  # use 50.0 in Europe
```

### 3. Run the server

**With Python**

```bash
pip install -r requirements.txt
python server.py
```

**With Docker**

```bash
docker build -t vepexpert-emg .
docker run -p 8000:8000 -p 8080:8080 -p 8081:8081 vepexpert-emg
```

Default ports (can be changed with the `HTTP_PORT`, `WEB_CLIENT_PORT` and `ESP32_PORT` environment variables):

| Port | Use |
|---|---|
| 8000 | HTTP – dashboard |
| 8080 | WebSocket – web clients |
| 8081 | WebSocket – ESP32 |

## Usage

1. Power the ESP32 with the EMG sensors and MPU6050 connected.
2. Start the server.
3. Open http://localhost:8000 in your browser and press **Connect**.
4. Calibrate the baseline posture when prompted.
5. Monitor the signals and export the session to CSV when finished.

## Technical Details

**Filtering**
- Notch filter: 60 Hz by default (50 Hz in Europe, see setup step 2), Q = 30
- Band-pass: 20–330 Hz, 4th-order Butterworth (configurable from the dashboard)
- Sample rate: 1650 Hz

**Posture analysis**
- Pitch: forward/backward tilt
- Roll: side-to-side tilt
- Posture score: 0–100, relative to the calibrated baseline

**Data export**
- Format: CSV
- Metrics: RMS, mean, channel imbalance, angles, posture score

## WebSocket API

**ESP32 → server**

```
EMG1,EMG2,pitch,roll                              # EMG with MPU6050
EMG1,EMG2                                         # EMG only
STATS,rms1,rms2,mean1,mean2,imbalance[,pitch,roll] # statistics
```

**Web client → server**

```json
{
  "type": "filter_settings",
  "notch_enabled": true,
  "low_pass_cutoff": 330.0,
  "high_pass_cutoff": 20.0
}
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/NewFeature`
3. Commit your changes: `git commit -m "Add NewFeature"`
4. Push the branch: `git push origin feature/NewFeature`
5. Open a pull request

## License

This project is licensed under the GNU General Public License v3.0. See [LICENSE](LICENSE).

## Contact

Esteban León Treviño Martínez – estebanman03@hotmail.com
