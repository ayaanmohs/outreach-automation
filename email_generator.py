import os
import re
import glob
import json
import pandas as pd
import csv
import argparse
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
DASHBOARD_DIR = "master_dashboard"
TEMPLATES_FILE = "email_templates.json"
STAGE_FILE = "email_drafts.csv"
TARGETS_FILE = "master_targets.csv"
DEFAULT_TEMPLATE_NAME = "default_outreach"

def extract_email(description):
    """
    Extracts email addresses from the description.
    """
    if pd.isna(description):
        return "CHECK_EMAIL@placeholder.com"
    email_regex = r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
    match = re.search(email_regex, str(description))
    if match:
        return match.group(0)
    return "CHECK_EMAIL@placeholder.com"

def parse_videos_from_breakdown(filepath):
    """
    Parses individual video details from the breakdown text file.
    """
    videos = []
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Split content by the video number pattern: "1. ", "2. ", etc.
    # e.g., "1. video title\n   - Video Link: ...\n"
    sections = re.split(r'\n\d+\.\s+', content)
    
    # The first section is the header metadata before the list, so skip it
    for section in sections[1:]:
        lines = section.strip().split('\n')
        if not lines:
            continue
            
        title = lines[0].strip()
        
        video_link = "N/A"
        category = "Affiliate Link"
        
        for line in lines[1:]:
            line_str = line.strip()
            if line_str.startswith('- Video Link:'):
                video_link = line_str.replace('- Video Link:', '').strip()
            elif line_str.startswith('- Link Categories:'):
                category = line_str.replace('- Link Categories:', '').strip()
                
        videos.append({
            "title": title,
            "video_link": video_link,
            "category": category
        })
        
    return videos

def parse_breakdown_txt(filepath):
    """
    Parses total metrics from master_dashboard/breakdown_<handle>.txt
    """
    metrics = {
        "total_views_affected": 0,
        "total_monthly_leak": 0.0,
        "total_yearly_exposure": 0.0,
        "daily_leak": 0.0
    }
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    views_match = re.search(r'Total Views Affected:\s*([0-9,.]+)', content)
    if views_match:
        metrics["total_views_affected"] = int(views_match.group(1).replace(',', ''))
        
    monthly_match = re.search(r'Adjusted Monthly Leak:\s*\$([0-9,.]+)', content)
    if monthly_match:
        metrics["total_monthly_leak"] = float(monthly_match.group(1).replace(',', ''))
        
    yearly_match = re.search(r'Adjusted Yearly Exposure:\s*\$([0-9,.]+)', content)
    if yearly_match:
        metrics["total_yearly_exposure"] = float(yearly_match.group(1).replace(',', ''))
        
    daily_match = re.search(r'Daily Cost of Inaction:\s*\$([0-9,.]+)', content)
    if daily_match:
        metrics["daily_leak"] = float(daily_match.group(1).replace(',', ''))
        
    return metrics

