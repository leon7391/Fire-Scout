#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_Sensor.h>
#include <Adafruit_SHT31.h>

#define SHT31_ADDRESS 0x44      
#define SCL_PIN 22
#define SDA_PIN 21
#define MQ2_PIN 36

Adafruit_SHT31 sht31 = Adafruit_SHT31();

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
}

void loop() {
  float temp = sht31.readTemperature();
  float hum = sht31.readHumidity();
  int mq2Value = analogRead(MQ2_PIN);

  Serial.println("------------------------------");

  if (isnan(temp)) Serial.println("Failed to read temperature");
  else Serial.print("Temperature: "), Serial.print(temp), Serial.println(" *C");
  if (isnan(hum)) Serial.println("Failed to read humidity");
  else Serial.print("Humidity: "), Serial.print(hum), Serial.println(" %");

  Serial.print("MQ2 Value: "), Serial.println(mq2Value);
  delay(2000);
}

