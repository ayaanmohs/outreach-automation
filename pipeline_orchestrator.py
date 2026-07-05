"""
pipeline_orchestrator.py
========================
Full outreach pipeline runner. Executes:
  1. Run lead_finder.py to populate internal_tools/creators_to_scan.txt
  2. Load pending handles from the queue file
  3. Audit up to 10 handles in parallel (ThreadPoolExecutor)
     (calculate_leaks internally calls internal_tools/channel_scanner.py)
  4. Move successfully audited handles to processed_handles.txt
  5. After all handles are processed → python email_generator.py
  6. Print a summary and remind you to review email_drafts.csv

Usage:
  python pipeline_orchestrator.py

  # Skip the audit step and only regenerate email drafts:
  python pipeline_orchestrator.py --drafts-only

  # Skip lead_finder (use existing queue):
  python pipeline_orchestrator.py --skip-lead-finder
"""

import os
import sys
import subprocess
import argparse
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Paths ──────────────────────────────────────────────────────────────
QUEUE_FILE      = "internal_tools/creators_to_scan.txt"
PROCESSED_FILE  = "processed_handles.txt"
CALCULATE_LEAKS = "calculate_leaks.py"
EMAIL_GENERATOR = "email_generator.py"
EMAIL_SENDER    = "email_sender.py"
DRAFTS_FILE     = "email_drafts.csv"
DASHBOARD_DIR   = "master_dashboard"

# Thread-safe lock for writing to shared files
_file_lock = threading.Lock()


def load_queue():
    """Return list of handles still pending audit."""
    if not os.path.exists(QUEUE_FILE):
        print(f"[ERROR] Queue file not found: {QUEUE_FILE}")
        return []
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def load_processed():
    """Return set of already-processed handles (lowercase, no @)."""
    if not os.path.exists(PROCESSED_FILE):
        return set()
    with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        return {line.strip().lower().lstrip("@") for line in f if line.strip()}


def mark_processed(handle):
    """Append a handle to processed_handles.txt (thread-safe)."""
    with _file_lock:
        needs_newline = False
        if os.path.exists(PROCESSED_FILE):
            with open(PROCESSED_FILE, "rb") as f:
                f.seek(0, 2)
                if f.tell() > 0:
                    f.seek(-1, 2)
                    needs_newline = f.read(1) != b"\n"
        with open(PROCESSED_FILE, "a", encoding="utf-8") as f:
            if needs_newline:
                f.write("\n")
            f.write(handle + "\n")
    print(f"  ✅ Marked {handle} as processed.")


def remove_from_queue(handle):
    """Remove a specific handle from creators_to_scan.txt (thread-safe)."""
    with _file_lock:
        if not os.path.exists(QUEUE_FILE):
            return
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        remaining = [
            line for line in lines
            if line.strip().lower().lstrip("@") != handle.lower().lstrip("@")
        ]
        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            f.writelines(remaining)


def audit_was_successful(handle):
    """
    Returns True if calculate_leaks produced output files for this handle.
    A 'clean' audit (no leaks) is still treated as successful — handle
    gets moved out of the queue so it doesn't get re-scanned repeatedly.
    """
    clean = handle.lstrip("@")
    breakdown_txt   = os.path.join(DASHBOARD_DIR, f"breakdown_{clean}.txt")
    categorized_csv = os.path.join(DASHBOARD_DIR, f"audit_{clean}_categorized.csv")
    return os.path.exists(breakdown_txt) or os.path.exists(categorized_csv)


def audit_handle(handle):
    """
    Run calculate_leaks.py --handle <handle> in a subprocess.
    Returns (handle, success_bool).
    """
    print(f"\n{'─'*60}")
    print(f"  [AUDIT] {handle}  •  {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'─'*60}")

    result = subprocess.run(
        [sys.executable, CALCULATE_LEAKS, "--handle", handle],
        capture_output=False   # stream stdout/stderr to terminal
    )

    success = audit_was_successful(handle)
    if success:
        mark_processed(handle)
        remove_from_queue(handle)
    else:
        print(f"  ⚠️  Audit for {handle} produced no output files — leaving in queue for retry.")

    return handle, success


