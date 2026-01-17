import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
BUCKET_NAME = "resumes"

import time

class SupabaseService:
    def __init__(self):
        if not SUPABASE_URL or not SUPABASE_KEY:
            print("⚠️ Warning: SUPABASE_URL or SUPABASE_KEY not found in .env")
            self.client = None
        else:
            self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # Cache: Key = f"{user_id}_{resume_filename}" -> Value = (List[Dict], timestamp)
        self.leads_cache = {}
        self.LEADS_CACHE_TTL = 60 # seconds

    def invalidate_leads_cache(self, user_id: int, resume_filename: str):
        """
        Manually validates the leads cache for a specific user/resume.
        """
        cache_key = f"{user_id}_{resume_filename}"
        if cache_key in self.leads_cache:
            del self.leads_cache[cache_key]
            print(f"🧹 Invalidated leads cache for {cache_key}")

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

    def get_credentials(self, email: str):
        """
        Fetches credentials for a specific email from the 'credentials' table.
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
        """
        if not self.client:
            return None

        try:
            response = self.client.table("users").select("*").eq("email", email).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Supabase User Fetch Error: {e}")
            return None

    def create_user(self, email: str, password_hash: str, full_name: str = None):
        """
        Creates a new user in the 'users' table.
        """
        if not self.client:
            raise Exception("Supabase client not initialized")

        try:
            data = {
                "email": email,
                "password_hash": password_hash,
                "full_name": full_name
            }
            response = self.client.table("users").insert(data).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Supabase User Create Error: {e}")
            # Likely duplicate email error
            raise e

    def update_user_profile(self, user_id: int, data: dict):
        """
        Updates the user's profile data (e.g. primary_resume_name, profile_data).
        """
        if not self.client:
            raise Exception("Supabase client not initialized")

        try:
            response = self.client.table("users").update(data).eq("id", user_id).execute()
            if response.data:
                return response.data[0]
            return None
        except Exception as e:
            print(f"❌ Supabase User Update Error: {e}")
            raise e

    def get_research_status(self, user_id: int):
        """
        Fetches only the 'profile_data' for the user to check research status.
        """
        if not self.client:
            return {}

        try:
            response = self.client.table("users").select("profile_data").eq("id", user_id).execute()
            if response.data:
                # Returns dict with 'profile_data' key
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

    def get_leads(self, user_id: int, resume_filename: str, limit: int = 50):
        """
        Fetches leads for a specific resume from the 'leads' table.
        """
        if not self.client:
             return []

        try:
            # Check Cache
            cache_key = f"{user_id}_{resume_filename}"
            if cache_key in self.leads_cache:
                data, timestamp = self.leads_cache[cache_key]
                if time.time() - timestamp < self.LEADS_CACHE_TTL:
                    # print(f"⚡ Cache Hit for leads: {cache_key}")
                    return data
                else:
                    # print(f"⌛ Cache Expired for leads: {cache_key}")
                    pass

            # Order by match_score desc, then created_at desc
            response = self.client.table("leads")\
                .select("*")\
                .eq("user_id", user_id)\
                .eq("resume_filename", resume_filename)\
                .order("match_score", desc=True)\
                .limit(limit)\
                .execute()

            # Update Cache
            self.leads_cache[cache_key] = (response.data, time.time())
            return response.data
        except Exception as e:
            print(f"❌ Supabase Leads Fetch Error: {e}")
            return []


    
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
