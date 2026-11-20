#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_SHT31.h>
#include <WiFi.h>
#include <MQTT.h>
#include <mqtt_define_v2.h>

#define SHT31_ADDRESS 0x44      
#define SCL_PIN 22
#define SDA_PIN 21
#define MQ2_PIN 36

#define MQTT_TOPIC "firescout/nodes/node01/telemetry"
#define MQTT_STATUS_TOPIC "firescout/nodes/node1/status"

Adafruit_SHT31 sht31 = Adafruit_SHT31();
WiFiClient network;
MQTTClient mqtt(256);

unsigned long lastRead = 0;
unsigned long lastWiFiTry = 0;
unsigned long lastMQTTTry = 0;

void maintainWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  if (millis() - lastWiFiTry >= 10000) {
    lastWiFiTry = millis();
    Serial.println("Connecting WiFi...");
    WiFi.disconnect();
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }
}

void maintainMQTT() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (mqtt.connected()) return;

  if (millis() - lastMQTTTry >= 5000) {
    lastMQTTTry = millis();
    Serial.println("Connecting MQTT...");

    bool connected;

    if (strlen(MQTT_USER) > 0) {
      connected = mqtt.connect(
        "firescout-node-01",
        MQTT_USER,
        MQTT_PASSWORD
      );
      mqtt.publish(
        MQTT_STATUS_TOPIC,
        "online",
        true,
        1
      );
    } else {
      connected = mqtt.connect("firescout-node-01");
    }

    if (connected) {
      Serial.println("MQTT Connected!");
    } else {
      Serial.println("MQTT Connection Failed");
    }
  }
}
void setup() {
  Serial.begin(115200);
  Wire.begin(SDA_PIN, SCL_PIN);

  analogReadResolution(12);
  analogSetPinAttenuation(MQ2_PIN, ADC_11db);

  if (sht31.begin(SHT31_ADDRESS)) {
    Serial.println("SHT31 Found");
  } else {
    Serial.println("SHT31 not Found");
  }

  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  mqtt.begin(MQTT_HOST, MQTT_PORT, network);
  mqtt.setWill(
    MQTT_STATUS_TOPIC,
    "offline",
    true,
    1
  );
}

void loop() {
  maintainWiFi();
  maintainMQTT();
  if (mqtt.connected()) mqtt.loop();
    if (millis() - lastRead >= 2000) {
    lastRead = millis();

    float temp = sht31.readTemperature();
    float hum = sht31.readHumidity();
    int mq2Value = analogRead(MQ2_PIN);

    if (isnan(temp) || isnan(hum)) {
      Serial.println("SHT31 Read Failed");
      return;
    }

    Serial.println("------------------");
    Serial.printf("Temperature: %.2f C\n", temp);
    Serial.printf("Humidity: %.2f %%\n", hum);
    Serial.printf("MQ2: %d\n", mq2Value);

    char payload[200];

    snprintf(
      payload,
      sizeof(payload),
      "{\"node_id\":\"firescout_node_01\","
      "\"temperature\":%.2f,"
      "\"humidity\":%.2f,"
      "\"mq2_raw\":%d}",
      temp, hum, mq2Value
    );

    if (mqtt.connected()) {
      if (mqtt.publish(MQTT_TOPIC, payload)) {
        Serial.println("MQTT Published!");
      } else {
        Serial.println("MQTT Publish Failed");
      }
    } else {
      Serial.println("MQTT Disconnected");
    }
  }
}
