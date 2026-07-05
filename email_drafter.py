import os
import re
import glob
import pandas as pd
import requests
import json
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
DEFAULT_MODEL = "gemini-1.5-flash"  # Highly efficient, cost-effective, and fast
STAGE_FILE = "email_drafts.csv"
TARGETS_FILE = "master_targets.csv"

def normalize_unicode_digits(text):
    """
    Normalizes mathematical bold and double-struck unicode digits (e.g., 𝟖𝟎𝟎.𝟕𝟖) to standard ASCII digits.
    """
    out = []
    for char in text:
        val = ord(char)
        if 0x1D7CE <= val <= 0x1D7D7:      # Mathematical bold (𝟎-𝟗)
            out.append(chr(val - 0x1D7CE + 0x30))
        elif 0x1D7D8 <= val <= 0x1D7E1:    # Double-struck
            out.append(chr(val - 0x1D7D8 + 0x30))
        elif 0x1D7E2 <= val <= 0x1D7EB:    # Sans-serif bold
            out.append(chr(val - 0x1D7E2 + 0x30))
        else:
            out.append(char)
    return "".join(out)

def parse_txt_report(filepath):
    """
    Parses a detailed text report in the scanner's format to extract individual videos and total metrics.
    """
    print(f"📄 Parsing text report: {os.path.basename(filepath)}")
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Normalize unicode bold numbers first
    normalized_content = normalize_unicode_digits(content)
    
    # Extract total metrics
    total_monthly_leak = 0.0
    total_yearly_exposure = 0.0
    daily_cost_of_inaction = 0.0
    
    total_monthly_match = re.search(r'Total Monthly Leak:\s*(?:\\)?\$([0-9,.]+)', normalized_content)
    if total_monthly_match:
        total_monthly_leak = float(total_monthly_match.group(1).replace(',', ''))
        
    total_yearly_match = re.search(r'Total Yearly Exposure:\s*(?:\\)?\$([0-9,.]+)', normalized_content)
    if total_yearly_match:
        total_yearly_exposure = float(total_yearly_match.group(1).replace(',', ''))
        
    daily_cost_match = re.search(r'Daily Cost of Inaction:\s*(?:\\)?\$([0-9,.]+)', normalized_content)
    if daily_cost_match:
        daily_cost_of_inaction = float(daily_cost_match.group(1).replace(',', ''))

    # Parse videos
    videos = []
    parts = normalized_content.split('#### ')
    for part in parts[1:]:
        lines = part.strip().split('\n')
        if not lines:
            continue
        
        # Line 0: "1. Video Title (671,513 views)"
        header = lines[0].strip()
        header_match = re.match(r'^\d+\.\s*(.*?)\s*\(([0-9,]+)\s*views\)', header)
        if header_match:
            title = header_match.group(1).strip()
            views = int(header_match.group(2).replace(',', ''))
        else:
            title = re.sub(r'^\d+\.\s*', '', header).strip()
            views = 0
            
        link_info = "N/A"
        leak_val = 0.0
        
        for line in lines[1:]:
            line_str = line.strip()
            if line_str.startswith('• Link:'):
                link_info = line_str.replace('• Link:', '').strip()
            elif line_str.startswith('• Adjusted Monthly Leak:'):
                leak_match = re.search(r'=\s*(?:\\)?\$([0-9,.]+)', line_str)
                if not leak_match:
                    leak_match = re.search(r'(?:\\)?\$([0-9,.]+)', line_str)
                if leak_match:
                    leak_val = float(leak_match.group(1).replace(',', ''))
        
        videos.append({
            "title": title,
            "views": views,
            "link_info": link_info,
            "leak": leak_val
        })
        
    # Sort videos by leak (highest first)
    videos = sorted(videos, key=lambda x: x['leak'], reverse=True)
    
    return {
        "videos": videos,
        "total_monthly_leak": total_monthly_leak,
        "total_yearly_exposure": total_yearly_exposure,
        "daily_cost_of_inaction": daily_cost_of_inaction
    }

def find_audit_file(handle):
    """
    Searches the workspace for an audit text/CSV file associated with the handle.
    """
    clean_handle = handle.lstrip('@').lower()
    
    # List of possible filename patterns
    patterns = [
        f"audit_{clean_handle}.txt",
        f"audit_{clean_handle}.csv",
        f"report_{clean_handle}.txt",
        f"report_{clean_handle}.csv",
        f"*{clean_handle}*.txt",
        f"*{clean_handle}*.csv"
    ]
    
    for pat in patterns:
        matches = glob.glob(pat)
        if matches:
            return matches[0]
            
    return None

