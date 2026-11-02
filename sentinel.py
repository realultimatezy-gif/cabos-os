import os
import json
import uuid
import time
import socket
import threading
import requests
from datetime import datetime
from flask import Flask, render_template_string, request, session, redirect, url_for, Response, jsonify
from cryptography.fernet import Fernet

try:
    import psutil
except ImportError:
    psutil = None

app = Flask(__name__)
app.secret_key = os.urandom(24)

AUTHOR_SIGNATURE = "Sentinel by ultimatezy"
DASHBOARD_PASSWORD = "admin"
SETTINGS_FILE = "sentinel_settings.json"

DEFAULT_PORTS = [21, 22, 80, 443, 8080]
LEAK_PATHS = [
    "/.env",
    "/config.json",
    "/backup.sql",
    "/admin/",
    "/api/v1/device/info",
    "/status"
]

ACTIVE_JOBS = {}
LOGIN_ATTEMPTS = {}
MAX_LOGIN_ATTEMPTS = 5
LOCKOUT_TIME = 60  # seconds

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"discord_webhook": "", "telegram_token": "", "telegram_chat_id": ""}

def save_settings(data):
    with open(SETTINGS_FILE, "w") as f:
        json.dump(data, f, indent=4)

def parse_ports(port_str):
    if not port_str or not port_str.strip():
        return DEFAULT_PORTS
    ports = set()
    parts = port_str.split(',')
    for part in parts:
        part = part.strip()
        if '-' in part:
            try:
                start, end = map(int, part.split('-'))
                if 1 <= start <= 65535 and 1 <= end <= 65535 and start <= end:
                    if (end - start) > 100:
                        end = start + 100
                    ports.update(range(start, end + 1))
            except ValueError:
                pass
        else:
            try:
                p = int(part)
                if 1 <= p <= 65535:
                    ports.add(p)
            except ValueError:
                pass
    return sorted(list(ports)) if ports else DEFAULT_PORTS

def is_rate_limited(ip):
    now = time.time()
    if ip in LOGIN_ATTEMPTS:
        attempts, first_attempt = LOGIN_ATTEMPTS[ip]
        if now - first_attempt > LOCKOUT_TIME:
            LOGIN_ATTEMPTS[ip] = (0, now)
            return False
        if attempts >= MAX_LOGIN_ATTEMPTS:
            return True
    return False

def record_failed_login(ip):
    now = time.time()
    if ip in LOGIN_ATTEMPTS:
        attempts, first_attempt = LOGIN_ATTEMPTS[ip]
        if now - first_attempt > LOCKOUT_TIME:
            LOGIN_ATTEMPTS[ip] = (1, now)
        else:
            LOGIN_ATTEMPTS[ip] = (attempts + 1, first_attempt)
    else:
        LOGIN_ATTEMPTS[ip] = (1, now)

def clear_login_attempts(ip):
    if ip in LOGIN_ATTEMPTS:
        del LOGIN_ATTEMPTS[ip]

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

def send_discord_notification(target, findings):
    settings = load_settings()
    url = settings.get("discord_webhook", "").strip()
    if not url:
        return

    high_count = sum(1 for f in findings if f.get("severity") == "HIGH")
    med_count = sum(1 for f in findings if f.get("severity") == "MEDIUM")
    low_count = sum(1 for f in findings if f.get("severity") == "LOW")

    description = f"**Target:** `{target}`\n"
    description += f"**Findings:** {len(findings)} total ({high_count} High, {med_count} Med, {low_count} Low)\n\n"

    if findings:
        description += "**Details:**\n"
        for f in findings[:5]:
            description += f"• `[{f['severity']}]` {f['type']}: {f['detail']}\n"
        if len(findings) > 5:
            description += f"...and {len(findings) - 5} more."
    else:
        description += "✅ No security findings detected."

    payload = {
        "embeds": [{
            "title": "🛡️ Sentinel Audit Completed",
            "description": description,
            "color": 15158332 if high_count > 0 else 3066993,
            "footer": {"text": AUTHOR_SIGNATURE}
        }]
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"[!] Discord alert failed: {e}")

