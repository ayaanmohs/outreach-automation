import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import pandas as pd
from datetime import datetime
import random, time
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
STAGE_FILE = "email_drafts.csv"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 465  # SSL port

def send_email(sender_email, app_password, recipient_email, subject, body):
    """
    Sends an email using Gmail SMTP and a Google App Password.
    """
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = subject
    
    # Attach email body (UTF-8 encoding)
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(sender_email, app_password)
            server.sendmail(sender_email, recipient_email, msg.as_string())
        return True
    except Exception as e:
        print(f"❌ SMTP Error: {e}")
        return False

def main():
    sender_email = os.getenv("GMAIL_USER") or os.getenv("SENDER_EMAIL")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    
    if not sender_email or not app_password:
        print("❌ Error: Missing GMAIL_USER or GMAIL_APP_PASSWORD in .env file.")
        print("💡 Please follow the setup guide to generate a Gmail App Password and configure it in your .env:")
        print("   GMAIL_USER=your_email@gmail.com")
        print("   GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx")
        return
        
    if not os.path.exists(STAGE_FILE):
        print(f"ℹ️  No drafts file found ({STAGE_FILE}). Run email_drafter.py first.")
        return
        
    try:
        df = pd.read_csv(STAGE_FILE)
    except Exception as e:
        print(f"❌ Error reading {STAGE_FILE}: {e}")
        return
        
    if df.empty:
        print("ℹ️  No drafts found in the stage file.")
        return
        
    # Check if 'Status' column exists
    if 'Status' not in df.columns:
        print("⚠️  Invalid drafts file. Status column not found.")
        return
        
    approved_mask = df['Status'].str.strip().str.lower() == 'approved'
    approved_count = approved_mask.sum()
    
    if approved_count == 0:
        print(f"ℹ️  No approved drafts found in {STAGE_FILE}.")
        print("💡 Open the file and change the 'Status' of the drafts you want to send from 'Pending Review' to 'Approved'.")
        return
        
    print(f"✉️  Found {approved_count} approved emails to send.")
    
    sent_count = 0
    for idx, row in df[approved_mask].iterrows():
        handle = row['Handle']
        recipient = row['Recipient Email']
        subject = row['Subject']
        body = row['Body']
        
        print(f"\n📧 Sending email to {row['Channel Name']} ({recipient})...")
        
        # Guard against placeholder emails
        if "placeholder.com" in recipient or "@example.com" in recipient:
            print(f"⚠️  Skipping: '{recipient}' is a placeholder email. Please correct it in {STAGE_FILE} first.")
            continue
            
        success = send_email(sender_email, app_password, recipient, subject, body)
        if success:
            print(f"✅ Successfully sent to {recipient}!")
            df.at[idx, 'Status'] = 'Sent'
            df.at[idx, 'Sent At'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sent_count += 1
        else:
            print(f"❌ Failed to send email to {recipient}.")
            df.at[idx, 'Status'] = 'Failed'
        # Randomised wait between 2 and 4 minutes to mimic human behaviour
        delay_seconds = random.randint(120, 240)
        print(f"⏳ Waiting {delay_seconds}s before next email...")
        time.sleep(delay_seconds)
            
    # Save the updated status back to the CSV
    try:
        df.to_csv(STAGE_FILE, index=False)
        print(f"\n💾 Status updates saved. Sent {sent_count} of {approved_count} approved emails.")
    except Exception as e:
        print(f"❌ Error saving updates to {STAGE_FILE}: {e}")

if __name__ == "__main__":
    main()
