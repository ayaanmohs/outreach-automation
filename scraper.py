import os
import re
import random
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from googleapiclient.discovery import build

load_dotenv()

# Configuration
MIN_SUBS = 1000
MAX_SUBS = 250000
MIN_VIEWS = 1000  
MIN_VIDEO_AGE_DAYS = 180
AFFILIATE_PATTERNS = ['amzn.to', 'amazon.com', 'bit.ly', 'rebrand.ly', 'tinyurl.com', 'shareasale', 'clickbank', 'impact.com', '?tag=', 'ref=', 'aff=', 'via=']

def get_youtube_client():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key: raise ValueError("Missing API Key.")
    return build("youtube", "v3", developerKey=api_key)

def is_monetizable_link(url):
    u = url.lower()
    return any(pattern in u for pattern in AFFILIATE_PATTERNS) or "github.com" in u

def smoke_test_link(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        return "GOLD" if response.status_code in [404, 410, 451] else "HEALTHY"
    except:
        return "UNCERTAIN"

def extract_clean_product_name(description, broken_link):
    """Finds the product name and cleans it for the team to use in comments."""
    lines = description.split('\n')
    for line in lines:
        if broken_link in line:
            # Clean symbols and the link itself
            clean = line.replace(broken_link, "").strip(" -:▶️👉🔗[]()#")
            # Prune long Amazon SEO titles to the first 3-4 words
            words = clean.split()
            if len(words) > 4:
                clean = " ".join(words[:4])
            return clean.lower()
    return "the link"

def get_channel_handle(youtube, channel_id):
    """Fetches the @handle for easier searching on IG/Twitter."""
    try:
        request = youtube.channels().list(part="snippet", id=channel_id)
        response = request.execute()
        return response['items'][0]['snippet'].get('customUrl', 'N/A')
    except:
        return "N/A"

def search_leads(query, target_gold=2, max_scan=50):
    youtube = get_youtube_client()
    leads = []
    seen_channels = set()
    videos_scanned = 0
    gold_found_total = 0
    next_page_token = None
    date_limit = (datetime.now() - timedelta(days=MIN_VIDEO_AGE_DAYS)).isoformat() + "Z"
    
    print(f"\n🔱 FETCHUP 'DATA SNIPER' v4.0 (GOLD ONLY)")
    print(f"🎯 TARGET: {query} | 🏆 GOAL: {target_gold} GOLD Leads\n")

    while gold_found_total < target_gold and videos_scanned < max_scan:
        search_request = youtube.search().list(
            q=f"{query} review tutorial accessories gear setup",
            part="snippet", type="video", videoDuration="medium",
            publishedBefore=date_limit, maxResults=50, pageToken=next_page_token, order="relevance"
        )
        search_response = search_request.execute()
        
        for item in search_response.get('items', []):
            if gold_found_total >= target_gold or videos_scanned >= max_scan: break
            
            videos_scanned += 1
            video_id = item['id']['videoId']
            channel_id = item['snippet']['channelId']
            channel_name = item['snippet']['channelTitle']
            
            if videos_scanned % 10 == 0:
                print(f"--- Scanned {videos_scanned} videos... (Found {gold_found_total} Valid GOLD) ---")

            if channel_id in seen_channels: continue

            # Get Detailed Stats
            video_request = youtube.videos().list(part="snippet,statistics", id=video_id)
            video_response = video_request.execute()
            if not video_response['items']: continue
            
            v_data = video_response['items'][0]
            views = int(v_data['statistics'].get('viewCount', 0))
            full_desc = v_data['snippet']['description']
            video_title = v_data['snippet']['title']
            
            if views < MIN_VIEWS: continue

            # Smoke Test
            links = re.findall(r'https?://[^\s<>"]+', full_desc)
            monetizable_links = [l for l in links if is_monetizable_link(l)]
            
            status, broken_link = "POTENTIAL", ""
            if monetizable_links:
                for link in monetizable_links[:12]: # Check more links for complexity
                    if smoke_test_link(link) == "GOLD":
                        status, broken_link = "GOLD", link
                        break

            if status != "GOLD":
                continue

            try:
                # Subscriber check
                request = youtube.channels().list(part="statistics", id=channel_id)
                response = request.execute()
                subs = int(response['items'][0]['statistics']['subscriberCount']) if response['items'] else 0
                
                if MIN_SUBS <= subs <= MAX_SUBS:
                    seen_channels.add(channel_id)
                    handle = get_channel_handle(youtube, channel_id)
                    product_name = extract_clean_product_name(full_desc, broken_link)
                    
                    leads.append({
                        "Video_Link": f"https://www.youtube.com/watch?v={video_id}",
                        "Broken_Product": product_name,
                        "Channel_Handle": handle,
                        "Channel_Name": channel_name,
                        "Broken_Link": broken_link,
                        "Views": views,
                        "Subs": subs,
                        "Video_Title": video_title
                    })
                    
                    gold_found_total += 1
                    print(f"🎯 [GOLD FOUND] {channel_name:.<25} | Product: {product_name}")
                else:
                    pass
            except:
                continue

        next_page_token = search_response.get('nextPageToken')
        if not next_page_token: break
            
    return leads, videos_scanned, gold_found_total

def main():
    try:
        query = input("Software/Topic/Gear: ")
        target_gold = int(input("How many GOLD leads?: ") or 2)
        max_limit = int(input("Max scan limit?: ") or 100)
        
        start_time = datetime.now()
        leads, scanned, gold_total = search_leads(query, target_gold=target_gold, max_scan=max_limit)
        
        if leads:
            df = pd.DataFrame(leads)
            filename = f"leads_{query.replace(' ', '_')}.csv"
            df.to_csv(filename, index=False)
            print(f"\n✨ SNIPER MISSION COMPLETE | Saved to {filename}")
        else:
            print("\n❌ No GOLD leads found.")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
