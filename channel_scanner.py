import os
import re
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
from googleapiclient.discovery import build
import pandas as pd

load_dotenv()

def get_youtube_client():
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("Missing YOUTUBE_API_KEY in .env file.")
    return build("youtube", "v3", developerKey=api_key)

def get_channel_id_from_handle(youtube, handle):
    """
    Resolves a YouTube handle (e.g., @MarySpender) to a channelId using the official forHandle param.
    """
    clean_handle = handle if handle.startswith('@') else f"@{handle}"
    
    print(f"🔍 Resolving handle: {clean_handle}...")
    
    try:
        request = youtube.channels().list(
            part="snippet,contentDetails,statistics",
            forHandle=clean_handle
        )
        response = request.execute()
        
        if response.get('items'):
            channel_id = response['items'][0]['id']
            channel_title = response['items'][0]['snippet']['title']
            print(f"✅ Found: {channel_title} ({channel_id})")
            return channel_id
        else:
            print("⚠️  forHandle failed, trying search fallback...")
            search_request = youtube.search().list(
                q=clean_handle,
                type="channel",
                part="snippet",
                maxResults=1
            )
            search_response = search_request.execute()
            if search_response.get('items'):
                return search_response['items'][0]['id']['channelId']
            
            print(f"❌ Could not resolve handle: {handle}")
            return None
    except Exception as e:
        print(f"❌ Error resolving handle: {e}")
        return None

def get_popular_videos(youtube, channel_id, max_results=40, min_age_years=2):
    """
    Retrieves the most popular "Evergreen" videos, excluding shorts.
    """
    date_limit = (datetime.now() - timedelta(days=min_age_years * 365)).isoformat() + "Z"
    
    print(f"📈 Fetching top {max_results} evergreen videos (Duration > 2m)...")
    
    videos = []
    search_request = youtube.search().list(
        channelId=channel_id,
        type="video",
        order="viewCount",
        part="snippet",
        publishedBefore=date_limit,
        videoDuration="medium", 
        maxResults=max_results
    )
    search_response = search_request.execute()
    
    for item in search_response.get('items', []):
        video_id = item['id']['videoId']
        title = item['snippet']['title']
        published_at = item['snippet']['publishedAt'].split('T')[0]
        
        video_request = youtube.videos().list(
            part="statistics",
            id=video_id
        )
        video_response = video_request.execute()
        
        if video_response['items']:
            stats = video_response['items'][0]['statistics']
            views = int(stats.get('viewCount', 0))
            videos.append({
                "video_id": video_id,
                "title": title,
                "views": views,
                "published_at": published_at,
                "link": f"https://www.youtube.com/watch?v={video_id}"
            })
            print(f"🎥 Found: {title[:50]}... ({views:,} views)")
            
    videos = sorted(videos, key=lambda x: x['views'], reverse=True)
    return videos

AFFILIATE_PATTERNS = [
    'amzn.to', 'amazon.com', 'bit.ly', 'rebrand.ly', 'tinyurl.com', 'shareasale', 'clickbank', 
    'impact.com', '?tag=', 'ref=', 'aff=', 'via=', 'whop.com', 'gumroad.com', 'teachable.com', 
    'kajabi.com', 'stan.store', 'beacons.ai', 'linktr.ee', 'patreon.com', 'buymeacoffee.com', 
    'substack.com', 'skool.com', 'course', 'training', 'offer', 'deal', 'shop', 'get', 'buy', 
    'discount', 'coupon', 'academy', 'masterclass', 'webinar'
]

EXCLUSION_LIST = [
    'instagram.com', 'twitter.com', 'x.com', 'facebook.com', 'linkedin.com', 'tiktok.com', 
    'youtube.com', 'google.com', 'apple.com', 'spotify.com', 'discord.gg', 't.me', 
    'w3.org', 'schema.org', 'wordpress.org'
]

def is_monetizable_link(url):
    u = url.lower()
    if any(ex in u for ex in EXCLUSION_LIST): return False
    return any(pattern in u for pattern in AFFILIATE_PATTERNS) or "github.com" in u

