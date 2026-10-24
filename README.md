# CYBERNAV: Cloud-Assisted Wheeled Robot with Voice & Vision Integration
**Final Year Project (FYP2) - FTKEE**

Autonomous 2WD Wheeled Robot featuring:
- **Vision Intelligence**: Set-of-Mark (SoM) visual prompting with Azure OpenAI (GPT-4o).
- **Voice Control**: Natural language command understanding via Azure AI Speech.
- **Edge Architecture**: Lightweight Python agent on Raspberry Pi Zero 2 W with reactive Time-of-Flight (VL53L0X) collision avoidance reflexes.
- **Web Command Center**: Real-time glassmorphism web dashboard with live camera feed, telemetry gauges, and manual safety overrides.

---

## Project Structure

```
├── .github/workflows/ci.yml       # GitHub Actions automated CI/CD pipeline
├── .env.example                  # Environment variables template
├── .env                          # Local configuration (Mock Azure / Real Azure)
├── requirements.txt              # Cloud Backend dependencies
├── backend/
│   ├── main.py                   # FastAPI application (WebSocket & REST API)
│   ├── config.py                 # Configuration settings loader
│   ├── services/
│   │   ├── azure_openai.py       # GPT-4o multimodal reasoning service
│   │   ├── azure_speech.py       # Azure Speech services integration
│   │   └── som_service.py        # Set-of-Mark (SoM) visual annotator
│   └── static/                   # Web Dashboard UI
│       ├── index.html            # Dashboard markup
│       ├── css/style.css         # Dark glassmorphism stylesheet
│       └── js/app.js             # Client WebSocket & voice controller
├── edge_robot/
│   ├── robot_agent.py            # Edge Python client (Safe Dry-Run & Hardware Mode)
│   └── requirements-pi.txt       # Lightweight Pi dependencies
└── docs/
    ├── SYSTEM_ARCHITECTURE.md    # Detailed architecture & schematic specification
    └── STEP_BY_STEP_GUIDE.md     # Step-by-step roadmap and hardware guide
```

---

## Step-by-Step Testing Guide (Motors Disconnected Safe Mode)

### 1. Start the Cloud Backend & Web Dashboard
In your first terminal:
```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```
Open your browser at: **[http://localhost:8000](http://localhost:8000)**

### 2. Start the Edge Robot Agent (Safe Dry-Run)
In a second terminal (on your laptop or on the Raspberry Pi):
```bash
python edge_robot/robot_agent.py
```
*Notice:*
- The robot agent connects to `ws://localhost:8000/ws/robot`.
- The Web Dashboard immediately updates to **ROBOT: CONNECTED**.
- Telemetry distance (420 mm) and camera feed appear on screen.
- When you click or speak *"Avoid the obstacle and reach the blue door"*, the motion plan is calculated by GPT-4o and dispatched to the robot, which logs each simulated motor primitive in real-time!

---

## Pushing to GitHub

To link this local project to your GitHub account:

```bash
git add .
git commit -m "feat: initial commit with full system architecture, backend, dashboard, and edge agent"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPO_NAME.git
git push -u origin main
```
