from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import os

# Import routers
from app.api.uploads import router as uploads_router
from app.api.auth import router as auth_router
from app.api.profile import router as profile_router
from app.api.agents import router as agents_router
from app.api.leads import router as leads_router
from app.api.chat import router as chat_router
from app.api.worker import router as worker_router

app = FastAPI(title="Applied Agent UI", description="UI for Resume Management and Agent Control")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API Routers
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(uploads_router, prefix="/api", tags=["Uploads"])
app.include_router(profile_router, prefix="/api/profile", tags=["Profile"])
app.include_router(agents_router, prefix="/api/agents", tags=["Agents"])
app.include_router(leads_router, prefix="/api/leads", tags=["Leads"])
app.include_router(chat_router, prefix="/api/chat", tags=["Chat"])
app.include_router(worker_router, prefix="/api/worker", tags=["Worker"])

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if not os.path.exists(static_dir):
    os.makedirs(static_dir)

# Explicit route for Login
@app.get("/login")
async def login_page():
    return FileResponse(os.path.join(static_dir, "login.html"))

# Explicit route for Index
@app.get("/")
async def index_page():
    return FileResponse(os.path.join(static_dir, "index.html"))

# Explicit route for Chat Sessions
@app.get("/chat/{session_id}")
async def chat_session_page(session_id: str):
    return FileResponse(os.path.join(static_dir, "index.html"))

# Explicit route for Profile
@app.get("/profile")
async def profile_page():
    return FileResponse(os.path.join(static_dir, "profile.html"))

# Explicit route for Jobs
@app.get("/jobs")
async def jobs_page():
    return FileResponse(os.path.join(static_dir, "jobs.html"))

app.mount("/static", StaticFiles(directory=static_dir), name="static_assets")
app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
