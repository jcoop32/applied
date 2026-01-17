from fastapi import APIRouter, Depends, HTTPException, Query
from app.services.supabase_client import supabase_service
from app.api.auth import get_current_user
from typing import List, Optional

router = APIRouter()

@router.get("/")
async def get_leads(
    resume: Optional[str] = Query(None, description="Filter by resume filename"),
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch job leads for the current user. 
    Optionally filter by resume context.
    """
    user_id = current_user['id']
    
    # If no resume specified, maybe try to get primary? 
    # Or just return empty list if strict context is needed?
    # Existing `get_leads` in supabase_client requires resume_filename.
    
    if not resume:
        # Try to get primary resume
        user_data = supabase_service.get_user_by_email(current_user['email'])
        if user_data and user_data.get('primary_resume_name'):
            resume = user_data['primary_resume_name']
        else:
            # Return empty or all? The service method currently requires resume_filename.
            # Strategy: If no resume, maybe we should fetch all leads? 
            # But the service structure relies on cache key user_resume.
            # For now, let's require it or default to primary.
            return {"leads": [], "resume_context": None, "message": "No resume context found."}

    leads = supabase_service.get_leads(user_id, resume, limit=limit)
    return {
        "leads": leads,
        "resume_context": resume
    }

@router.get("/counts")
async def get_lead_counts(current_user: dict = Depends(get_current_user)):
    """
    Get counts of leads grouped by resume.
    """
    user_id = current_user['id']
    counts = supabase_service.get_lead_counts(user_id)
    return counts
