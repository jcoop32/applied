# 🚀 Applied: Autonomous Career Agent Platform

**Applied** is a next-generation AI career assistant designed to automate job searching and applying. Re-architected in 2026, it features a **Glassmorphic Real-Time Chat Interface** that orchestrates autonomous agents on **Google Cloud Run** using **Browser Use**.

The platform is designed for **stealth**, **scale**, and **speed**, leveraging a hybrid execution model where lightweight tasks run locally and heavy automation runs in ephemeral cloud containers.

---

## 🛠 Technology Stack

- **AI Core:** Google Gemini 2.5 Flash (via `google-genai`)
- **Automation Framework:** [Browser Use](https://browser-use.com/) + Playwright
- **Backend:** FastAPI (Python 3.11) + Uvicorn
- **Frontend:** Vanilla JS + CSS3 Glassmorphism + Server-Sent Events (SSE)
- **Database:** Supabase (PostgreSQL) + Realtime
- **Infrastructure:** Google Cloud Run (Dockerized) + MCP Bridge
- **Execution:** Hybrid (Local Docker + Cloud Dispatch)

---

## ✨ Key Features

### 🤖 Intelligent Agents
- **Resume Expert:** Parses unstructured resumes into structured JSON profiles using Gemini Vision.
- **Researcher:** Scrapes job boards (LinkedIn, Indeed, Glassdoor, etc.) using smart queries and stealth browsing.
- **Applier:** Navigate complex ATS flows (Workday, Greenhouse, Lever) to submit applications autonomously.

### 💬 Real-Time Command Center
- **Chat-First UI:** Interact with agents naturally. "Find me 5 Python jobs" or "Apply to the first one."
- **Live Execution Streaming:** Watch agents think and act in real-time. Logs are streamed via Supabase Realtime/SSE directly to the chat bubble.
- **Glassmorphic Design:** A premium, distraction-free interface built with modern CSS variables and backdrop filters.

### ☁️ Cloud-Native Architecture
- **Zero-Config Deployment:** Deploys to Google Cloud Run with a single script (`./deploy.sh`).
- **Session Persistence:** Application state is synced across devices.
- **Job Tracking:** All found leads and applications are saved to a persistent Supabase database.

---

## 🚀 Getting Started

### 1. Prerequisites
- Docker Desktop installed
- A [Supabase](https://supabase.com/) project (Free tier works great)
- A Google Cloud Project (for Cloud Run)
- [Gemini API Key](https://aistudio.google.com/)

### 2. Configuration
Create a `.env` file in the root directory:

```bash
cp .env.example .env
```

Fill in your secrets:
```env
# AI & Security
GEMINI_API_KEY=your_key_here
SECRET_KEY=generate_a_random_string

# Database
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

### 3. Local Development (Docker)
Run the entire stack locally:

```bash
docker-compose up --build
```

Access the app at: **http://localhost:8000**

### 4. Cloud Deployment
Deploy to Google Cloud Run to enable 24/7 background agents:

```bash
# Ensure gcloud is authenticated
gcloud auth login

# Run the deployment script
./deploy.sh
```

---

## 📂 Project Structure

```text
applied/
├── app/
│   ├── agents/          # Agent Logic (Worker, Researcher, Applier)
│   ├── api/             # FastAPI Endpoints (Chat, Auth, Webhooks)
│   ├── core/            # Config & Security
│   ├── services/        # Supabase Service & Agent Runner
│   └── main.py          # App Entry Point
├── static/              # Frontend (JS, CSS, Assets)
├── templates/           # HTML Templates
├── deploy.sh            # Cloud Run Deployment Script
├── Dockerfile           # Production Container
└── agent_notes.md       # 🧠 Project Knowledge Base & Debug Logs
```

## 🐛 Troubleshooting

If you encounter issues, **please check `agent_notes.md` first**. This file serves as the project's long-term memory, containing:
- Known bugs and usage patterns
- Fix strategies for common errors (WebSocket 401, Timeout issues)
- Architectural constraints
