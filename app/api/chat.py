from fastapi import APIRouter, Depends, HTTPException, Body, BackgroundTasks
from fastapi.responses import StreamingResponse
from app.api.auth import get_current_user
from app.agents.chat_agent import ChatAgent
from app.services.supabase_client import supabase_service
from app.services.log_stream import log_stream_manager
import os
import json
import asyncio
from pydantic import BaseModel
from typing import List, Optional

router = APIRouter()

class CreateSessionRequest(BaseModel):
    title: Optional[str] = "New Chat"

class UpdateSessionRequest(BaseModel):
    title: str

class MessageRequest(BaseModel):
    message: str
    session_id: Optional[int | str] = None # Optional for legacy/first-msg auto-create

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
    success = supabase_service.delete_chat_session(session_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete session")
    return {"status": "success"}

@router.get("/sessions/{session_id}/messages")
async def get_session_messages(
    session_id: str,
    current_user: dict = Depends(get_current_user)
):
    return supabase_service.get_chat_history(session_id)

async def handle_agent_action(action, user_id, session_id, available_resumes, current_user, api_key):
    """
    Executes side-effects for agent actions (Research/Apply).
    Returns a modified response_text string if needed (e.g. errors).
    """
    extra_response = ""
    
    
    try:
        if action["type"] == "research":
            args = action["payload"]
            resume_filename = args.get("resume_filename")
            limit = int(args.get("limit", 20))
            job_title = args.get("job_title_override")
            location = args.get("location_override")
            
            if resume_filename not in available_resumes:
               pass # logging handled in agent text usually

            from app.services.agent_runner import run_research_pipeline, update_research_status
            
            # Idempotency Check
            current_status = supabase_service.get_research_status(user_id).get(resume_filename, {}).get("status")
            if current_status in ["SEARCHING", "QUEUED"]:
                msg = f"\n\n(⚠️ Research for **{resume_filename}** is already in progress. Please wait or cancel the current task.)"
                return msg

            update_research_status(user_id, resume_filename, "SEARCHING")
            
            # Local or Cloud Dispatch (logic handled inside run_research_pipeline now)
            asyncio.create_task(run_research_pipeline(
                user_id=user_id,
                resume_filename=resume_filename,
                api_key=api_key,
                limit=limit,
                job_title=job_title,
                location=location,
                session_id=session_id
            ))


        elif action["type"] == "apply":
            args = action["payload"]
            job_url = args.get("job_url")
            job_title = args.get("job_title")
            resume_filename = args.get("resume_filename")
            
            # 1. Fallback: Lookup by Title
            if not job_url and job_title:
                lead = supabase_service.get_lead_by_title(user_id, job_title)
                if lead:
                    job_url = lead['url']
                    extra_response = f"\n\n✅ Found job match: **{lead['title']}** at **{lead['company']}**"
                else:
                    extra_response = f"\n\n❌ Could not find a saved job matching '**{job_title}**'. Please provide the URL or search for it first."
                    return extra_response 
                    
            if not job_url:
                return "\n\nI couldn't identify which job to apply to."

            # 2. Resume Fallback
            if not resume_filename:
                user_row = supabase_service.get_user_by_email(current_user['email'])
                profile_data = user_row.get('profile_data', {})
                resume_filename = profile_data.get('primary_resume_name')
                if resume_filename:
                    extra_response += f"\n\n(Using default resume: **{resume_filename}**)"
                else:
                    return "\n\nI found the job but I don't know which resume to use. Please specify a resume or set a primary one in your Profile."

            extra_instructions = args.get("extra_instructions")
            # Map frontend mode to execution_mode
            # 'cloud' -> 'cloud_run' (Google Cloud Run)
            # 'browser_use' -> 'browser_use_cloud' (Local Controller + Managed Browser)
            # 'local' -> 'local' (Docker/Local)
            if mode == "cloud":
                execution_mode = "cloud_run" 
            elif mode == "browser_use":
                execution_mode = "browser_use_cloud"
            else:
                execution_mode = "local"

            from app.services.agent_runner import run_applier_task
            
            user_data = supabase_service.get_user_by_email(current_user['email'])
            profile_blob = user_data.get('profile_data', {})
            if 'email' not in profile_blob: profile_blob['email'] = current_user['email']
            if 'full_name' not in profile_blob and user_data.get('full_name'): profile_blob['full_name'] = user_data.get('full_name')
            if 'user_id' not in profile_blob: profile_blob['user_id'] = user_id
            
            if extra_instructions:
                profile_blob['apply_instructions'] = extra_instructions
            
            supabase_service.update_lead_status_by_url(user_id, job_url, "IN_PROGRESS", resume_filename=resume_filename)

            async def _run_apply():
                try:
                    remote_path = f"{user_id}/{resume_filename}"
                    file_bytes = supabase_service.download_file(remote_path)
                    
                    tmp_path = f"/tmp/apply_{user_id}_{resume_filename}"
                    with open(tmp_path, "wb") as f:
                        f.write(file_bytes)
                    
                    await run_applier_task(job_url, tmp_path, profile_blob, api_key, resume_filename=resume_filename, execution_mode=execution_mode, session_id=session_id)
                    
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                except Exception as e:
                    print(f"❌ Apply via Chat Failed: {e}")
                    supabase_service.update_lead_status_by_url(user_id, job_url, "FAILED")
                    supabase_service.save_chat_message(session_id, "model", f"❌ Application Failed: {e}")

            asyncio.create_task(_run_apply())

    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({
            "type": "error", 
            "content": f"Failed to execute agent action: {str(e)}"
        })

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
        title = (payload.message[:30] + "...") if len(payload.message) > 30 else payload.message
        session = supabase_service.create_chat_session(user_id, title)
        if session:
            session_id = session['id']
        else:
             raise HTTPException(status_code=500, detail="Failed to init session")

    # 2. Save User Message
    supabase_service.save_chat_message(session_id, "user", payload.message)

    # 3. Fetch Context
    resumes_list = supabase_service.list_resumes(user_id)
    available_resumes = [r['name'] for r in resumes_list]
    db_history = supabase_service.get_chat_history(session_id)
    history = [{"role": msg['role'], "content": msg['content']} for msg in db_history if msg['content'] != payload.message]

    # Initialize Agent
    agent = ChatAgent(api_key=api_key)
    
    # 4. Stream Generator
    async def response_generator():
        full_response = ""
        final_action = None
        
        # Yield metadata event for session ID (so client knows it if it was created)
        yield json.dumps({"type": "meta", "session_id": session_id}) + "\n"

        async for chunk in agent.generate_response_stream(
            user_id=user_id,
            message=payload.message,
            history=history,
            available_resumes=available_resumes
        ):
            if chunk["type"] == "token":
                full_response += chunk["content"]
                yield json.dumps(chunk) + "\n" # NDJSON format
            elif chunk["type"] == "end":
                final_action = chunk.get("action")
        
        # 5. Handle Action Side-Effects
        if final_action:
            try:
                extra_text = await handle_agent_action(final_action, user_id, session_id, available_resumes, current_user, api_key)
                if extra_text:
                    full_response += extra_text
                    yield json.dumps({"type": "token", "content": extra_text}) + "\n"
            except Exception as e:
                import traceback
                traceback.print_exc()
                error_msg = f"\n\n❌ Agent Error: {str(e)}"
                full_response += error_msg
                yield json.dumps({"type": "token", "content": error_msg}) + "\n"

        # 6. Save Final Bot Message
        supabase_service.save_chat_message(session_id, "model", full_response)
        
        # Yield Done (Validation and handling done)
        yield json.dumps({
            "type": "end", 
            "content": full_response, 
            "action": final_action,
            "session_id": session_id
        }) + "\n"

    return StreamingResponse(response_generator(), media_type="application/x-ndjson")

@router.get("/stream/{session_id}")
async def stream_logs(session_id: str):
    """
    SSE Endpoint for real-time agent logs.
    """
    return StreamingResponse(
        log_stream_manager.subscribe(session_id), 
        media_type="text/event-stream"
    )

@router.post("/research/cancel")
async def cancel_research(
    payload: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    resume_filename = payload.get("resume_filename")
    if not resume_filename:
        # Try primary resume
        profile = supabase_service.get_user_profile(current_user['id'])
        resume_filename = profile.get("primary_resume_name")
        
    if not resume_filename:
         raise HTTPException(status_code=400, detail="Resume filename required")

    from app.services.agent_runner import update_research_status
    update_research_status(current_user['id'], resume_filename, "CANCEL_REQUESTED")
    
    # Also notify session if provided
    session_id = payload.get("session_id")
    if session_id:
        supabase_service.save_chat_message(session_id, "model", "🛑 Cancellation requested... Stopping agents.")
        
    return {"status": "cancelled", "resume": resume_filename}
