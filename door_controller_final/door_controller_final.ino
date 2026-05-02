// ============================================================
//  DOOR CONTROLLER — ESP32  (Digital Twin Edition)
//  Servo 1 (Door 1): Analog touch sensor — GPIO 36
//  Servo 2 (Door 2): Joystick X-axis   — GPIO 34
//  Mode switch     : Button            — GPIO 4  (debounced)
//  Max angle       : Rotary encoder    — GPIO 18/19
//  Cloud           : HiveMQ MQTT over SSL
//  Commands        : Subscribes to "commands/" topic
// ============================================================

#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <ESP32Servo.h>
#include <ESP32Encoder.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <Adafruit_MQTT.h>
#include <Adafruit_MQTT_Client.h>

// ------------------------------------------------------------
// *** CONFIGURE THESE ***
// ------------------------------------------------------------
#define WIFI_SSID    "WIFI_SSID"
#define WIFI_PASS    "WIFI_PASSWORD"
#define MQTT_SERVER  "URL"
#define MQTT_PORT    8883
#define MQTT_USER    "Username"
#define MQTT_PASS    "Password"
#define TOPIC_STATE  "doorcontroller/state"
#define TOPIC_CMD    "doorcontroller/commands"
// ------------------------------------------------------------

// OLED
#define SCREEN_WIDTH  128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

// Pins
#define BUTTON      4
#define TOUCH       36     // analog touch sensor
#define JOY_X       34
#define JOY_Y       35
#define JOY_BTN     17
#define ENC_CLK     18
#define ENC_DT      19
#define ENC_SW      5
#define SERVO1_PIN  25
#define SERVO2_PIN  26
#define BUZZER      27
#define RGB_RED     32
#define RGB_GREEN   33
#define RGB_BLUE    23
#define TWO_COLOR   13

#define TOUCH_THRESHOLD 100

// Objects
Servo        door1;
Servo        door2;
ESP32Encoder encoder;

// WiFi & MQTT
WiFiClientSecure         wifiClient;
Adafruit_MQTT_Client     mqtt(&wifiClient, MQTT_SERVER, MQTT_PORT, MQTT_USER, MQTT_PASS);

// Publish  — sensor state → dashboard
Adafruit_MQTT_Publish    feedState = Adafruit_MQTT_Publish(&mqtt, TOPIC_STATE);

// Subscribe — dashboard commands → ESP32
Adafruit_MQTT_Subscribe  cmdFeed   = Adafruit_MQTT_Subscribe(&mqtt, TOPIC_CMD);

// State
bool mode            = false;   // false=Door1(touch)  true=Door2(joystick)
bool door1Open       = false;
bool door2Open       = false;
bool lastButtonState = HIGH;
int  maxAngle        = 90;
int  lastEncoderVal  = 0;
int  lastJoyAngle    = -1;

// Timing
unsigned long lastPublishMs = 0;
#define PUBLISH_INTERVAL 200

// ============================================================
//  SETUP
// ============================================================
void setup() {
    Serial.begin(115200);

    pinMode(BUTTON,    INPUT_PULLUP);
    pinMode(TOUCH,     INPUT);
    pinMode(JOY_BTN,   INPUT_PULLUP);
    pinMode(ENC_SW,    INPUT_PULLUP);
    pinMode(TWO_COLOR, OUTPUT);
    pinMode(RGB_RED,   OUTPUT);
    pinMode(RGB_GREEN, OUTPUT);
    pinMode(RGB_BLUE,  OUTPUT);
    pinMode(BUZZER,    OUTPUT);

    door1.attach(SERVO1_PIN);
    door2.attach(SERVO2_PIN);
    door1.write(0);
    door2.write(0);

    encoder.attachHalfQuad(ENC_CLK, ENC_DT);
    encoder.setCount(90);

    if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
        Serial.println("OLED not found — continuing");
    }

    updateDisplay();
    setRGB();

    connectWiFi();
    wifiClient.setInsecure();   // SSL without cert verification
    connectMQTT();

    publishState(0);
}

