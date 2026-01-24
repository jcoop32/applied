import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
SUPABASE_KEY = os.getenv("SUPABASE_KEY") # Legacy Fallback
BUCKET_NAME = "resumes"

import time

from functools import lru_cache

class SupabaseService:
    def __init__(self):
        key = SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY
        if not SUPABASE_URL or not key:
            print("⚠️ Warning: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not found in .env")
            self.client = None
        else:
            # Passing SUPABASE_URL as-is to avoid "Storage endpoint URL should have a trailing slash" warning
            # Use Service Role Key for Backend -> Bypasses RLS for admin tasks
            self.client: Client = create_client(SUPABASE_URL, key)
        
        # Cache: Key = f"{user_id}_{resume_filename}" -> Value = (List[Dict], timestamp)
        self.leads_cache = {}
        self.LEADS_CACHE_TTL = 60 # seconds

    def invalidate_leads_cache(self, user_id: int, resume_filename: str):
        """
        Manually validates the leads cache for a specific user/resume.
        """
        cache_key = f"{user_id}_{resume_filename}"
        if cache_key in self.leads_cache:
            # Naive invalidation: remove all keys starting with prefix
            keys_to_remove = [k for k in self.leads_cache if k.startswith(cache_key)]
            for k in keys_to_remove:
                del self.leads_cache[k]
            print(f"🧹 Invalidated {len(keys_to_remove)} cache entries for {cache_key}")

    def upload_resume(self, file_content: bytes, file_name: str, user_id: int, content_type: str = "application/pdf") -> str:
        """
        Uploads a resume to the user's folder in the bucket: user_id/filename
        Returns the public URL.
        """
        if not self.client:
             raise Exception("Supabase client not initialized")

        path = f"{user_id}/{file_name}"

        try:
            # Attempt upload
            self.client.storage.from_(BUCKET_NAME).upload(
                path=path,
                file=file_content,
                file_options={"content-type": content_type, "upsert": "true"}
            )

            public_url = self.client.storage.from_(BUCKET_NAME).get_public_url(path)
            return public_url

        except Exception as e:
            # Check for "Bucket not found" error string
            error_str = str(e)
            if "Bucket not found" in error_str or "404" in error_str:
                print(f"⚠️ Bucket '{BUCKET_NAME}' not found. Attempting to create...")
                try:
                    self.client.storage.create_bucket(BUCKET_NAME, options={"public": True})
                    print(f"✅ Bucket '{BUCKET_NAME}' created successfully.")

                    # Retry upload
                    self.client.storage.from_(BUCKET_NAME).upload(
                        path=path,
                        file=file_content,
                        file_options={"content-type": content_type, "upsert": "true"}
                    )
                    public_url = self.client.storage.from_(BUCKET_NAME).get_public_url(path)
                    return public_url
                except Exception as create_error:
                    print(f"❌ Failed to create/upload to bucket: {create_error}")
                    raise e

            print(f"❌ Supabase Upload Error: {e}")
            raise e

    def upload_file(self, file_content: bytes, file_name: str, user_id: int, content_type: str = "application/octet-stream") -> str:
        """
        Generic wrapper for uploading files to the user's folder.
        """
        return self.upload_resume(file_content, file_name, user_id, content_type)

    def list_resumes(self, user_id: int):
        """
        Lists resumes in the user's specific folder.
        """
        if not self.client:
             return []

        try:
            # List files in the folder "user_id/"
            files = self.client.storage.from_(BUCKET_NAME).list(path=f"{user_id}")

            result = []
            for f in files:
                if f['name'] == '.emptyFolderPlaceholder': continue # Skip system files
                
                # Filter for actual resume documents
                lower_name = f['name'].lower()
                if not (lower_name.endswith('.pdf') or lower_name.endswith('.docx') or lower_name.endswith('.doc')):
                    continue
                result.append({
                    "name": f['name'],
                    "id": f['id'],
                    "created_at": f.get('created_at'),
                    "metadata": f.get('metadata'),
                    "url": self.client.storage.from_(BUCKET_NAME).get_public_url(f"{user_id}/{f['name']}")
                })
            return result
        except Exception as e:
            print(f"❌ Supabase List Error: {e}")
            return []

    @lru_cache(maxsize=128)
    def get_credentials(self, email: str):
        """
        Fetches credentials for a specific email from the 'credentials' table.
        Cached.
        """
        if not self.client:
            print("⚠️ Supabase client not initialized.")
            return []

        try:
            response = self.client.table("credentials").select("*").eq("email", email).execute()
            return response.data
        except Exception as e:
            print(f"❌ Supabase Credential Fetch Error: {e}")
            return []

    def save_credential(self, domain: str, email: str, password: str, user_id: int = None):
        """
        Saves or updates a credential in the 'credentials' table.
        """
        if not self.client:
             print("⚠️ Supabase client not initialized.")
             return

        try:
            data = {
                "domain": domain,
                "email": email,
                "password": password,
                "user_id": user_id
            }
            # Upsert on email/domain
            self.client.table("credentials").upsert(data, on_conflict="email, domain").execute()
            print(f"✅ Saved credential for {domain} to DB.")
        except Exception as e:
            print(f"❌ Supabase Credential Save Error: {e}")

    # --- User Management ---
    def get_user_by_email(self, email: str):
        """
        Fetches a user by email from the 'users' table.
        Only fetches auth fields: id, email, password_hash, created_at
        """
        if not self.client:
            return None

        try:
            response = self.client.table("users").select("id, email, password_hash, created_at").eq("email", email).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Supabase User Fetch Error: {e}")
            return None

    @lru_cache(maxsize=128)
    def get_user_profile(self, user_id: int):
        """
        Fetches the user's profile from the 'profiles' table.
        Cached.
        """
        if not self.client:
            return None
        try:
            response = self.client.table("profiles").select("*").eq("user_id", user_id).execute()
            if response.data:
                return response.data[0]
            # Fallback if profile missing (shouldn't happen with trigger)
            return None 
        except Exception as e:
            print(f"❌ Supabase Profile Fetch Error: {e}")
            return None

    def create_user(self, email: str, password_hash: str, full_name: str = None):
        """
        Creates a new user in the 'users' table.
        The DB Trigger 'on_auth_user_created' will auto-create the 'profiles' row.
        If full_name is provided, we update the profile immediately after.
        """
        if not self.client:
            raise Exception("Supabase client not initialized")

        try:
            # 1. Insert into Users (Auth only)
            data = {
                "email": email,
                "password_hash": password_hash
            }
            response = self.client.table("users").insert(data).execute()
            
            if response.data:
                user = response.data[0]
                user_id = user['id']
                
                # 2. Update Profile with Full Name if provided
                if full_name:
                    try:
                        self.update_user_profile(user_id, {"full_name": full_name})
                        user['full_name'] = full_name # Return composite object for immediate UI use
                    except Exception as pe:
                        print(f"⚠️ Failed to update profile name: {pe}")
                
                return user
            return None
        except Exception as e:
            print(f"❌ Supabase User Create Error: {e}")
            raise e

    def clear_user_cache(self, user_id: int):
        """
        Clears the LRU cache for user profile and credentials (best effort).
        """
        self.get_user_profile.cache_clear()
        self.get_credentials.cache_clear()

    def update_user_profile(self, user_id: int, data: dict):
        """
        Updates the user's profile data in the 'profiles' table.
        """
        if not self.client:
            raise Exception("Supabase client not initialized")

        try:
            # ensure data only contains profile fields
            response = self.client.table("profiles").update(data).eq("user_id", user_id).execute()
            if response.data:
                # Clear cache on update
                self.clear_user_cache(user_id)
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Supabase User Update Error: {e}")
            raise e

    def get_research_status(self, user_id: int):
        """
        Fetches only the 'profile_data' from 'profiles' table.
        """
        if not self.client:
            return {}

        try:
            response = self.client.table("profiles").select("profile_data").eq("user_id", user_id).execute()
            if response.data:
                return response.data[0].get('profile_data', {})
            return {}
        except Exception as e:
            print(f"❌ Supabase Status Fetch Error: {e}")
            return {}

    def download_file(self, path: str) -> bytes:
        """
        Downloads a file from the bucket as bytes.
        """
        if not self.client:
            raise Exception("Supabase client not initialized")

        try:
            response = self.client.storage.from_(BUCKET_NAME).download(path)
            # response is bytes directly in some versions, or needs .read()
            return response
        except Exception as e:
            print(f"❌ Supabase Download Error: {e}")
            raise e

    def delete_file(self, path: str):
        """
        Deletes a file from the bucket.
        """
        if not self.client:
             raise Exception("Supabase client not initialized")

        try:
            self.client.storage.from_(BUCKET_NAME).remove([path])
            return True
        except Exception as e:
             print(f"❌ Supabase Delete Error: {e}")
             raise e

    # --- Leads / Jobs Management ---
    def get_lead_counts(self, user_id: int) -> dict:
        """
        Returns a dictionary mapping resume_filename to the count of leads found.
        """
        if not self.client:
            return {}

        try:
            # Fetch all resume_filenames for this user
            response = self.client.table("leads")\
                .select("resume_filename")\
                .eq("user_id", user_id)\
                .execute()

            from collections import Counter
            counts = Counter(row['resume_filename'] for row in response.data)
            return dict(counts)
        except Exception as e:
            print(f"❌ Supabase Lead Count Error: {e}")
            return {}

    def save_leads_bulk(self, user_id: int, resume_filename: str, leads: list):
        """
        Inserts multiple leads into the 'leads' table.
        leads: list of dicts with keys (title, company, url, match_score, match_reason, query_source)
        """
        if not self.client:
             print("⚠️ Supabase client not initialized.")
             return

        if not leads:
            return

        # Prepare records
        records = []
        for lead in leads:
            records.append({
                "user_id": user_id,
                "resume_filename": resume_filename,
                "title": lead.get("title"),
                "company": lead.get("company"),
                "url": lead.get("url"),
                "match_score": lead.get("match_score"),
                "match_reason": lead.get("match_reason"),
                "query_source": lead.get("query_source"),
                "status": "NEW"
            })

        try:
            # Application-side deduplication to ensure cumulative add without overwriting
            # 1. Fetch existing URLs for this user/resume
            existing_res = self.client.table("leads")\
                .select("url")\
                .eq("user_id", user_id)\
                .eq("resume_filename", resume_filename)\
                .execute()

            existing_urls = {row['url'] for row in existing_res.data} if existing_res.data else set()

            # 2. Filter out duplicates
            new_records = []
            for lead in leads:
                if lead.get("url") not in existing_urls:
                    new_records.append({
                        "user_id": user_id,
                        "resume_filename": resume_filename,
                        "title": lead.get("title"),
                        "company": lead.get("company"),
                        "url": lead.get("url"),
                        "match_score": lead.get("match_score"),
                        "match_reason": lead.get("match_reason"),
                        "query_source": lead.get("query_source"),
                        "status": "NEW",
                        # "created_at": "now()" # Supabase defaults this usually
                    })

            if new_records:
                self.client.table("leads").insert(new_records).execute()
                print(f"✅ Saved {len(new_records)} new leads to DB (skipped {len(leads) - len(new_records)} duplicates).")
                
                # Invalidate Cache
                self.invalidate_leads_cache(user_id, resume_filename)
            else:
                 print("ℹ️ No new leads to save (all duplicates).")

        except Exception as e:
             print(f"❌ Supabase Leads Save Error: {e}")

    def get_lead_by_title(self, user_id: int, input_text: str):
        """
        Fetches a lead by Title, handling "Title at Company" formats.
        """
        if not self.client: return None

        # Helper to execute query
        def _search(title_query, company_query=None):
            q = self.client.table("leads").select("*").eq("user_id", user_id)
            q = q.ilike("title", f"%{title_query}%")
            if company_query:
                q = q.ilike("company", f"%{company_query}%")
            return q.order("created_at", desc=True).limit(1).execute()

        try:
            # 1. Try separating " at " (e.g. "Software Engineer at Google")
            import re
            # Split on " at " case-insensitive
            parts = re.split(r'\s+at\s+', input_text, flags=re.IGNORECASE)
            
            # Scenario A: We found a split (Title + Company)
            if len(parts) >= 2:
                # Assume last part is company, join rest as title
                candidate_company = parts[-1].strip()
                candidate_title = " at ".join(parts[:-1]).strip()
                
                print(f"🕵️‍♀️ Strict Search -> Title: '{candidate_title}' | Company: '{candidate_company}'")

                # Attempt 1: Match Title AND Company
                res = _search(candidate_title, candidate_company)
                if res.data: 
                    print(f"✅ Strict Match Found: {res.data[0]['title']} @ {res.data[0]['company']}")
                    return res.data[0]
                else:
                    print("❌ Strict Match Failed.")

                # DANGEROUS FALLBACK REMOVED: Do NOT search just by title if user specified company.
                # It causes false positives (e.g. finding 'Dev at Google' when asking for 'Dev at Facebook')

            # Scenario B: Search full string in Title column
            # Useful if "at" wasn't a separator, or if the user typed the Company in the Title field manually?
            print(f"🕵️‍♀️ Fallback Search (Full String) -> Title: '{input_text}'")
            res = _search(input_text)
            if res.data: 
                print(f"✅ Fallback Match Found: {res.data[0]['title']}")
                return res.data[0]

            return None

        except Exception as e:
            print(f"❌ Supabase Lead Fetch by Title Error: {e}")
            return None

    def get_lead_by_url(self, user_id: int, url: str):
        """
        Fetches a lead by URL for a specific user.
        """
        if not self.client:
            return None

        try:
            response = self.client.table("leads")\
                .select("*")\
                .eq("user_id", user_id)\
                .eq("url", url)\
                .execute()
            
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Supabase Lead Fetch Error: {e}")
            return None

    def update_lead_status_by_url(self, user_id: int, url: str, status: str, resume_filename: str = None):
        """
        Updates the status of a lead by URL (e.g. to 'APPLIED').
        """
        if not self.client:
             print("⚠️ Supabase client not initialized.")
             return

        try:
            self.client.table("leads")\
                .update({"status": status})\
                .eq("user_id", user_id)\
                .eq("url", url)\
                .execute()
            print(f"✅ Updated lead status to '{status}' for {url}")
            
            # Invalidate Cache if resume_filename provided
            if resume_filename:
                self.invalidate_leads_cache(user_id, resume_filename)

        except Exception as e:
            print(f"❌ Supabase Lead Status Update Error: {e}")

    def update_lead_status(self, lead_id: int, status: str, user_id: int = None, resume_filename: str = None):
        """
        Updates the status of a lead by ID.
        """
        if not self.client:
             print("⚠️ Supabase client not initialized.")
             return

        try:
            self.client.table("leads")\
                .update({"status": status})\
                .eq("id", lead_id)\
                .execute()
            print(f"✅ Updated lead status to '{status}' for ID {lead_id}")
            
            # Invalidate Cache
            if user_id and resume_filename:
                self.invalidate_leads_cache(user_id, resume_filename)

        except Exception as e:
            print(f"❌ Supabase Lead Status ID Update Error: {e}")

    def delete_lead(self, lead_id: int, user_id: int):
        """
        Deletes a lead by ID.
        """
        if not self.client:
             print("⚠️ Supabase client not initialized.")
             return False

        try:
            self.client.table("leads")\
                .delete()\
                .eq("id", lead_id)\
                .eq("user_id", user_id)\
                .execute()
            print(f"✅ Deleted lead ID {lead_id}")
            
            # Since we don't know the resume context easily here without fetching, 
            # we might want to just clear the cache for this user generally 
            # OR relies on the caller to know? 
            # Ideally obtaining the resume_filename before delete would allow precise invalidation.
            # For now, let's just proceed.
            return True

        except Exception as e:
            print(f"❌ Supabase Lead Delete Error: {e}")
            return False

    def get_leads(self, user_id: int, resume_filename: str, page: int = 1, limit: int = 10):
        """
        Fetches leads for a specific resume from the 'leads' table with pagination.
        Returns {"leads": [], "total": 0}
        """
        if not self.client:
             return {"leads": [], "total": 0}

        try:
            # Check Cache
            cache_key = f"{user_id}_{resume_filename}_{page}_{limit}"
            if cache_key in self.leads_cache:
                data, timestamp = self.leads_cache[cache_key]
                if time.time() - timestamp < self.LEADS_CACHE_TTL:
                    # print(f"⚡ Cache Hit for leads: {cache_key}")
                    return data
                else:
                    # print(f"⌛ Cache Expired for leads: {cache_key}")
                    pass

            # Calculate Pagination
            start = (page - 1) * limit
            end = start + limit - 1

            # Order by match_score desc, then created_at desc
            response = self.client.table("leads")\
                .select("*", count="exact")\
                .eq("user_id", user_id)\
                .eq("resume_filename", resume_filename)\
                .order("match_score", desc=True)\
                .range(start, end)\
                .execute()

            result = {
                "leads": response.data,
                "total": response.count
            }

            # Update Cache
            self.leads_cache[cache_key] = (result, time.time())
            return result
        except Exception as e:
            print(f"❌ Supabase Leads Fetch Error: {e}")
            return {"leads": [], "total": 0}


    
    # --- Chat Persistence ---
    def ensure_chat_tables(self):
        """
        Creates chat_sessions and chat_messages tables if they don't exist.
        (Naive SQL execution via REST or just assume existence if creating manually. 
         Supabase-py client doesn't support 'create table' easily without RPC or raw SQL.
         For this demo, we'll assume they exist OR try to create if failure? 
         Actually, we can use the 'rpc' call if we had a function, or just rely on the user/migration.
         
         Better approach for this agent: We'll assume they exist. 
         If user hasn't created them, we might error. 
         Let's just try to insert/select and let it fail if missing (logs will show).
        """
        pass

    def create_chat_session(self, user_id: int, title: str = "New Chat"):
        """
        Creates a new chat session.
        """
        if not self.client: return None
        try:
            data = {"user_id": user_id, "title": title}
            # 'chat_sessions' table must exist: id (serial), user_id (int), title (text), created_at (ts)
            response = self.client.table("chat_sessions").insert(data).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Create Chat Session Error: {e}")
            return None

    def update_chat_session_title(self, session_id: int, title: str):
        """
        Updates the title of a chat session.
        """
        if not self.client: return None
        try:
            response = self.client.table("chat_sessions")\
                .update({"title": title})\
                .eq("id", session_id)\
                .execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Update Chat Session Error: {e}")
            return None

    def delete_chat_session(self, session_id: int):
        """
        Deletes a chat session and its messages (cascade usually handles messages if configured, 
        otherwise we might need to delete messages first). 
        Assuming Postgres ON DELETE CASCADE is set up.
        If not, we delete messages first manually.
        """
        if not self.client: return False
        try:
            # Manual cascade just in case
            self.client.table("chat_messages").delete().eq("session_id", session_id).execute()
            
            response = self.client.table("chat_sessions")\
                .delete()\
                .eq("id", session_id)\
                .execute()
            
            # response.data usually contains deleted rows
            return True
        except Exception as e:
            print(f"❌ Delete Chat Session Error: {e}")
            return False


    def get_chat_sessions(self, user_id: int):
        """
        Fetches all chat sessions for a user, ordered by recent.
        """
        if not self.client: return []
        try:
            response = self.client.table("chat_sessions")\
                .select("*")\
                .eq("user_id", user_id)\
                .order("created_at", desc=True)\
                .execute()
            return response.data
        except Exception as e:
            print(f"❌ Get Chat Sessions Error: {e}")
            return []

    def save_chat_message(self, session_id: int, role: str, content: str):
        """
        Saves a message to a session.
        """
        if not self.client: return
        try:
            data = {
                "session_id": session_id,
                "role": role,
                "content": content
            }
            # 'chat_messages' table: id, session_id, role, content, created_at
            self.client.table("chat_messages").insert(data).execute()
        except Exception as e:
            print(f"❌ Save Chat Message Error: {e}")

    def get_chat_history(self, session_id: int):
        """
        Get all messages for a session.
        """
        if not self.client: return []
        try:
            response = self.client.table("chat_messages")\
                .select("*")\
                .eq("session_id", session_id)\
                .order("created_at", desc=False)\
                .execute()
            return response.data
        except Exception as e:
            print(f"❌ Get Chat History Error: {e}")
            return []

# Singleton instance
supabase_service = SupabaseService()
