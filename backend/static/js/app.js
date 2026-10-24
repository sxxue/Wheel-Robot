/**
 * CYBERNAV // FYP2 Web Dashboard Client Controller
 * Handles real-time WebSockets, Speech Recognition, and Telemetry
 */

class DashboardController {
  constructor() {
    this.ws = null;
    this.currentMode = "som"; // "som" or "raw"
    this.rawImageData = null;
    this.somImageData = null;
    this.isRecording = false;
    this.speechRecognizer = null;

    this.initElements();
    this.initSpeechRecognition();
    this.bindEvents();
    this.connectWebSocket();
  }

  initElements() {
    // Status Pills
    this.serverDot = document.getElementById("server-dot");
    this.serverText = document.getElementById("server-text");
    this.robotDot = document.getElementById("robot-dot");
    this.robotText = document.getElementById("robot-text");
    this.azureDot = document.getElementById("azure-dot");
    this.azureText = document.getElementById("azure-text");

    // Viewport
    this.viewportImg = document.getElementById("viewport-img");
    this.tabSom = document.getElementById("tab-som");
    this.tabRaw = document.getElementById("tab-raw");
    this.marksLegend = document.getElementById("marks-legend");
    this.btnSnapshot = document.getElementById("btn-snapshot");

    // Voice & Commands
    this.btnMic = document.getElementById("btn-mic");
    this.micStatusText = document.getElementById("mic-status-text");
    this.commandInput = document.getElementById("command-input");
    this.btnExecute = document.getElementById("btn-execute");
    this.voiceLangSelect = document.getElementById("voice-lang-select");
    this.quickChips = document.querySelectorAll(".prompt-chip");

    // Motion Plan
    this.planContainer = document.getElementById("plan-container");
    this.planTarget = document.getElementById("plan-target");
    this.planExplanation = document.getElementById("plan-explanation");
    this.stepsList = document.getElementById("steps-list");

    // Telemetry
    this.distanceValue = document.getElementById("distance-value");
    this.distanceBarFill = document.getElementById("distance-bar-fill");
    this.distanceAlert = document.getElementById("distance-alert");

    // Logs
    this.terminalConsole = document.getElementById("terminal-console");

    // Manual D-Pad
    this.dpadBtns = document.querySelectorAll(".dpad-btn");
  }

  initSpeechRecognition() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      this.speechRecognizer = new SpeechRecognition();
      this.speechRecognizer.continuous = false;
      this.speechRecognizer.interimResults = true;
      this.currentLang = this.voiceLangSelect ? this.voiceLangSelect.value : "en-US";
      this.speechRecognizer.lang = this.currentLang;

      this.speechRecognizer.onstart = () => {
        this.isRecording = true;
        this.btnMic.classList.add("recording");
        const langText = this.voiceLangSelect ? this.voiceLangSelect.options[this.voiceLangSelect.selectedIndex].text : "English";
        this.micStatusText.innerText = `🎙️ Listening in ${langText}... Speak your command.`;
      };

