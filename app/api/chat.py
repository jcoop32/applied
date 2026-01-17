from fastapi import APIRouter, Depends, HTTPException, Body
from app.api.auth import get_current_user
from app.agents.chat_agent import ChatAgent
from app.services.supabase_client import supabase_service
import os
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Chat"

class UpdateSessionRequest(BaseModel):
    title: str

class MessageRequest(BaseModel):
    message: str
    session_id: Optional[str] = None # Optional for legacy/first-msg auto-create
    # history: List[dict] = [] # We'll fetch from DB now

@router.get("/sessions")
async def get_sessions(current_user: dict = Depends(get_current_user)):
    return supabase_service.get_chat_sessions(current_user['id'])

@router.post("/sessions")
async def create_session(
    payload: CreateSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    session = supabase_service.create_chat_session(current_user['id'], payload.title)
    if not session:
        raise HTTPException(status_code=500, detail="Failed to create session")
    return session

@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: int,
    payload: UpdateSessionRequest,
    current_user: dict = Depends(get_current_user)
):
    session = supabase_service.update_chat_session_title(session_id, payload.title)
    if not session:
        raise HTTPException(status_code=500, detail="Failed to update session")
    return session

@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: int,
    current_user: dict = Depends(get_current_user)
):
    # Security: In real app, verify user owns session
    success = supabase_service.delete_chat_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete session")
    return {"status": "success"}

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    # Security: Verify session belongs to user? 
    # (Supabase RLS would handle this, but for now we trust ID or check ownership if strict)
    # Fast check:
    # session = ... get session ... if session.user_id != cur_id ...
    # proceeding with read
    return supabase_service.get_chat_history(session_id)

@router.post("/message")
async def chat_message(
    payload: MessageRequest,
    current_user: dict = Depends(get_current_user)
):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Gemini API Key missing")
    
    user_id = current_user['id']
    session_id = payload.session_id

    # 1. If no session, create one
    if not session_id:
        # Title based on first few words
        title = (payload.message[:30] + "...") if len(payload.message) > 30 else payload.message
        session = supabase_service.create_chat_session(user_id, title)
        if session:
            session_id = session['id']
        else:
             raise HTTPException(status_code=500, detail="Failed to init session")

    # 2. Save User Message
    supabase_service.save_chat_message(session_id, "user", payload.message)

    # 3. Fetch Available Resumes for Context
    resumes_list = supabase_service.list_resumes(user_id)
    available_resumes = [r['name'] for r in resumes_list]

    # 4. Fetch History (from DB)
    db_history = supabase_service.get_chat_history(session_id)
    history = [{"role": msg['role'], "content": msg['content']} for msg in db_history if msg['content'] != payload.message]

    # Initialize Agent
    agent = ChatAgent(api_key=api_key)
    
    # Generate Response (with Tools)
    agent_response = await agent.generate_response(
        user_id=user_id,
        message=payload.message,
        history=history,
        available_resumes=available_resumes
    )
    
    response_text = agent_response["content"]
    action = agent_response["action"]
    
    # 5. Handle Actions (if any)
    if action:
        if action["type"] == "research":
            # Extract args
            args = action["payload"]
            resume_filename = args.get("resume_filename")
            limit = int(args.get("limit", 20))
            job_title = args.get("job_title_override")
            location = args.get("location_override")
            
            # Validate Resume
            if resume_filename not in available_resumes:
                response_text += f"\n\n(Internal Note: Attempted to use invalid resume '{resume_filename}'. Defaulting logic needed?)"
                # Just fail safely or let runner handle 
            
            # Trigger Research Pipeline
            from app.services.agent_runner import run_research_pipeline, update_research_status
            
            # Update Status immediately
            update_research_status(user_id, resume_filename, "SEARCHING")
            
            background_tasks.add_task(
                run_research_pipeline,
                user_id=user_id,
                resume_filename=resume_filename,
                api_key=api_key,
                limit=limit,
                job_title=job_title,
                location=location,
                search_provider="google", # Default
                session_id=session_id
            )

        elif action["type"] == "apply":
            args = action["payload"]
            job_url = args.get("job_url")
            resume_filename = args.get("resume_filename")
            extra_instructions = args.get("extra_instructions")
            mode = args.get("mode", "cloud")
            
            use_cloud = (mode == "cloud")
            
            # Trigger Apply Pipeline
            from app.services.agent_runner import run_applier_task
            
            # Get Context
            user_data = supabase_service.get_user_by_email(current_user['email'])
            profile_blob = user_data.get('profile_data', {})
            if 'email' not in profile_blob: profile_blob['email'] = current_user['email']
            if 'full_name' not in profile_blob and user_data.get('full_name'): profile_blob['full_name'] = user_data.get('full_name')
            
            if extra_instructions:
                profile_blob['apply_instructions'] = extra_instructions
            
            # Update Status
            supabase_service.update_lead_status_by_url(user_id, job_url, "IN_PROGRESS", resume_filename=resume_filename)

            # Wrapper for download & run
            import asyncio
            async def _run_apply():
                try:
                    remote_path = f"{user_id}/{resume_filename}"
                    file_bytes = supabase_service.download_file(remote_path)
                    
                    tmp_path = f"/tmp/apply_{user_id}_{resume_filename}"
                    with open(tmp_path, "wb") as f:
                        f.write(file_bytes)
                    
                    await run_applier_task(job_url, tmp_path, profile_blob, api_key, resume_filename=resume_filename, use_cloud=use_cloud, session_id=session_id)
                    
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception as e:
                    print(f"❌ Apply via Chat Failed: {e}")
                    supabase_service.update_lead_status_by_url(user_id, job_url, "FAILED")
                    supabase_service.save_chat_message(session_id, "model", f"❌ Application Failed: {e}")

            background_tasks.add_task(_run_apply)

    # 6. Save Bot Response
    supabase_service.save_chat_message(session_id, "model", response_text)
    
    return {
        "role": "model", 
        "content": response_text, 
        "session_id": session_id 
    }

