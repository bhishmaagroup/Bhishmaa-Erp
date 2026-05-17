
import smtplib
from email.mime.text import MIMEText
from models.super import SystemSetting

def send_system_email(recipient_email, subject, body):
    # Fetch credentials from your existing DB settings
    settings = {s.key: s.value for s in SystemSetting.query.all()}
    
    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = settings.get('SMTP_USER', 'noreply@platform.com')
    msg['To'] = recipient_email

    try:
        with smtplib.SMTP(settings.get('SMTP_HOST', 'smtp.gmail.com'), 
                          int(settings.get('SMTP_PORT', 587))) as server:
            server.starttls()
            server.login(settings.get('SMTP_USER'), settings.get('SMTP_PASS'))
            server.send_message(msg)
    except Exception as e:
        print(f"Email failed: {e}")