#!/usr/bin/env python3
import socket
import struct
import json

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False
    print("  [INFO] paho-mqtt no instalado. Solo se imprimirá en consola.")
    print("  Para instalarlo: pip install paho-mqtt")

PUERTO = 5689
GRUPO_MULTICAST = "ff03::1"

THINGSBOARD_HOST = "localhost"
THINGSBOARD_PORT = 1883
THINGSBOARD_TOKEN = "COLOCA_AQUI_TU_TOKEN"

mqtt_client = None
if HAS_MQTT:
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.username_pw_set(THINGSBOARD_TOKEN)
    mqtt_client.on_connect = lambda c, u, f, r, v: print(f"  MQTT conectado (rc={v})")
    try:
        mqtt_client.connect(THINGSBOARD_HOST, THINGSBOARD_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"  [WARN] No se pudo conectar a ThingsBoard: {e}")
        mqtt_client = None

sock = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

for iface_name in ["wpan0", "eth0", "wlan0"]:
    try:
        ifidx = socket.if_nametoindex(iface_name)
        sock.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_JOIN_GROUP,
                        struct.pack("16sI", socket.inet_pton(socket.AF_INET6, GRUPO_MULTICAST), ifidx))
        print(f"  unido a {GRUPO_MULTICAST} en {iface_name}")
    except (OSError, AttributeError):
        pass

sock.bind(("", PUERTO))
print(f"Escuchando en puerto {PUERTO} ...")

while True:
    datos, addr = sock.recvfrom(1024)
    try:
        msg = json.loads(datos.decode())
        print(f"[{addr[0]}] node={msg['node_id']}  seq={msg['seq']}  temp={msg['temp']}°C")

        if mqtt_client:
            telemetry = json.dumps({
                "node_id": msg["node_id"],
                "temperature": msg["temp"],
                "seq": msg["seq"]
            })
            mqtt_client.publish("v1/devices/me/telemetry", telemetry)
    except Exception as e:
        print(f"[{addr[0]}] error: {e}")
