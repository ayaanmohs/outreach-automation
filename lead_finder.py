import os
import re
import time
import sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

# Import rotating key manager from project root
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from youtube_client_manager import get_youtube_client as _get_rotating_client

# --- CONFIGURATION ---
MIN_SUBS = 200000
MAX_SUBS = 2000000
MIN_CHANNEL_AGE_YEARS = 3
MIN_LINK_DENSITY = 5
MAX_LEADS_PER_RUN = 50
SAVE_CHECKPOINT_EVERY = 5

# Base niches to feed to Gemini
NICHES = [
    "Video Editing Software",
    "Notion Productivity Systems",
    "Shopify Dropshipping",
    "CapCut Video Creation",
    "Photography & Camera Gear",
    "Kajabi & Course Creation"
]

AFFILIATE_PATTERNS = [
    'amzn.to', 'amazon.com', 'bit.ly', 'rebrand.ly', 'tinyurl.com', 'shareasale', 'clickbank', 
    'impact.com', '?tag=', 'ref=', 'aff=', 'via=', 'whop.com', 'gumroad.com', 'teachable.com', 
    'kajabi.com', 'stan.store', 'beacons.ai', 'linktr.ee', 'patreon.com', 'buymeacoffee.com', 
    'substack.com', 'skool.com', 'course', 'training', 'offer', 'deal', 'shop', 'get', 'buy', 
    'discount', 'coupon', 'academy', 'masterclass', 'webinar'
]

def get_youtube_client():
    """Returns a YouTube client using the rotating key manager."""
    youtube, key = _get_rotating_client()
    print(f"🔑 Using API key: {key[:8]}…")
    return youtube

def get_gemini_keywords():
    """Uses Gemini API to generate 20 fresh keywords that haven't been used before."""
    genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    processed_file = "internal_tools/keywords_processed.md"
    used_keywords = []
    
    # Read already used keywords
    if os.path.exists(processed_file):
        with open(processed_file, "r", encoding="utf-8") as f:
            used_keywords = [line.strip() for line in f if line.strip()]
            
    print(f"🧠 Gemini: Found {len(used_keywords)} already processed keywords in memory.")
    print("🧠 Gemini: Brainstorming 20 brand new long-tail search queries...")
    
    prompt = f"""
    Act as a YouTube marketing expert. Generate 20 highly-specific, long-tail search queries that people type into YouTube to find in-depth tutorials, software reviews, or full setups in these niches:
    {', '.join(NICHES)}
    
    These queries should target creators likely to drop affiliate links or digital products in their descriptions. (e.g. "My cinematic LUTs breakdown", "Notion workspace setup walkthrough").
    
    DO NOT generate any of the following queries, as we have already used them:
    {', '.join(used_keywords) if used_keywords else "None"}
    
    CRITICAL INSTRUCTION: Output ONLY the 20 queries. One per line. Do not use bullet points, numbering, quotes, or any introductory text. Just the raw keywords.
    """
    
    response = model.generate_content(prompt)
    new_keywords = [kw.strip("-*\"' ") for kw in response.text.strip().split('\n') if kw.strip()]
    
    # Save the new keywords to our "Do Not Repeat" file
    os.makedirs(os.path.dirname(processed_file), exist_ok=True)
    with open(processed_file, "a", encoding="utf-8") as f:
        for kw in new_keywords:
            f.write(kw + "\n")
            
    print(f"✨ Gemini successfully invented {len(new_keywords)} fresh keywords!")
    return new_keywords

def get_processed_handles():
    processed = set()
    # Check processed_handles.txt (already audited)
    if os.path.exists("processed_handles.txt"):
        with open("processed_handles.txt", "r") as f:
            processed.update(line.strip().lower() for line in f if line.strip())
    
    # Check internal_tools/creators_to_scan.txt (already found in current queue)
    if os.path.exists("internal_tools/creators_to_scan.txt"):
        with open("internal_tools/creators_to_scan.txt", "r") as f:
            processed.update(line.strip().lower() for line in f if line.strip())
            
    return processed