def run_email_generator():
    """Run email_generator.py to (re)build email_drafts.csv."""
    print(f"\n{'═'*60}")
    print("  [DRAFTS] Generating email drafts...")
    print(f"{'═'*60}\n")
    result = subprocess.run(
        [sys.executable, EMAIL_GENERATOR],
        capture_output=False
    )
    return result.returncode == 0


def print_summary(audited, skipped, failed, drafts_generated):
    print(f"\n{'═'*60}")
    print("  PIPELINE COMPLETE — SUMMARY")
    print(f"{'═'*60}")
    print(f"  Handles audited successfully : {audited}")
    print(f"  Handles skipped (already processed): {skipped}")
    print(f"  Handles failed / no output   : {failed}")
    print(f"  New email drafts generated   : {drafts_generated}")
    if drafts_generated > 0:
        print(f"\n  📋 Review your drafts in  →  {DRAFTS_FILE}")
        print("     Change 'Status' from 'Pending Review' to 'Approved'")
        print("     for any email you want to send, then run:")
        print(f"       python {EMAIL_SENDER}")
    print(f"{'═'*60}\n")


def count_rows(drafts_file):
    """Return current row count of drafts file (0 if missing)."""
    if not os.path.exists(drafts_file):
        return 0
    import csv
    with open(drafts_file, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
    return max(0, len(rows) - 1)  # subtract header


def main():
    parser = argparse.ArgumentParser(
        description="Outreach Automation Pipeline Orchestrator"
    )
    parser.add_argument(
        "--drafts-only",
        action="store_true",
        help="Skip auditing — only regenerate email_drafts.csv from existing dashboard data."
    )
    parser.add_argument(
        "--skip-lead-finder",
        action="store_true",
        help="Do not run lead_finder.py before the audit step."
    )
    args = parser.parse_args()

    print(f"\n{'═'*60}")
    print("  🚀 OUTREACH PIPELINE — STARTING")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'═'*60}\n")

    audited_count = 0
    skipped_count = 0
    failed_count  = 0

    if not args.drafts_only:
        # ── Step 0: Run lead_finder ─────────────────────────────────────
        if not args.skip_lead_finder:
            print("🔍 Running lead_finder to populate queue...")
            result = subprocess.run([sys.executable, "lead_finder.py"], capture_output=False)
            if result.returncode != 0:
                print("⚠️  lead_finder.py exited with errors — proceeding with existing queue.")

        # ── Step 1: Load queue ──────────────────────────────────────────
        handles = load_queue()
        if not handles:
            print(f"  ℹ️  Queue is empty ({QUEUE_FILE}). Nothing to audit.")
        else:
            processed = load_processed()
            pending = [h for h in handles if h.lower().lstrip("@") not in processed]
            skipped_count = len(handles) - len(pending)

            print(f"  📋 {len(handles)} handle(s) in queue.")
            print(f"  ✔️  {skipped_count} handle(s) already processed (skipping).")
            print(f"  🚀 Auditing {len(pending)} handle(s) in parallel (up to 10 at once)...\n")

            if pending:
                # ── Step 2: Parallel audit ──────────────────────────────
                with ThreadPoolExecutor(max_workers=3) as executor:
                    future_map = {executor.submit(audit_handle, h): h for h in pending}
                    for future in as_completed(future_map):
                        handle, success = future.result()
                        if success:
                            audited_count += 1
                        else:
                            failed_count += 1

    # ── Step 3: Generate email drafts ───────────────────────────────────
    before  = count_rows(DRAFTS_FILE)
    success = run_email_generator()
    after   = count_rows(DRAFTS_FILE)
    new_drafts = max(0, after - before)

    if not success:
        print("  ⚠️  email_generator.py exited with an error — check output above.")

    # ── Step 4: Summary ─────────────────────────────────────────────────
    print_summary(audited_count, skipped_count, failed_count, new_drafts)


if __name__ == "__main__":
    main()
