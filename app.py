from flask import Flask, send_from_directory, request, jsonify
from extensions import db, login_manager, mail
import os
import sys
from datetime import datetime
from werkzeug.security import generate_password_hash

# MODELS
from models.school import School
from models.super_admin import SuperAdmin
from subject.routes import subject


def create_app():

    # =========================================================
    # 🔥 EXE SAFE BASE DIR
    # =========================================================
    BASE_DIR = getattr(sys, '_MEIPASS', os.path.abspath("."))

    app = Flask(
        __name__,
        template_folder=os.path.join(BASE_DIR, 'templates'),
        static_folder=os.path.join(BASE_DIR, 'static')
    )

    # =========================================================
    # 🔐 SECRET
    # =========================================================
    app.config['SECRET_KEY'] = 'secret-key'

    # =========================================================
    # 🔥 HYBRID DATABASE MODE
    # =========================================================
    IS_ONLINE = os.environ.get("IS_ONLINE", "false").lower()

    if IS_ONLINE == "true":

        print("🌐 ONLINE MODE (PostgreSQL)")

        DATABASE_URL = os.environ.get("DATABASE_URL")

        if not DATABASE_URL:
            raise Exception("❌ DATABASE_URL not set")

        DATABASE_URL = DATABASE_URL.replace(
            "postgres://",
            "postgresql://"
        )

    else:

        print("💻 OFFLINE MODE (SQLite)")

        DATABASE_URL = "sqlite:///" + os.path.join(
            BASE_DIR,
            "offline.db"
        )

    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # =========================================================
    # 🔥 DATABASE ENGINE OPTIONS
    # =========================================================
    if IS_ONLINE == "true":

        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {

            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_size": 5,
            "max_overflow": 2,
            "pool_timeout": 30,

            "connect_args": {
                "sslmode": "require"
            }
        }

    else:

        app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {}

    # =========================================================
    # 📧 GMAIL SMTP CONFIG
    # =========================================================
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'

    app.config['MAIL_PORT'] = 587

    app.config['MAIL_USE_TLS'] = True

    app.config['MAIL_USERNAME'] = 'bhishmaagroup@gmail.com'

    app.config['MAIL_PASSWORD'] = 'lxlsukrrignjhlgx'

    app.config['MAIL_DEFAULT_SENDER'] = (
        'Bhishmaa Group <bhishmaagroup@gmail.com>'
    )

    # =========================================================
    # 🔧 INIT EXTENSIONS
    # =========================================================
    db.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    # =========================================================
    # 📁 UPLOAD FOLDER
    # =========================================================
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    @app.route('/uploads/<path:filename>')
    def uploaded_files(filename):

        return send_from_directory(
            UPLOAD_FOLDER,
            filename
        )

    # =========================================================
    # 🔐 LICENSE API
    # =========================================================
    @app.route("/api/check_license")
    def check_license():

        school_code = request.args.get("school_code")

        if not school_code:
            return jsonify({
                "status": "invalid"
            })

        school = School.query.filter_by(
            school_code=school_code
        ).first()

        if not school:
            return jsonify({
                "status": "invalid"
            })

        if not school.is_active:
            return jsonify({
                "status": "blocked"
            })

        if (
            school.expiry_date and
            school.expiry_date < datetime.utcnow()
        ):
            return jsonify({
                "status": "expired"
            })

        return jsonify({
            "status": "active"
        })

    # =========================================================
    # 📧 TEST MAIL ROUTE
    # =========================================================
    from utils.email import send_system_email

    @app.route("/test-mail")
    def test_mail():

        send_system_email(

            "YOUR_PERSONAL_EMAIL@gmail.com",

            "Bhishmaa SMTP Test",

            """
            <h1>SMTP Working Successfully</h1>

            <p>Debian + Gmail SMTP Connected</p>
            """,

            True
        )

        return "MAIL SENT"

    # =========================================================
    # 🔥 BLUEPRINTS
    # =========================================================
    from auth.routes import auth
    from dashboard.routes import dashboard
    from student.routes import student
    from super.routes import super_admin
    from school.routes import school_bp
    from teacher.routes import teacher
    from fee.routes import fee_bp
    from attendance.routes import attendance
    from transport.routes import transport
    from idcard import idcard_bp
    from import_export.routes import import_export
    from bulk.routes import bulk_bp
    from face_attendance.routes import face_bp

    app.register_blueprint(bulk_bp)
    app.register_blueprint(face_bp)
    app.register_blueprint(attendance)
    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(student)
    app.register_blueprint(super_admin)
    app.register_blueprint(school_bp)
    app.register_blueprint(transport)
    app.register_blueprint(subject)

    app.register_blueprint(
        idcard_bp,
        url_prefix="/dashboard/idcard"
    )

    app.register_blueprint(import_export)
    app.register_blueprint(teacher)
    app.register_blueprint(fee_bp)

    # =========================================================
    # 🔥 LOAD MODELS
    # =========================================================
    import models

    # =========================================================
    # 🔥 AUTO CREATE SUPER ADMIN
    # =========================================================
    def create_default_super_admin():

        try:

            if SuperAdmin.query.count() == 0:

                admin = SuperAdmin(
                    username="enough",
                    password=generate_password_hash(
                        "enough"
                    )
                )

                db.session.add(admin)
                db.session.commit()

                print("✅ Default Super Admin Created")

        except Exception as e:

            print("⚠ DB not ready:", e)

    # =========================================================
    # 🔥 DB INIT
    # =========================================================
    with app.app_context():

        try:

            db.create_all()

            create_default_super_admin()

        except Exception as e:

            print("⚠ DB INIT SKIPPED:", e)

    return app


# =========================================================
# 🚀 START APP
# =========================================================
app = create_app()


# =========================================================
# 💻 LOCAL / EXE RUN
# =========================================================
if __name__ == '__main__':

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
