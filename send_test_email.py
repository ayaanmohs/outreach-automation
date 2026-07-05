import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

def main():
    sender_email = os.getenv("GMAIL_USER")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    
    if not sender_email or not app_password:
        print("❌ Error: Missing GMAIL_USER or GMAIL_APP_PASSWORD in .env file.")
        print("💡 Please ensure your .env file has the following:")
        print("   GMAIL_USER=your_email@gmail.com")
        print("   GMAIL_APP_PASSWORD=abcdefghijklmnop")
        return

    print("🔌 Gmail Connection Test Script")
    print("---------------------------------")
    recipient = input("Recipient Email: ")
    subject = input("Subject: ")
    body = input("Message Body: ")

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    print(f"\n📧 Connecting to Gmail SMTP server on behalf of {sender_email}...")
    try:
        # Connect via SSL
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(sender_email, app_password)
            print("🔑 Authentication successful! Sending email...")
            server.sendmail(sender_email, recipient, msg.as_string())
        print(f"✅ Email successfully sent to {recipient}!")
    except Exception as e:
        print(f"❌ Failed to send email: {e}")

if __name__ == "__main__":
    main()
