# 🚀 Applied: Autonomous Career Agent

**Applied** is a vision-first AI agent designed to automate the tedious parts of the job search. Built with Python, Gemini 2.0, and Playwright, it doesn't just "find" jobs—it sees the web, understands forms, and handles the application process for you.

---

## 🛠 Features

- **Smart Discovery:** Scans job boards for roles that actually match your skills.
- **Vision-First Automation:** Navigates complex job portals (Workday, etc.) using visual coordinate mapping.
- **Dynamic Tailoring:** Rewrites resume bullet points to align with job descriptions in real-time.
- **Status Tracking:** Automatically logs into portals to check application progress.

---

## 📂 Project Structure

```text
applied/
├── main.py              # The Manager (Orchestrator)
├── agents/              # The Brains
│   ├── researcher.py    # Finds jobs
│   ├── matcher.py       # Scores compatibility
│   └── applier.py       # Handles the browser
├── utils/               # The Hands & Tools
│   ├── browser_ctrl.py  # Playwright controller
│   └── resume_parser.py # PDF processing
├── data/                # Your resume and logs
├── .env                 # API Keys (Private)
└── requirements.txt     # Python dependencies
```
