# ============================================================
#  Digital Twin Server
#  Bridges HiveMQ MQTT  ←→  Browser via WebSocket
#  Run : pip install flask flask-socketio paho-mqtt
#  Then: python server.py
#  Open: http://localhost:5000
# ============================================================

import json
import threading
import paho.mqtt.client as mqtt
from flask import Flask, render_template_string
from flask_socketio import SocketIO, emit
from datetime import datetime
import csv, os

# ------------------------------------------------------------
# *** CONFIGURE THESE — must match your ESP32 sketch ***
# ------------------------------------------------------------
BROKER        = "URL"
PORT          = 8883
USERNAME      = "Username"
PASSWORD      = "Password"
TOPIC_STATE   = "doorcontroller/state"
TOPIC_CMD     = "doorcontroller/commands"
LOG_FILE      = "door_log.csv"
# ------------------------------------------------------------

app       = Flask(__name__)
socketio  = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# Shared state
latest = {
    "door1":    "CLOSED",
    "door2":    "CLOSED",
    "mode":     "DOOR1",
    "maxAngle": 90,
    "joyAngle": 0,
    "connected": False
}

# CSV logging setup
write_header = not os.path.exists(LOG_FILE)
logfile = open(LOG_FILE, "a", newline="")
writer  = csv.writer(logfile)
if write_header:
    writer.writerow(["timestamp", "door1", "door2", "mode", "maxAngle", "joyAngle"])

# ── MQTT callbacks ───────────────────────────────────────────
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        latest["connected"] = True
        print("✓ HiveMQ connected")
        client.subscribe(TOPIC_STATE)
    else:
        print(f"✗ MQTT failed rc={rc}")

def on_disconnect(client, userdata, rc):
    latest["connected"] = False
    print("MQTT disconnected — will reconnect")

def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode())
        latest.update(data)
        latest["connected"] = True

        # Log to CSV
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            data.get("door1", ""),
            data.get("door2", ""),
            data.get("mode",  ""),
            data.get("maxAngle", ""),
            data.get("joyAngle", "")
        ])
        logfile.flush()

        # Push to all connected browsers
        socketio.emit("state_update", latest)
    except Exception as e:
        print(f"Parse error: {e}")

# ── Connect MQTT in background thread ────────────────────────
mqtt_client = mqtt.Client(client_id="python_server", clean_session=True)
mqtt_client.username_pw_set(USERNAME, PASSWORD)
mqtt_client.tls_set()
mqtt_client.on_connect    = on_connect
mqtt_client.on_disconnect = on_disconnect
mqtt_client.on_message    = on_message

def start_mqtt():
    print(f"Connecting MQTT to {BROKER}:{PORT}")
    mqtt_client.connect(BROKER, PORT, keepalive=60)
    mqtt_client.loop_forever()

threading.Thread(target=start_mqtt, daemon=True).start()

# ── Browser sends a command → publish to ESP32 ───────────────
@socketio.on("send_command")
def handle_command(cmd):
    mqtt_client.publish(TOPIC_CMD, cmd)
    print(f"Command sent: {cmd}")

# ── Serve the dashboard HTML ──────────────────────────────────
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

