#!/usr/bin/env python3
import subprocess
import select
import json
import time
import sys

try:
    import paho.mqtt.client as mqtt
    HAS_MQTT = True
except ImportError:
    HAS_MQTT = False

THINGSBOARD_HOST = "localhost"
THINGSBOARD_PORT = 1883
THINGSBOARD_TOKEN = "8iItxXH5faM3npql5T6d"

mqtt_client = None
if HAS_MQTT:
    def on_connect(c, u, f, r, v):
        print("  MQTT conectado", flush=True)
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.username_pw_set(THINGSBOARD_TOKEN)
    mqtt_client.on_connect = on_connect
    try:
        mqtt_client.connect(THINGSBOARD_HOST, THINGSBOARD_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        print(f"  [WARN] MQTT: {e}", flush=True)
        mqtt_client = None

print("  Iniciando listener Thread...", flush=True)

proc = subprocess.Popen(
    ["docker", "exec", "-i", "otbr", "script", "-q", "-c", "ot-ctl", "/dev/null"],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
)

time.sleep(3)
proc.stdin.write(b"udp open\n")
proc.stdin.flush()
time.sleep(0.5)
proc.stdin.write(b"udp bind :: 5689\n")
proc.stdin.flush()
print("  Escuchando en puerto 5689 (Thread)", flush=True)

buf = b""

while True:
    r, _, _ = select.select([proc.stdout], [], [], 5)
    if not r:
        continue
    chunk = proc.stdout.read1(4096)
    if not chunk:
        break
    buf += chunk
    while b"\n" in buf:
        line, buf = buf.split(b"\n", 1)
        line = line.strip()
        if not line or b"Done" in line or line == b">" or b"udp " in line:
            continue
        if b"bytes from" in line:
            try:
                parts = line.split(b"}")[0].split(b"{", 1)
                if len(parts) == 2:
                    msg = json.loads(b"{" + parts[1] + b"}")
                    print(f"[{msg.get('node_id','?')}] seq={msg.get('seq','?')}  temp={msg.get('temp','?')}°C", flush=True)
                    if mqtt_client:
                        mqtt_client.publish("v1/devices/me/telemetry", json.dumps(msg))
            except Exception:
                pass

print("  [INFO] Cerrando...", flush=True)