def smoke_test_link(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
        if response.status_code in [404, 410, 451]: return "GOLD"
        return "HEALTHY"
    except: return "UNCERTAIN"

def audit_videos(youtube, videos):
    """
    Audits descriptions, capturing "Anchor Text" context for each broken link.
    """
    print(f"\n🔍 Starting Deep Audit on {len(videos)} videos...")
    print("--------------------------------------------------")
    
    results = []
    for i, video in enumerate(videos):
        video_id = video['video_id']
        print(f"\n[{i+1}/{len(videos)}] 🎥 Video: {video['title'][:60]}...")
        
        video_request = youtube.videos().list(part="snippet", id=video_id)
        video_response = video_request.execute()
        
        if not video_response['items']: continue
        description = video_response['items'][0]['snippet']['description']
        
        # Regex to find links and up to 50 chars of context before it
        findings = re.findall(r'(.{0,50})(https?://[^\s<>"]+)', description)
        
        broken_with_context = []
        seen_links = set()
        for anchor, raw_url in findings:
            link = re.sub(r'[.,!?)]+$', '', raw_url)
            if not is_monetizable_link(link) or link in seen_links: continue
            
            seen_links.add(link)
            status = smoke_test_link(link)
            if status == "GOLD":
                clean_anchor = anchor.strip().replace('\n', ' ')
                print(f"     ❌ [DEAD] {link} (Context: {clean_anchor})")
                broken_with_context.append({"link": link, "anchor": clean_anchor})
        
        if broken_with_context:
            results.append({
                "title": video['title'],
                "link": video['link'],
                "views": video['views'],
                "published_at": video['published_at'],
                "findings": broken_with_context
            })
    return results

def get_channel_metadata(youtube, channel_id):
    request = youtube.channels().list(part="snippet", id=channel_id)
    response = request.execute()
    if response.get('items'):
        snippet = response['items'][0]['snippet']
        return {
            "title": snippet['title'],
            "description": snippet['description'][:200].replace('\n', ' ') + "..."
        }
    return {"title": "Unknown", "description": "No description available."}

if __name__ == "__main__":
    youtube = get_youtube_client()
    handle = input("Enter YouTube Handle (e.g., @MarySpender): ")
    channel_id = get_channel_id_from_handle(youtube, handle)
    
    if channel_id:
        channel_meta = get_channel_metadata(youtube, channel_id)
        popular_videos = get_popular_videos(youtube, channel_id, max_results=50, min_age_years=1.5)
        print(f"\n✅ Retrieved {len(popular_videos)} videos.")
        
        audit_results = audit_videos(youtube, popular_videos)
        
        if audit_results:
            rows = []
            total_views_affected = 0
            total_dead_links = 0
            for res in audit_results:
                total_views_affected += res['views']
                total_dead_links += len(res['findings'])
                
                # Requested formatting: Link   Anchor   Link   Anchor
                findings_str = ""
                for f in res['findings']:
                    findings_str += f"{f['link']}   {f['anchor']}   "
                
                # Final CSV Structure with "3 spaces" separators
                rows.append({
                    "Video Title": res['title'],
                    "   ": "   ",
                    "Video Link": res['link'],
                    "    ": "   ",
                    "Views": res['views'],
                    "     ": "   ",
                    "Uploaded": res['published_at'],
                    "      ": "   ",
                    "Broken Findings (Link + Anchor)": findings_str.strip()
                })
            
            df = pd.DataFrame(rows)
            audit_filename = f"audit_{handle.lstrip('@')}.csv"
            df.to_csv(audit_filename, index=False)
            
            master_file = "master_targets.csv"
            master_row = {
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Handle": handle,
                "Channel Name": channel_meta['title'],
                "Total Broken Links": total_dead_links,
                "Views Affected": total_views_affected,
                "Channel Description": channel_meta['description']
            }
            master_df = pd.DataFrame([master_row])
            if os.path.exists(master_file):
                master_df.to_csv(master_file, mode='a', header=False, index=False)
            else:
                master_df.to_csv(master_file, index=False)
            
            print(f"\n✨ Audit Complete. Found {total_dead_links} broken links.")
            print(f"📁 Detailed report saved to: {audit_filename}")

            # --- Link Repetition Analysis (High Impact) ---
            link_map = {}
            for res in audit_results:
                for f in res['findings']:
                    l = f['link']
                    if l not in link_map: link_map[l] = []
                    link_map[l].append(res['title'])
            
            repeated = {l: vids for l, vids in link_map.items() if len(vids) > 1}
            
            if repeated:
                print("\n📊 Link Repetition Report (High Impact):")
                print("--------------------------------------------------")
                rep_rows = []
                for l, vids in sorted(repeated.items(), key=lambda x: len(x[1]), reverse=True):
                    print(f"🔗 {l}")
                    print(f"   ⚠️  Repeated in {len(vids)} videos:")
                    for v in vids:
                        print(f"   - {v}")
                    rep_rows.append({
                        "Broken Link": l,
                        "Occurrence Count": len(vids),
                        "Affected Videos": " | ".join(vids)
                    })
                
                rep_filename = f"repetition_{handle.lstrip('@')}.csv"
                pd.DataFrame(rep_rows).to_csv(rep_filename, index=False)
                print(f"\n📁 Repetition report saved to: {rep_filename}")
            else:
                print("\nℹ️  No repeated broken links found across the audited videos.")

            print(f"🗃️  Master targets updated.")
        else:
            print("\n✅ Clean Audit! No broken links found.")
    else:
        print("\nPlease try again.")