def extract_email(description):
    """
    Attempts to extract an email address from the channel description.
    """
    email_regex = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    match = re.search(email_regex, description)
    if match:
        return match.group(0)
    return "CHECK_EMAIL@placeholder.com"

def call_gemini_api(api_key, model, prompt):
    """
    Calls the Gemini API to get subject and body using JSON response.
    """
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    headers = {'Content-Type': 'application/json'}
    
    data = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json"
        }
    }
    
    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        res_json = response.json()
        try:
            text_response = res_json['candidates'][0]['content']['parts'][0]['text']
            return json.loads(text_response)
        except Exception as e:
            raise ValueError(f"Failed to parse JSON response from Gemini: {e}. Raw response: {text_response}")
    else:
        raise ValueError(f"Gemini API Error (HTTP {response.status_code}): {response.text}")

def draft_email_for_creator(api_key, channel_name, handle, email, audit_data):
    """
    Aggregates metrics and constructs an optimized, value-first cold email prompt for Gemini.
    """
    # Extract top 3 videos for personalization
    all_videos = audit_data["videos"]
    top_videos = all_videos[:3]
    remaining_count = len(all_videos) - 3
    remaining_leak = sum(v["leak"] for v in all_videos[3:])
    
    # Format the top videos context
    videos_context = ""
    for idx, v in enumerate(top_videos, 1):
        videos_context += f"Video {idx}: '{v['title']}'\n"
        videos_context += f"  - Views: {v['views']:,}\n"
        videos_context += f"  - Broken Link Info: {v['link_info']}\n"
        videos_context += f"  - Estimated Monthly Commission Loss: ${v['leak']:.2f}\n\n"
        
    summary_context = (
        f"Total Monthly Leakage across all videos: ${audit_data['total_monthly_leak']:.2f}\n"
        f"Total Yearly Exposure/Loss: ${audit_data['total_yearly_exposure']:.2f}\n"
        f"Daily Cost of Inaction: ${audit_data['daily_cost_of_inaction']:.2f}\n"
    )
    if remaining_count > 0:
        summary_context += f"Note: There are {remaining_count} other videos with broken links, totaling an additional ${remaining_leak:.2f}/mo in leaks.\n"

    # Load copying playbook principles
    prompt = f"""
You are a Copywriting Psychologist and Outbound Specialist. Your task is to draft a highly personalized cold email to the YouTube creator "{channel_name}" (handle: {handle}) alerting them of broken affiliate links on their channel.

Here is the data found by our scanner:
---
[TOP VIDEOS AUDITED]
{videos_context}

[OVERALL AUDIT METRICS]
{summary_context}
---

Your outreach strategy MUST follow the FetchUp Conversion playbook:
1. **Persona:** Helpful peer / developer who built a tool to scan their own channel because broken links drove them nuts. NEVER sound like a pushy salesman or agency.
2. **Subject Line Rules:**
   - Keep it informal, lowercase, and specific.
   - Example: "broken links in {channel_name}'s videos" or "quick heads up re: some broken links on your channel".
   - Avoid marketing clickbait.
3. **Email Body Rules:**
   - Start friendly and direct (e.g. "Hey {channel_name},").
   - Lead with the highest-impact video (Video 1) and specify exactly which link is broken (e.g. "the Amazon link for the camera is returning a 404").
   - Mention that you ran a quick scan and also saw a couple of other popular videos affected (mention Video 2 or Video 3 briefly).
   - Use the **ROI/Revenue Leak** metric naturally: explain that these videos get a lot of views, costing them an estimated ${audit_data['total_monthly_leak']:.0f}/month in lost commissions.
   - **Zero-Commitment CTA:** Offer to send them the full report with the complete list of broken links and where they are located, so they can swap them out easily. "Happy to send the list over if you want to swap them out? No catch, just paying it forward."
   - Do NOT try to sell or pitch FetchUp or a subscription in this first email. The goal is only to get them to reply.
   - Word count: Under 120 words. No walls of text. Make it easy to read.

Return your response in raw JSON format with the following keys:
- "subject": "Your subject line here"
- "body": "Your email body here (use \\n for line breaks)"
"""

    return call_gemini_api(api_key, DEFAULT_MODEL, prompt)

