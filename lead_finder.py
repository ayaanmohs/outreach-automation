import os
import re
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

# --- CONFIGURATION ---
MIN_SUBS = 200000
MAX_SUBS = 2000000
MIN_CHANNEL_AGE_YEARS = 3
MIN_LINK_DENSITY = 5
MAX_LEADS_PER_RUN = 20
SAVE_CHECKPOINT_EVERY = 5

# High-intent "Link Rot" keywords
KEYWORDS = [
    "My desk setup 2022", "Logitech MX Master 3S review", "Sony A7IV long term review",
    "Best productivity apps for mac 2023", "Everyday Carry tech 2022", "What's in my tech bag 2023",
    "Home office upgrades 2022", "Aesthetic workspace tour 2022", "Budget 4k editing pc 2023",
    "Top chrome extensions for productivity 2022", "Best budget camera for youtube 2023",
    "Filmmaking gear for beginners 2022", "Best shopify apps for beginners 2023",
    "Notion for small business tutorial 2022", "How to automate your life with zapier",
    "Best microphones for podcasting 2022", "Ultrawide monitor vs dual monitor 2022",
    "Secret tech gear you need 2023", "Minimalist tech setup tour", "Best laptop for students 2023"
]

AFFILIATE_PATTERNS = [
    'amzn.to', 'amazon.com', 'bit.ly', 'rebrand.ly', 'tinyurl.com', 'shareasale', 'clickbank', 
    'impact.com', '?tag=', 'ref=', 'aff=', 'via=', 'whop.com', 'gumroad.com', 'teachable.com', 
    'kajabi.com', 'stan.store', 'beacons.ai', 'linktr.ee', 'patreon.com', 'buymeacoffee.com', 
    'substack.com', 'skool.com', 'course', 'training', 'offer', 'deal', 'shop', 'get', 'buy', 
    'discount', 'coupon', 'academy', 'masterclass', 'webinar'
]

def get_youtube_client():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("Missing YOUTUBE_API_KEY in .env file.")
    return build("youtube", "v3", developerKey=api_key)

def get_processed_handles():
    processed = set()
    # Check processed_handles.txt (already audited)
    if os.path.exists("processed_handles.txt"):
        with open("processed_handles.txt", "r") as f:
            processed.update(line.strip().lower() for line in f if line.strip())
    
    # Check creators_to_scan.txt (already found in current queue)
    if os.path.exists("creators_to_scan.txt"):
        with open("creators_to_scan.txt", "r") as f:
            processed.update(line.strip().lower() for line in f if line.strip())
            
    return processed

def save_to_scan_list(handles):
    """
    Appends found handles to creators_to_scan.txt.
    """
    with open("creators_to_scan.txt", "a") as f:
        for h in handles:
            f.write(h + "\n")
    print(f"💾 Checkpoint: {len(handles)} leads saved to creators_to_scan.txt")

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
            print("\n🏁 Session limit reached (20 leads). Stopping.")
            break
            
        print(f"\n🔍 Searching keyword: '{kw}'")
        try:
            # 1. Search for top videos for this keyword
            search_request = youtube.search().list(
                q=kw,
                type="video",
                part="snippet",
                maxResults=10,
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
    
    new_leads = find_leads(youtube, KEYWORDS, processed)
    
    if new_leads:
        print(f"\n✨ Mission Complete. Total {len(new_leads)} unique handles found.")
    else:
        print("\n❌ No new leads found matching criteria.")
