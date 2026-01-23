from fastapi import APIRouter, Depends, HTTPException, Query
from app.services.supabase_client import supabase_service
from app.api.auth import get_current_user
from typing import List, Optional

router = APIRouter()

@router.get("/")
async def get_leads(
    resume: Optional[str] = Query(None, description="Filter by resume filename"),
    page: int = 1,
    limit: int = 10,
    current_user: dict = Depends(get_current_user)
):
    """
    Fetch job leads for the current user. 
    Optionally filter by resume context.
    """
    user_id = current_user['id']
    
    if not resume:
        # Try to get primary resume
        user_data = supabase_service.get_user_by_email(current_user['email'])
        if user_data and user_data.get('primary_resume_name'):
            resume = user_data['primary_resume_name']
        else:
            return {"leads": [], "total": 0, "resume_context": None, "message": "No resume context found."}

    result = supabase_service.get_leads(user_id, resume, page=page, limit=limit)
    
    return {
        "leads": result["leads"],
        "total": result["total"],
        "page": page,
        "limit": limit,
        "resume_context": resume
    }

@router.delete("/{lead_id}")
async def delete_lead(lead_id: int, current_user: dict = Depends(get_current_user)):
    """
    Delete a job lead.
    """
    user_id = current_user['id']
    success = supabase_service.delete_lead(lead_id, user_id)
    if not success:
         raise HTTPException(status_code=500, detail="Failed to delete lead")
    return {"status": "success", "message": f"Lead {lead_id} deleted."}

@router.get("/counts")
async def get_lead_counts(current_user: dict = Depends(get_current_user)):
    """
    Get counts of leads grouped by resume.
    """
    user_id = current_user['id']
    counts = supabase_service.get_lead_counts(user_id)
    return counts
