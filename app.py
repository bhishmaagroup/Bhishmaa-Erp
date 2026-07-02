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
    from idcard.routes import idcard_bp
    from import_export.routes import import_export
    from bulk.routes import bulk_bp
    from exam.routes import exam_bp
    from timetable.routes import timetable_bp
    from result.routes import result_bp
    from academics.routes import academics_bp
    

    app.register_blueprint(bulk_bp)
    app.register_blueprint(idcard_bp)
    app.register_blueprint(attendance)
    app.register_blueprint(auth)
    app.register_blueprint(dashboard)
    app.register_blueprint(student)
    app.register_blueprint(super_admin)
    app.register_blueprint(school_bp)
    app.register_blueprint(transport)
    app.register_blueprint(subject)
    app.register_blueprint(exam_bp)
    app.register_blueprint(timetable_bp)
    app.register_blueprint(result_bp)
    app.register_blueprint(academics_bp)

  

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
    # 🔥 DB INIT & MIGRATIONS
    # =========================================================
    with app.app_context():

        try:

            db.create_all()

            # Dynamic migrations for SQLite & Postgres
            from sqlalchemy import inspect
            inspector = inspect(db.engine)
            
            # Check subject table columns
            if 'subject' in inspector.get_table_names():
                sub_cols = [c['name'] for c in inspector.get_columns('subject')]
                if 'subject_type' not in sub_cols:
                    db.session.execute(db.text("ALTER TABLE subject ADD COLUMN subject_type VARCHAR(50) DEFAULT 'Theory'"))
                if 'status' not in sub_cols:
                    db.session.execute(db.text("ALTER TABLE subject ADD COLUMN status BOOLEAN DEFAULT 1"))
            
            # Check exams table columns
            if 'exams' in inspector.get_table_names():
                exams_cols = [c['name'] for c in inspector.get_columns('exams')]
                if 'exam_group_id' not in exams_cols:
                    db.session.execute(db.text("ALTER TABLE exams ADD COLUMN exam_group_id INTEGER"))
                if 'status' not in exams_cols:
                    db.session.execute(db.text("ALTER TABLE exams ADD COLUMN status VARCHAR(20) DEFAULT 'Draft'"))

            # Check exam_schedules table columns
            if 'exam_schedules' in inspector.get_table_names():
                sched_cols = [c['name'] for c in inspector.get_columns('exam_schedules')]
                if 'section' not in sched_cols:
                    db.session.execute(db.text("ALTER TABLE exam_schedules ADD COLUMN section VARCHAR(10)"))
                for col in ['max_theory', 'pass_theory', 'max_practical', 'pass_practical', 'max_viva', 'pass_viva', 'max_internal', 'pass_internal']:
                    if col not in sched_cols:
                        def_val = 100.0 if 'max_theory' in col else (33.0 if 'pass_theory' in col else 0.0)
                        db.session.execute(db.text(f"ALTER TABLE exam_schedules ADD COLUMN {col} FLOAT DEFAULT {def_val}"))

            # Check exam_marks table columns
            if 'exam_marks' in inspector.get_table_names():
                marks_cols = [c['name'] for c in inspector.get_columns('exam_marks')]
                for col in ['theory_obtained', 'practical_obtained', 'viva_obtained', 'internal_obtained', 'grace_marks']:
                    if col not in marks_cols:
                        db.session.execute(db.text(f"ALTER TABLE exam_marks ADD COLUMN {col} FLOAT DEFAULT 0.0"))

            # Check exam_results table columns
            if 'exam_results' in inspector.get_table_names():
                res_cols = [c['name'] for c in inspector.get_columns('exam_results')]
                if 'section_rank' not in res_cols:
                    db.session.execute(db.text("ALTER TABLE exam_results ADD COLUMN section_rank INTEGER"))
                if 'school_rank' not in res_cols:
                    db.session.execute(db.text("ALTER TABLE exam_results ADD COLUMN school_rank INTEGER"))
                if 'gpa' not in res_cols:
                    db.session.execute(db.text("ALTER TABLE exam_results ADD COLUMN gpa FLOAT DEFAULT 0.0"))
                if 'cgpa' not in res_cols:
                    db.session.execute(db.text("ALTER TABLE exam_results ADD COLUMN cgpa FLOAT DEFAULT 0.0"))

            db.session.commit()
            print("✅ Dynamic Schema Migrations Checked & Completed")

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
        port=11000,
        debug=False
    )