// ============================================================
//  LOOP
// ============================================================
void loop() {
    handleButton();
    handleEncoder();

    if (!mode) {
        handleDoor1();
    } else {
        handleDoor2();
    }

    // Handle incoming commands from dashboard
    handleCommands();

    // Publish state periodically
    if (millis() - lastPublishMs > PUBLISH_INTERVAL) {
        int joyAngle = map(analogRead(JOY_X), 0, 4095, 0, maxAngle);
        publishState(joyAngle);
        lastPublishMs = millis();
    }

    // Keep MQTT alive
    mqtt.processPackets(10);
    if (!mqtt.ping()) connectMQTT();
}

// ============================================================
//  BUTTON — debounced mode switch
// ============================================================
void handleButton() {
    static unsigned long lastDebounceTime = 0;
    bool currentState = digitalRead(BUTTON);

    if (currentState == LOW && lastButtonState == HIGH) {
        if (millis() - lastDebounceTime > 200) {
            mode = !mode;
            beep(100);
            updateDisplay();
            setRGB();
            lastDebounceTime = millis();
            Serial.println(mode ? "Mode: DOOR2 (joystick)" : "Mode: DOOR1 (touch)");
        }
    }
    lastButtonState = currentState;
}

// ============================================================
//  ENCODER — sets maxAngle (10–180°)
// ============================================================
void handleEncoder() {
    int encoderVal = constrain(encoder.getCount(), 10, 180);
    encoder.setCount(encoderVal);

    if (encoderVal != lastEncoderVal) {
        maxAngle = encoderVal;
        lastEncoderVal = encoderVal;
        updateDisplay();
        Serial.print("Max angle: ");
        Serial.println(maxAngle);
    }
}

// ============================================================
//  DOOR 1 — analog touch sensor toggles servo
// ============================================================
void handleDoor1() {
    static bool lastTouchState = false;
    int  touchVal   = analogRead(TOUCH);
    bool touchState = touchVal > TOUCH_THRESHOLD;

    if (touchState && !lastTouchState) {
        door1Open = !door1Open;
        door1.write(door1Open ? maxAngle : 0);
        digitalWrite(TWO_COLOR, door1Open ? HIGH : LOW);
        beep(50);
        updateDisplay();
        Serial.println(door1Open ? "Door1 OPEN" : "Door1 CLOSED");
    }
    lastTouchState = touchState;
}

// ============================================================
//  DOOR 2 — joystick X controls servo continuously
// ============================================================
void handleDoor2() {
    int joyX  = analogRead(JOY_X);
    int angle = map(joyX, 0, 4095, 0, maxAngle);

    if (abs(angle - lastJoyAngle) > 1) {
        door2.write(angle);
        digitalWrite(TWO_COLOR, door1Open ? HIGH : LOW);
        door2Open    = angle > (maxAngle / 2);
        lastJoyAngle = angle;
        updateDisplay();
    }
}

// ============================================================
//  COMMAND HANDLER — receives instructions from dashboard
// ============================================================
void handleCommands() {
    Adafruit_MQTT_Subscribe *sub;
    while ((sub = mqtt.readSubscription(5))) {
        if (sub == &cmdFeed) {
            String cmd = String((char *)cmdFeed.lastread);
            cmd.trim();
            Serial.println("Command received: " + cmd);

            if (cmd == "door1_open") {
                door1Open = true;
                door1.write(maxAngle);
                digitalWrite(TWO_COLOR, HIGH);
                beep(50);
            }
            else if (cmd == "door1_close") {
                door1Open = false;
                door1.write(0);
                digitalWrite(TWO_COLOR, LOW);
                beep(50);
            }
            else if (cmd == "door2_open") {
                door2Open = true;
                door2.write(maxAngle);
                beep(50);
            }
            else if (cmd == "door2_close") {
                door2Open = false;
                door2.write(0);
                beep(50);
            }
            else if (cmd == "mode_door1") {
                mode = false;
                setRGB();
            }
            else if (cmd == "mode_door2") {
                mode = true;
                setRGB();
            }
            else if (cmd.startsWith("angle:")) {
                int val = cmd.substring(6).toInt();
                if (val >= 10 && val <= 180) {
                    maxAngle = val;
                    encoder.setCount(val);
                }
            }

            updateDisplay();
        }
    }
}

