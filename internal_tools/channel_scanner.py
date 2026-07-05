import os
import re
import sys
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from googleapiclient.discovery import build

# Add the project root to sys.path so we can import youtube_client_manager
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from youtube_client_manager import get_youtube_client

load_dotenv(os.path.join(PROJECT_ROOT, ".env"))


def get_channel_id_from_handle(youtube, handle):
    clean_handle = handle if handle.startswith('@') else f"@{handle}"
    print(f"🔍 Resolving handle: {clean_handle}...")
    try:
        response = youtube.channels().list(
            part="snippet,contentDetails,statistics",
            forHandle=clean_handle
        ).execute()

        if response.get('items'):
            channel_id = response['items'][0]['id']
            channel_title = response['items'][0]['snippet']['title']
            print(f"✅ Found: {channel_title} ({channel_id})")
            return channel_id
        else:
            print("⚠️  forHandle failed, trying search fallback...")
            search_response = youtube.search().list(
                q=clean_handle, type="channel", part="snippet", maxResults=1
            ).execute()
            if search_response.get('items'):
                return search_response['items'][0]['id']['channelId']
            print(f"❌ Could not resolve handle: {handle}")
            return None
    except Exception as e:
        print(f"❌ Error resolving handle: {e}")
        return None


def fetch_video_stats(api_key, video_id, title, published_at):
    """Fetch view count for a single video — runs in parallel."""
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        resp = youtube.videos().list(part="statistics", id=video_id).execute()
        if resp['items']:
            views = int(resp['items'][0]['statistics'].get('viewCount', 0))
            return {
                "video_id": video_id,
                "title": title,
                "views": views,
                "published_at": published_at,
                "link": f"https://www.youtube.com/watch?v={video_id}"
            }
    except Exception as e:
        print(f"  ⚠️ Stats fetch failed for {video_id}: {e}")
    return None


def get_popular_videos(youtube, api_key, channel_id, max_results=40, min_age_years=2):
    """
    Retrieves the most popular evergreen videos.
    Fetches video stats IN PARALLEL for speed.
    """
    date_limit = (datetime.now() - timedelta(days=min_age_years * 365)).isoformat() + "Z"
    print(f"📈 Fetching top {max_results} evergreen videos...")

    search_response = youtube.search().list(
        channelId=channel_id,
        type="video",
        order="viewCount",
        part="snippet",
        publishedBefore=date_limit,
        videoDuration="medium",
        maxResults=max_results
    ).execute()

    items = search_response.get('items', [])
    if not items:
        return []

    # Fetch all video stats IN PARALLEL
    videos = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {
            ex.submit(
                fetch_video_stats,
                api_key,
                item['id']['videoId'],
                item['snippet']['title'],
                item['snippet']['publishedAt'].split('T')[0]
            ): item for item in items
        }
        for future in as_completed(futures):
            result = future.result()
            if result:
                videos.append(result)
                print(f"🎥 {result['title'][:55]}... ({result['views']:,} views)")

    return sorted(videos, key=lambda x: x['views'], reverse=True)


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
    if any(ex in u for ex in EXCLUSION_LIST):
        return False
    return any(pattern in u for pattern in AFFILIATE_PATTERNS) or "github.com" in u


def smoke_test_link(url):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    try:
        response = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        return "GOLD" if response.status_code in [404, 410, 451] else "HEALTHY"
    except:
        return "UNCERTAIN"


def audit_single_video(api_key, video):
    """
    Fetch description + smoke-test links for ONE video.
    This runs in parallel across all videos.
    """
    video_id = video['video_id']
    try:
        youtube = build("youtube", "v3", developerKey=api_key)
        resp = youtube.videos().list(part="snippet", id=video_id).execute()
        if not resp['items']:
            return None
        description = resp['items'][0]['snippet']['description']
    except Exception as e:
        print(f"  ⚠️ Description fetch failed for {video_id}: {e}")
        return None

    findings_raw = re.findall(r'(.{0,50})(https?://[^\s<>"]+)', description)

    broken_with_context = []
    seen_links = set()

    # Smoke-test links in parallel too
    candidate_links = []
    for anchor, raw_url in findings_raw:
        link = re.sub(r'[.,!?)]+$', '', raw_url)
        if not is_monetizable_link(link) or link in seen_links:
            continue
        seen_links.add(link)
        candidate_links.append((anchor, link))
    if candidate_links:                                                                                                                                                                                                 
            # Removed the nested ThreadPoolExecutor to prevent PC deadlocks!                                                                                                                                                
            for anchor, link in candidate_links:                                                                                                                                                                            
                status = smoke_test_link(link)                                                                                                                                                                              
                if status == "GOLD":                                                                                                                                                                                        
                    clean_anchor = anchor.strip().replace('\n', ' ')                                                                                                                                                        
                    print(f"     ❌ [DEAD] {link[:70]}")
                    broken_with_context.append({"link": link, "anchor": clean_anchor})

    if broken_with_context:
        return {
            "title": video['title'],
            "link": video['link'],
            "views": video['views'],
            "published_at": video['published_at'],
            "findings": broken_with_context
        }
    return None