      this.speechRecognizer.onresult = (event) => {
        let transcript = "";
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          transcript += event.results[i][0].transcript;
        }
        this.commandInput.value = transcript;
      };

      this.speechRecognizer.onerror = (event) => {
        console.warn("Speech recognition error:", event.error);
        this.stopRecording();
        this.micStatusText.innerText = `Microphone error (${event.error}). Type command instead.`;
      };

      this.speechRecognizer.onend = () => {
        this.stopRecording();
      };
    } else {
      this.micStatusText.innerText = "Speech API not supported in this browser. Use text input.";
    }
  }

  toggleVoice() {
    if (!this.speechRecognizer) {
      alert("Browser speech recognition is not supported. Please type in your command!");
      return;
    }
    if (this.isRecording) {
      this.speechRecognizer.stop();
    } else {
      try {
        if (this.voiceLangSelect) {
          this.currentLang = this.voiceLangSelect.value;
          this.speechRecognizer.lang = this.currentLang;
        }
        this.speechRecognizer.start();
      } catch (e) {
        console.error(e);
      }
    }
  }

  stopRecording() {
    this.isRecording = false;
    this.btnMic.classList.remove("recording");
    const langText = this.voiceLangSelect ? this.voiceLangSelect.options[this.voiceLangSelect.selectedIndex].text : "your language";
    this.micStatusText.innerText = `Ready in ${langText}. Click mic or type command.`;
  }

  bindEvents() {
    // Mode toggles
    this.tabSom.addEventListener("click", () => this.switchView("som"));
    this.tabRaw.addEventListener("click", () => this.switchView("raw"));

    // Language dropdown change
    if (this.voiceLangSelect) {
      this.voiceLangSelect.addEventListener("change", () => {
        this.currentLang = this.voiceLangSelect.value;
        if (this.speechRecognizer) {
          this.speechRecognizer.lang = this.currentLang;
        }
        const langText = this.voiceLangSelect.options[this.voiceLangSelect.selectedIndex].text;
        this.micStatusText.innerText = `Language set to ${langText}. Click mic to speak.`;
        this.log(`🌐 Speech recognition language switched to ${this.currentLang} (${langText})`);
      });
    }

    // Mic click
    this.btnMic.addEventListener("click", () => this.toggleVoice());

    // Execute button
    this.btnExecute.addEventListener("click", () => this.executeCommand());
    this.commandInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.executeCommand();
    });

    // Quick chips
    this.quickChips.forEach((chip) => {
      chip.addEventListener("click", () => {
        if (chip.dataset.lang && this.voiceLangSelect) {
          this.voiceLangSelect.value = chip.dataset.lang;
          this.currentLang = chip.dataset.lang;
          if (this.speechRecognizer) {
            this.speechRecognizer.lang = this.currentLang;
          }
        }
        this.commandInput.value = chip.dataset.prompt;
        this.executeCommand();
      });
    });

    // Snapshot button
    this.btnSnapshot.addEventListener("click", () => this.requestSnapshot());

    // Manual D-Pad buttons
    this.dpadBtns.forEach((btn) => {
      btn.addEventListener("click", () => {
        const action = btn.dataset.action;
        this.sendManualMotor(action);
      });
    });
  }

  switchView(mode) {
    this.currentMode = mode;
    if (mode === "som") {
      this.tabSom.classList.add("btn-primary");
      this.tabSom.classList.remove("btn-secondary");
      this.tabRaw.classList.remove("btn-primary");
      this.tabRaw.classList.add("btn-secondary");
      if (this.somImageData) this.viewportImg.src = this.somImageData;
    } else {
      this.tabRaw.classList.add("btn-primary");
      this.tabRaw.classList.remove("btn-secondary");
      this.tabSom.classList.remove("btn-primary");
      this.tabSom.classList.add("btn-secondary");
      if (this.rawImageData) this.viewportImg.src = this.rawImageData;
    }
  }

  connectWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws/dashboard`;

    this.log("Connecting to Cloud Orchestrator WebSocket: " + wsUrl);

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.serverDot.className = "status-dot active";
      this.serverText.innerText = "CLOUD: ONLINE";
      this.log("Connected to Cloud Orchestrator.");
    };

    this.ws.onclose = () => {
      this.serverDot.className = "status-dot error";
      this.serverText.innerText = "CLOUD: RECONNECTING...";
      this.log("WebSocket connection closed. Retrying in 3s...");
      setTimeout(() => this.connectWebSocket(), 3000);
    };

    this.ws.onerror = (err) => {
      console.error("WS error:", err);
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.handleMessage(data);
      } catch (e) {
        console.error("Error parsing WS message:", e);
      }
    };
  }

  handleMessage(msg) {
    switch (msg.type) {
      case "INITIAL_STATE":
        this.updateRobotStatus(msg.robot_connected);
        this.updateDistance(msg.tof_distance_mm);
        if (msg.som_image) {
          this.somImageData = msg.som_image;
          this.rawImageData = msg.raw_image;
          this.renderImage();
        }
        if (msg.marks) this.renderMarks(msg.marks);
        if (msg.latest_plan) this.renderPlan(msg.latest_plan);
        if (msg.ai_config) {
          this.azureDot.className = "status-dot active";
          this.azureText.innerText = msg.ai_config.status_text || "AI: GEMINI 3.8 FLASH";
          const badge = document.getElementById("ai-engine-badge");
          if (badge && msg.ai_config.provider === "gemini") {
            badge.innerText = "SPEECH + GEMINI 3.8 FLASH";
          }
        }
        break;

      case "ROBOT_STATUS":
        this.updateRobotStatus(msg.connected);
        this.log(msg.message);
        break;

      case "TELEMETRY":
        this.updateDistance(msg.tof_distance_mm);
        break;

      case "IMAGE_UPDATE":
        this.rawImageData = msg.raw_image;
        this.somImageData = msg.som_image;
        this.renderImage();
        if (msg.marks) this.renderMarks(msg.marks);
        if (msg.tof_distance_mm) this.updateDistance(msg.tof_distance_mm);
        this.log("Visual frame updated with Set-of-Mark annotations.");
        break;

      case "NEW_PLAN":
        this.renderPlan(msg.plan);
        this.log(`Plan generated: ${msg.plan.identified_target} (Dispatched: ${msg.dispatched_to_robot})`);
        break;

      case "ROBOT_LOG":
        this.log(`[ROBOT] ${msg.message}`);
        break;
    }
  }

  updateRobotStatus(connected) {
    if (connected) {
      this.robotDot.className = "status-dot active";
      this.robotText.innerText = "ROBOT: CONNECTED";
    } else {
      this.robotDot.className = "status-dot error";
      this.robotText.innerText = "ROBOT: DISCONNECTED";
    }
  }

  updateDistance(mm) {
    if (mm === undefined || mm === null) return;
    this.distanceValue.innerText = mm;

    // 0 to 1000mm scale
    const percentage = Math.min(100, Math.max(5, (mm / 1000) * 100));
    this.distanceBarFill.style.width = `${percentage}%`;

    if (mm < 150) {
      this.distanceAlert.className = "distance-alert-pill danger";
      this.distanceAlert.innerText = "COLLISION RISK (<150mm)";
    } else if (mm < 350) {
      this.distanceAlert.className = "distance-alert-pill";
      this.distanceAlert.style.color = "var(--accent-amber)";
      this.distanceAlert.innerText = "OBSTACLE NEAR";
    } else {
      this.distanceAlert.className = "distance-alert-pill";
      this.distanceAlert.style.color = "var(--accent-green)";
      this.distanceAlert.innerText = "PATH CLEAR";
    }
  }

  renderImage() {
    this.viewportImg.src = this.currentMode === "som" ? this.somImageData : this.rawImageData;
  }

  renderMarks(marks) {
    this.marksLegend.innerHTML = "";
    marks.forEach((m) => {
      const tag = document.createElement("div");
      tag.className = `mark-tag mark-${m.id}`;
      tag.innerHTML = `<strong>[${m.id}]</strong> ${m.label}`;
      this.marksLegend.appendChild(tag);
    });
  }

  renderPlan(plan) {
    if (!plan) return;
    this.planContainer.style.display = "flex";
    this.planTarget.innerText = `Target: ${plan.identified_target || "Identified Target"}`;
    this.planExplanation.innerText = plan.explanation || "Reasoning complete.";

    this.stepsList.innerHTML = "";
    if (plan.commands && Array.isArray(plan.commands)) {
      plan.commands.forEach((cmd, idx) => {
        const li = document.createElement("li");
        li.className = "step-item";
        li.innerHTML = `
          <span><span class="step-badge">#${idx + 1}</span> ${cmd.action}</span>
          <span style="color: var(--text-dim);">${cmd.degrees ? cmd.degrees + '°' : ''} ${cmd.duration_s ? cmd.duration_s + 's' : ''} (PWM ${cmd.speed || 0})</span>
        `;
        this.stepsList.appendChild(li);
      });
    }
  }

  async executeCommand() {
    const text = this.commandInput.value.trim();
    if (!text) return;

    this.log(`Dispatching command: "${text}"`);
    this.btnExecute.disabled = true;
    this.btnExecute.innerText = "Reasoning...";

    try {
      const res = await fetch("/api/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: text })
      });
      const data = await res.json();
      if (data.status === "success") {
        this.renderPlan(data.plan);
      } else {
        alert("Command failed: " + (data.message || "Unknown error"));
      }
    } catch (e) {
      console.error(e);
      alert("Error sending command to cloud server.");
    } finally {
      this.btnExecute.disabled = false;
      this.btnExecute.innerText = "Execute";
    }
  }

  async sendManualMotor(action) {
    this.log(`Manual motor control triggered: ${action}`);
    try {
      const res = await fetch("/api/test-motor", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: action, speed: 160, duration_s: 0.8 })
      });
      const data = await res.json();
      if (data.status !== "success") {
        this.log(`⚠️ Motor warning: ${data.message}`);
      }
    } catch (e) {
      this.log(`⚠️ Motor communication error: ${e}`);
    }
  }

  requestSnapshot() {
    this.log("Requesting frame snapshot from robot...");
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "REQUEST_SNAPSHOT" }));
    }
  }

  log(msg) {
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement("div");
    entry.className = "log-entry";
    entry.innerHTML = `<span class="log-time">[${time}]</span> <span class="log-msg">${msg}</span>`;
    this.terminalConsole.appendChild(entry);
    this.terminalConsole.scrollTop = this.terminalConsole.scrollHeight;
  }
}

// Instantiate on page load
document.addEventListener("DOMContentLoaded", () => {
  window.dashboard = new DashboardController();
});
