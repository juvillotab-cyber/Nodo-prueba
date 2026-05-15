#!/usr/bin/env python3
import subprocess, select, json, time, os, urllib.request, urllib.error, urllib.parse

THINGSBOARD_URL = "http://localhost:8080"
TB_USER = "tenant@thingsboard.org"
TB_PASS = "tenant"
CACHE_FILE = os.path.expanduser("~/.tb_device_cache.json")

print("  Iniciando listener Thread + ThingsBoard...", flush=True)

if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE) as f:
        CACHE = json.load(f)
    print(f"  Cache: {len(CACHE)} dispositivos", flush=True)
else:
    CACHE = {}

def guardar_cache():
    with open(CACHE_FILE, "w") as f:
        json.dump(CACHE, f)

TOKEN = json.loads(urllib.request.urlopen(
    urllib.request.Request(f"{THINGSBOARD_URL}/api/auth/login",
        data=json.dumps({"username": TB_USER, "password": TB_PASS}).encode(),
        headers={"Content-Type": "application/json"})
).read())["token"]

HEADERS = {"Content-Type": "application/json", "X-Authorization": f"Bearer {TOKEN}"}

def api(method, path, data=None):
    req = urllib.request.Request(f"{THINGSBOARD_URL}{path}",
        data=json.dumps(data).encode() if data else None,
        headers=HEADERS, method=method)
    try:
        raw = urllib.request.urlopen(req).read()
        return json.loads(raw) if raw else True
    except urllib.error.HTTPError as e:
        print(f"  [API {e.code}] {method} {path}", flush=True)
        return None

def get_token(node_id):
    if node_id in CACHE:
        return CACHE[node_id]

    # Buscar si ya existe en ThingsBoard
    dev = api("GET", f"/api/tenant/devices?deviceName={urllib.parse.quote(node_id)}")
    if dev and dev.get("id"):
        did = dev["id"]["id"]
    else:
        # Crear nuevo
        dev = api("POST", "/api/device", {"name": node_id, "type": "default"})
        if not dev:
            return None
        did = dev["id"]["id"]
        print(f"  [NUEVO] {node_id} creado", flush=True)

    creds = api("GET", f"/api/device/{did}/credentials")
    if not creds:
        return None
    token = creds["credentialsId"]
    CACHE[node_id] = token
    guardar_cache()
    return token



proc = subprocess.Popen(
    ["docker", "exec", "-i", "otbr", "script", "-q", "-c", "ot-ctl", "/dev/null"],
    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
)
time.sleep(3)
proc.stdin.write(b"udp open\nudp bind :: 5689\n")
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
                    nid = msg.get("node_id", "?")
                    print(f"[{nid}] seq={msg.get('seq','?')}  temp={msg.get('temp','?')}°C", flush=True)
                    token = get_token(nid)
                    if token:
                        api("POST", f"/api/v1/{token}/telemetry", msg)
            except Exception as e:
                print(f"  [WARN] {e}", flush=True)

print("  [INFO] Cerrando...", flush=True)