def audit_videos(api_key, videos):
    """
    Audits ALL videos IN PARALLEL — each video's description is fetched
    and its links are smoke-tested concurrently.
    """
    print(f"\n🔍 Auditing {len(videos)} videos IN PARALLEL...")
    print("--------------------------------------------------")

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(audit_single_video, api_key, v): v for v in videos}
        for i, future in enumerate(as_completed(futures), 1):
            video = futures[future]
            print(f"  [{i}/{len(videos)}] ✅ Done: {video['title'][:55]}...")
            result = future.result()
            if result:
                results.append(result)

    return results


def get_channel_metadata(youtube, channel_id):
    try:
        response = youtube.channels().list(part="snippet", id=channel_id).execute()
        if response.get('items'):
            snippet = response['items'][0]['snippet']
            return {
                "title": snippet['title'],
                "description": snippet.get('description', 'No description available.')
            }
    except Exception as e:
        print(f"⚠️ Could not fetch channel metadata: {e}")
    return {"title": "Unknown", "description": "No description available."}


if __name__ == "__main__":
    youtube, used_key = get_youtube_client()
    print(f"✅ Using API key: {used_key[:8]}…")

    if len(sys.argv) >= 2:
        handle = sys.argv[1]
        max_results = int(sys.argv[2]) if len(sys.argv) >= 3 else 50
    else:
        handle = input("Enter YouTube Handle (e.g., @MarySpender): ")
        max_results = 50

    channel_id = get_channel_id_from_handle(youtube, handle)

    if channel_id:
        channel_meta = get_channel_metadata(youtube, channel_id)
        popular_videos = get_popular_videos(youtube, used_key, channel_id, max_results=max_results, min_age_years=1.5)
        print(f"\n✅ Retrieved {len(popular_videos)} videos. Starting parallel audit...")

        audit_results = audit_videos(used_key, popular_videos)

        if audit_results:
            rows = []
            total_views_affected = 0
            total_dead_links = 0
            for res in audit_results:
                total_views_affected += res['views']
                total_dead_links += len(res['findings'])

                findings_str = ""
                for f in res['findings']:
                    findings_str += f"{f['link']}   {f['anchor']}   "

                rows.append({
                    "Video Title": res['title'],
                    "Video Link": res['link'],
                    "Views": res['views'],
                    "Uploaded": res['published_at'],
                    "Broken Findings (Link + Anchor)": findings_str.strip()
                })

            df = pd.DataFrame(rows)
            audit_filename = f"audit_{handle.lstrip('@')}.csv"
            df.to_csv(audit_filename, index=False)

            master_file = os.path.join(PROJECT_ROOT, "master_targets.csv")
            master_row = {
                "Date": datetime.now().strftime("%Y-%m-%d"),
                "Handle": handle,
                "Channel Name": channel_meta['title'],
                "Total Broken Links": total_dead_links,
                "Views Affected": total_views_affected,
                "Channel Description": channel_meta['description']
            }
            master_df = pd.DataFrame([master_row])
            master_df.to_csv(master_file, mode='w', header=True, index=False)

            print(f"\n✨ Audit Complete. Found {total_dead_links} broken links.")
            print(f"📁 Report: {audit_filename}")

            # Link repetition report
            link_map = {}
            for res in audit_results:
                for f in res['findings']:
                    link_map.setdefault(f['link'], []).append(res['title'])

            repeated = {l: vids for l, vids in link_map.items() if len(vids) > 1}
            if repeated:
                print("\n📊 Repeated broken links:")
                rep_rows = []
                for l, vids in sorted(repeated.items(), key=lambda x: len(x[1]), reverse=True):
                    print(f"  🔗 {l} — in {len(vids)} videos")
                    rep_rows.append({
                        "Broken Link": l,
                        "Occurrence Count": len(vids),
                        "Affected Videos": " | ".join(vids)
                    })
                pd.DataFrame(rep_rows).to_csv(f"repetition_{handle.lstrip('@')}.csv", index=False)
            else:
                print("\nℹ️  No repeated broken links found.")

            print("🗃️  Master targets updated.")
        else:
            print("\n✅ Clean Audit! No broken links found.")
    else:
        print("\nCould not resolve channel. Please try again.")
