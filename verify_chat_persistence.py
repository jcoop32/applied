
import asyncio
import os
from app.services.supabase_client import supabase_service
from app.api.agents import run_research_pipeline
# Mock dependencies if needed, but integration test with Supabase is better if feasible.

async def test_standard_chat_persistence():
    print("--- Testing Standard Chat Persistence ---")
    user_id = "test-user-id" # We need a real user ID usually, or we mock
    # Fetch a real user
    users = supabase_service.client.table("users").select("id").limit(1).execute()
    if not users.data:
        print("❌ No users found to test with.")
        return
    
    user_id = users.data[0]['id']
    print(f"👤 Using User ID: {user_id}")
    
    # 1. Create Session
    session = supabase_service.create_chat_session(user_id, "Test Chat Verification")
    if not session:
        print("❌ Failed to create session.")
        return
    print(f"✅ Created Session: {session['id']} - {session['title']}")
    
    # 2. Add Message
    supabase_service.save_chat_message(session['id'], "user", "Hello Persistence")
    messages = supabase_service.get_chat_history(session['id'])
    if len(messages) == 1 and messages[0]['content'] == "Hello Persistence":
        print("✅ Message persisted correctly.")
    else:
        print(f"❌ Message persistence failed: {messages}")
        
    # 3. Rename
    updated = supabase_service.update_chat_session_title(session['id'], "Renamed Test Chat")
    if updated['title'] == "Renamed Test Chat":
        print("✅ Rename successful.")
    else:
        print("❌ Rename failed.")

    # 4. Delete
    success = supabase_service.delete_chat_session(session['id'])
    remaining = supabase_service.client.table("chat_sessions").select("*").eq("id", session['id']).execute()
    if success and not remaining.data:
        print("✅ Delete successful.")
    else:
        print("❌ Delete failed.")

async def test_session_creation_logic():
    print("\n--- Testing Logic for Agent Session Creation (Dry Run) ---")
    # We can't easily run the full pipeline without API keys/files, but we can check if the code runs without syntax errors
    # and if the function accepts session_id.
    import inspect
    from app.services.agent_runner import run_applier_task, run_research_pipeline
    
    sig_research = inspect.signature(run_research_pipeline)
    if 'session_id' in sig_research.parameters:
        print("✅ run_research_pipeline accepts session_id")
    else:
        print("❌ run_research_pipeline MISSING session_id")

    sig_apply = inspect.signature(run_applier_task)
    if 'session_id' in sig_apply.parameters:
        print("✅ run_applier_task accepts session_id")
    else:
         print("❌ run_applier_task MISSING session_id")

if __name__ == "__main__":
    asyncio.run(test_standard_chat_persistence())
    asyncio.run(test_session_creation_logic())
