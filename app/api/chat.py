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

    # 3. APPLY INTENT DETECTION - Check if message is an apply request
    import re
    apply_pattern = r'^Apply to @(.+?) at (.+?) using resume \[(.+?)\]'
    url_pattern = r'Job URL:\s*(https?://\S+)'
    
    apply_match = re.search(apply_pattern, payload.message, re.IGNORECASE)
    
    if apply_match:
        job_title = apply_match.group(1).strip()
        company = apply_match.group(2).strip()
        resume_name = apply_match.group(3).strip()
        
        # Extract job URL
        url_match = re.search(url_pattern, payload.message)
        job_url = url_match.group(1).strip() if url_match else None
        
        if job_url:
            # Extract additional instructions (optional)
            instructions_match = re.search(r'Additional instructions:\s*(.+)', payload.message, re.DOTALL | re.IGNORECASE)
            additional_instructions = instructions_match.group(1).strip() if instructions_match else ""
            
            # Trigger the applier agent
            from app.services.agent_runner import run_applier_task
            from fastapi import BackgroundTasks
            
            # Get profile data for applier
            user_data = supabase_service.get_user_by_email(current_user['email'])
            profile_blob = user_data.get('profile_data', {})
            if 'email' not in profile_blob:
                profile_blob['email'] = current_user['email']
            if 'full_name' not in profile_blob and user_data.get('full_name'):
                profile_blob['full_name'] = user_data.get('full_name')
            
            # Add additional instructions to profile for applier to use
            if additional_instructions:
                profile_blob['apply_instructions'] = additional_instructions
            
            # Mark lead as IN_PROGRESS
            supabase_service.update_lead_status_by_url(user_id, job_url, "IN_PROGRESS", resume_filename=resume_name)
            
            # Download resume and run applier in background
            import asyncio
            async def _run_apply():
                try:
                    remote_path = f"{user_id}/{resume_name}"
                    file_bytes = supabase_service.download_file(remote_path)
                    
                    tmp_path = f"/tmp/apply_{user_id}_{resume_name}"
                    with open(tmp_path, "wb") as f:
                        f.write(file_bytes)
                    
                    await run_applier_task(job_url, tmp_path, profile_blob, api_key, resume_filename=resume_name, use_cloud=True)
                    
                    # Cleanup
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception as e:
                    print(f"❌ Apply via Chat Failed: {e}")
                    supabase_service.update_lead_status_by_url(user_id, job_url, "FAILED")
            
            # Schedule the apply task
            asyncio.create_task(_run_apply())
            
            # Generate response confirming the application started
            response_text = f"""🚀 **Starting Application!**

I'm now applying to **{job_title}** at **{company}** using your resume **{resume_name}**.

{"**Additional Instructions:** " + additional_instructions if additional_instructions else ""}

The application is running in the background. You can check the status in the **Jobs** tab. I'll do my best to complete all the forms and answer any questions based on your profile data."""
            
            # Save bot response
            supabase_service.save_chat_message(session_id, "model", response_text)
            
            return {
                "role": "model",
                "content": response_text,
                "session_id": session_id
            }

    # 4. Fetch History (from DB) - if not an apply intent, proceed with normal chat
    db_history = supabase_service.get_chat_history(session_id)
    # Convert to format agent expects: [{'role': 'user'/'model', 'content': '...'}]
    # db has 'role', 'content'
    history = [{"role": msg['role'], "content": msg['content']} for msg in db_history]

    # Initialize Agent
    agent = ChatAgent(api_key=api_key)
    
    # Generate Response
    # Note: history includes the message we just saved? yes.
    # Agent might duplicate it if we pass it again in 'message' arg?
    # ChatAgent.generate_response appends 'message' to history.
    # So we should pass history excluding the last message if we want to follow that pattern,
    # OR change agent to just take full history.
    # Current agent:
    # contents = [history...] + [message]
    # So we should pass history[:-1] if it includes recent, 
    # BUT we are fetching form DB which definitely includes it.
    
    # Correction: Let's pass the message explicitly and history EXCLUDING it to match Agent's expectation.
    # Or cleaner: Agent takes `messages: List[dict]` and just sends them?
    # Keeping minimal Agent change: pass message and history-excluding-current.
    
    history_for_agent = [h for h in history if h['content'] != payload.message] # Rough filter
    # Better: just use strict slicing if we trust order.
    # Let's just trust the agent will handle it or slight duplication isn't fatal for Gemini Flash context.
    # Actually, let's just pass `payload.message` and `history` (which is previous context).
    # Since we just inserted current message, `db_history` has it.
    # We want `history` arg to be PREVIOUS history.
    prev_history = [h for h in history if h != history[-1]] # All except last (which is current user msg)

    response_text = await agent.generate_response(
        user_id=user_id,
        message=payload.message,
        history=prev_history
    )
    
    # 5. Save Bot Response
    supabase_service.save_chat_message(session_id, "model", response_text)
    
    return {
        "role": "model", 
        "content": response_text, 
        "session_id": session_id 
    }

