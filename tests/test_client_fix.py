import sys
import os

# Mock environment if needed
os.environ["SUPABASE_URL"] = "https://mock.supabase.co"
os.environ["SUPABASE_KEY"] = "mock_key"

try:
    from app.services.supabase_client import SupabaseService
    
    # Initialize without crashing
    client = SupabaseService()
    
    # Mock the internal client to avoid real network calls
    class MockClient:
        def table(self, name): return self
        def select(self, *args): return self
        def eq(self, *args): return self
        def update(self, *args): return self
        def execute(self): 
            class APIResponse:
                data = [{"id": 123}]
            return APIResponse()
            
    client.client = MockClient()
    
    print("✅ Service initialized")
    
    # Test new method existence
    if hasattr(client, 'get_lead_by_url'):
        print("✅ get_lead_by_url exists")
    else:
        print("❌ get_lead_by_url MISSING")
        sys.exit(1)
        
    if hasattr(client, 'update_lead_status_by_url'):
        print("✅ update_lead_status_by_url exists")
    else:
        print("❌ update_lead_status_by_url MISSING")
        sys.exit(1)
        
    print("Tests Passed!")
    
except ImportError as e:
    print(f"❌ Import Failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"❌ Test Failed: {e}")
    sys.exit(1)
