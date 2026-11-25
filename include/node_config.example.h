
#pragma once

// Unique node number: "01", "02", "03", ...
#define NODE_NUMBER "01"

#define NODE_ID "firescout_node_" NODE_NUMBER
#define MQTT_CLIENT_ID "firescout-node-" NODE_NUMBER

// WIFI CONFIGURATION
#define WIFI_SSID "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"

// MQTT CONFIGURATION
#define MQTT_HOST "YOUR_BROKER_IP"
#define MQTT_PORT 1883

#define MQTT_USER "YOUR_MQTT_USERNAME"
#define MQTT_PASSWORD "YOUR_MQTT_PASSWORD"

// MQTT TOPICS 
#define MQTT_TELEMETRY_TOPIC \
    "firescout/nodes/node" NODE_NUMBER "/telemetry"

#define MQTT_STATUS_TOPIC \
    "firescout/nodes/node" NODE_NUMBER "/status"

#define MQTT_HEARTBEAT_TOPIC \
    "firescout/nodes/node" NODE_NUMBER "/heartbeat"
