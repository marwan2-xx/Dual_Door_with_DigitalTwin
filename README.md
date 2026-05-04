# Dual_Door_with_DigitalTwin


---

## 🛠️ Technologies Used

### 🔌 Embedded / IoT
- ESP32 (C++ / Arduino framework)  
- Sensors: Touch, Joystick, Rotary Encoder  
- Actuators: Dual Servo Motors  
- OLED Display  

### 🧠 Backend
- Python (Flask)  
- WebSocket  
- MQTT Client  

### ☁️ Cloud
- HiveMQ Cloud (MQTT over TLS)  

### 📂 Data Handling
- JSON telemetry format  
- CSV logging  

---

## ⚙️ How It Works

1. 📥 ESP32 reads sensor inputs (touch, joystick, encoder)  
2. 📡 Publishes door state and angle via MQTT (every 200 ms)  
3. 🖥️ Flask backend subscribes to MQTT topics  
4. 🔁 Backend forwards data to dashboard via WebSocket  
5. 🎮 User sends control commands → MQTT → ESP32  
6. 🧾 Telemetry is logged into CSV for analysis  

---

## 👨‍💻 My Contributions

- 🧩 Designed and implemented the full system architecture  
- ⚙️ Built ESP32 firmware for sensor integration and servo control  
- 🔐 Established secure MQTT communication over TLS  
- 🌉 Developed Flask backend bridging MQTT and WebSocket  
- 📊 Implemented real-time digital twin dashboard  
- 💾 Added telemetry logging and persistence  

---

 

---



## ✍️ Author
Marwan Ibrahim
