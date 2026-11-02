import os
import json
import socket
import requests
from datetime import datetime
from flask import Flask, render_template_string, request
from cryptography.fernet import Fernet

app = Flask(__name__)

PORTS_TO_SCAN = [21, 22, 80, 443, 8080]
LEAK_PATHS = [
    "/.env",
    "/config.json",
    "/backup.sql",
    "/admin/",
    "/api/v1/device/info",
    "/status"
]

def get_or_create_key():
    key_file = "sentinel.key"
    if os.path.exists(key_file):
        with open(key_file, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(key_file, "wb") as f:
            f.write(key)
        return key

def perform_full_audit(target):
    findings = []
    
    # 1. Port Scan
    for port in PORTS_TO_SCAN:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        result = s.connect_ex((target, port))
        if result == 0:
            findings.append({"type": "OPEN_PORT", "detail": f"Port {port} is OPEN", "severity": "MEDIUM"})
        s.close()

    # 2. Web Leak Scan
    url_base = f"http://{target}" if not target.startswith("http") else target
    for path in LEAK_PATHS:
        full_url = url_base.rstrip("/") + path
        try:
            res = requests.get(full_url, timeout=2, allow_redirects=False)
            if res.status_code == 200:
                findings.append({"type": "EXPOSED_FILE", "detail": full_url, "severity": "HIGH"})
            elif res.status_code == 403:
                findings.append({"type": "RESTRICTED_PATH", "detail": full_url, "severity": "LOW"})
        except requests.exceptions.RequestException:
            pass

    save_encrypted_log(target, findings)
    return findings

def save_encrypted_log(target, findings):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    clean_target = target.replace("http://", "").replace("https://", "").replace("/", "_")
    filename = f"classified_audit_{clean_target}_{timestamp}.json.enc"
    
    report = {
        "metadata": {
            "tool": "SENTINEL-EDR",
            "target": target,
            "timestamp": str(datetime.now())
        },
        "findings": findings
    }
    
    key = get_or_create_key()
    fernet = Fernet(key)
    encrypted = fernet.encrypt(json.dumps(report, indent=4).encode('utf-8'))
    
    with open(filename, "wb") as f:
        f.write(encrypted)

def decrypt_log_file(filename):
    if not os.path.exists(filename):
        return None
    try:
        key = get_or_create_key()
        fernet = Fernet(key)
        with open(filename, "rb") as f:
            encrypted_data = f.read()
        return json.loads(fernet.decrypt(encrypted_data).decode('utf-8'))
    except Exception as e:
        return {"error": f"Decryption failed: {str(e)}"}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>SENTINEL EDR</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: monospace; background: #0f172a; color: #38bdf8; padding: 15px; margin: 0; }
        .box { max-width: 600px; margin: auto; background: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #334155; }
        h1 { color: #f87171; text-align: center; font-size: 1.4rem; margin-top: 0; }
        nav { display: flex; gap: 10px; margin-bottom: 20px; }
        nav a { flex: 1; text-align: center; padding: 10px; background: #334155; color: #38bdf8; text-decoration: none; border-radius: 4px; font-weight: bold; }
        nav a.active { background: #0284c7; color: #fff; }
        input, select, button { width: 100%; padding: 10px; margin: 8px 0; background: #0f172a; border: 1px solid #475569; color: #fff; border-radius: 4px; box-sizing: border-box; }
        button { background: #0284c7; font-weight: bold; cursor: pointer; border: none; }
        button:hover { background: #0369a1; }
        ul { padding-left: 20px; }
        .HIGH { color: #ef4444; font-weight: bold; }
        .MEDIUM { color: #f97316; }
        .LOW { color: #facc15; }
    </style>
</head>
<body>
    <div class="box">
        <h1>🛡️ SENTINEL EDR DASHBOARD</h1>
        <nav>
            <a href="/" class="{{ 'active' if page == 'scan' else '' }}">New Audit</a>
            <a href="/logs" class="{{ 'active' if page == 'logs' else '' }}">Decrypted Logs</a>
        </nav>

        {% if page == 'scan' %}
        <form method="POST">
            <label>Target Domain or IP Address:</label>
            <input type="text" name="target" placeholder="e.g. scanme.nmap.org or 192.168.163.1" required>
            <button type="submit">Run Security Audit</button>
        </form>
        {% if target %}
            <h3>Results for: {{ target }}</h3>
            <ul>
            {% for f in findings %}
                <li class="{{ f.severity }}">[{{ f.severity }}] {{ f.type }}: {{ f.detail }}</li>
            {% else %}
                <li style="color:#4ade80;">No open leaks or exposed ports detected.</li>
            {% endfor %}
            </ul>
        {% endif %}

        {% elif page == 'logs' %}
        <form method="POST">
            <label>Select Encrypted Log File:</label>
            <select name="selected_log">
                {% for log in log_files %}
                    <option value="{{ log }}">{{ log }}</option>
                {% else %}
                    <option value="">No encrypted log files found</option>
                {% endfor %}
            </select>
            <button type="submit" {{ 'disabled' if not log_files else '' }}>Decrypt & View</button>
        </form>
        {% if decrypted_data %}
            <h3>Decrypted Report Content</h3>
            <ul>
            {% for f in decrypted_data.findings %}
                <li class="{{ f.severity }}">[{{ f.severity }}] {{ f.type }}: {{ f.detail }}</li>
            {% else %}
                <li style="color:#4ade80;">No security findings were logged in this session.</li>
            {% endfor %}
            </ul>
        {% endif %}
        {% endif %}
    </div>
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def scan():
    findings, target = None, None
    if request.method == "POST":
        target = request.form.get("target")
        if target:
            findings = perform_full_audit(target)
    return render_template_string(HTML_TEMPLATE, page="scan", target=target, findings=findings)

@app.route("/logs", methods=["GET", "POST"])
def logs():
    log_files = [f for f in os.listdir(".") if f.endswith(".json.enc")]
    decrypted_data = None
    if request.method == "POST":
        selected_log = request.form.get("selected_log")
        if selected_log:
            decrypted_data = decrypt_log_file(selected_log)
    return render_template_string(HTML_TEMPLATE, page="logs", log_files=log_files, decrypted_data=decrypted_data)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True)