def send_telegram_notification(target, findings):
    settings = load_settings()
    token = settings.get("telegram_token", "").strip()
    chat_id = settings.get("telegram_chat_id", "").strip()
    if not token or not chat_id:
        return

    high_count = sum(1 for f in findings if f.get("severity") == "HIGH")
    med_count = sum(1 for f in findings if f.get("severity") == "MEDIUM")

    msg = f"🛡️ *Sentinel Audit Completed*\n"
    msg += f"*Target:* `{target}`\n"
    msg += f"*Findings:* {len(findings)} total ({high_count} High, {med_count} Med)\n\n"

    if findings:
        for f in findings[:5]:
            msg += f"• `[{f['severity']}]` {f['type']}: {f['detail']}\n"
        if len(findings) > 5:
            msg += f"...and {len(findings) - 5} more."
    else:
        msg += "✅ No security findings detected."

    api_url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(api_url, json=payload, timeout=5)
    except Exception as e:
        print(f"[!] Telegram alert failed: {e}")

def async_audit_worker(job_id, target, ports_to_scan):
    ACTIVE_JOBS[job_id] = {
        "target": target,
        "ports": ports_to_scan,
        "status": "RUNNING",
        "findings": []
    }
    findings = []

    for port in ports_to_scan:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1.0)
        result = s.connect_ex((target, port))
        if result == 0:
            findings.append({"type": "OPEN_PORT", "detail": f"Port {port} is OPEN", "severity": "MEDIUM"})
        s.close()

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
    ACTIVE_JOBS[job_id]["status"] = "COMPLETED"
    ACTIVE_JOBS[job_id]["findings"] = findings

    threading.Thread(target=send_discord_notification, args=(target, findings)).start()
    threading.Thread(target=send_telegram_notification, args=(target, findings)).start()

