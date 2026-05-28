import os
import json
import urllib.request
import urllib.error

API_KEY = "rnd_CUMhPIu96bPiucBx3jzCKXgnaaFP"
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def request(method, url, data=None):
    req = urllib.request.Request(url, headers=HEADERS, method=method)
    if data:
        req.data = json.dumps(data).encode("utf-8")
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTPError: {e.code} {e.read().decode()}")
        exit(1)

print("Fetching Owner ID...")
owners = request("GET", "https://api.render.com/v1/owners")
if not owners:
    print("No owners found.")
    exit(1)
owner_id = owners[0]["owner"]["id"]
print(f"Owner ID: {owner_id}")

env_vars = []
env_path = "/Users/mac/.gemini/antigravity/scratch/polymarket-bot/.env"
with open(env_path, "r") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            env_vars.append({"key": key.strip(), "value": val.strip(), "generateValue": False})

# Replace MAX_RESOLUTION_DAYS to 0.04
found = False
for e in env_vars:
    if e["key"] == "MAX_RESOLUTION_DAYS":
        e["value"] = "0.04"
        found = True
if not found:
    env_vars.append({"key": "MAX_RESOLUTION_DAYS", "value": "0.04", "generateValue": False})

env_vars.append({"key": "PYTHON_VERSION", "value": "3.11.0", "generateValue": False})

payload = {
    "type": "web_service",
    "name": "polymarket-bot-2026",
    "ownerId": owner_id,
    "repo": "https://github.com/Richmondeke/polymarket-bot-2026",
    "autoDeploy": "yes",
    "branch": "main",
    "serviceDetails": {
        "env": "python",
        "region": "frankfurt",
        "plan": "free",
        "envSpecificDetails": {
            "buildCommand": "pip install -r requirements.txt",
            "startCommand": "bash start.sh"
        },
        "envVars": env_vars
    }
}

print("Creating Web Service...")
data = request("POST", "https://api.render.com/v1/services", data=payload)
print("SUCCESS!")
print("Service ID:", data.get("id"))
print("Dashboard URL:", data.get("service", {}).get("dashboardUrl", "Not found"))
print("App URL:", data.get("service", {}).get("serviceDetails", {}).get("url", "Not found"))
