
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
        # Mock time to ensure hit
        with unittest.mock.patch('time.time', return_value=self.service.leads_cache[f"{user_id}_{resume}"][1] + 1):
            result2 = self.service.get_leads(user_id, resume)
            self.assertEqual(result2, mock_data)
            self.assertEqual(mock_execute.execute.call_count, 1) # Should NOT increment

        # 3. Cache Expiry vs Invalidation
        # Test Invalidation (Explicit delete)
        # We assume update_lead_status calls .update().eq().execute()
        self.service.update_lead_status(1, "APPLIED", user_id=user_id, resume_filename=resume)
        
        # Verify cache cleared
        cache_key = f"{user_id}_{resume}"
        self.assertNotIn(cache_key, self.service.leads_cache)

        # 4. Third Fetch (Cache Miss - Refetch)
        result3 = self.service.get_leads(user_id, resume)
        self.assertEqual(result3, mock_data)
        self.assertEqual(mock_execute.execute.call_count, 2)

    def test_get_leads_expiry(self):
        user_id = 100
        resume = "test_expiry.pdf"
        mock_data = [{"id": 2, "title": "Job 2"}]
        
        mock_execute = MagicMock()
        mock_execute.execute.return_value.data = mock_data
        
        self.service.client.table.return_value\
            .select.return_value\
            .eq.return_value\
            .eq.return_value\
            .order.return_value\
            .limit.return_value = mock_execute

        # 1. Fetch
        self.service.get_leads(user_id, resume)
        
        # 2. Fetch again (Hit)
        with unittest.mock.patch('time.time', return_value=self.service.leads_cache[f"{user_id}_{resume}"][1] + 1):
            self.service.get_leads(user_id, resume)
            self.assertEqual(mock_execute.execute.call_count, 1)

        # 3. Fetch after TTL (Miss)
        # Advance time by TTL + 1
        start_time = self.service.leads_cache[f"{user_id}_{resume}"][1]
        with unittest.mock.patch('time.time', return_value=start_time + self.service.LEADS_CACHE_TTL + 1):
             self.service.get_leads(user_id, resume)
             self.assertEqual(mock_execute.execute.call_count, 2)

if __name__ == "__main__":
    unittest.main()
