
import unittest
from unittest.mock import MagicMock
from app.services.supabase_client import SupabaseService

class TestLeadsCache(unittest.TestCase):
    def setUp(self):
        # Initialize service with mocked client
        self.service = SupabaseService()
        self.service.client = MagicMock()
        self.service.leads_cache = {} # Ensure clean cache

    def test_get_leads_caching(self):
        user_id = 99
        resume = "test_resume.pdf"
        mock_data = [{"id": 1, "title": "Job 1"}]
        
        # Mock the chain: client.table().select()...execute()
        mock_execute = MagicMock()
        mock_execute.execute.return_value.data = mock_data
        
        self.service.client.table.return_value\
            .select.return_value\
            .eq.return_value\
            .eq.return_value\
            .order.return_value\
            .limit.return_value = mock_execute

        # 1. First Fetch (Cache Miss)
        result1 = self.service.get_leads(user_id, resume)
        self.assertEqual(result1, mock_data)
        self.assertEqual(mock_execute.execute.call_count, 1)

        # 2. Second Fetch (Cache Hit)
        result2 = self.service.get_leads(user_id, resume)
        self.assertEqual(result2, mock_data)
        self.assertEqual(mock_execute.execute.call_count, 1) # Should NOT increment

        # 3. Invalidate via Update Status
        # We assume update_lead_status calls .update().eq().execute()
        self.service.update_lead_status(1, "APPLIED", user_id=user_id, resume_filename=resume)
        
        # Verify cache cleared
        cache_key = f"{user_id}_{resume}"
        self.assertNotIn(cache_key, self.service.leads_cache)

        # 4. Third Fetch (Cache Miss - Refetch)
        result3 = self.service.get_leads(user_id, resume)
        self.assertEqual(result3, mock_data)
        self.assertEqual(mock_execute.execute.call_count, 2)

if __name__ == "__main__":
    unittest.main()
