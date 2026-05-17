from flask import Blueprint, render_template, send_file,request,redirect
from flask_login import login_required, current_user
from models.student import Student
from models.fee import StudentFeeLedger
from models.attendance import StudentAttendance
from models.teacher import Teacher
from models.school import School
from extensions import db
from datetime import date, datetime
from sqlalchemy import func
import os
from flask import current_app
from sqlalchemy import func
from extensions import db
from werkzeug.utils import secure_filename
from utils.holiday import load_holidays, get_next_holiday
from utils.notice_pdf import generate_notice_pdf
from models.notice import NoticeLog
from models.teacher import Teacher, SalaryRecord
from models.attendance import TeacherAttendance
from super.routes import subscription_required

dashboard = Blueprint('dashboard', __name__, url_prefix='/dashboard')


# ======================================================
# 🏠 MAIN DASHBOARD
# ======================================================
@dashboard.route('/')
@login_required
@subscription_required  # 🔥 This is the gatekeeper
def home():

    if current_user.role == 'student':

        

        student = Student.query.get(current_user.student_id)

        # ===== ATTENDANCE =====
        records = StudentAttendance.query.filter_by(
            student_id=student.id
        ).all()

        total_days = len(records)
        present_days = sum(r.status == "P" for r in records)
        absent_days = total_days - present_days

        attendance_percent = round((present_days / total_days) * 100, 1) if total_days else 0

        # ===== FEES =====
        fee_records = StudentFeeLedger.query.filter_by(
            student_id=student.id
        ).all()

        total_fee = sum(f.total_amount or 0 for f in fee_records)
        paid_fee = sum(f.paid_amount or 0 for f in fee_records)
        pending_fee = total_fee - paid_fee

        # ===== NOTICES =====
        notices = NoticeLog.query.filter_by(
            school_id=current_user.school_id
        ).order_by(NoticeLog.created_at.desc()).limit(5).all()

        return render_template(
            "dashboard/student_panel.html",
            student=student,
            attendance_percent=attendance_percent,
            present_days=present_days,
            absent_days=absent_days,
            total_fee=total_fee,
            paid_fee=paid_fee,
            pending_fee=pending_fee,
            notices=notices,
            fee_records=fee_records,
            attendance_records=records
        )

    if current_user.role == 'teacher':

        
        

        teacher = Teacher.query.get(current_user.employee_id)

        # ===== ATTENDANCE =====
        records = TeacherAttendance.query.filter_by(
            teacher_id=teacher.id,
            school_id=current_user.school_id
        ).all()

        total_days = len(records)
        present_days = sum(r.status == "P" for r in records)
        absent_days = sum(r.status == "A" for r in records)
        late_days = sum(r.status == "L" for r in records)
        half_days = sum(r.status == "H" for r in records)

        attendance_percent = round((present_days / total_days) * 100, 1) if total_days else 0

        # ===== SALARY =====
        salary_records = SalaryRecord.query.filter_by(
            staff_id=teacher.id,
            school_id=current_user.school_id
        ).order_by(SalaryRecord.month.desc()).all()

        total_salary = sum(s.net_salary or 0 for s in salary_records)

        # ===== NOTICES =====
        notices = NoticeLog.query.filter_by(
            school_id=current_user.school_id
        ).order_by(NoticeLog.created_at.desc()).limit(5).all()

        return render_template(
            "dashboard/teacher_panel.html",
            teacher=teacher,
            attendance_percent=attendance_percent,
            present_days=present_days,
            absent_days=absent_days,
            late_days=late_days,
            half_days=half_days,
            salary_records=salary_records,
            total_salary=total_salary,
            notices=notices,
            attendance_records=records
        )

    if current_user.role == 'admin':

        school = School.query.get(current_user.school_id)

        # ===============================
        # Academic Session Auto (April–March)
        # ===============================
        today = datetime.today()

        if today.month >= 4:
            start_year = today.year
            end_year = today.year + 1
        else:
            start_year = today.year - 1
            end_year = today.year

        academic_year = f"{start_year}–{end_year}"

        # ===============================
        # Dashboard Stats
        # ===============================
        total_students = Student.query.filter_by(
            school_id=current_user.school_id
        ).count()

        total_teachers = Teacher.query.filter_by(
            school_id=current_user.school_id
        ).count()

        today_admissions = Student.query.filter(
            Student.school_id == current_user.school_id,
            func.date(Student.created_at) == date.today()
        ).count()

        # ✅ PostgreSQL-compatible: replaced func.strftime('%m', ...) with func.to_char(..., 'MM')
        # SQLite used: func.strftime('%m', Student.created_at)
        # PostgreSQL uses: func.to_char(Student.created_at, 'MM')
        monthly_data = db.session.query(
            month_format(
    Student.created_at
),
            func.count(Student.id)
        ).filter(
            Student.school_id == current_user.school_id
        ).group_by(
            month_format(
    Student.created_at
)
        ).all()

        months = [m[0] for m in monthly_data]
        counts = [m[1] for m in monthly_data]

        # ===============================
        # Fee Stats (placeholder)
        # ===============================
        fee_paid = 0
        fee_pending = 0

        return render_template(
            'dashboard/admin.html',
            school=school,
            academic_year=academic_year,
            total_students=total_students,
            total_teachers=total_teachers,
            today_admissions=today_admissions,
            months=months,
            counts=counts,
            fee_paid=fee_paid,
            fee_pending=fee_pending,
            fee_alerts=fee_pending > 0
        )

    return "Unauthorized", 403