def save_to_scan_list(handles):
    """
    Appends found handles to internal_tools/creators_to_scan.txt.
    """
    with open("internal_tools/creators_to_scan.txt", "a") as f:
        for h in handles:
            f.write(h + "\n")
    print(f"💾 Checkpoint: {len(handles)} leads saved to internal_tools/creators_to_scan.txt")

def is_monetizable_count(description):
    links = re.findall(r'https?://[^\s<>"]+', description)
    count = 0
    for link in links:
        if any(pattern in link.lower() for pattern in AFFILIATE_PATTERNS):
            count += 1
    return count

def find_leads(youtube, keywords, processed):
    leads = []
    found_this_run = set()
    current_batch = []
    
    print(f"🚀 Starting Lead Discovery (Limit: {MAX_LEADS_PER_RUN} leads)...")
    
    for kw in keywords:
        if len(leads) >= MAX_LEADS_PER_RUN:
            print("\n🏁 Session limit reached (100 leads). Stopping.")
            break
            
        print(f"\n🔍 Searching keyword: '{kw}'")
        try:
            # 1. Search for top videos for this keyword
            search_request = youtube.search().list(
                q=kw,
                type="video",
                part="snippet",
                maxResults=20,
                order="relevance"
            )
            search_response = search_request.execute()
            
            # 2. Iterate through results to find the FIRST matching creator
            for item in search_response.get('items', []):
                channel_id = item['snippet']['channelId']
                
                # Fetch detailed channel info
                chan_request = youtube.channels().list(
                    part="snippet,statistics",
                    id=channel_id
                )
                chan_response = chan_request.execute()
                
                if not chan_response.get('items'): continue
                
                chan_data = chan_response['items'][0]
                handle = chan_data['snippet'].get('customUrl')
                if not handle: handle = f"@{channel_id}"
                if not handle.startswith('@'): handle = f"@{handle}"
                
                # --- APPLY FILTERS ---
                
                # A. Deduplication (Check against processed AND findings in current run)
                if handle.lower() in processed or handle.lower() in found_this_run:
                    continue
                
                # B. Subscriber Check
                subs = int(chan_data['statistics'].get('subscriberCount', 0))
                if not (MIN_SUBS <= subs <= MAX_SUBS):
                    continue
                
                # C. Channel Age Check
                pub_date = chan_data['snippet']['publishedAt']
                pub_dt = datetime.strptime(pub_date.split('T')[0], "%Y-%m-%d")
                age_limit = datetime.now() - timedelta(days=MIN_CHANNEL_AGE_YEARS * 365)
                if pub_dt > age_limit:
                    continue
                    
                # D. Link Density Check (on the specific video found)
                video_id = item['id']['videoId']
                vid_request = youtube.videos().list(part="snippet", id=video_id)
                vid_response = vid_request.execute()
                description = vid_response['items'][0]['snippet']['description']
                
                if is_monetizable_count(description) < MIN_LINK_DENSITY:
                    continue
                
                # SUCCESS: Found the first match for this keyword
                print(f"✅ MATCH FOUND: {handle} ({subs:,} subs)")
                leads.append(handle)
                current_batch.append(handle)
                found_this_run.add(handle.lower())
                
                # Checkpoint Save
                if len(current_batch) >= SAVE_CHECKPOINT_EVERY:
                    save_to_scan_list(current_batch)
                    current_batch = []
                
                break # Move to next keyword immediately
                
        except Exception as e:
            print(f"❌ Error during keyword '{kw}': {e}")
            
    # Final cleanup save
    if current_batch:
        save_to_scan_list(current_batch)
            
    return leads

if __name__ == "__main__":
    youtube = get_youtube_client()
    processed = get_processed_handles()
    
    # Automatically brainstorm fresh keywords using Gemini
    new_keywords = get_gemini_keywords()
    
    new_leads = find_leads(youtube, new_keywords, processed)
    
    if new_leads:
        print(f"\n✨ Mission Complete. Total {len(new_leads)} unique handles found.")
    else:
        print("\n❌ No new leads found matching criteria.")
