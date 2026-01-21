import os
import asyncio
from mcp.server.fastmcp import FastMCP
from app.services.supabase_client import supabase_service

# Initialize FastMCP with SSE transport settings implied by the run method
mcp = FastMCP("Supabase MCP")

@mcp.tool()
def get_leads(user_id: int, resume_filename: str) -> str:
    """
    Get job leads for a user and resume.
    Returns a JSON string of leads.
    """
    leads = supabase_service.get_leads(user_id, resume_filename)
    # Convert dates/objects to serializable format if needed, but get_leads returns dicts
    return str(leads)

@mcp.tool()
def update_lead_status(lead_id: int, status: str) -> str:
    """
    Update the status of a specific job lead.
    """
    supabase_service.update_lead_status(lead_id, status)
    return f"Updated lead {lead_id} to status {status}"

@mcp.tool()
def save_credential(domain: str, email: str, password: str) -> str:
    """
    Save or update credentials for a domain.
    """
    supabase_service.save_credential(domain, email, password)
    return f"Saved credential for {domain}"

@mcp.tool()
def get_user_profile(email: str) -> str:
    """
    Get user profile data by email.
    """
    # 1. Get User ID from Auth
    user = supabase_service.get_user_by_email(email)
    if not user:
        return "User not found"
    
    # 2. Get Profile Data
    profile = supabase_service.get_user_profile(user['id'])
    
    # 3. Merge
    if profile:
        full_data = {**user, **profile}
    else:
        full_data = user
        
    # Remove sensitive
    full_data.pop('password_hash', None)
    
    return str(full_data)

@mcp.resource("leads://{user_id}/pending")
def get_pending_leads(user_id: int) -> str:
    """
    Get all leads with status 'NEW' for a user.
    """
    # We might need a custom query or filter existing get_leads
    # Since get_leads requires resume_filename, we might need to fetch all or use a new method
    # For now, let's use a direct client call or helper if available
    # supabase_service.get_leads requires resume_filename. 
    # Let's add a helper or do a direct query here since we have the service instance
    
    # We'll do a direct query using the service's client if possible, or robustly handle it.
    if not supabase_service.client:
        return "Supabase client not initialized"
        
    try:
        response = supabase_service.client.table("leads")\
            .select("*")\
            .eq("user_id", user_id)\
            .eq("status", "NEW")\
            .execute()
        return str(response.data)
    except Exception as e:
        return f"Error fetching pending leads: {e}"

if __name__ == "__main__":
    # Serve using SSE on port 8001
    import uvicorn
    print("Starting Supabase MCP Server on port 8001 (SSE)...")
    uvicorn.run(mcp.sse_app, host="0.0.0.0", port=8001)
