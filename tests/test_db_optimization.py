
import asyncio
import time
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from jose import jwt
from app.api.auth import get_current_user, user_cache, SECRET_KEY, ALGORITHM
# from app.services.supabase_client import supabase_service 

# Helper to generate token
def create_test_token(email="test@example.com", user_id=1):
    expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode = {"sub": email, "id": user_id, "exp": expire}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

class TestDBOptimization(unittest.IsolatedAsyncioTestCase):
    async def test_get_current_user_caching(self):
        # Setup
        token = create_test_token()
        user_cache.clear() # Reset cache
        
        # Mock supa
        with patch("app.services.supabase_client.supabase_service.get_user_by_email") as mock_get_user:
            mock_get_user.return_value = {"id": 1, "email": "test@example.com"}
            
            # 1. First Call - Should hit DB
            user1 = await get_current_user(token)
            self.assertEqual(user1["email"], "test@example.com")
            self.assertEqual(mock_get_user.call_count, 1)
            
            # 2. Second Call - Should hit Cache
            user2 = await get_current_user(token)
            self.assertEqual(user2["email"], "test@example.com")
            # count should NOT increment
            self.assertEqual(mock_get_user.call_count, 1) 
            
            # 3. Fast forward time (simulate expiry)
            email = "test@example.com"
            # Set to 100s ago (stale)
            user_cache[email] = (user1, datetime.utcnow().timestamp() - 100) 
            
            # 4. Third Call - Should hit DB again
            user3 = await get_current_user(token)
            self.assertEqual(mock_get_user.call_count, 2)

if __name__ == "__main__":
    unittest.main()
