import os
import re
import sys
import argparse
import pandas as pd
import subprocess
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

DASHBOARD_DIR = "master_dashboard"

if not os.path.exists(DASHBOARD_DIR):
    os.makedirs(DASHBOARD_DIR)


def get_velocity(days_old, views):
    if views > 10_000_000: return 0.0006
    months_old = days_old / 30.44
    if months_old < 3: return 0.25
    if months_old < 12: return 0.02
    if months_old < 36: return 0.005
    return 0.0006


def categorize_link(url, anchor):
    u = str(url).lower()
    a = str(anchor).lower()

    if "patreon" in u or "patreon" in a or "support" in a:
        return "RECURRING / PATREON", 15.00
    if any(p in u for p in ["gumroad.com", "teachable.com", "kajabi.com", "stan.store", "course", "academy", "masterclass", "webinar", "preset", "lut"]):
        return "COURSE / DIGITAL PRODUCT", 15.00
    if any(p in u for p in ["unacademy", "onelink.me", "sponsorship", "deal"]):
        return "PARTNERSHIP / SPONSORSHIP", 12.50
    if any(p in u for p in ["clkmg.com", "software", "vpn", "hosting"]):
        return "SAAS / SOFTWARE", 12.50
    if any(p in u for p in ["case", "cover", "strap", "cable", "hub", "sleeve", "bag", "pouch", "stand", "mount"]):
        return "SECONDARY GEAR / CASES", 3.50
    return "AFFILIATE (Gear/Tech)", 7.10


def parse_findings(findings_str):
    if pd.isna(findings_str) or not str(findings_str).strip():
        return []

    parts = [p.strip() for p in str(findings_str).split('   ') if p.strip()]

    parsed = []
    for i in range(0, len(parts), 2):
        if i + 1 < len(parts):
            link = parts[i]
            anchor = parts[i + 1]
            cat, epc = categorize_link(link, anchor)
            parsed.append({
                "link": link,
                "anchor": anchor,
                "category": cat,
                "epc": epc
            })
    return parsed


def calculate_video_leak(views, uploaded_date, parsed_links):
    if not parsed_links:
        return 0.0, 0.0, 0, []

    try:
        upload_dt = datetime.strptime(str(uploaded_date).strip(), "%Y-%m-%d")
        days_old = (datetime.now() - upload_dt).days
    except Exception:
        days_old = 1000

    velocity = get_velocity(days_old, views)
    monthly_views = int(views * velocity)

    ctr = 0.012 if views > 1_000_000 else 0.042

    avg_epc = sum(link['epc'] for link in parsed_links) / len(parsed_links)

    monthly_leak = (monthly_views * ctr * avg_epc) * 0.80
    yearly_exposure = monthly_leak * 12

    categories = list(set(link['category'] for link in parsed_links))

    return round(monthly_leak, 2), round(yearly_exposure, 2), monthly_views, categories