// ============================================================
//  OLED
// ============================================================
void updateDisplay() {
    display.clearDisplay();
    display.setTextColor(WHITE);
    display.setTextSize(1);

    display.setCursor(0, 0);
    display.println(mode ? ">> DOOR 2 MODE <<" : ">> DOOR 1 MODE <<");
    display.drawLine(0, 10, 128, 10, WHITE);

    display.setCursor(0, 14);
    display.print("Door 1: ");
    display.println(door1Open ? "OPEN" : "CLOSED");

    display.setCursor(0, 26);
    display.print("Door 2: ");
    display.println(door2Open ? "OPEN" : "CLOSED");

    display.setCursor(0, 38);
    display.print("Max Angle: ");
    display.print(maxAngle);
    display.println(" deg");

    display.setCursor(0, 52);
    display.println(!mode ? "Control: TOUCH" : "Control: JOYSTICK");

    display.display();
}

// ============================================================
//  RGB
// ============================================================
void setRGB() {
    digitalWrite(RGB_RED,   LOW);
    digitalWrite(RGB_GREEN, LOW);
    digitalWrite(RGB_BLUE,  LOW);
    if (!mode) {
        digitalWrite(RGB_BLUE,  HIGH);
    } else {
        digitalWrite(RGB_GREEN, HIGH);
    }
}

// ============================================================
//  BUZZER
// ============================================================
void beep(int duration) {
    digitalWrite(BUZZER, HIGH);
    delay(duration);
    digitalWrite(BUZZER, LOW);
}

// ============================================================
//  WIFI
// ============================================================
void connectWiFi() {
    Serial.print("Connecting to WiFi");
    WiFi.begin(WIFI_SSID, WIFI_PASS);
    int retries = 0;
    while (WiFi.status() != WL_CONNECTED && retries < 20) {
        delay(500);
        Serial.print(".");
        retries++;
    }
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\nWiFi connected! IP: " + WiFi.localIP().toString());
    } else {
        Serial.println("\nWiFi FAILED — running offline");
    }
}

// ============================================================
//  MQTT
// ============================================================
void connectMQTT() {
    if (WiFi.status() != WL_CONNECTED) return;

    mqtt.subscribe(&cmdFeed);   // register subscription before connecting

    Serial.print("Connecting to HiveMQ");
    int retries = 0;
    int8_t ret;
    while ((ret = mqtt.connect()) != 0 && retries < 5) {
        Serial.println(" Error: " + String(mqtt.connectErrorString(ret)));
        mqtt.disconnect();
        delay(2000);
        retries++;
    }
    if (mqtt.connected()) {
        Serial.println("\nHiveMQ connected!");
    } else {
        Serial.println("\nMQTT FAILED — running offline");
    }
}

// ============================================================
//  PUBLISH STATE
// ============================================================
void publishState(int joyAngle) {
    if (!mqtt.connected()) {
        connectMQTT();
        if (!mqtt.connected()) return;
    }

    String json = "{";
    json += "\"door1\":\""  + String(door1Open ? "OPEN" : "CLOSED") + "\",";
    json += "\"door2\":\""  + String(door2Open ? "OPEN" : "CLOSED") + "\",";
    json += "\"mode\":\""   + String(mode ? "DOOR2" : "DOOR1")      + "\",";
    json += "\"maxAngle\":" + String(maxAngle)                       + ",";
    json += "\"joyAngle\":" + String(joyAngle);
    json += "}";

    if (feedState.publish(json.c_str())) {
        Serial.println("Published: " + json);
    } else {
        Serial.println("Publish failed");
    }
}
