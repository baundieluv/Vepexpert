#include <WiFi.h>
#include <WebSocketsClient.h>
#include <Wire.h>
#include <MPU6050.h>

// WiFi credentials
const char* ssid = "INFINITUMC8B1_2.4";       // Your WiFi SSID
const char* password = "7707061957";         // Empty string for open networks

// WebSocket server settings
const char* ws_server = "192.168.1.88";  // Your server IP
const uint16_t ws_port = 8081;            // Port for ESP32 connection

// Maximum connection attempts
const int MAX_WIFI_ATTEMPTS = 20;
const int WIFI_RETRY_DELAY = 500;

// EMG sensor configuration - UPDATED FOR ESP32-WROOM
const int emgPin1 = 34;          // ADC1_CH0 (GPIO36) for first EMG sensor
const int emgPin2 = 35;          // ADC1_CH3 (GPIO39) for second EMG sensor
const int sampleRate = 1650;    // Sample rate in Hz
const int sampleInterval = 1000000 / sampleRate; // Microseconds

// ESP32-WROOM specific I2C pins
const int I2C_SDA_PIN = 21;      // SDA pin for ESP32-WROOM (GPIO21)
const int I2C_SCL_PIN = 22;      // SCL pin for ESP32-WROOM (GPIO22)

// Sample buffering to reduce transmission frequency
const int TRANSMISSION_BUFFER_SIZE = 4;  // Send every N samples
int transmissionCounter = 0;

// RMS calculation variables
const int windowSize = 50;      // Window size for RMS calculation
int emg1Values[windowSize];     // Buffer for EMG1 values
int emg2Values[windowSize];     // Buffer for EMG2 values
int windowIndex = 0;
unsigned long lastCalculationTime = 0;
const unsigned long calculationInterval = 500000; // Calculate every 500ms

// MPU6050 configuration
MPU6050 mpu;
bool mpuInitialized = false;
float pitchAngle = 0;     // Forward/backward tilt (lumbar angle proxy)
float rollAngle = 0;      // Side-to-side tilt
unsigned long lastMpuReadTime = 0;
const unsigned long mpuReadInterval = 50000; // Read MPU every 50ms (20Hz)

// Global objects
WebSocketsClient webSocket;
unsigned long lastSampleTime = 0;
boolean connected = false;

// Statistics variables
float rms1 = 0, rms2 = 0;
float mean1 = 0, mean2 = 0;
float imbalancePercentage = 0;

// Connection monitoring
unsigned long lastPingSent = 0;
const unsigned long PING_INTERVAL = 10000; // Send ping every 10 seconds
bool reconnecting = false;

// MPU reading optimization
// Exponential moving average filter for MPU readings to reduce noise
float emaAlpha = 0.3;      // EMA coefficient (0-1): higher = more responsive, lower = smoother
float pitchEMA = 0;
float rollEMA = 0;
bool firstMpuReading = true;

void webSocketEvent(WStype_t type, uint8_t * payload, size_t length) {
  switch(type) {
    case WStype_DISCONNECTED:
      Serial.println("[WS] Disconnected");
      connected = false;
      break;
    case WStype_CONNECTED:
      Serial.println("[WS] Connected to server");
      connected = true;
      
      // Reset transmission counter when connected
      transmissionCounter = 0;
      break;
    case WStype_TEXT:
      // Handle incoming messages if needed
      break;
    case WStype_ERROR:
      Serial.println("[WS] Error occurred");
      connected = false;
      break;
    case WStype_PING:
      // Respond with pong automatically (handled by library)
      Serial.println("[WS] Received ping");
      break;
    case WStype_PONG:
      // Reset reconnection flag
      reconnecting = false;
      break;
    default:
      break;
  }
}

bool setupWiFi() {
  Serial.println("\n[WiFi] Connecting to: " + String(ssid));
  
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  
  // Optional: Set WiFi power saving mode to NONE for better responsiveness
  // esp_wifi_set_ps(WIFI_PS_NONE);
  
  WiFi.begin(ssid, password);
  
  int attempts = 0;
  while (WiFi.status() != WL_CONNECTED && attempts < MAX_WIFI_ATTEMPTS) {
    delay(WIFI_RETRY_DELAY);
    Serial.print(".");
    attempts++;
  }
  
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[WiFi] Connection successful!");
    Serial.print("[WiFi] IP address: ");
    Serial.println(WiFi.localIP());
    return true;
  } else {
    Serial.println("\n[WiFi] Connection failed! Status code: " + String(WiFi.status()));
    return false;
  }
}

