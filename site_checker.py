import requests
import re
import sys

def check_site_brute_force(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    }
    
    print(f"\n🔱 [BRUTE FORCE] Auditing Site: {url}")
    print("--------------------------------------------------")
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        # Use Regex to find URLs even inside JavaScript/JSON blobs
        raw_html = response.text
        # Look for anything starting with http/https that looks like a link
        links = re.findall(r'https?://[^\s<>"]+', raw_html)
        
        # Filter out common junk
        filtered_links = []
        exclude = ['beacons.ai', 'w3.org', 'google', 'facebook', 'twitter', 'instagram', 'linkedin', 'schema.org']
        for l in links:
            if not any(x in l.lower() for x in exclude):
                filtered_links.append(l)
        
        unique_links = list(set(filtered_links))
        print(f"🔗 Found {len(unique_links)} potential outgoing links in the source code. Testing now...\n")
        
        gold_count = 0
        for i, link in enumerate(unique_links):
            try:
                # Beacons often uses redirects, so allow_redirects is key
                res = requests.get(link, headers=headers, timeout=8, allow_redirects=True)
                if res.status_code == 404:
                    print(f"❌ [GOLD] 404 Found: {link}")
                    gold_count += 1
            except:
                pass
                
        print("\n--------------------------------------------------")
        print(f"✨ Brute Force Complete. Total GOLD found: {gold_count}")
        if gold_count == 0:
            print("💡 TIP: Beacons is an app. If this failed, hit his OLD YouTube videos instead.")
        
    except Exception as e:
        print(f"❌ Critical Error: {e}")

if __name__ == "__main__":
    target_site = input("Enter the Website URL: ")
    if not target_site.startswith("http"):
        target_site = "https://" + target_site
    check_site_brute_force(target_site)