def run_audit(handle):
    print(f"\n[{handle}] [START] Starting Audit...")
    SCANNER_PATH = "internal_tools/channel_scanner.py"

    try:
        subprocess.run([sys.executable, SCANNER_PATH, handle, "50"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[{handle}] [ERROR] Scanner failed: {e}")
        return None

    clean_handle = handle.lstrip('@')
    input_csv = f"audit_{clean_handle}.csv"

    if not os.path.exists(input_csv):
        print(f"[{handle}] [WARNING] No audit file created. Channel may be clean or unavailable.")
        return None

    try:
        df = pd.read_csv(input_csv)
        if df.empty:
            print(f"[{handle}] [CLEAN] Audit was clean (empty file).")
            return None

        # Strip whitespace from all column names and drop empty spacer columns
        df.columns = [c.strip() for c in df.columns]
        df = df.loc[:, df.columns != '']

        all_videos = []
        total_monthly_leak = 0.0
        total_yearly_exposure = 0.0
        total_views_affected = 0

        for _, row in df.iterrows():
            title = row['Video Title']
            video_link = row['Video Link']
            views = int(row['Views'])
            uploaded = row['Uploaded']
            findings_str = row['Broken Findings (Link + Anchor)']

            parsed_links = parse_findings(findings_str)
            if not parsed_links:
                continue

            m_leak, y_leak, m_views, categories = calculate_video_leak(views, uploaded, parsed_links)

            total_monthly_leak += m_leak
            total_yearly_exposure += y_leak
            total_views_affected += views

            all_videos.append({
                "Video Title": title,
                "Video Link": video_link,
                "Views": views,
                "Monthly Views": m_views,
                "Monthly Leak": m_leak,
                "Yearly Exposure": y_leak,
                "Categories": ", ".join(categories),
                "Raw Findings": findings_str
            })

        if not all_videos:
            print(f"[{handle}] [CLEAN] No valid monetizable leaks found.")
            return None

        raw_df = pd.DataFrame(all_videos)
        raw_csv_path = os.path.join(DASHBOARD_DIR, f"audit_{clean_handle}_categorized.csv")
        raw_df.to_csv(raw_csv_path, index=False)

        top_10 = sorted(all_videos, key=lambda x: x['Monthly Leak'], reverse=True)[:10]

        txt_path = os.path.join(DASHBOARD_DIR, f"breakdown_{clean_handle}.txt")
        with open(txt_path, 'w', encoding='utf-8') as f:
            f.write(f"CREATOR AUDIT BREAKDOWN: {handle}\n")
            f.write(f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n")
            f.write("CHANNEL-WIDE AUDIT METRICS:\n")
            f.write(f"- Total Views Affected: {total_views_affected:,} views\n")
            f.write(f"- Adjusted Monthly Leak: ${round(total_monthly_leak, 2):,}\n")
            f.write(f"- Adjusted Yearly Exposure: ${round(total_yearly_exposure, 2):,}\n")
            f.write(f"- Daily Cost of Inaction: ${round(total_yearly_exposure / 365, 2):,}\n")
            f.write("=" * 60 + "\n\n")

            f.write(f"TOP {len(top_10)} LEAKING VIDEOS BREAKDOWN:\n\n")
            for idx, vid in enumerate(top_10, 1):
                f.write(f"{idx}. {vid['Video Title']}\n")
                f.write(f"   - Video Link: {vid['Video Link']}\n")
                f.write(f"   - Views: {vid['Views']:,}\n")
                f.write(f"   - Monthly Views: {vid['Monthly Views']:,}\n")
                f.write(f"   - Adjusted Monthly Leak: ${vid['Monthly Leak']}\n")
                f.write(f"   - Adjusted Yearly Exposure: ${vid['Yearly Exposure']}\n")
                f.write(f"   - Link Categories: {vid['Categories']}\n")
                f.write("\n")

        print(f"[{handle}] [SUCCESS] Saved: audit_{clean_handle}_categorized.csv | breakdown_{clean_handle}.txt")
        return {"Handle": handle, "Total Leak": total_yearly_exposure}

    except Exception as e:
        print(f"[{handle}] [ERROR] Analysis error: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    parser = argparse.ArgumentParser(description="Calculate revenue leaks for YouTube creators.")
    parser.add_argument(
        "--handle",
        type=str,
        default=None,
        help="Single creator handle to audit (e.g. @reysu). If omitted, reads all handles from internal_tools/creators_to_scan.txt."
    )
    args = parser.parse_args()

    if args.handle:
        handles = [args.handle]
    else:
        HANDLES_FILE = "internal_tools/creators_to_scan.txt"
        if not os.path.exists(HANDLES_FILE):
            print(f"[ERROR] {HANDLES_FILE} not found.")
            return

        with open(HANDLES_FILE, 'r') as f:
            handles = [line.strip() for line in f if line.strip()]

    if not handles:
        print("[INFO] No handles to process.")
        return

    # 10 workers: audits up to 10 creators simultaneously
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(run_audit, h) for h in handles]
        all_summary = []
        for future in as_completed(futures):
            res = future.result()
            if res:
                all_summary.append(res)

    print("\n" + "=" * 60)
    print("BATCH AUDIT COMPLETE SUMMARY")
    print("=" * 60)
    if all_summary:
        for s in all_summary:
            print(f"  {s['Handle']}: ${round(s['Total Leak'], 2):,} Annual Leak")
    else:
        print("  No revenue leaks detected.")


if __name__ == "__main__":
    main()
