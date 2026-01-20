import os
import asyncio
import requests
import re
from urllib.parse import urlparse
from google import genai
from playwright.async_api import async_playwright
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP
mcp = FastMCP("Browser Automation MCP")

KNOWN_ATS = ["greenhouse.io", "lever.co", "workday.com", "ashbyhq.com", "bamboohr.com", "smartrecruiters.com", "icims.com"]
KNOWN_AGGREGATORS = ["adzuna.com", "indeed.com", "linkedin.com", "ziprecruiter.com", "glassdoor.com"]

class UrlResolver:
    def __init__(self, api_key: str):
        self.api_key = api_key
        # We enforce headless for the server
        self.headless = True

    async def resolve_url_with_browser(self, url: str) -> str:
        """
        Uses a lightweight headless browser to follow JS redirects.
        """
        print(f"🌐 Browser Resolver: navigating to {url}")
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--disable-infobars"]
                )
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    locale="en-US"
                )
                page = await context.new_page()
                
                await page.set_extra_http_headers({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9"
                })
                
                try:
                    await page.goto(url, timeout=30000, wait_until="domcontentloaded")
                    # Wait for JS redirects
                    await page.wait_for_timeout(10000)
                    
                    final_url = page.url
                    print(f"🌐 Browser Resolver landed on: {final_url}")
                    
                    if not any(agg in final_url for agg in ["adzuna.com", "indeed.com", "linkedin.com"]):
                         return final_url

                    # FALLBACK: Aggregator handling
                    print("⚠️ Still on aggregator. Scanning page content for hidden ATS links...")
                    content = await page.content()
                    
                    # 1. Regex Scan
                    for ats in KNOWN_ATS:
                        match = re.search(r'https?://[^"\'\s>]*' + re.escape(ats) + r'[^"\'\s>]*', content)
                        if match:
                            found_url = match.group(0)
                            print(f"🎯 Found hidden ATS link in DOM (Regex): {found_url}")
                            return found_url

                    # 2. LLM Scan
                    print("🧠 Asking LLM to find the redirect/ATS link in the blocked page...")
                    truncated_content = content[:50000] 
                    prompt = f"""
                    I am stuck on a job aggregator page (Adzuna) that failed to redirect.
                    Analyze the HTML below and find the DIRECT link to the applicant tracking system (ATS) or the employer's site.
                    Look for hidden URLs, 'window.location', 'meta refresh', or simple 'Click here' links.
                    
                    Prioritize domains like: {', '.join(KNOWN_ATS)}
                    
                    HTML:
                    {truncated_content}
                    
                    Rules:
                    1. Return ONLY the URL.
                    2. If not found, return 'NOT_FOUND'.
                    """
                    
                    client = genai.Client(api_key=self.api_key)
                    response = await asyncio.to_thread(
                        client.models.generate_content,
                        model='gemini-2.5-flash',
                        contents=prompt
                    )
                    llm_url = (response.text or "").strip()
                    
                    url_match = re.search(r'https?://[^\s<>"]+|www\.[^\s<>"]+', llm_url)
                    if url_match:
                         clean_url = url_match.group(0)
                         if "adzuna" not in clean_url and "http" in clean_url:
                             print(f"🎯 LLM found hidden link: {clean_url}")
                             return clean_url
                            
                    return final_url
                    
                except Exception as nav_e:
                     print(f"⚠️ Browser navigation error: {nav_e}")
                     return url
                finally:
                    await browser.close()
        except Exception as e:
            print(f"⚠️ Browser Resolver failed: {e}")
            return url

    async def resolve_application_url(self, job_url: str) -> str:
        """
        Fetches the raw HTML via requests and asks the LLM
        to identify the correct job application URL.
        """
        print(f"🕵️ Resolving true application URL for: {job_url}")

        try:
            # 1. Fetch RAW HTML
            def fetch_raw():
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                }
                response = requests.get(job_url, headers=headers, timeout=10, allow_redirects=True)
                return response.text, response.url

            html_content, final_url = await asyncio.to_thread(fetch_raw)

            # 2. Ask the LLM
            client = genai.Client(api_key=self.api_key)

            prompt = f"""
            I have the raw HTML content of a job posting page below.
            Find the URL for the "Apply", "Apply Now", "Apply on Company Site", or "Start Application" button.

            rules:
            1. Return ONLY the raw URL. No JSON, no text, no markdown.
            2. PRIORITIZE links to external generic ATS platforms: {', '.join(KNOWN_ATS)}.
            3. AVOID links to other aggregators if possible: {', '.join(KNOWN_AGGREGATORS)}.
            4. If the only link is an aggregator (e.g. Adzuna), return it, but try to find the button that says "Go to company site" or "Apply on Employer Site".
            5. If the URL is relative (starts with /), append it to the base domain: {final_url}
            6. If the page shows "Access Denied", "Security Check", or similar blockage, look for ANY link that contains "redirect", "click", "authenticate", or the job ID, which might bypass the block.

            HTML Content (Truncated if too large):
            {html_content[:100000]}
            """

            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=prompt
            )

            extracted_text = (response.text or "").strip()
            
            # Regex to find the first URL
            url_match = re.search(r'https?://[^\s<>"]+|www\.[^\s<>"]+', extracted_text)
            if url_match:
                extracted_url = url_match.group(0)
            else:
                extracted_url = extracted_text

            if extracted_url and "http" in extracted_url:
                print(f"🤖 LLM identified Apply URL: {extracted_url}")
                
                # --- REDIRECT CHASER LOGIC ---
                domain = urlparse(extracted_url).netloc
                
                if any(agg in domain for agg in KNOWN_AGGREGATORS):
                    print(f"⚠️ Detected Aggregator URL ({domain}). Attempting to follow redirects...")
                    
                    async def follow_redirects(url):
                        headers = {
                            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        try:
                            # 1. Standard Redirect Follow
                            loop = asyncio.get_event_loop()
                            r = await loop.run_in_executor(None, lambda: requests.get(url, headers=headers, allow_redirects=True, timeout=15))
                            final_url = r.url
                            
                            # 2. Soft Redirect / Block Page Check
                            if "adzuna" in final_url or "Access Denied" in r.text or "Security Check" in r.text or "authenticate" in r.text:
                                # Look for /authenticate links or any redirect_to param
                                auth_match = re.search(r'href=["\'](/?authenticate[^"\']+)["\']', r.text)
                                if auth_match:
                                    rel_link = auth_match.group(1)
                                    final_auth_link = f"https://www.adzuna.com{rel_link}" if rel_link.startswith("/") else rel_link
                                    return await self.resolve_url_with_browser(final_auth_link)
                                
                                js_match = re.search(r'window\.location\s*=\s*["\']([^"\']+)["\']', r.text)
                                if js_match:
                                    return await self.resolve_url_with_browser(js_match.group(1))
                                    
                            if any(agg in final_url for agg in KNOWN_AGGREGATORS):
                                print(f"⚠️ Still on aggregator ({final_url}). Switching to Browser Resolution...")
                                return await self.resolve_url_with_browser(final_url)

                            return final_url
                            
                        except Exception as e:
                            print(f"⚠️ Redirect check failed: {e}")
                        return url

                    final_dest = await follow_redirects(extracted_url)
                    
                    if final_dest != extracted_url:
                        print(f"🎯 Redirect Chaser resolved: {extracted_url} -> {final_dest}")
                        extracted_url = final_dest
                    else:
                        print(f"⚠️ Could not resolve redirect or URL is unchanged.")

                # Final Validation
                final_domain = urlparse(extracted_url).netloc
                if any(agg in final_domain for agg in KNOWN_AGGREGATORS):
                    print(f"❌ Failed to resolve URL. Stuck on aggregator: {final_domain}")
                    # In MCP context, we might prefer returning the original URL if getting stuck, 
                    # or returning what we found and letting the user decide.
                    # We'll return it but the agent might struggle.

                return extracted_url

            return final_url

        except Exception as e:
            print(f"⚠️ Resolution failed: {e}")
            import traceback
            traceback.print_exc()
            return job_url

# Initialize Resolver
resolver = UrlResolver(api_key=os.getenv("GEMINI_API_KEY"))

@mcp.tool()
async def resolve_job_url(raw_url: str) -> str:
    """
    Takes a raw job link (e.g. from Adzuna), performs HTTP/Playwright/LLM analysis
    to find the direct ATS link, and returns the clean URL.
    """
    return await resolver.resolve_application_url(raw_url)

if __name__ == "__main__":
    # Serve using SSE on port 8002
    import uvicorn
    print("Starting Browser MCP Server on port 8002 (SSE)...")
    uvicorn.run(mcp.sse_app, host="0.0.0.0", port=8002)
