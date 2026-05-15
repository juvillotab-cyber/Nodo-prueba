#!/usr/bin/env python3
"""
Escucha datos de sensores desde la red Thread via ot-ctl,
crea automáticamente dispositivos en ThingsBoard para cada node_id nuevo,
y publica la telemetría en el dispositivo correspondiente.
"""
import subprocess
import select
import json
import time
import os
import urllib.request
import urllib.error

# ── Cosas que probablemente quieras cambiar ──
THINGSBOARD_URL = "http://localhost:8080"
TB_USER = "tenant@thingsboard.org"
TB_PASS = "tenant"
# ─────────────────────────────────────────────

print("  Iniciando listener Thread + ThingsBoard...", flush=True)

# ── Autenticación en ThingsBoard ──
def tb_login():
    req = urllib.request.Request(
        f"{THINGSBOARD_URL}/api/auth/login",
        data=json.dumps({"username": TB_USER, "password": TB_PASS}).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())["token"]
    except Exception as e:
        print(f"  [ERROR] No se pudo autenticar en ThingsBoard: {e}", flush=True)
        return None

TB_TOKEN = tb_login()
if not TB_TOKEN:
    print("  [FATAL] Sin acceso a ThingsBoard. Saliendo.", flush=True)
    exit(1)

HEADERS = {"Content-Type": "application/json", "X-Authorization": f"Bearer {TB_TOKEN}"}

def tb_get(url):
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        resp = urllib.request.urlopen(req)
        return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def tb_post(url, data):
    req = urllib.request.Request(
        url, data=json.dumps(data).encode(),
        headers=HEADERS, method="POST",
    )
    return json.loads(urllib.request.urlopen(req).read())

def tb_post_raw(url, data):
    req = urllib.request.Request(
        url, data=data.encode(),
        headers=HEADERS, method="POST",
    )
    return urllib.request.urlopen(req).read()

# ── Cache de dispositivos: node_id → access token ──
DEVICE_CACHE = {}

def obtener_o_crear_dispositivo(node_id):
    if node_id in DEVICE_CACHE:
        return DEVICE_CACHE[node_id]

    # Verificar si ya existe
    existing = tb_get(f"{THINGSBOARD_URL}/api/tenant/devices?deviceName={node_id}")
    if existing and existing.get("data") and len(existing["data"]) > 0:
        device_id = existing["data"][0]["id"]["id"]
    else:
        # Crear nuevo dispositivo
        new_dev = tb_post(f"{THINGSBOARD_URL}/api/device", {"name": node_id, "type": "ThreadSensor"})
        device_id = new_dev["id"]["id"]
        print(f"  [NUEVO] Dispositivo creado: {node_id}", flush=True)

    # Obtener token de acceso
    creds = tb_get(f"{THINGSBOARD_URL}/api/device/{device_id}/credentials")
    token = creds["credentialsId"]
    DEVICE_CACHE[node_id] = token
    print(f"  [OK] {node_id} → token registrado", flush=True)
    return token

# ── Iniciar sesión ot-ctl ──
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
                    node_id = msg.get("node_id", "unknown")
                    print(f"[{node_id}] seq={msg.get('seq','?')}  temp={msg.get('temp','?')}°C", flush=True)
                    token = obtener_o_crear_dispositivo(node_id)
                    telemetry = json.dumps(msg)
                    tb_post_raw(
                        f"{THINGSBOARD_URL}/api/v1/{token}/telemetry",
                        telemetry,
                    )
            except Exception:
                pass

print("  [INFO] Cerrando...", flush=True)
