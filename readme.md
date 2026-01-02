# 🚀 Applied: Autonomous Career Agent Platform

**Applied** is a vision-first AI agent platform designed to automate the job search. Now re-architected as a secure, containerized web application, it allows users to manage their resumes, profiles, and automated applications through a modern glassmorphic interface.

---

## 🛠 Tech Stack

- **Backend:** FastAPI (Python 3.11), Uvicorn
- **Frontend:** HTML5, CSS3 (Glassmorphism), Vanilla JS
- **Database & Storage:** Supabase (PostgreSQL, Blob Storage)
- **Authentication:** JWT (JSON Web Tokens) + BCrypt Hashing
- **AI Core:** Google Gemini 2.5 (via `google-genai`)
- **Automation:** Playwright (Headless Browser)
- **Infrastructure:** Docker & Docker Compose

---

## ✨ Features

### 🔐 Secure Authentication
- User Registration & Login with secure password hashing.
- **JWT-based sessions** to protect API routes and user data.
- **Data Isolation:** Each user's resumes are stored in isolated paths (`user_id/filename`).

### 📄 Resume Hub
- **Drag & Drop Upload**: Easily upload PDF/DOCX resumes.
- **Primary Resume**: The first upload is auto-starred ⭐ as your primary resume.
- **Management**: View, download, or delete resumes directly from the dashboard.

### 👤 AI Profile Parsing
- **Auto-Fill Profile**: Select your primary resume and let Gemini 2.5 parse it.
- **Structured Data**: Extracts skills, experience, and education into JSON format used for automated applications.
- **Manual Control**: Edit your profile details and parsed data at any time.

---

## 🚀 Getting Started

### 1. Prerequisites
- Docker & Docker Compose
- A [Supabase](https://supabase.com/) Project

### 2. Environment Setup
Create a `.env` file in the root directory:
```env
SUPABASE_URL="your-supabase-url"
SUPABASE_KEY="your-supabase-anon-key"
GEMINI_API_KEY="your-gemini-key"
SECRET_KEY="your-jwt-secret-key"
```


### 4. Running the App
The entire application is containerized. Simply run:

```bash
docker-compose up --build
```

Access the application at: **http://localhost:8000**

---

## 📂 Project Structure

```text
applied/
├── app/
│   ├── api/             # FastAPI Routes (Auth, Uploads, Profile)
│   ├── services/        # Supabase Client & Logic
│   ├── agents/          # AI Agents (Applier, Researcher)
│   └── utils/           # Helpers (Resume Parser, Passwords)
├── static/              # Frontend Assets (HTML, CSS, JS)
├── Dockerfile           # App Container Definition
├── docker-compose.yml   # Orchestration
├── main.py              # Application Entry Point
└── requirements.txt     # Dependencies
```