def main():
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        print("❌ Error: Missing GEMINI_API_KEY or YOUTUBE_API_KEY in .env file.")
        return
        
    if not os.path.exists(TARGETS_FILE):
        print(f"❌ Error: {TARGETS_FILE} not found. Run the channel scanner first.")
        return
        
    targets_df = pd.read_csv(TARGETS_FILE)
    if targets_df.empty:
        print("ℹ️  No targets found in master_targets.csv.")
        return
        
    # Read existing drafts to avoid overwriting or duplicates
    existing_drafts = set()
    if os.path.exists(STAGE_FILE):
        try:
            drafts_df = pd.read_csv(STAGE_FILE)
            existing_drafts = set(drafts_df['Handle'].str.lower().tolist())
        except Exception:
            pass
            
    drafts_list = []
    
    print(f"🚀 Processing {len(targets_df)} targets from {TARGETS_FILE}...")
    
    for idx, row in targets_df.iterrows():
        handle = str(row['Handle'])
        channel_name = str(row['Channel Name'])
        description = str(row.get('Channel Description', ''))
        
        if handle.lower() in existing_drafts:
            print(f"⏭️  Skipping {handle} (Draft already exists in {STAGE_FILE})")
            continue
            
        audit_file = find_audit_file(handle)
        if not audit_file:
            print(f"⚠️  Could not find audit file (CSV or TXT) for {handle}. Skipping.")
            continue
            
        try:
            # Parse audit file (support both text reports and CSV)
            if audit_file.endswith('.txt'):
                audit_data = parse_txt_report(audit_file)
            else:
                # Fallback to CSV parser if needed
                print(f"📊 Reading CSV audit file: {audit_file}")
                df_audit = pd.read_csv(audit_file)
                # Clean up column names to prevent spacing issues
                df_audit.columns = [col.strip() for col in df_audit.columns]
                
                # Extract views and leaks
                videos = []
                for _, v_row in df_audit.iterrows():
                    title = v_row.get('Video Title', 'Unknown Video')
                    views = int(str(v_row.get('Views', 0)).replace(',', ''))
                    link = v_row.get('Broken Findings (Link + Anchor)', 'N/A')
                    # If leak is not present in csv, estimate it
                    leak = float(v_row.get('Leak', 0.0))
                    if leak == 0.0:
                        # Placeholder estimation (e.g. 0.5% evergreen * 4.2% CTR * $7 EPC * 0.8)
                        leak = (views * 0.005 * 0.042 * 7.10) * 0.8
                    videos.append({
                        "title": title,
                        "views": views,
                        "link_info": link,
                        "leak": leak
                    })
                videos = sorted(videos, key=lambda x: x['leak'], reverse=True)
                audit_data = {
                    "videos": videos,
                    "total_monthly_leak": sum(v['leak'] for v in videos),
                    "total_yearly_exposure": sum(v['leak'] for v in videos) * 12,
                    "daily_cost_of_inaction": (sum(v['leak'] for v in videos) * 12) / 365
                }
                
            if not audit_data["videos"]:
                print(f"⚠️  No broken videos parsed from {audit_file}. Skipping.")
                continue
                
            email = extract_email(description)
            
            print(f"🤖 Calling Gemini to draft email for {channel_name} ({handle})...")
            draft = draft_email_for_creator(api_key, channel_name, handle, email, audit_data)
            
            drafts_list.append({
                "Handle": handle,
                "Channel Name": channel_name,
                "Recipient Email": email,
                "Subject": draft["subject"],
                "Body": draft["body"],
                "Status": "Pending Review"
            })
            print(f"✅ Draft created successfully!")
            
        except Exception as e:
            print(f"❌ Error drafting for {handle}: {e}")
            
    # Append or write new drafts to CSV
    if drafts_list:
        new_drafts_df = pd.DataFrame(drafts_list)
        if os.path.exists(STAGE_FILE):
            new_drafts_df.to_csv(STAGE_FILE, mode='a', header=False, index=False)
        else:
            new_drafts_df.to_csv(STAGE_FILE, index=False)
        print(f"\n💾 Saved {len(drafts_list)} new drafts to {STAGE_FILE}")
    else:
        print("\nℹ️  No new drafts generated.")

if __name__ == "__main__":
    main()
