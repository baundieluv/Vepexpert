# Vepexpert EMG – Dual Channel EMG with Posture Analysis

Vepexpert EMG is a dual-channel electromyography (EMG) monitoring system with integrated posture analysis. It is built on the ESP32 microcontroller and the MPU6050 sensor, featuring real-time signal processing, interactive visualization, and flexible data export.

 Developed at Universidad de Guadalajara as a Graduation Project.

 # Features

Real-time dual-channel EMG monitoring

Advanced digital filtering (notch, low-pass, high-pass)

Posture analysis with MPU6050 (pitch and roll)

Calibration and posture scoring system (0–100 scale)

Interactive web dashboard (Chart.js)

Data export to CSV (10min, 30min, 1hr, or full session)

Docker support for easy deployment

# System Components
Hardware

ESP32-WROOM – main microcontroller

EMG Sensors – two analog input channels

MPU6050 – 6-axis accelerometer + gyroscope

Software

Python Server – WebSocket server with digital filtering

Web Dashboard – HTML5/JavaScript interface

ESP32 Firmware – Arduino-based data acquisition

📂 Project Structure
vepexpert-emg/
├── server.py              # Main WebSocket server
├── static/
│   └── index.html         # Web dashboard
├── sketch_apr10a.ino      # ESP32 firmware
├── Dockerfile             # Docker configuration
├── requirements.txt       # Python dependencies
└── README.md              # This file

# Installation & Setup
1. Python Requirements
pip install -r requirements.txt

2. Hardware Required

ESP32-WROOM-32

EMG sensors (ADC compatible)

MPU6050 (optional for posture analysis)

WiFi connection

3. ESP32 Configuration

Edit sketch_apr10a.ino with your network and server details:

const char* ssid = "YOUR_WIFI_SSID";
const char* password = "YOUR_PASSWORD";
const char* ws_server = "SERVER_IP";


Pinout:

EMG Channel 1 → GPIO34

EMG Channel 2 → GPIO35

I2C SDA → GPIO21

I2C SCL → GPIO22

4. Start the Server
python server.py


Default ports:

WebSocket (Web clients): 8080

WebSocket (ESP32): 8081

HTTP (Dashboard): 8000

# Docker Deployment
## Build
docker build -t vepexpert-emg .

## Run
docker run -p 8000:8000 -p 8080:8080 -p 8081:8081 vepexpert-emg

## Usage

Connect ESP32 with EMG sensors and MPU6050

Upload sketch_apr10a.ino to ESP32

Start the server: python server.py

Open http://localhost:8000 in your browser

Press Connect on the dashboard

Calibrate baseline posture when prompted

# Technical Details
Digital Filtering

Notch filter: 60 Hz (line noise removal)

Bandpass filter: 20–330 Hz (configurable)

Sample rate: 1650 Hz

Posture Analysis

Pitch: forward/backward tilt angle

Roll: side-to-side tilt angle

Posture Score: 0–100 scale

Data Export

Format: CSV

Metrics: RMS, Mean, Imbalance, Angles, Posture Score

## WebSocket API
ESP32 → Server
## EMG with MPU
"EMG1,EMG2,pitch,roll"

## EMG only
"EMG1,EMG2"

## Statistics
"STATS,rms1,rms2,mean1,mean2,imbalance[,pitch,roll]"

Web Client → Server
{
  "type": "filter_settings",
  "notch_enabled": true,
  "low_pass_cutoff": 330.0,
  "high_pass_cutoff": 20.0
}

## Contributing

Fork the repository

Create a feature branch (git checkout -b feature/NewFeature)

Commit changes (git commit -m 'Add NewFeature')

Push to branch (git push origin feature/NewFeature)

Open a Pull Request

## License

This project is licensed under the GNU General Public License v3.0.

# Contact

Esteban León Treviño Martínez
 ## estebanman03@hotmail.com
