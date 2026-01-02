from app.services.supabase_client import supabase_service
import json

try:
    res = supabase_service.client.table('leads').select('*').limit(1).execute()
    if res.data:
        print("Keys:", res.data[0].keys())
        print(json.dumps(res.data[0], indent=2))
    else:
        print("No leads found.")
except Exception as e:
    print("Error:", e)