def main():
    # Argument parser for optional single-handle mode
    parser = argparse.ArgumentParser(description='Generate email drafts')
    parser.add_argument('--handle', type=str, help='Process a single handle (without @)')
    args = parser.parse_args()
    single_handle = args.handle.lower().lstrip('@') if args.handle else None

    # 1. Load templates
    if not os.path.exists(TEMPLATES_FILE):
        print(f"❌ Error: Templates file '{TEMPLATES_FILE}' not found.")
        return
        
    with open(TEMPLATES_FILE, 'r', encoding='utf-8') as f:
        templates = json.load(f)
        
    template = templates.get(DEFAULT_TEMPLATE_NAME)
    if not template:
        print(f"❌ Error: Default template '{DEFAULT_TEMPLATE_NAME}' not found in templates.json.")
        return

    # 2. Helper to lazily fetch channel details for a given handle
    def get_creator_info(handle_key):
        """Return dict with channel_name and description for handle_key (lowercase, no @)."""
        if not os.path.exists(TARGETS_FILE):
            return {"channel_name": handle_key, "description": ""}
        try:
            with open(TARGETS_FILE, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    h = str(row.get('Handle', '')).strip().lower().lstrip('@')
                    if h == handle_key:
                        return {
                            "channel_name": row.get('Channel Name', h),
                            "description": row.get('Channel Description', '')
                        }
        except Exception as e:
            print(f"⚠️  Warning reading {TARGETS_FILE}: {e}")
        return {"channel_name": handle_key, "description": ""}

    # 3. Read existing drafts to avoid duplicates
    existing_drafts = set()
    if os.path.exists(STAGE_FILE):
        try:
            drafts_df = pd.read_csv(STAGE_FILE)
            if 'Handle' in drafts_df.columns:
                existing_drafts = set(drafts_df['Handle'].str.lower().tolist())
        except Exception:
            pass

    # 4. Determine which breakdown files to process
    if single_handle:
        # Look for a specific breakdown file matching the handle
        target_file = os.path.join(DASHBOARD_DIR, f"breakdown_{single_handle}.txt")
        breakdown_files = [target_file] if os.path.exists(target_file) else []
        if not breakdown_files:
            print(f"⚠️  No breakdown file found for handle '{single_handle}'.")
            return
    else:
        breakdown_pattern = os.path.join(DASHBOARD_DIR, "breakdown_*.txt")
        breakdown_files = glob.glob(breakdown_pattern)
        if not breakdown_files:
            print(f"ℹ️  No breakdown files found in '{DASHBOARD_DIR}/'. Run calculate_leaks.py first.")
            return
    
    new_drafts = []
    
    print(f"🚀 Processing {len(breakdown_files)} breakdown report(s)...")
    
    for txt_file in breakdown_files:
        filename = os.path.basename(txt_file)
        # Extract clean handle name: breakdown_username.txt -> username
        clean_handle = filename.replace("breakdown_", "").replace(".txt", "")
        handle_with_at = f"@{clean_handle}"
        
        if handle_with_at.lower() in existing_drafts:
            print(f"⏭️  Skipping {handle_with_at} (Draft already exists in {STAGE_FILE})")
            continue
            
        csv_file = os.path.join(DASHBOARD_DIR, f"audit_{clean_handle}_categorized.csv")
        has_csv = os.path.exists(csv_file)
        
        try:
            # Parse metrics from txt
            metrics = parse_breakdown_txt(txt_file)
            
            top_video_title = "Unknown Video"
            category = "Affiliate Link"
            broken_link_url = "[insert broken link]"
            total_broken_videos = 1
            
            if has_csv:
                # Load and parse top video info from categorized CSV
                audit_df = pd.read_csv(csv_file)
                if not audit_df.empty:
                    total_broken_videos = len(audit_df)
                    top_video = audit_df.iloc[0]
                    top_video_title = top_video.get('Video Title', 'Unknown Video')
                    category = top_video.get('Categories', 'Affiliate Link')
                    raw_findings = str(top_video.get('Raw Findings', ''))
                    
                    # Extract first URL from Raw Findings (split by 3 spaces)
                    findings_parts = [p.strip() for p in raw_findings.split('   ') if p.strip()]
                    broken_link_url = findings_parts[0] if findings_parts else "N/A"
            else:
                # Fallback: Parse from text breakdown directly
                txt_videos = parse_videos_from_breakdown(txt_file)
                if txt_videos:
                    total_broken_videos = len(txt_videos)
                    top_video = txt_videos[0]
                    top_video_title = top_video["title"]
                    category = top_video["category"]
                    broken_link_url = "[insert broken link]"
            
            # Look up channel details
            # Lazy lookup of creator info for this handle
            creator_info = get_creator_info(clean_handle.lower())
            channel_name = creator_info["channel_name"]
            email = extract_email(creator_info["description"])
            
            # Fill placeholders
            placeholders = {
                "channel_name": channel_name,
                "top_video_title": top_video_title,
                "category": category,
                "broken_link_url": broken_link_url,
                "total_broken_videos": str(total_broken_videos),
                "total_monthly_leak": f"{metrics['total_monthly_leak']:.2f}",
                "daily_leak": f"{metrics['daily_leak']:.2f}"
            }
            
            subject = template["subject"].format(**placeholders)
            body = template["body"].format(**placeholders)
            
            new_drafts.append({
                "Handle": handle_with_at,
                "Channel Name": channel_name,
                "Recipient Email": email,
                "Subject": subject,
                "Body": body,
                "Status": "Pending Review"
            })
            print(f"✅ Generated draft for {handle_with_at}")
            
        except Exception as e:
            print(f"❌ Error generating draft for {handle_with_at}: {e}")
            
    # Append or create email_drafts.csv
    if new_drafts:
        new_df = pd.DataFrame(new_drafts)
        if os.path.exists(STAGE_FILE):
            # Read existing to ensure correct headers/columns match
            try:
                existing_df = pd.read_csv(STAGE_FILE)
                # Keep matching columns structure
                for col in existing_df.columns:
                    if col not in new_df.columns:
                        new_df[col] = ""
                new_df = new_df[existing_df.columns]
                new_df.to_csv(STAGE_FILE, mode='a', header=False, index=False)
            except Exception:
                new_df.to_csv(STAGE_FILE, mode='a', header=False, index=False)
        else:
            new_df.to_csv(STAGE_FILE, index=False)
        print(f"\n💾 Saved {len(new_drafts)} new drafts to {STAGE_FILE}")
    else:
        print("\nℹ️  No new drafts to generate.")

if __name__ == "__main__":
    main()
