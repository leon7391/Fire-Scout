
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <MQTT.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_SHT31.h>
#include <node_config.h>

#define SHT31_ADDRESS 0x44
#define SDA_PIN 21
#define SCL_PIN 22
#define MQ2_PIN 36

const unsigned long SENSOR_INTERVAL = 2000;
const unsigned long HEARTBEAT_INTERVAL = 2000;
const unsigned long WIFI_RETRY_INTERVAL = 10000;
const unsigned long MQTT_RETRY_INTERVAL = 5000;
const unsigned long SENSOR_RETRY_INTERVAL = 10000;

Adafruit_SHT31 sht31 = Adafruit_SHT31();

WiFiClient network;
MQTTClient mqtt(512);

unsigned long lastSensorTime = 0;
unsigned long lastHeartbeatTime = 0;
unsigned long lastWiFiTry = 0;
unsigned long lastMQTTTry = 0;
unsigned long lastSensorTry = 0;

uint32_t telemetrySequence = 0;

char bootId[16] = {0};

bool sht31Ready = false;
// WIFI CONNECTION
void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  unsigned long now = millis();

  if (now - lastWiFiTry >= WIFI_RETRY_INTERVAL) {
    lastWiFiTry = now;

    Serial.println("[WIFI] Reconnecting...");

    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}
// MQTT CONNECTION
void maintainMQTT() {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  if (mqtt.connected()) {
    return;
  }

  unsigned long now = millis();

  if (now - lastMQTTTry < MQTT_RETRY_INTERVAL) {
    return;
  }

  lastMQTTTry = now;

  Serial.println("[MQTT] Connecting...");

  bool connected = false;

  if (strlen(MQTT_USER) > 0) {
    connected = mqtt.connect(
      MQTT_CLIENT_ID,
      MQTT_USER,
      MQTT_PASSWORD
    );
  } else {
    connected = mqtt.connect(MQTT_CLIENT_ID);
  }

  if (connected) {
    Serial.println("[MQTT] Connected!");

    bool published = mqtt.publish(
      MQTT_STATUS_TOPIC,
      "online",
      true,
      1
    );

    if (published) {
      Serial.println("[STATUS] ONLINE published");
    } else {
      Serial.println("[STATUS] Publish failed");
    }
  } else {
    Serial.printf(
      "[MQTT] Connection failed: %d\n",
      (int)mqtt.lastError()
    );
  }
}
// SHT31 SENSOR HEALTH
void maintainSHT31() {
  if (sht31Ready) {
    return;
  }

  unsigned long now = millis();

  if (now - lastSensorTry >= SENSOR_RETRY_INTERVAL) {
    lastSensorTry = now;

    Serial.println("[SHT31] Initializing...");

    sht31Ready = sht31.begin(SHT31_ADDRESS);

    if (sht31Ready) {
      Serial.println("[SHT31] Sensor ready");
    } else {
      Serial.println("[SHT31] Sensor unavailable");
    }
  }
}
// READ AND PUBLISH TELEMETRY
void publishTelemetry() {
  if (!sht31Ready) {
    Serial.println("[SENSOR] SHT31 unavailable");
    return;
  }

  float temperature = sht31.readTemperature();
  float humidity = sht31.readHumidity();

  int mq2Raw = analogRead(MQ2_PIN);

  if (
    !isfinite(temperature) ||
    !isfinite(humidity) ||
    temperature < -40.0f ||
    temperature > 125.0f ||
    humidity < 0.0f ||
    humidity > 100.0f
  ) {
    sht31Ready = false;

    Serial.println("[SENSOR] Invalid SHT31 reading");
    return;
  }

  telemetrySequence++;

  char payload[320];

  int written = snprintf(
    payload,
    sizeof(payload),
    "{"
      "\"node_id\":\"%s\","
      "\"schema_version\":2,"
      "\"boot_id\":\"%s\","
      "\"seq\":%lu,"
      "\"uptime_ms\":%lu,"
      "\"temperature\":%.2f,"
      "\"humidity\":%.2f,"
      "\"mq2_raw\":%d,"
      "\"sensor_status\":\"OK\""
    "}",
    NODE_ID,
    bootId,
    (unsigned long)telemetrySequence,
    (unsigned long)millis(),
    temperature,
    humidity,
    mq2Raw
  );

  if (written < 0 ||
      written >= (int)sizeof(payload)) {
    Serial.println("[MQTT] Telemetry payload too large");
    return;
  }

  Serial.printf(
    "[SENSOR] Temp: %.2f C | Hum: %.2f %% | MQ2: %d\n",
    temperature,
    humidity,
    mq2Raw
  );

  if (!mqtt.connected()) {
    Serial.println("[MQTT] Telemetry skipped: offline");
    return;
  }

  bool published = mqtt.publish(
    MQTT_TELEMETRY_TOPIC,
    payload,
    false,
    0
  );

  if (published) {
    Serial.printf(
      "[TELEMETRY] Published seq=%lu\n",
      (unsigned long)telemetrySequence
    );
  } else {
    Serial.println("[TELEMETRY] Publish failed");
  }
}
// HEARTBEAT
void publishHeartbeat() {
  if (!mqtt.connected()) {
    return;
  }

  char payload[256];

  int written = snprintf(
    payload,
    sizeof(payload),
    "{"
      "\"node_id\":\"%s\","
      "\"uptime_ms\":%lu,"
      "\"wifi_rssi\":%ld,"
      "\"sht31_ok\":%s,"
      "\"mqtt_connected\":true"
    "}",
    NODE_ID,
    (unsigned long)millis(),
    (long)WiFi.RSSI(),
    sht31Ready ? "true" : "false"
  );

  if (written < 0 ||
      written >= (int)sizeof(payload)) {
    Serial.println("[HEARTBEAT] Payload too large");
    return;
  }

  bool published = mqtt.publish(
    MQTT_HEARTBEAT_TOPIC,
    payload,
    false,
    0
  );

  if (published) {
    Serial.println("[HEARTBEAT] Published");
  } else {
    Serial.println("[HEARTBEAT] Publish failed");
  }
}
// SETUP
void setup() {
  Serial.begin(115200);

  Wire.begin(SDA_PIN, SCL_PIN);

  analogReadResolution(12);
  analogSetPinAttenuation(MQ2_PIN, ADC_11db);

  snprintf(
    bootId,
    sizeof(bootId),
    "%08lx",
    (unsigned long)esp_random()
  );

  Serial.println("============================");
  Serial.println("FIRE SCOUT ESP32 FIRMWARE V2.2");
  Serial.println("============================");

  sht31Ready = sht31.begin(SHT31_ADDRESS);

  if (sht31Ready) {
    Serial.println("[SHT31] Found");
  } else {
    Serial.println("[SHT31] Not found");
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  lastWiFiTry = millis();
  lastSensorTry = millis();

  mqtt.begin(MQTT_HOST, MQTT_PORT, network);

  mqtt.setKeepAlive(10);

  mqtt.setWill(
    MQTT_STATUS_TOPIC,
    "offline",
    true,
    1
  );

  Serial.println("[SYSTEM] Setup complete");
}
// MAIN LOOP
void loop() {
  maintainWiFi();
  maintainMQTT();
  maintainSHT31();

  if (mqtt.connected()) {
    mqtt.loop();
  }

  unsigned long now = millis();

  if (now - lastSensorTime >= SENSOR_INTERVAL) {
    lastSensorTime = now;
    publishTelemetry();
  }

  if (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL) {
    lastHeartbeatTime = now;
    publishHeartbeat();
  }
}