void setupWebSocket() {
  Serial.println("[WS] Setting up WebSocket client...");
  Serial.println("[WS] Server: " + String(ws_server) + ":" + String(ws_port));
  
  // Server address, port, and URL
  webSocket.begin(ws_server, ws_port, "/");
  
  // Event handler
  webSocket.onEvent(webSocketEvent);
  
  // Try to reconnect every 5000ms if connection fails
  webSocket.setReconnectInterval(5000);
  
  // Enable automatic heartbeat (if available in your library version)
  // If this causes errors, comment it out
  webSocket.enableHeartbeat(25000, 3000, 2);
  
  Serial.println("[WS] WebSocket client started");
}

bool setupMPU() {
  Serial.println("[MPU] Initializing MPU6050...");
  
  // Initialize I2C communication with ESP32-WROOM specific pins
  Wire.begin(I2C_SDA_PIN, I2C_SCL_PIN);
  Wire.setClock(400000); // Set I2C to 400kHz for faster communication
  
  // Set timeout for I2C communication to avoid hanging if MPU isn't connected
  Wire.setTimeOut(1000);  // 1000ms timeout
  
  // Try to initialize device with timeout protection
  bool initSuccess = false;
  unsigned long startTime = millis();
  const unsigned long timeout = 3000;  // 3 second timeout
  
  while (millis() - startTime < timeout) {
    // Initialize the MPU6050
    mpu.initialize();
    
    // Check connection
    if (mpu.testConnection()) {
      initSuccess = true;
      break;
    }
    
    // Wait a bit before retrying
    delay(100);
  }
  
  // If initialization failed, return false
  if (!initSuccess) {
    Serial.println("[MPU] Connection failed after multiple attempts!");
    return false;
  }
  
  // Set full scale ranges for both gyro and accelerometer
  mpu.setFullScaleGyroRange(MPU6050_GYRO_FS_250);     // +/- 250 degrees/sec
  mpu.setFullScaleAccelRange(MPU6050_ACCEL_FS_2);     // +/- 2g
  
  // Optional: Set digital low pass filter
  mpu.setDLPFMode(MPU6050_DLPF_BW_5);  // 5Hz DLPF
  
  // Reset EMA values
  firstMpuReading = true;
  
  Serial.println("[MPU] MPU6050 initialized successfully");
  return true;
}

void calculateStatistics() {
  // Calculate RMS
  float sum1 = 0, sum2 = 0;
  float sumSquared1 = 0, sumSquared2 = 0;
  
  for (int i = 0; i < windowSize; i++) {
    // Mean calculation
    sum1 += emg1Values[i];
    sum2 += emg2Values[i];
    
    // RMS calculation
    sumSquared1 += (emg1Values[i] * emg1Values[i]);
    sumSquared2 += (emg2Values[i] * emg2Values[i]);
  }
  
  // Calculate mean values
  mean1 = sum1 / windowSize;
  mean2 = sum2 / windowSize;
  
  // Calculate RMS values
  rms1 = sqrt(sumSquared1 / windowSize);
  rms2 = sqrt(sumSquared2 / windowSize);
  
  // Calculate imbalance percentage
  float maxRMS = max(rms1, rms2);
  float minRMS = min(rms1, rms2);
  
  if (maxRMS > 0) {
    imbalancePercentage = ((maxRMS - minRMS) / maxRMS) * 100.0;
  } else {
    imbalancePercentage = 0;
  }
}

