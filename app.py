"""
app.py — Bhishmaa Intelligent School ERP
=========================================
Offline-first: always runs on local SQLite.
Cloud PostgreSQL syncs automatically when internet is available.
No .env file needed for sync — just set CLOUD_HOST below.
"""

from flask import Flask, send_from_directory, request, jsonify
from extensions import db, login_manager, mail
import os
import sys
from datetime import datetime
from werkzeug.security import generate_password_hash

# ══════════════════════════════════════════════════════════════
# ☁ CLOUD DATABASE CONFIG — Edit karo apna server IP/domain
# ══════════════════════════════════════════════════════════════
CLOUD_HOST     = "erp.bhishmaagroup.in"
CLOUD_PORT     = 5432
CLOUD_USER     = "enoughsudhanshu"
CLOUD_PASSWORD = "awadhnath"
CLOUD_DB       = "erpdb"

def _build_cloud_url():
    host = (os.environ.get("CLOUD_HOST", "") or CLOUD_HOST).strip()
    if not host:
        return None
    return (
        f"postgresql://{CLOUD_USER}:{CLOUD_PASSWORD}"
        f"@{host}:{CLOUD_PORT}/{CLOUD_DB}"
        f"?connect_timeout=5&sslmode=prefer"
    )


def create_app():

    # ── EXE safe base dir ────────────────────────────────────
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.abspath("."))

    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static'),
    )

    # ── Secret key ───────────────────────────────────────────
    app.config['SECRET_KEY'] = 'bhishmaa-super-secret-key'

    # ══════════════════════════════════════════════════════════
    # 💾 DATABASE — ALWAYS SQLite locally
    # ══════════════════════════════════════════════════════════
    IS_ONLINE = os.environ.get("IS_ONLINE", "false").lower()

    if IS_ONLINE == "true":
        # Cloud server mode
        cloud_url = os.environ.get("DATABASE_URL", "")
        if not cloud_url:
            cloud_url = _build_cloud_url()
        if not cloud_url:
            raise Exception("❌ Cloud DB URL missing (set CLOUD_HOST in app.py)")
        DATABASE_URL = cloud_url.replace("postgres://", "postgresql://", 1)
        print("🌐 ONLINE MODE (PostgreSQL)")
    else:
        # Offline/desktop mode — SQLite
        DATABASE_URL = "sqlite:///" + os.path.join(BASE_DIR, "offline.db")
        print("💻 OFFLINE MODE (SQLite) — cloud sync will auto-start when internet is available")

    app.config['SQLALCHEMY_DATABASE_URI']        = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    if IS_ONLINE == "true":
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
            "pool_pre_ping": True, "pool_recycle": 300,
            "pool_size": 5, "max_overflow": 2, "pool_timeout": 30,
            "connect_args": {"sslmode": "prefer"},
        }
    else:
        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {}

    # Inject cloud URL into dual_db module at startup
    cloud_url_for_sync = _build_cloud_url()
    if cloud_url_for_sync:
        os.environ.setdefault("DATABASE_URL", cloud_url_for_sync)

    # ── Email config ─────────────────────────────────────────
    app.config['MAIL_SERVER']         = 'smtp.gmail.com'
    app.config['MAIL_PORT']           = 587
    app.config['MAIL_USE_TLS']        = True
    app.config['MAIL_USERNAME']       = 'bhishmaagroup@gmail.com'
    app.config['MAIL_PASSWORD']       = 'lxlsukrrignjhlgx'
    app.config['MAIL_DEFAULT_SENDER'] = 'Bhishmaa Group <bhishmaagroup@gmail.com>'

    # ── Init extensions ──────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # Init sync event listeners
    from utils.sync_engine import init_sync_engine, migrate_sqlite_db, start_sync_scheduler
    init_sync_engine(app)

    # ── Upload folder ────────────────────────────────────────
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    @app.route('/uploads/<path:filename>')
    def uploaded_files(filename):
        return send_from_directory(UPLOAD_FOLDER, filename)

    # ── License API ──────────────────────────────────────────
    from models.school import School

    @app.route("/api/check_license")
    def check_license():
        school_code = request.args.get("school_code")
        if not school_code:
            return jsonify({"status": "invalid"})
        school = School.query.filter_by(school_code=school_code).first()
        if not school:
            return jsonify({"status": "invalid"})
        if not school.is_active:
            return jsonify({"status": "blocked"})
        if school.expiry_date and school.expiry_date < datetime.utcnow():
            return jsonify({"status": "expired"})
        return jsonify({"status": "active"})

    # ── Test mail ────────────────────────────────────────────
    from utils.email import send_system_email

    @app.route("/test-mail")
    def test_mail():
        send_system_email(
            "YOUR_PERSONAL_EMAIL@gmail.com",
            "Bhishmaa SMTP Test",
            "<h1>SMTP Working</h1>",
            True
        )
        return "MAIL SENT"

    # ── Blueprints ───────────────────────────────────────────
    from auth.routes import auth
    from dashboard.routes import dashboard
    from student.routes import student
    from super.routes import super_admin
    from school.routes import school_bp
    from teacher.routes import teacher
    from fee.routes import fee_bp
    from attendance.routes import attendance
    from transport.routes import transport
    from idcard.routes import idcard_bp
    from import_export.routes import import_export
    from bulk.routes import bulk_bp
    from exam.routes import exam
    from tc.routes import tc_bp
    from promotion.routes import promotion_bp
    from sync.routes import sync_bp
    from subject.routes import subject

    for bp in [
        bulk_bp, idcard_bp, attendance, auth, dashboard, student,
        super_admin, school_bp, transport, subject, exam, tc_bp,
        promotion_bp, import_export, teacher, fee_bp, sync_bp,
    ]:
        app.register_blueprint(bp)

    # ── Load models ──────────────────────────────────────────
    import models

    # ── DB Init ──────────────────────────────────────────────
    with app.app_context():
        try:
            from utils.auto_migrate import auto_migrate
            auto_migrate(app)

            # Enable WAL mode for SQLite
            if IS_ONLINE != "true":
                migrate_sqlite_db(app)

            # Create default super admin if missing
            from models.super_admin import SuperAdmin
            if SuperAdmin.query.count() == 0:
                db.session.add(SuperAdmin(
                    username="enough",
                    password=generate_password_hash("enough")
                ))
                db.session.commit()
                print("✅ Default Super Admin Created")

            # Seed existing offline data to sync queue
            from utils.sync_engine import seed_sync_queue_from_existing_data
            seed_sync_queue_from_existing_data()

        except Exception as e:
            print(f"⚠ DB INIT WARNING: {e}")

    # ── Background threads ───────────────────────────────────
    # 1. Scheduler — sync every 60 seconds when online
    start_sync_scheduler(app)

    # 2. Internet monitor — detects connect/disconnect events
    from utils.sync_engine import internet_monitor_thread
    internet_monitor_thread(app)

    print("🚀 Bhishmaa ERP started. Cloud sync: AUTO (when internet available)")

    return app


# ══════════════════════════════════════════════════════════════
# 🚀 STARTUP
# ══════════════════════════════════════════════════════════════
app = create_app()

if __name__ == '__main__':
    from threading import Thread
    import webview

    def run_flask():
        app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)

    t = Thread(target=run_flask, daemon=True)
    t.start()

    webview.create_window(
        title="Bhishmaa Intelligent School ERP",
        url="http://127.0.0.1:8000/",
        width=1280, height=800, resizable=True
    )
    webview.start()