def save_encrypted_log(target, findings):
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    clean_target = target.replace("http://", "").replace("https://", "").replace("/", "_")
    filename = f"classified_audit_{clean_target}_{timestamp}.json.enc"
    
    report = {
        "metadata": {
            "tool": "SENTINEL-EDR",
            "signature": AUTHOR_SIGNATURE,
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
    <title>Sentinel by ultimatezy</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    {% if auto_refresh %}
    <meta http-equiv="refresh" content="5">
    {% endif %}
    <style>
        body { font-family: monospace; background: #0f172a; color: #38bdf8; padding: 15px; margin: 0; }
        .box { max-width: 600px; margin: auto; background: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #334155; }
        h1 { color: #f87171; text-align: center; font-size: 1.4rem; margin-top: 0; margin-bottom: 5px; }
        .signature { text-align: center; color: #94a3b8; font-size: 0.85rem; margin-bottom: 15px; font-weight: bold; }
        nav { display: flex; gap: 4px; margin-bottom: 20px; flex-wrap: wrap; }
        nav a { flex: 1; min-width: 90px; text-align: center; padding: 8px 4px; background: #334155; color: #38bdf8; text-decoration: none; border-radius: 4px; font-weight: bold; font-size: 0.75rem; }
        nav a.active { background: #0284c7; color: #fff; }
        input, select, button, .btn-action { width: 100%; padding: 10px; margin: 8px 0; background: #0f172a; border: 1px solid #475569; color: #fff; border-radius: 4px; box-sizing: border-box; display: block; text-align: center; text-decoration: none; font-weight: bold; }
        button, .btn-action { background: #0284c7; cursor: pointer; border: none; }
        button:hover, .btn-action:hover { background: #0369a1; }
        .btn-html { background: #10b981; }
        .btn-html:hover { background: #059669; }
        .btn-csv { background: #f59e0b; }
        .btn-csv:hover { background: #d97706; }
        .btn-json { background: #8b5cf6; }
        .btn-json:hover { background: #7c3aed; }
        .badge { padding: 4px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: bold; }
        .RUNNING { background: #f97316; color: #fff; }
        .COMPLETED { background: #22c55e; color: #fff; }
        ul { padding-left: 20px; }
        .HIGH { color: #ef4444; font-weight: bold; }
        .MEDIUM { color: #f97316; }
        .LOW { color: #facc15; }
        footer { margin-top: 20px; text-align: center; font-size: 0.75rem; color: #64748b; }
        .logout { display: inline-block; text-align: right; width: 100%; color: #ef4444; text-decoration: none; font-size: 0.8rem; margin-bottom: 10px; }
        .refresh-status { font-size: 0.75rem; color: #f97316; text-align: center; margin-top: 5px; font-weight: bold; }
        .hint { font-size: 0.75rem; color: #64748b; margin-top: -4px; margin-bottom: 8px; }
        .btn-group { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
        .metric-card { background: #0f172a; padding: 12px; margin-bottom: 10px; border-radius: 4px; border: 1px solid #334155; display: flex; justify-content: space-between; align-items: center; }
        .metric-value { font-size: 1.2rem; font-weight: bold; color: #38bdf8; }
    </style>
</head>
<body>
    <div class="box">
        <h1>🛡️ SENTINEL EDR DASHBOARD</h1>
        <div class="signature">Signed by: {{ signature }}</div>
        
        {% if session.get('authenticated') %}
        <a href="/logout" class="logout">[ Logout ]</a>
        <nav>
            <a href="/" class="{{ 'active' if page == 'scan' else '' }}">New Audit</a>
            <a href="/logs" class="{{ 'active' if page == 'logs' else '' }}">Decrypted Logs</a>
            <a href="/settings" class="{{ 'active' if page == 'settings' else '' }}">Webhooks</a>
            <a href="/monitor" class="{{ 'active' if page == 'monitor' else '' }}">System Monitor</a>
        </nav>

        {% if page == 'scan' %}
        <form method="POST">
            <label>Target Domain or IP Address:</label>
            <input type="text" name="target" placeholder="e.g. scanme.nmap.org or 192.168.1.1" required>
            
            <label>Custom Ports / Port Ranges:</label>
            <input type="text" name="ports" placeholder="e.g. 80, 443, 8000-8080 (Leave blank for default)">
            <div class="hint">Accepts single ports (80) or ranges (20-100). Defaults to 21,22,80,443,8080.</div>

            <button type="submit">Start Async Background Scan</button>
        </form>

        {% if auto_refresh %}
            <div class="refresh-status">⚡ Scan in progress... Auto-refreshing every 5 seconds.</div>
        {% endif %}

        {% if jobs %}
            <h3>Active & Recent Scan Tasks</h3>
            {% for jid, info in jobs.items() %}
                <div style="background:#0f172a; padding:10px; margin-bottom:10px; border-radius:4px;">
                    <div><strong>Target:</strong> {{ info.target }}</div>
                    <div style="font-size:0.8rem; color:#94a3b8;"><strong>Scanned Ports:</strong> {{ info.ports }}</div>
                    <div style="margin-top:5px;">
                        <strong>Status:</strong> <span class="badge {{ info.status }}">{{ info.status }}</span>
                    </div>
                    {% if info.status == 'COMPLETED' %}
                        <ul>
                        {% for f in info.findings %}
                            <li class="{{ f.severity }}">[{{ f.severity }}] {{ f.type }}: {{ f.detail }}</li>
                        {% else %}
                            <li style="color:#4ade80;">No leaks or open ports detected on tested targets.</li>
                        {% endfor %}
                        </ul>
                    {% endif %}
                </div>
            {% endfor %}
        {% endif %}

        {% elif page == 'logs' %}
        <form method="POST">
            <label>Select Encrypted Log File:</label>
            <select name="selected_log">
                {% for log in log_files %}
                    <option value="{{ log }}" {{ 'selected' if selected_log == log else '' }}>{{ log }}</option>
                {% else %}
                    <option value="">No encrypted log files found</option>
                {% endfor %}
            </select>
            <button type="submit" {{ 'disabled' if not log_files else '' }}>Decrypt & View</button>
        </form>
        {% if decrypted_data %}
            <h3>Decrypted Report Content</h3>
            <p style="font-size: 0.8rem; color: #94a3b8;">Author: {{ decrypted_data.metadata.signature }}</p>
            <ul>
            {% for f in decrypted_data.findings %}
                <li class="{{ f.severity }}">[{{ f.severity }}] {{ f.type }}: {{ f.detail }}</li>
            {% else %}
                <li style="color:#4ade80;">No security findings were logged in this session.</li>
            {% endfor %}
            </ul>
            <div class="btn-group">
                <a href="/export/{{ selected_log }}" class="btn-action btn-html">📥 HTML</a>
                <a href="/export_csv/{{ selected_log }}" class="btn-action btn-csv">📊 CSV</a>
                <a href="/export_json/{{ selected_log }}" class="btn-action btn-json">📦 JSON</a>
            </div>
        {% endif %}

        {% elif page == 'settings' %}
        <h3>Webhook Notifications</h3>
        {% if msg %}
            <p style="color:#22c55e; text-align:center; font-weight:bold;">{{ msg }}</p>
        {% endif %}
        <form method="POST" action="/settings">
            <label>Discord Webhook URL:</label>
            <input type="text" name="discord_webhook" value="{{ settings.discord_webhook }}" placeholder="https://discord.com/api/webhooks/...">
            
            <label>Telegram Bot Token:</label>
            <input type="text" name="telegram_token" value="{{ settings.telegram_token }}" placeholder="e.g. 8838099072:ABCdef...">
            
            <label>Telegram Chat ID:</label>
            <input type="text" name="telegram_chat_id" value="{{ settings.telegram_chat_id }}" placeholder="e.g. 6988588938">

            <button type="submit">Save Webhook Settings</button>
        </form>

        {% elif page == 'monitor' %}
        <h3>🖥️ Live System Resource Monitor</h3>
        <p style="font-size:0.8rem; color:#94a3b8; text-align:center;">Real-time Termux device health metrics</p>
        
        <div class="metric-card">
            <div>CPU Usage</div>
            <div class="metric-value" id="cpu-val">--</div>
        </div>
        <div class="metric-card">
            <div>Memory Usage</div>
            <div class="metric-value" id="mem-val">--</div>
        </div>
        <div class="metric-card">
            <div>Disk Usage</div>
            <div class="metric-value" id="disk-val">--</div>
        </div>

        <script>
        async function fetchStats() {
            try {
                let res = await fetch('/api/system-stats');
                if (res.ok) {
                    let data = await res.json();
                    document.getElementById('cpu-val').innerText = data.cpu + '%';
                    document.getElementById('mem-val').innerText = data.memory + '%';
                    document.getElementById('disk-val').innerText = data.disk + '%';
                }
            } catch(e) {}
        }
        setInterval(fetchStats, 3000);
        fetchStats();
        </script>
        {% endif %}

        {% else %}
        <form method="POST" action="/login">
            <label>Dashboard Access Password:</label>
            <input type="password" name="password" placeholder="Enter Access Password" required>
            <button type="submit">Unlock Dashboard</button>
        </form>
        {% if error %}
            <p style="color:#ef4444; text-align:center; font-weight:bold;">{{ error }}</p>
        {% endif %}
        {% endif %}

        <footer>Secured with AES-128 | {{ signature }}</footer>
    </div>
</body>
</html>
"""

@app.route("/login", methods=["POST"])
def login():
    client_ip = request.remote_addr
    if is_rate_limited(client_ip):
        return render_template_string(HTML_TEMPLATE, page="login", error="Too many failed login attempts. Locked out for 60 seconds.", signature=AUTHOR_SIGNATURE), 429

    entered_pw = request.form.get("password")
    if entered_pw == DASHBOARD_PASSWORD:
        clear_login_attempts(client_ip)
        session['authenticated'] = True
        return redirect(url_for('scan'))

    record_failed_login(client_ip)
    return render_template_string(HTML_TEMPLATE, page="login", error="Invalid Password", signature=AUTHOR_SIGNATURE)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('scan'))

@app.route("/", methods=["GET", "POST"])
def scan():
    if not session.get('authenticated'):
        return render_template_string(HTML_TEMPLATE, page="login", signature=AUTHOR_SIGNATURE)
        
    if request.method == "POST":
        target = request.form.get("target")
        raw_ports = request.form.get("ports")
        if target:
            ports = parse_ports(raw_ports)
            job_id = str(uuid.uuid4())[:8]
            t = threading.Thread(target=async_audit_worker, args=(job_id, target, ports))
            t.daemon = True
            t.start()

    has_running_jobs = any(info["status"] == "RUNNING" for info in ACTIVE_JOBS.values())
            
    return render_template_string(HTML_TEMPLATE, page="scan", jobs=ACTIVE_JOBS, signature=AUTHOR_SIGNATURE, auto_refresh=has_running_jobs)

@app.route("/logs", methods=["GET", "POST"])
def logs():
    if not session.get('authenticated'):
        return render_template_string(HTML_TEMPLATE, page="login", signature=AUTHOR_SIGNATURE)

    log_files = [f for f in os.listdir(".") if f.endswith(".json.enc")]
    decrypted_data = None
    selected_log = None
    if request.method == "POST":
        selected_log = request.form.get("selected_log")
        if selected_log:
            decrypted_data = decrypt_log_file(selected_log)
    return render_template_string(HTML_TEMPLATE, page="logs", log_files=log_files, decrypted_data=decrypted_data, selected_log=selected_log, signature=AUTHOR_SIGNATURE, auto_refresh=False)

@app.route("/settings", methods=["GET", "POST"])
def settings_page():
    if not session.get('authenticated'):
        return render_template_string(HTML_TEMPLATE, page="login", signature=AUTHOR_SIGNATURE)

    msg = None
    if request.method == "POST":
        discord_url = request.form.get("discord_webhook", "").strip()
        telegram_token = request.form.get("telegram_token", "").strip()
        telegram_chat_id = request.form.get("telegram_chat_id", "").strip()

        new_settings = {
            "discord_webhook": discord_url,
            "telegram_token": telegram_token,
            "telegram_chat_id": telegram_chat_id
        }
        save_settings(new_settings)
        msg = "Webhook configuration saved successfully!"

    current_settings = load_settings()
    return render_template_string(HTML_TEMPLATE, page="settings", settings=current_settings, msg=msg, signature=AUTHOR_SIGNATURE, auto_refresh=False)

@app.route("/monitor")
def monitor_page():
    if not session.get('authenticated'):
        return redirect(url_for('scan'))
    return render_template_string(HTML_TEMPLATE, page="monitor", signature=AUTHOR_SIGNATURE, auto_refresh=False)

@app.route("/api/system-stats")
def system_stats():
    if not session.get('authenticated'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    cpu = 0
    memory = 0
    disk = 0
    if psutil:
        try:
            cpu = psutil.cpu_percent(interval=None)
            memory = psutil.virtual_memory().percent
            disk = psutil.disk_usage('/').percent
        except Exception:
            pass

    return jsonify({
        'cpu': cpu,
        'memory': memory,
        'disk': disk
    })

@app.route("/export/<filename>")
def export_report(filename):
    if not session.get('authenticated'):
        return redirect(url_for('scan'))

    decrypted_data = decrypt_log_file(filename)
    if not decrypted_data or "error" in decrypted_data:
        return "Log file invalid or decryption failed.", 400

    target = decrypted_data["metadata"]["target"]
    timestamp = decrypted_data["metadata"]["timestamp"]
    findings = decrypted_data["findings"]

    findings_html = ""
    for f in findings:
        findings_html += f"<li><strong>[{f['severity']}] {f['type']}:</strong> {f['detail']}</li>\n"
    if not findings:
        findings_html = "<li style='color:green;'>No security findings detected.</li>"

    html_report = f"""<!DOCTYPE html>
<html>
<head>
    <title>Audit Report - {target}</title>
    <style>
        body {{ font-family: monospace; background: #0f172a; color: #38bdf8; padding: 20px; }}
        .box {{ max-width: 600px; margin: auto; background: #1e293b; padding: 20px; border-radius: 8px; border: 1px solid #334155; }}
        h1 {{ color: #f87171; }}
        ul {{ padding-left: 20px; }}
        .footer {{ margin-top: 20px; font-size: 0.8rem; color: #64748b; border-top: 1px solid #334155; padding-top: 10px; }}
    </style>
</head>
<body>
    <div class="box">
        <h1>🛡️ SENTINEL SECURITY REPORT</h1>
        <p><strong>Target:</strong> {target}</p>
        <p><strong>Timestamp:</strong> {timestamp}</p>
        <p><strong>Auditor Signature:</strong> {AUTHOR_SIGNATURE}</p>
        <hr style="border-color: #334155;">
        <h3>Findings</h3>
        <ul>{findings_html}</ul>
        <div class="footer">Generated by Sentinel EDR | {AUTHOR_SIGNATURE}</div>
    </div>
</body>
</html>"""

    out_name = filename.replace(".json.enc", ".html")
    return Response(
        html_report,
        mimetype="text/html",
        headers={"Content-disposition": f"attachment; filename={out_name}"}
    )

@app.route("/export_csv/<filename>")
def export_csv(filename):
    if not session.get('authenticated'):
        return redirect(url_for('scan'))

    decrypted_data = decrypt_log_file(filename)
    if not decrypted_data or "error" in decrypted_data:
        return "Log file invalid or decryption failed.", 400

    findings = decrypted_data.get("findings", [])
    csv_lines = ["Type,Severity,Detail"]
    for f in findings:
        detail_clean = f['detail'].replace('"', '""')
        csv_lines.append(f'"{f["type"]}","{f["severity"]}","{detail_clean}"')

    csv_content = "\n".join(csv_lines)
    out_name = filename.replace(".json.enc", ".csv")

    return Response(
        csv_content,
        mimetype="text/csv",
        headers={"Content-disposition": f"attachment; filename={out_name}"}
    )

@app.route("/export_json/<filename>")
def export_json(filename):
    if not session.get('authenticated'):
        return redirect(url_for('scan'))

    decrypted_data = decrypt_log_file(filename)
    if not decrypted_data or "error" in decrypted_data:
        return "Log file invalid or decryption failed.", 400

    json_content = json.dumps(decrypted_data, indent=4)
    out_name = filename.replace(".json.enc", ".json")

    return Response(
        json_content,
        mimetype="application/json",
        headers={"Content-disposition": f"attachment; filename={out_name}"}
    )

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, threaded=True)