void readLumbarAngle() {
  if (!mpuInitialized) return;
  
  // Wrap MPU reading in a try-catch like structure to prevent hanging
  bool readSuccess = false;
  
  // Set a timeout for the reading operation
  unsigned long startTime = millis();
  const unsigned long readTimeout = 100;  // 100ms timeout (reduced from 500ms)
  
  while (millis() - startTime < readTimeout && !readSuccess) {
    try {
      // Read accelerometer data
      int16_t ax, ay, az;
      
      // Attempt to read acceleration data
      mpu.getAcceleration(&ax, &ay, &az);
      
      // If we got here without errors, process the data
      // Convert to G forces
      float accelX = ax / 16384.0;  // For +/-2g range
      float accelY = ay / 16384.0;
      float accelZ = az / 16384.0;
      
      // Calculate pitch (forward/backward tilt) - using X and Z
      float newPitch = atan2(accelX, sqrt(accelY * accelY + accelZ * accelZ)) * 180.0 / PI;
      
      // Calculate roll (side-to-side tilt) - using Y and Z
      float newRoll = atan2(accelY, accelZ) * 180.0 / PI;
      
      // Apply EMA filter to smooth readings
      if (firstMpuReading) {
        pitchEMA = newPitch;
        rollEMA = newRoll;
        firstMpuReading = false;
      } else {
        pitchEMA = (emaAlpha * newPitch) + ((1.0 - emaAlpha) * pitchEMA);
        rollEMA = (emaAlpha * newRoll) + ((1.0 - emaAlpha) * rollEMA);
      }
      
      // Use the filtered values
      pitchAngle = pitchEMA;
      rollAngle = rollEMA;
      
      // Reading succeeded
      readSuccess = true;
    } catch(...) {
      // If any error occurred, wait a bit and retry
      delayMicroseconds(1000);
    }
  }
  
  // If reading failed completely, mark the MPU as uninitialized to prevent further attempts
  if (!readSuccess) {
    static unsigned long lastFailReport = 0;
    static int failureCount = 0;
    
    if (millis() - lastFailReport > 5000) {  // Report failure once every 5 seconds
      lastFailReport = millis();
      Serial.println("[MPU] Failed to read data from MPU6050. Check connection.");
      
      // After several consecutive failures, we might want to reinitialize or mark as disconnected
      failureCount++;
      
      if (failureCount > 10) {
        Serial.println("[MPU] Too many failures. Disabling MPU6050.");
        mpuInitialized = false;
        failureCount = 0;
      }
    }
  }
}

void setup() {
  // Initialize serial communication with higher baud rate for debugging
  Serial.begin(115200);
  delay(1000); // Allow serial to stabilize
  
  Serial.println("\n\n=========================================");
  Serial.println("ESP32-WROOM Dual Channel EMG with MPU6050");
  Serial.println("=========================================");
  
  // Configure ADC for ESP32-WROOM
  analogSetWidth(12);           // Set resolution to 12 bits
  analogSetAttenuation(ADC_11db); // Set attenuation for higher voltage range (up to ~3.9V)
  
  // Initialize buffers
  for (int i = 0; i < windowSize; i++) {
    emg1Values[i] = 0;
    emg2Values[i] = 0;
  }
  
  // Initialize MPU6050
  mpuInitialized = setupMPU();
  
  if (!mpuInitialized) {
    Serial.println("[WARNING] MPU6050 initialization failed. Continuing with EMG-only mode.");
    // Set a flag or variable if needed to indicate MPU6050 is not available
  } else {
    Serial.println("[INFO] MPU6050 initialized successfully. Angle measurement enabled.");
  }
  
  // Connect to WiFi
  if (setupWiFi()) {
    // Setup WebSocket connection
    setupWebSocket();
  } else {
    Serial.println("[ERROR] WiFi connection failed. Check your network settings.");
  }
}

void reconnectIfNeeded() {
  static unsigned long lastReconnectAttempt = 0;
  const unsigned long reconnectInterval = 10000; // 10 seconds between reconnection attempts
  
  // Check WiFi connection
  if (WiFi.status() != WL_CONNECTED) {
    unsigned long currentMillis = millis();
    if (currentMillis - lastReconnectAttempt > reconnectInterval) {
      Serial.println("[WiFi] Connection lost, attempting to reconnect...");
      lastReconnectAttempt = currentMillis;
      setupWiFi();
    }
  } else if (!connected && !reconnecting) {
    // If WiFi is connected but WebSocket is not, try to reconnect
    unsigned long currentMillis = millis();
    if (currentMillis - lastReconnectAttempt > reconnectInterval) {
      Serial.println("[WS] Connection lost, attempting to reconnect...");
      lastReconnectAttempt = currentMillis;
      reconnecting = true;
      
      // For more aggressive reconnection, can restart the websocket client
      webSocket.disconnect();
      delay(500);
      setupWebSocket();
    }
  }
  
  // Send WebSocket ping to keep connection alive
  unsigned long currentMillis = millis();
  if (connected && currentMillis - lastPingSent > PING_INTERVAL) {
    lastPingSent = currentMillis;
    webSocket.sendPing();
  }
}

