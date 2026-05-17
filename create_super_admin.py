from app import create_app
from extensions import db
from models.super_admin import SuperAdmin
from werkzeug.security import generate_password_hash
import random, string
from utils.email import send_system_email

ADMIN_EMAIL = "enoughsudhanshu@gmail.com"


def generate_password():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))


def create_super_admin():

    app = create_app()   # 🔥 IMPORTANT (no circular import)

    with app.app_context():

        # 🔒 Check admin exists
        admin = SuperAdmin.query.first()

        if admin:
            print("Admin already exists → skip")
            return

        username = "enough"
        password = generate_password()

        admin = SuperAdmin(
            username=username,
            password=generate_password_hash(password)
        )

        db.session.add(admin)
        db.session.commit()

        # 📧 SEND EMAIL ONLY ON FIRST CREATE
        try:
            send_system_email(
                to_email=ADMIN_EMAIL,
                subject="Super Admin Credentials",
                body=f"""
Super Admin Created

Username: {username}
Password: {password}

⚠ Change password after login.
"""
            )
        except Exception as e:
            print("Email failed:", e)

        print("✅ Admin created & email sent")