# ======================================================
# 🔔 HOLIDAY NOTICE (UI + WHATSAPP)
# ======================================================
@dashboard.route("/holiday-notice")
@login_required
def holiday_notice():

    school = School.query.get(current_user.school_id)

    pdf_path = os.path.join(
        current_app.root_path,
        "static", "uploads", "holidays",
        f"{current_user.school_id}.pdf"
    )

    if not os.path.exists(pdf_path):
        return "Holiday list PDF not uploaded"

    holidays = load_holidays(pdf_path)
    holiday = get_next_holiday(holidays)

    if not holiday:
        return "No upcoming holiday found"

    hdate = holiday["date"].strftime("%d %B %Y")

    # ================= ENGLISH =================
    parent_en = (
        "📢 *HOLIDAY NOTICE*\n\n"
        "Dear Parents,\n\n"
        f"This is to inform you that the school will remain closed on "
        f"*{hdate}* due to *{holiday['reason']}*.\n\n"
        "Regular classes will resume from the next working day.\n\n"
        f"Regards,\n{school.school_name}"
    )

    teacher_en = (
        "📢 *STAFF NOTICE*\n\n"
        "Dear Teachers,\n\n"
        f"The school will remain closed on *{hdate}* due to "
        f"*{holiday['reason']}*.\n\n"
        "Please plan academic work accordingly.\n\n"
        f"— {school.school_name}"
    )

    # ================= HINDI =================
    parent_hi = (
        "📢 *अवकाश सूचना*\n\n"
        "प्रिय अभिभावकों,\n\n"
        f"आपको सूचित किया जाता है कि विद्यालय "
        f"*{hdate}* को *{holiday['reason']}* के कारण बंद रहेगा।\n\n"
        "अगले कार्यदिवस से कक्षाएं पुनः प्रारंभ होंगी।\n\n"
        f"सादर,\n{school.school_name}"
    )

    teacher_hi = (
        "📢 *स्टाफ सूचना*\n\n"
        "प्रिय शिक्षकगण,\n\n"
        f"{holiday['reason']} के कारण विद्यालय "
        f"*{hdate}* को बंद रहेगा।\n\n"
        "कृपया शैक्षणिक योजना अनुसार कार्य करें।\n\n"
        f"— {school.school_name}"
    )

    # ================= LOG SAVE (SAFE) =================
    log = NoticeLog(
        school_id=school.id,
        notice_type="HOLIDAY",
        title="Holiday Notice",
        message_en=parent_en,
        message_hi=parent_hi,
        target_group="parents",
        sent_status=False
    )
    db.session.add(log)
    db.session.commit()

    return render_template(
        "dashboard/holiday_notice.html",
        holiday=holiday,
        parent_en=parent_en,
        parent_hi=parent_hi,
        teacher_en=teacher_en,
        teacher_hi=teacher_hi,
        log_id=log.id,
        hindi_only=getattr(school, "hindi_only", False)  # 🔥 SAFE
    )


# ======================================================
# 📄 HOLIDAY NOTICE PDF
# ======================================================
@dashboard.route("/holiday-notice/pdf")
@login_required
def holiday_notice_pdf():

    pdf_path = os.path.join(
        current_app.root_path,
        "static", "uploads", "holidays",
        f"{current_user.school_id}.pdf"
    )

    if not os.path.exists(pdf_path):
        return "Holiday list PDF not uploaded"

    holidays = load_holidays(pdf_path)
    holiday = get_next_holiday(holidays)

    if not holiday:
        return "No upcoming holiday found"

    pdf_buffer = generate_notice_pdf(holiday, current_user.school)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name="Holiday_Notice.pdf",
        mimetype="application/pdf"
    )


# ======================================================
# ✅ MARK NOTICE AS SENT
# ======================================================
@dashboard.route("/notice/mark-sent/<int:log_id>")
@login_required
def mark_notice_sent(log_id):

    log = NoticeLog.query.get_or_404(log_id)
    log.sent_status = True
    log.sent_at = datetime.utcnow()
    db.session.commit()

    return "OK"


# ======================================================
# 📜 NOTICE HISTORY
# ======================================================
@dashboard.route("/notice-history")
@login_required
def notice_history():

    notices = NoticeLog.query.filter_by(
        school_id=current_user.school_id
    ).order_by(NoticeLog.created_at.desc()).all()

    return render_template(
        "dashboard/notice_history.html",
        notices=notices
    )


# ======================================================
# 🏫 SCHOOL OPERATIONS DASHBOARD
# ======================================================
@dashboard.route("/operations")
@login_required
def school_operations():

    if current_user.role not in ["admin", "teacher"]:
        return "Unauthorized", 403

    total_notices = NoticeLog.query.filter_by(
        school_id=current_user.school_id
    ).count()

    sent_notices = NoticeLog.query.filter_by(
        school_id=current_user.school_id,
        sent_status=True
    ).count()

    attendance_percent = 92  # static safe start

    return render_template(
        "dashboard/operations.html",
        total_notices=total_notices,
        sent_notices=sent_notices,
        attendance_percent=attendance_percent,
        role=current_user.role
    )




@dashboard.route("/holiday-upload", methods=["GET", "POST"])
@login_required
def holiday_upload():

    if current_user.role != "admin":
        return "Unauthorized", 403

    if request.method == "POST":

        file = request.files.get("holiday_pdf")

        if not file or not file.filename.endswith(".pdf"):
            return "Only PDF allowed"

        filename = f"{current_user.school_id}.pdf"

        upload_path = os.path.join(
            current_app.root_path,
            "static", "uploads", "holidays"
        )

        os.makedirs(upload_path, exist_ok=True)

        file.save(os.path.join(upload_path, secure_filename(filename)))

        return redirect("/dashboard/holiday-notice")

    return render_template("dashboard/holiday_upload.html")


def month_format(column):

    if "sqlite" in str(db.engine.url):

        return func.strftime(
            '%m',
            column
        )

    else:

        return func.to_char(
            column,
            'MM'
        )