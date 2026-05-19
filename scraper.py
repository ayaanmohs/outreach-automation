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

def extract_product_name(description, broken_link):
    """Attempts to find the product name associated with a link."""
    lines = description.split('\n')
    for line in lines:
        if broken_link in line:
            # Look for common patterns: "Product Name: http://link" or "Product Name - http://link"
            clean_line = line.replace(broken_link, "").strip(" -:▶️👉🔗")
            if clean_line and len(clean_line) < 50:
                return clean_line
    return "that product"

def extract_timestamp_and_context(description):
    timestamps = re.findall(r'(\d{1,2}:\d{2})', description)
    if not timestamps: return None, "the vid"
    return timestamps[0], "the intro"

def generate_buying_intent_comment(video_title, broken_link, views, description):
    """Generates high-reply 'Buying Intent' comments."""
    if not broken_link: return ""
    
    product = extract_product_name(description, broken_link)
    ts, context = extract_timestamp_and_context(description)
    formatted_views = f"{int(views):,}"
    
    # "Money Alarm" Trigger Templates
    templates = [
        f"yo that breakdown at {ts if ts else ''} was so good. btw i tried to click the {product} link in the desc cos i wanted to grab it but it's 404ing? just me?",
        f"really solid vid. just a heads up tho—the {product} link is dead? was looking to buy but got a 404. with {formatted_views} views u're probably losing a lot of sales there!",
        f"wait is the {product} link in the desc broken? just tried clicking it and it 404'd. was gonna check it out but can't buy it now lol. thought i'd let u know",
        f"man that {product} part was great. just a heads up though, i think the link in the desc is down (got a 404). i wanted to join/buy but couldn't! might be missing out on some revenue there"
    ]
    
    return random.choice(templates)

def search_leads(query, target_gold=2, max_scan=50):
    youtube = get_youtube_client()
    leads = []
    seen_channels = set()
    videos_scanned = 0
    gold_found_total = 0
    next_page_token = None
    date_limit = (datetime.now() - timedelta(days=MIN_VIDEO_AGE_DAYS)).isoformat() + "Z"
    
    print(f"\n🔱 FETCHUP 'BUYING INTENT' ENGINE v2.9")
    print(f"🎯 TARGET: {query} | 🏆 GOAL: {target_gold} GOLD Leads\n")

    while gold_found_total < target_gold and videos_scanned < max_scan:
        search_request = youtube.search().list(
            q=f"{query} review tutorial setup gear",
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

            video_request = youtube.videos().list(part="snippet,statistics", id=video_id)
            video_response = video_request.execute()
            if not video_response['items']: continue
            
            v_data = video_response['items'][0]
            views = int(v_data['statistics'].get('viewCount', 0))
            full_desc = v_data['snippet']['description']
            video_title = v_data['snippet']['title']
            
            if views < MIN_VIEWS: continue

            links = re.findall(r'https?://[^\s<>"]+', full_desc)
            monetizable_links = [l for l in links if is_monetizable_link(l)]
            status, broken_link = "POTENTIAL", ""
            
            if monetizable_links:
                for link in monetizable_links[:10]:
                    if smoke_test_link(link) == "GOLD":
                        status, broken_link = "GOLD", link
                        break

            try:
                request = youtube.channels().list(part="statistics", id=channel_id)
                response = request.execute()
                subs = int(response['items'][0]['statistics']['subscriberCount']) if response['items'] else 0
                
                if MIN_SUBS <= subs <= MAX_SUBS:
                    seen_channels.add(channel_id)
                    draft = generate_buying_intent_comment(video_title, broken_link, views, full_desc) if status == "GOLD" else ""
                    
                    leads.append({
                        "Video_Link": f"https://www.youtube.com/watch?v={video_id}",
                        "Broken_Link": broken_link,
                        "Draft_Comment": draft,
                        "Channel": channel_name,
                        "Status": status,
                        "Subs": subs,
                        "Views": views,
                        "Video_Title": video_title
                    })
                    
                    if status == "GOLD":
                        gold_found_total += 1
                        print(f"⭐ [GOLD] {channel_name:.<25} | Buying Intent Generated.")
                elif status == "GOLD":
                    pass
            except:
                continue

        next_page_token = search_response.get('nextPageToken')
        if not next_page_token: break
            
    return leads, videos_scanned, gold_found_total

def main():
    try:
        query = input("Keyword/Topic/Gear: ")
        target_gold = int(input("How many GOLD leads?: ") or 2)
        max_limit = int(input("Max scan limit?: ") or 100)
        
        start_time = datetime.now()
        leads, scanned, gold_total = search_leads(query, target_gold=target_gold, max_scan=max_limit)
        
        if leads:
            df = pd.DataFrame(leads)
            df['SortOrder'] = df['Status'].apply(lambda x: 0 if x == 'GOLD' else 1)
            df = df.sort_values('SortOrder').drop('SortOrder', axis=1)
            filename = f"leads_{query.replace(' ', '_')}.csv"
            df.to_csv(filename, index=False)
            print(f"\n✨ DONE | Scanned {scanned} vids | Saved to {filename}")
        else:
            print("\n❌ No leads found.")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    main()