void loop() {
  // Check for reconnection if needed
  reconnectIfNeeded();
  
  // Keep the WebSocket connection alive if WiFi is connected
  if (WiFi.status() == WL_CONNECTED) {
    webSocket.loop();
  }
  
  // Check if it's time to take a sample
  unsigned long currentMicros = micros();
  if (currentMicros - lastSampleTime >= sampleInterval) {
    lastSampleTime = currentMicros;
    
    // Read EMG sensors - use direct port manipulation for faster reading if possible
    int emg1Value = analogRead(emgPin1);
    int emg2Value = analogRead(emgPin2);
    
    // Store values in buffer
    emg1Values[windowIndex] = emg1Value;
    emg2Values[windowIndex] = emg2Value;
    
    // Increment and wrap window index
    windowIndex = (windowIndex + 1) % windowSize;
    
    // If connected to WebSocket server, buffer and send data
    if (connected) {
      transmissionCounter++;
      
      // Only send every N samples to reduce transmission frequency
      if (transmissionCounter >= TRANSMISSION_BUFFER_SIZE) {
        transmissionCounter = 0;
        
        String dataString;
        // Pre-allocate string size to avoid dynamic allocations
        dataString.reserve(32);
        
        // Include MPU6050 data if available
        if (mpuInitialized) {
          dataString = String(emg1Value) + "," + String(emg2Value) + "," + String(pitchAngle, 1) + "," + String(rollAngle, 1);
        } else {
          dataString = String(emg1Value) + "," + String(emg2Value);
        }
        
        webSocket.sendTXT(dataString);
      }
    } else {
      // Periodically print connection status if not connected
      static unsigned long lastStatusPrint = 0;
      if (millis() - lastStatusPrint > 5000) { // Every 5 seconds
        lastStatusPrint = millis();
        Serial.println("[Status] Waiting for WebSocket connection...");
        Serial.println("[Status] WiFi status: " + String(WiFi.status() == WL_CONNECTED ? "Connected" : "Disconnected"));
      }
    }
  }
  
  // Read MPU6050 periodically - use a less frequent update for posture
  if (mpuInitialized && (currentMicros - lastMpuReadTime >= mpuReadInterval)) {
    lastMpuReadTime = currentMicros;
    readLumbarAngle();
  }
  
  // Calculate statistics periodically
  if (currentMicros - lastCalculationTime >= calculationInterval) {
    lastCalculationTime = currentMicros;
    
    calculateStatistics();
    
    // Send statistics to server
    if (connected) {
      String statsString;
      // Pre-allocate string size to avoid dynamic allocations
      statsString.reserve(64);
      
      // Include MPU6050 data if available
      if (mpuInitialized) {
        statsString = "STATS," + String(rms1, 2) + "," + String(rms2, 2) + "," + 
                      String(mean1, 2) + "," + String(mean2, 2) + "," + 
                      String(imbalancePercentage, 2) + "," +
                      String(pitchAngle, 1) + "," + String(rollAngle, 1);
      } else {
        statsString = "STATS," + String(rms1, 2) + "," + String(rms2, 2) + "," + 
                      String(mean1, 2) + "," + String(mean2, 2) + "," + 
                      String(imbalancePercentage, 2);
      }
      
      webSocket.sendTXT(statsString);
    }
    
    // Print statistics for debugging - but less frequently to reduce Serial load
    static unsigned long lastDebugPrint = 0;
    if (millis() - lastDebugPrint > 5000) { // Every 5 seconds instead of every calculation
      lastDebugPrint = millis();
      
      if (mpuInitialized) {
        Serial.println("RMS1: " + String(rms1) + ", RMS2: " + String(rms2) + 
                       ", Mean1: " + String(mean1) + ", Mean2: " + String(mean2) + 
                       ", Imbalance: " + String(imbalancePercentage) + "%" +
                       ", Pitch: " + String(pitchAngle) + "°" +
                       ", Roll: " + String(rollAngle) + "°");
      } else {
        Serial.println("RMS1: " + String(rms1) + ", RMS2: " + String(rms2) + 
                       ", Mean1: " + String(mean1) + ", Mean2: " + String(mean2) + 
                       ", Imbalance: " + String(imbalancePercentage) + "%");
      }
    }
  }
  
  // Add a small delay to allow other processes (WiFi, BT, etc.) to run
  // This can help with stability in some cases
  yield();
}