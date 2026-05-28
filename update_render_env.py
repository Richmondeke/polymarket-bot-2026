import os
import json
import urllib.request
import urllib.error

API_KEY = "rnd_CUMhPIu96bPiucBx3jzCKXgnaaFP"
SERVICE_ID = "srv-d8b8jqdckfvc73cpiu70" # polymarket-bot-2026 (frankfurt)
HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Accept": "application/json",
    "Content-Type": "application/json"
}

def request(method, url, data=None):
    req = urllib.request.Request(url, headers=HEADERS, method=method)
    if data is not None:
        req.data = json.dumps(data).encode("utf-8")
    try:
        import ssl
        context = ssl._create_unverified_context()
        with urllib.request.urlopen(req, context=context) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        print(f"HTTPError: {e.code} {e.read().decode()}")
        exit(1)

# Read .env file
env_vars = []
env_path = ".env"
with open(env_path, "r") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            key, val = line.split("=", 1)
            # Remove inline comments if any
            if " #" in val:
                val = val.split(" #", 1)[0].strip()
            env_vars.append({"key": key.strip(), "value": val.strip()})

# Add python version if not present
if not any(e["key"] == "PYTHON_VERSION" for e in env_vars):
    env_vars.append({"key": "PYTHON_VERSION", "value": "3.11.0"})

print(f"Read {len(env_vars)} variables from .env")
print("Updating Render Environment Variables for polymarket-bot-singapore...")

# Render PUT env-vars takes a list of key/value pairs
resp = request("PUT", f"https://api.render.com/v1/services/{SERVICE_ID}/env-vars", env_vars)
print("SUCCESS!")
print(f"Updated service {SERVICE_ID} successfully.")