# ── Dashboard HTML (inline so it's one file) ─────────────────
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ESP32 Digital Twin</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.6.1/socket.io.min.js"></script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: system-ui, sans-serif; background: #0f0f1a; color: #e0e0f0; min-height: 100vh; }

  header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 16px 24px;
    background: #1a1a2e;
    border-bottom: 1px solid #2a2a4a;
  }
  header h1 { font-size: 16px; font-weight: 500; letter-spacing: 0.5px; }
  #status-dot {
    width: 10px; height: 10px; border-radius: 50%;
    background: #444; display: inline-block; margin-right: 8px;
    transition: background 0.4s;
  }
  #status-dot.live { background: #2ec4b6; box-shadow: 0 0 6px #2ec4b6; }
  #status-text { font-size: 13px; color: #888; }
  #msg-count { font-size: 12px; color: #555; margin-left: 16px; }

  main { padding: 24px; max-width: 1100px; margin: 0 auto; }

  .grid-top { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  .grid-mid  { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
  .grid-bot  { display: grid; grid-template-columns: 1fr; gap: 16px; }

  .card {
    background: #1a1a2e;
    border: 1px solid #2a2a4a;
    border-radius: 12px;
    padding: 20px;
  }
  .card-label {
    font-size: 11px; text-transform: uppercase; letter-spacing: 1px;
    color: #666; margin-bottom: 10px;
  }

  /* Status indicator blocks */
  .status-block {
    display: flex; align-items: center; justify-content: center;
    height: 80px; border-radius: 10px;
    font-size: 22px; font-weight: 500;
    transition: background 0.3s, color 0.3s;
  }
  .status-open   { background: #0d3d38; color: #2ec4b6; border: 1px solid #2ec4b644; }
  .status-closed { background: #3d1515; color: #e63946; border: 1px solid #e6394644; }

  /* Mode badge */
  #mode-badge {
    display: inline-block; padding: 6px 18px; border-radius: 20px;
    font-size: 14px; font-weight: 500; margin-top: 8px;
    transition: background 0.3s;
  }
  .mode-door1 { background: #1a2a4a; color: #5bc0eb; border: 1px solid #5bc0eb44; }
  .mode-door2 { background: #1a3a1a; color: #a8e063; border: 1px solid #a8e06344; }

  /* Angle display */
  #angle-val { font-size: 42px; font-weight: 300; color: #e0e0f0; line-height: 1; }
  #angle-max { font-size: 13px; color: #555; margin-top: 4px; }
  .angle-bar-bg { background: #2a2a4a; border-radius: 4px; height: 8px; margin-top: 12px; }
  .angle-bar-fg { background: #5bc0eb; border-radius: 4px; height: 8px; transition: width 0.2s; }

  /* Controls */
  .control-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
  button {
    padding: 10px 18px; border-radius: 8px; border: 1px solid #3a3a5a;
    background: #1a1a2e; color: #e0e0f0; font-size: 13px; cursor: pointer;
    transition: background 0.2s, border-color 0.2s;
  }
  button:hover { background: #2a2a4a; border-color: #5bc0eb; }
  button.btn-open  { border-color: #2ec4b644; }
  button.btn-open:hover  { background: #0d3d38; border-color: #2ec4b6; }
  button.btn-close { border-color: #e6394644; }
  button.btn-close:hover { background: #3d1515; border-color: #e63946; }
  button.btn-mode  { border-color: #5bc0eb44; }
  button.btn-mode:hover  { background: #1a2a4a; border-color: #5bc0eb; }

  input[type=range] {
    width: 100%; accent-color: #5bc0eb; margin: 10px 0;
  }
  .slider-row { display: flex; align-items: center; gap: 12px; }
  .slider-row span { min-width: 36px; text-align: right; font-size: 14px; color: #5bc0eb; }

  canvas { max-height: 180px; }

  .section-title { font-size: 13px; font-weight: 500; color: #888; margin-bottom: 14px; }
</style>
</head>
<body>

<header>
  <h1>ESP32 Door Controller — Digital Twin</h1>
  <div style="display:flex; align-items:center;">
    <span id="status-dot"></span>
    <span id="status-text">Connecting...</span>
    <span id="msg-count">0 messages</span>
  </div>
</header>

<main>

  <!-- Row 1: Door states + Mode -->
  <div class="grid-top">
    <div class="card">
      <div class="card-label">Door 1 — Touch sensor</div>
      <div class="status-block status-closed" id="door1-block">CLOSED</div>
    </div>
    <div class="card">
      <div class="card-label">Door 2 — Joystick</div>
      <div class="status-block status-closed" id="door2-block">CLOSED</div>
    </div>
    <div class="card" style="text-align:center;">
      <div class="card-label">Active mode</div>
      <div id="mode-badge" class="mode-door1">DOOR 1</div>
      <div style="margin-top:14px; font-size:12px; color:#555;">Physical button or use controls below</div>
    </div>
  </div>

  <!-- Row 2: Angle + Chart -->
  <div class="grid-mid">
    <div class="card">
      <div class="card-label">Joystick angle</div>
      <div id="angle-val">0°</div>
      <div id="angle-max">Max: 90°</div>
      <div class="angle-bar-bg"><div class="angle-bar-fg" id="angle-bar" style="width:0%"></div></div>
    </div>
    <div class="card">
      <div class="card-label">Joystick history</div>
      <canvas id="joyChart"></canvas>
    </div>
  </div>

  <!-- Row 3: Controls -->
  <div class="card" style="margin-bottom:16px;">
    <div class="section-title">Remote controls — commands sent directly to ESP32</div>

    <div style="margin-bottom:18px;">
      <div class="card-label">Door 1</div>
      <div class="control-row">
        <button class="btn-open"  onclick="cmd('door1_open')">Open Door 1</button>
        <button class="btn-close" onclick="cmd('door1_close')">Close Door 1</button>
      </div>
    </div>

    <div style="margin-bottom:18px;">
      <div class="card-label">Door 2</div>
      <div class="control-row">
        <button class="btn-open"  onclick="cmd('door2_open')">Open Door 2</button>
        <button class="btn-close" onclick="cmd('door2_close')">Close Door 2</button>
      </div>
    </div>

    <div style="margin-bottom:18px;">
      <div class="card-label">Mode</div>
      <div class="control-row">
        <button class="btn-mode" onclick="cmd('mode_door1')">Switch to Door 1 (Touch)</button>
        <button class="btn-mode" onclick="cmd('mode_door2')">Switch to Door 2 (Joystick)</button>
      </div>
    </div>

    <div>
      <div class="card-label">Set max angle — sent on release</div>
      <div class="slider-row">
        <input type="range" min="10" max="180" value="90" id="angle-slider"
               oninput="document.getElementById('slider-val').textContent=this.value+'°'"
               onchange="cmd('angle:'+this.value)">
        <span id="slider-val">90°</span>
      </div>
    </div>
  </div>

</main>

<script>
  const socket = io();
  let msgCount = 0;
  const joyData = Array(80).fill(0);

  // Chart
  const ctx = document.getElementById("joyChart").getContext("2d");
  const joyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: Array(80).fill(""),
      datasets: [{
        data: joyData,
        borderColor: "#5bc0eb",
        borderWidth: 2,
        fill: true,
        backgroundColor: "rgba(91,192,235,0.08)",
        pointRadius: 0,
        tension: 0.3
      }]
    },
    options: {
      animation: false,
      scales: {
        y: { min: 0, max: 180, grid: { color: "#2a2a4a" }, ticks: { color: "#555" } },
        x: { display: false }
      },
      plugins: { legend: { display: false } }
    }
  });

  // Update UI from incoming state
  socket.on("state_update", (d) => {
    msgCount++;
    document.getElementById("msg-count").textContent = msgCount + " messages";
    document.getElementById("status-dot").className = "live";
    document.getElementById("status-text").textContent = "Live  ";

    // Door 1
    const d1 = document.getElementById("door1-block");
    d1.textContent = d.door1;
    d1.className = "status-block " + (d.door1 === "OPEN" ? "status-open" : "status-closed");

    // Door 2
    const d2 = document.getElementById("door2-block");
    d2.textContent = d.door2;
    d2.className = "status-block " + (d.door2 === "OPEN" ? "status-open" : "status-closed");

    // Mode
    const mb = document.getElementById("mode-badge");
    mb.textContent = d.mode;
    mb.className = "mode-badge " + (d.mode === "DOOR1" ? "mode-door1" : "mode-door2");

    // Angle
    const joy = d.joyAngle || 0;
    const max = d.maxAngle || 90;
    document.getElementById("angle-val").textContent = joy + "°";
    document.getElementById("angle-max").textContent = "Max: " + max + "°";
    document.getElementById("angle-bar").style.width = Math.round((joy / 180) * 100) + "%";

    // Sync slider if max angle changed from encoder
    document.getElementById("angle-slider").value = max;
    document.getElementById("slider-val").textContent = max + "°";

    // Chart
    joyData.push(joy);
    joyData.shift();
    joyChart.data.datasets[0].data = [...joyData];
    joyChart.update("none");
  });

  socket.on("disconnect", () => {
    document.getElementById("status-dot").className = "";
    document.getElementById("status-text").textContent = "Offline";
  });

  function cmd(c) {
    socket.emit("send_command", c);
    console.log("Sent:", c);
  }
</script>
</body>
</html>
"""

# ── Run ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Dashboard running at http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
