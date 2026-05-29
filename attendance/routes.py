from flask import Blueprint, render_template, request, redirect, flash, send_file, jsonify, session
from flask_login import login_required, current_user
from datetime import date, datetime
from sqlalchemy import extract
import io, calendar
import pandas as pd
import matplotlib.pyplot as plt
from extensions import db
from models.teacher import Teacher
from models.student import Student
from models.school import School
from models.attendance import TeacherAttendance, StudentAttendance
from models.holiday import Holiday
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle,
    Spacer, Image
)
from math import radians
from math import sin
from math import cos
from math import sqrt
from math import atan2
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.units import inch
from models.subject_attendance import SubjectAttendance
from models.teacher_subject import TeacherSubject
from models.student_subject import StudentSubject
from models.subject import Subject


attendance = Blueprint("attendance", __name__, url_prefix="/attendance")


def inside_school(
    school_lat,
    school_lng,
    current_lat,
    current_lng,
    radius=100
):

    R = 6371000

    dlat = radians(current_lat - school_lat)
    dlon = radians(current_lng - school_lng)

    a = (
        sin(dlat / 2) ** 2
        +
        cos(radians(school_lat))
        *
        cos(radians(current_lat))
        *
        sin(dlon / 2) ** 2
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a)
    )

    distance = R * c

    return distance <= radius

# ======================================================
# ATTENDANCE DASHBOARD
# ======================================================
@attendance.route("/")
@login_required
def attendance_dashboard():
    return render_template("attendance/index.html")


# ======================================================
# TEACHER ATTENDANCE (❌ DO NOT TOUCH LOGIC)
# ======================================================
@attendance.route("/teacher", methods=["GET", "POST"])
@login_required
def teacher_attendance():

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).all()

    today = date.today()

    if request.method == "POST":
        for t in teachers:
            status = request.form.get(f"status_{t.id}", "P")

            record = TeacherAttendance.query.filter_by(
                school_id=current_user.school_id,
                teacher_id=t.id,
                attendance_date=today
            ).first()

            if record:
                record.status = status
            else:
                db.session.add(
                    TeacherAttendance(
                        school_id=current_user.school_id,
                        teacher_id=t.id,
                        attendance_date=today,
                        status=status
                    )
                )

        db.session.commit()
        flash("Teacher attendance saved", "success")
        return redirect(request.url)

    return render_template(
        "attendance/teacher.html",
        teachers=teachers
    )


# ==================================================
# TEACHER LEDGER (LIST)
# ==================================================
@attendance.route("/teacher/ledger")
@login_required
def teacher_ledger_list():

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).all()

    return render_template(
        "attendance/teacher_ledger_list.html",
        teachers=teachers
    )


# ======================================================
# SINGLE TEACHER LEDGER
# /attendance/teacher/ledger/<id>
# ======================================================
@attendance.route("/teacher/ledger/<int:teacher_id>")
@login_required
def teacher_ledger_view(teacher_id):

    teacher = Teacher.query.filter_by(
        id=teacher_id,
        school_id=current_user.school_id
    ).first_or_404()

    from_date = request.args.get("from")
    to_date = request.args.get("to")

    q = TeacherAttendance.query.filter_by(
        school_id=current_user.school_id,
        teacher_id=teacher.id
    )

    if from_date:
        q = q.filter(TeacherAttendance.attendance_date >= from_date)
    if to_date:
        q = q.filter(TeacherAttendance.attendance_date <= to_date)

    records = q.order_by(
        TeacherAttendance.attendance_date.desc()
    ).all()

    P = sum(r.status == "P" for r in records)
    A = sum(r.status == "A" for r in records)
    L = sum(r.status == "L" for r in records)
    H = sum(r.status == "H" for r in records)

    working = P + A + L + H
    score = P + (L * 0.75) + (H * 0.5)
    percent = round((score / working) * 100, 1) if working else 0

    return render_template(
        "attendance/teacher_ledger_view.html",
        teacher=teacher,
        records=records,
        P=P, A=A, L=L, H=H,
        percent=percent
    )

@attendance.route("/teacher/ledger/<int:teacher_id>/pdf")
@login_required
def teacher_ledger_pdf(teacher_id):

    teacher = Teacher.query.get_or_404(teacher_id)
    school = School.query.get(current_user.school_id)

    records = TeacherAttendance.query.filter_by(
        teacher_id=teacher.id,
        school_id=current_user.school_id
    ).order_by(TeacherAttendance.attendance_date).all()

    school = School.query.get(current_user.school_id)

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15,
        rightMargin=15,
        topMargin=15,
        bottomMargin=15
    )

    styles = getSampleStyleSheet()

    from reportlab.lib.styles import ParagraphStyle

    school_title = ParagraphStyle(
        "SchoolTitle",
        fontSize=18,
        leading=20,        # tight but readable
        alignment=1,
        fontName="Helvetica-Bold",
        spaceAfter=0
    )

    school_sub = ParagraphStyle(
        "SchoolSub",
       fontSize=10,
        leading=12,
        alignment=1,
        spaceBefore=2
    )

    elements = []

    # ================= HEADER =================
    header = Table([
    [
        Image(school.logo, 0.9*inch, 0.9*inch) if school.logo else "",
        Paragraph(
            f"""
            <b>{school.school_name.upper()}</b><br/>
            <font size="10">
            {school.address}, {school.city}<br/>
            Phone: {school.phone} 
            </font>
            """,
            school_title
        )
    ]
], colWidths=[1.1*inch, 9.9*inch])


    header.setStyle(TableStyle([
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ("TOPPADDING", (0,0), (-1,-1), 2),
    ("LINEBELOW", (0,0), (-1,0), 1.5, colors.black),
]))


    elements.append(header)
    elements.append(Spacer(1, 8))

    # ================= META =================
    meta = Table([[
        
        "Session : 2025–26"
    ]], colWidths=[4*inch, 4*inch, 3*inch])

    meta.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))

    elements.append(meta)
    elements.append(Spacer(1, 6))


    # ================= TEACHER INFO =================
    full_name = f"{teacher.first_name} " \
                f"{teacher.middle_name + ' ' if teacher.middle_name else ''}" \
                f"{teacher.last_name or ''}"

    elements.append(Paragraph(
        f"<b>Teacher Name:</b> {full_name}",
        
    ))

    elements.append(Spacer(1, 6))

    # ================= TABLE =================
    table_data = [["Date", "Status"]]

    P = A = L = H = 0

    for r in records:
        table_data.append([
            r.attendance_date.strftime("%d-%m-%Y"),
            r.status
        ])
        if r.status == "P": P += 1
        elif r.status == "A": A += 1
        elif r.status == "L": L += 1
        elif r.status == "H": H += 1

    table = Table(table_data, colWidths=[3*inch, 2*inch])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.5, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("ALIGN", (1,1), (-1,-1), "CENTER"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold")
    ]))

    elements.append(table)
    elements.append(Spacer(1, 14))

    # ================= SUMMARY =================
    total = P + A + L + H
    percent = round(((P + L*0.75 + H*0.5) / total) * 100, 1) if total else 0

    elements.append(Paragraph(
        f"<b>P:</b> {P} &nbsp;&nbsp;"
        f"<b>A:</b> {A} &nbsp;&nbsp;"
        f"<b>L:</b> {L} &nbsp;&nbsp;"
        f"<b>H:</b> {H} &nbsp;&nbsp;"
        f"<b>Attendance %:</b> {percent}",
        styles["Normal"]
    ))

    elements.append(Spacer(1, 40))

    # ================= SIGNATURE =================
    signature = Table([
        ["__________________________", "__________________________"],
        ["Teacher Signature", "Principal (Stamp & Signature)"]
    ], colWidths=[3*inch, 3*inch])

    signature.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 18),
        ("FONTNAME", (0,1), (-1,1), "Helvetica-Bold"),
    ]))

    elements.append(signature)

    # ================= BUILD =================
    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="teacher_ledger.pdf"
    )


# ======================================================
# SINGLE TEACHER LEDGER EXCEL
# ======================================================
@attendance.route("/teacher/ledger/<int:teacher_id>/excel")
@login_required
def teacher_ledger_excel(teacher_id):

    teacher = Teacher.query.get_or_404(teacher_id)

    records = TeacherAttendance.query.filter_by(
        teacher_id=teacher.id,
        school_id=current_user.school_id
    ).all()

    rows = []
    for r in records:
        rows.append({
            "Date": r.attendance_date,
            "Status": r.status
        })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="teacher_ledger.xlsx"
    )



# ======================================================
# SINGLE TEACHER MONTHLY ATTENDANCE
# /attendance/teacher/monthly/<id>?month=YYYY-MM
# ======================================================
@attendance.route("/teacher/monthly/<int:teacher_id>")
@login_required
def teacher_monthly(teacher_id):

    month = request.args.get("month")
    if not month:
        return "Month required", 400

    year, mon = map(int, month.split("-"))

    days = [
        date(year, mon, d)
        for d in range(1, calendar.monthrange(year, mon)[1] + 1)
    ]

    records = TeacherAttendance.query.filter(
        TeacherAttendance.school_id == current_user.school_id,
        TeacherAttendance.teacher_id == teacher_id,
        TeacherAttendance.attendance_date.between(days[0], days[-1])
    ).all()

    attendance = {r.attendance_date: r.status for r in records}

    return render_template(
        "attendance/teacher_monthly.html",
        days=days,
        attendance=attendance,
        month=month
    )


@attendance.route("/teacher/register/monthly/pdf")
@login_required
def teacher_monthly_register_pdf():

    month = request.args.get("month")
    if not month:
        abort(400, "Month is required")

    year, mon = map(int, month.split("-"))
    total_days = calendar.monthrange(year, mon)[1]
    days = [date(year, mon, d) for d in range(1, total_days + 1)]

    school = School.query.get(current_user.school_id)

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Teacher.first_name).all()

    records = TeacherAttendance.query.filter(
        TeacherAttendance.school_id == current_user.school_id,
        TeacherAttendance.attendance_date.between(days[0], days[-1])
    ).all()

    # ================= MAP ATTENDANCE =================
    attendance = {}
    for r in records:
        attendance.setdefault(r.teacher_id, {})
        attendance[r.teacher_id][r.attendance_date] = r.status

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        topMargin=25,
        bottomMargin=25,
        leftMargin=20,
        rightMargin=20
    )

    styles = getSampleStyleSheet()
    from reportlab.lib.styles import ParagraphStyle

    school_title = ParagraphStyle(
        "school_title",
        fontSize=18,
        alignment=1,
        fontName="Helvetica-Bold"
    )

    school_sub = ParagraphStyle(
        "school_sub",
        fontSize=10,
        alignment=1
    )

    elements = []

    # ================= HEADER =================
    header = Table([
        [
            Image(school.logo, 1*inch, 1*inch) if school.logo else "",
            Paragraph(school.school_name.upper(), school_title)
        ],
        [
            "",
            Paragraph(
                f"{school.address}, {school.city}<br/>"
                f"Phone: {school.phone} | Email: {school.email}",
                school_sub
            )
        ]
    ], colWidths=[1.2*inch, 9.8*inch])

    header.setStyle(TableStyle([
        ("SPAN", (1,0), (1,1)),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LINEBELOW", (0,1), (-1,1), 1.3, colors.black),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))

    elements.append(header)
    elements.append(Spacer(1, 10))

    # ================= META =================
    meta = Table([[
        "Teacher Monthly Attendance Register",
        f"Month : {calendar.month_name[mon]} {year}",
        "Session : 2025–26"
    ]], colWidths=[4*inch, 4*inch, 3*inch])

    meta.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))

    elements.append(meta)
    elements.append(Spacer(1, 8))

    # ================= TABLE =================
    table_data = [
        ["#", "Teacher Name"] + [str(d.day) for d in days] + ["P", "A", "L", "H", "%"]
    ]

    for i, t in enumerate(teachers, 1):
        P = A = L = H = 0

        name = f"{t.first_name} " \
               f"{t.middle_name + ' ' if t.middle_name else ''}" \
               f"{t.last_name or ''}"

        row = [i, name]

        for d in days:
            st = attendance.get(t.id, {}).get(d)

            if d.weekday() == 6:
                row.append("")  # Sunday
            elif st == "P":
                row.append("P"); P += 1
            elif st == "A":
                row.append("A"); A += 1
            elif st == "L":
                row.append("L"); L += 1
            elif st == "H":
                row.append("H"); H += 1
            else:
                row.append("")

        working = P + A + L + H
        score = P + (L * 0.75) + (H * 0.5)
        percent = round((score / working) * 100, 1) if working else 0

        row.extend([P, A, L, H, f"{percent}%"])
        table_data.append(row)

    col_widths = (
        [0.3*inch, 2.2*inch] +
        [0.28*inch] * len(days) +
        [0.35*inch, 0.35*inch, 0.35*inch, 0.35*inch, 0.6*inch]
    )

    table = Table(table_data, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("ALIGN", (2,1), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))

    # ================= SIGNATURE =================
    footer = Table([
        ["__________________________", "__________________________"],
        ["Class Teacher", "Principal (Stamp & Signature)"]
    ], colWidths=[5*inch, 5*inch])

    footer.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("TOPPADDING", (0,0), (-1,-1), 18),
        ("FONTNAME", (0,1), (-1,1), "Helvetica-Bold"),
    ]))

    elements.append(footer)

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="teacher_monthly.pdf"
    )


# ======================================================
# SINGLE TEACHER YEARLY ATTENDANCE
# /attendance/teacher/yearly/<id>
# ======================================================
@attendance.route("/teacher/yearly/<int:teacher_id>")
@login_required
def teacher_yearly(teacher_id):

    teacher = Teacher.query.filter_by(
        id=teacher_id,
        school_id=current_user.school_id
    ).first_or_404()

    summary = []

    for m in range(1, 13):
        records = TeacherAttendance.query.filter(
            TeacherAttendance.school_id == current_user.school_id,
            TeacherAttendance.teacher_id == teacher.id,
            db.extract("month", TeacherAttendance.attendance_date) == m
        ).all()

        P = sum(r.status == "P" for r in records)
        A = sum(r.status == "A" for r in records)
        L = sum(r.status == "L" for r in records)
        H = sum(r.status == "H" for r in records)

        total = P + A + L + H
        percent = round((P / total) * 100, 1) if total else 0

        summary.append({
            "month": calendar.month_name[m],
            "P": P,
            "A": A,
            "L": L,
            "H": H,
            "percent": percent
        })

    return render_template(
        "attendance/teacher_yearly.html",
        teacher=teacher,
        summary=summary
    )


# ======================================================
# ALL TEACHERS – MONTHLY REGISTER
# /attendance/teacher/register?month=YYYY-MM
# ======================================================
@attendance.route("/teacher/register")
@login_required
def teacher_monthly_register():

    month = request.args.get("month")
    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).all()

    days = []
    attendance = {}

    if month:
        year, mon = map(int, month.split("-"))
        days = [
            date(year, mon, d)
            for d in range(1, calendar.monthrange(year, mon)[1] + 1)
        ]

        records = TeacherAttendance.query.filter(
            TeacherAttendance.school_id == current_user.school_id,
            TeacherAttendance.attendance_date.between(days[0], days[-1])
        ).all()

        for r in records:
            attendance.setdefault(r.teacher_id, {})
            attendance[r.teacher_id][r.attendance_date] = r.status

    return render_template(
        "attendance/teacher_register.html",
        teachers=teachers,
        days=days,
        attendance=attendance,
        month=month
    )


# ======================================================
# ALL TEACHERS – YEARLY REGISTER
# /attendance/teacher/yearly-register
# ======================================================
@attendance.route("/teacher/yearly-register")
@login_required
def teacher_yearly_register():

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).all()

    yearly = {}

    for t in teachers:
        yearly[t.id] = []

        for m in range(1, 13):
            records = TeacherAttendance.query.filter(
                TeacherAttendance.school_id == current_user.school_id,
                TeacherAttendance.teacher_id == t.id,
                db.extract("month", TeacherAttendance.attendance_date) == m
            ).all()

            P = sum(r.status == "P" for r in records)
            A = sum(r.status == "A" for r in records)
            L = sum(r.status == "L" for r in records)
            H = sum(r.status == "H" for r in records)

            total = P + A + L + H
            percent = round((P / total) * 100, 1) if total else 0

            yearly[t.id].append({
                "month": calendar.month_name[m],
                "P": P,
                "A": A,
                "L": L,
                "H": H,
                "percent": percent
            })

    return render_template(
        "attendance/teacher_yearly_register.html",
        teachers=teachers,
        yearly=yearly
    )


# ======================================================
# STUDENT ATTENDANCE (DAILY MARKING)
# ======================================================
@attendance.route("/student", methods=["GET", "POST"])
@login_required
def student_attendance():

    class_name = request.args.get("class")
    section = request.args.get("section")
    today = date.today()

    students = []

    if class_name and section:
        students = Student.query.filter_by(
            school_id=current_user.school_id,
            student_class=class_name,
            section=section
        ).all()

    if request.method == "POST":
        for s in students:
            status = request.form.get(f"status_{s.id}", "P")

            record = StudentAttendance.query.filter_by(
                school_id=current_user.school_id,
                student_id=s.id,
                attendance_date=today
            ).first()

            if record:
                record.status = status
            else:
                db.session.add(
                    StudentAttendance(
                        school_id=current_user.school_id,
                        student_id=s.id,
                        student_class=s.student_class,
                        section=s.section,
                        attendance_date=today,
                        status=status
                    )
                )

        db.session.commit()
        flash("Student attendance saved", "success")
        return redirect(request.url)

    return render_template("attendance/student.html", students=students)


# ======================================================
# STUDENT LEDGER – CLASS / SECTION LIST
# ======================================================
@attendance.route("/student/ledger")
@login_required
def student_ledger_search():

    class_name = request.args.get("class")
    section = request.args.get("section")

    students = []

    if class_name and section:
        students = Student.query.filter_by(
            school_id=current_user.school_id,
            student_class=class_name,
            section=section
        ).all()

    return render_template("attendance/ledger.html", students=students)


# ======================================================
# SINGLE STUDENT LEDGER (VIEW + EDIT)
# ======================================================
@attendance.route("/student/ledger/<int:student_id>", methods=["GET", "POST"])
@login_required
def student_ledger_view(student_id):

    student = Student.query.filter_by(
        id=student_id,
        school_id=current_user.school_id
    ).first_or_404()

    records = StudentAttendance.query.filter_by(
        school_id=current_user.school_id,
        student_id=student.id
    ).order_by(StudentAttendance.attendance_date.desc()).all()

    if request.method == "POST":
        for r in records:
            new_status = request.form.get(f"status_{r.id}")
            if new_status:
                r.status = new_status
        db.session.commit()
        flash("Attendance updated", "success")
        return redirect(request.url)

    present = sum(1 for r in records if r.status == "P")
    total = len(records)
    percentage = round((present / total) * 100, 2) if total else 0

    return render_template(
        "attendance/student_ledger.html",
        student=student,
        records=records,
        present=present,
        total=total,
        percentage=percentage
    )


# ======================================================
# CLASS MONTHLY REGISTER (SCREEN VIEW)
# URL → /attendance/student/class-register
# ======================================================
@attendance.route("/student/class-register")
@login_required
def class_attendance_register():

    class_name = request.args.get("class")
    section = request.args.get("section")
    month = request.args.get("month")

    students, days, attendance = [], [], {}

    if class_name and section and month:
        year, mon = map(int, month.split("-"))
        total_days = calendar.monthrange(year, mon)[1]
        days = [date(year, mon, d) for d in range(1, total_days + 1)]

        students = Student.query.filter_by(
            school_id=current_user.school_id,
            student_class=class_name,
            section=section
        ).all()

        records = StudentAttendance.query.filter(
            StudentAttendance.school_id == current_user.school_id,
            StudentAttendance.attendance_date.between(days[0], days[-1])
        ).all()

        for r in records:
            attendance.setdefault(r.student_id, {})
            attendance[r.student_id][r.attendance_date] = r.status

    return render_template(
        "attendance/class_register.html",
        students=students,
        days=days,
        attendance=attendance,
        class_name=class_name,
        section=section,
        month=month
    )


# ======================================================
# CLASS REGISTER PDF EXPORT
# ======================================================
@attendance.route("/student/class-register/pdf")
@login_required
def class_register_pdf():

    class_name = request.args["class"]
    section = request.args["section"]
    month = request.args["month"]

    year, mon = map(int, month.split("-"))
    total_days = calendar.monthrange(year, mon)[1]
    days = [date(year, mon, d) for d in range(1, total_days + 1)]

    students = Student.query.filter_by(
        school_id=current_user.school_id,
        student_class=class_name,
        section=section
    ).all()

    records = StudentAttendance.query.filter(
        StudentAttendance.school_id == current_user.school_id,
        StudentAttendance.attendance_date.between(days[0], days[-1])
    ).all()

    attendance = {}
    for r in records:
        attendance.setdefault(r.student_id, {})
        attendance[r.student_id][r.attendance_date] = r.status

    school = School.query.get(current_user.school_id)

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=landscape(A4),
        leftMargin=15,
        rightMargin=15,
        topMargin=15,
        bottomMargin=15
    )

    styles = getSampleStyleSheet()

    from reportlab.lib.styles import ParagraphStyle

    school_title = ParagraphStyle(
        "SchoolTitle",
        fontSize=18,
        leading=20,        # tight but readable
        alignment=1,
        fontName="Helvetica-Bold",
        spaceAfter=0
    )

    school_sub = ParagraphStyle(
        "SchoolSub",
       fontSize=10,
        leading=12,
        alignment=1,
        spaceBefore=2
    )

    elements = []

    # ================= HEADER =================
    header = Table([
    [
        Image(school.logo, 0.9*inch, 0.9*inch) if school.logo else "",
        Paragraph(
            f"""
            <b>{school.school_name.upper()}</b><br/>
            <font size="10">
            {school.address}, {school.city}<br/>
            Phone: {school.phone} 
            </font>
            """,
            school_title
        )
    ]
], colWidths=[1.1*inch, 9.9*inch])


    header.setStyle(TableStyle([
    ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ("TOPPADDING", (0,0), (-1,-1), 2),
    ("LINEBELOW", (0,0), (-1,0), 1.5, colors.black),
]))


    elements.append(header)
    elements.append(Spacer(1, 8))

    # ================= META =================
    meta = Table([[
        f"Class : {class_name}-{section}",
        f"Month : {calendar.month_name[mon]} {year}",
        "Session : 2025–26"
    ]], colWidths=[4*inch, 4*inch, 3*inch])

    meta.setStyle(TableStyle([
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("FONTNAME", (0,0), (-1,-1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))

    elements.append(meta)
    elements.append(Spacer(1, 6))

    # ================= REGISTER TABLE =================
    table_data = [
        ["#", "Student Name"] + [str(d.day) for d in days] + ["P", "A", "%"]
    ]

    for i, s in enumerate(students, 1):
        P = A = 0
        row = [i, f"{s.first_name} {s.last_name}"]

        for d in days:
            st = attendance.get(s.id, {}).get(d)
            if d.weekday() == 6:
                row.append("")          # Sunday
            elif st == "P":
                row.append("P"); P += 1
            elif st == "A":
                row.append("A"); A += 1
            else:
                row.append("")

        percent = round((P / (P + A)) * 100, 1) if (P + A) else 0
        row.extend([P, A, f"{percent}%"])
        table_data.append(row)

    col_widths = (
        [0.2*inch, 1.2*inch] +        # Student name reduced
        [0.30*inch] * len(days) +     # Day columns wider
        [0.2*inch, 0.2*inch, 0.5*inch]
    )

    table = Table(
        table_data,
        colWidths=col_widths,
        repeatRows=1
    )

    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 0.3, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 7),
        ("ALIGN", (2,1), (-1,-1), "CENTER"),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 18))

    # ================= FOOTER =================
    footer = Table([[
        "Date: ____________",
        "Class Teacher",
        "Principal (Stamp)"
    ]], colWidths=[3.5*inch, 4*inch, 4*inch])

    footer.setStyle(TableStyle([
        ("TOPPADDING", (0,0), (-1,-1), 20),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
    ]))

    elements.append(footer)

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="class_attendance_register.pdf"
    )



# ======================================================
# CLASS REGISTER EXCEL EXPORT
# ======================================================
@attendance.route("/student/class-register/excel")
@login_required
def class_register_excel():

    class_name = request.args["class"]
    section = request.args["section"]
    month = request.args["month"]

    year, mon = map(int, month.split("-"))
    total_days = calendar.monthrange(year, mon)[1]
    days = [date(year, mon, d) for d in range(1, total_days + 1)]

    students = Student.query.filter_by(
        school_id=current_user.school_id,
        student_class=class_name,
        section=section
    ).all()

    records = StudentAttendance.query.filter(
        StudentAttendance.school_id == current_user.school_id,
        StudentAttendance.attendance_date.between(days[0], days[-1])
    ).all()

    attendance = {}
    for r in records:
        attendance.setdefault(r.student_id, {})
        attendance[r.student_id][r.attendance_date] = r.status

    rows = []
    for s in students:
        row = {"Student": f"{s.first_name} {s.last_name}"}
        P = A = 0
        for d in days:
            st = attendance.get(s.id, {}).get(d)
            if st == "P":
                row[d.day] = "P"; P += 1
            elif st == "A":
                row[d.day] = "A"; A += 1
            else:
                row[d.day] = ""
        row["P"] = P
        row["A"] = A
        row["%"] = round((P/(P+A))*100, 1) if (P+A) else 0
        rows.append(row)

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(output, as_attachment=True,
                     download_name="class_attendance_register.xlsx")


# ======================================================
# LEDGER PDF EXPORT (ADVANCE DESIGN + SCHOOL DETAILS)
# ======================================================
@attendance.route("/student/ledger/<int:student_id>/pdf")
@login_required
def student_ledger_pdf(student_id):

    student = Student.query.get_or_404(student_id)
    school = School.query.get(current_user.school_id)

    records = StudentAttendance.query.filter_by(
        school_id=current_user.school_id,
        student_id=student.id
    ).order_by(StudentAttendance.attendance_date).all()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    elements = []

    # ================= HEADER =================
    header_table_data = []

    if school and school.logo:
        header_table_data.append([
            Image(school.logo, 1.2*inch, 1.2*inch),
            Paragraph(
                f"<para align='center'><b>{school.school_name}</b><br/>{school.address or ''}</para>",
                styles["Title"]
            )
        ])
    else:
        header_table_data.append([
            "",
            Paragraph(
                f"<para align='center'><b>{school.school_name}</b><br/>{school.address or ''}</para>",
                styles["Title"]
            )
        ])

    header_table = Table(header_table_data, colWidths=[1.5*inch, 4.5*inch])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LINEBELOW", (0,-1), (-1,-1), 1, colors.black),
    ]))

    elements.append(header_table)
    elements.append(Spacer(1, 16))

    # ================= STUDENT INFO =================
    student_info = f"""
    <b>Student Name:</b> {student.first_name} {student.middle_name or ''} {student.last_name or ''}<br/>
    <b>Class:</b> {student.student_class} {student.section}
    """

    info_box = Table([[Paragraph(student_info, styles["Normal"])]],
                     colWidths=[6*inch])
    info_box.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 1, colors.grey),
        ("PADDING", (0,0), (-1,-1), 10)
    ]))

    elements.append(info_box)
    elements.append(Spacer(1, 20))

    # ================= ATTENDANCE TABLE =================
    data = [["Date", "Status"]]
    present = 0

    for r in records:
        status = "Present" if r.status == "P" else "Absent"
        if r.status == "P":
            present += 1
        data.append([r.attendance_date.strftime("%d-%m-%Y"), status])

    attendance_table = Table(data, colWidths=[3*inch, 3*inch])
    attendance_table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("GRID", (0,0), (-1,-1), 0.5, colors.grey),
        ("ALIGN", (0,0), (-1,-1), "CENTER"),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold")
    ]))

    elements.append(attendance_table)
    elements.append(Spacer(1, 16))

    # ================= SUMMARY =================
    total = len(records)
    percentage = round((present / total) * 100, 2) if total else 0

    summary = f"""
    <b>Total Days:</b> {total} &nbsp;&nbsp;&nbsp;
    <b>Present:</b> {present} &nbsp;&nbsp;&nbsp;
    <b>Attendance %:</b> {percentage}%
    """

    elements.append(Paragraph(summary, styles["Normal"]))
    elements.append(Spacer(1, 20))

    # ================= FOOTER =================
    footer = f"""
    <para align='center'>
    Generated on {date.today().strftime("%d-%m-%Y")} <br/>
    School ERP – Attendance Ledger
    </para>
    """
    elements.append(Paragraph(footer, styles["Italic"]))

    # BUILD PDF
    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="attendance_ledger.pdf"
    )



# ======================================================
# LEDGER EXCEL EXPORT
# ======================================================
@attendance.route("/student/ledger/<int:student_id>/excel")
@login_required
def student_ledger_excel(student_id):

    student = Student.query.get_or_404(student_id)

    records = StudentAttendance.query.filter_by(
        school_id=current_user.school_id,
        student_id=student.id
    ).order_by(StudentAttendance.attendance_date).all()

    rows = []
    for r in records:
        rows.append({
            "Date": r.attendance_date.strftime("%d-%m-%Y"),
            "Status": "Present" if r.status == "P" else "Absent"
        })

    df = pd.DataFrame(rows)

    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="attendance_ledger.xlsx"
    )


# ======================================================
# HOLIDAY MASTER
# ======================================================
@attendance.route("/holiday", methods=["GET", "POST"])
@login_required
def holiday_master():

    if request.method == "POST":
        db.session.add(Holiday(
            school_id=current_user.school_id,
            holiday_date=datetime.strptime(
                request.form["holiday_date"], "%Y-%m-%d"
            ).date(),
            title=request.form["title"]
        ))
        db.session.commit()
        flash("Holiday added", "success")

    holidays = Holiday.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Holiday.holiday_date).all()

    return render_template("attendance/holiday.html", holidays=holidays)

# ======================================================
# STUDENT YEARLY REGISTER (MONTH-WISE)
# ======================================================
@attendance.route("/student/yearly/<int:student_id>")
@login_required
def student_yearly_register(student_id):

    student = Student.query.get_or_404(student_id)

    records = StudentAttendance.query.filter_by(
        school_id=current_user.school_id,
        student_id=student.id
    ).all()

    yearly = {}

    for r in records:
        key = r.attendance_date.strftime("%Y-%m")
        yearly.setdefault(key, {"P":0,"A":0,"L":0,"H":0})

        yearly[key][r.status] += 1

    summary = []
    for m, v in yearly.items():
        working = v["P"] + v["A"] + v["L"] + v["H"]
        present_score = v["P"] + (v["L"]*0.75) + (v["H"]*0.5)
        percent = round((present_score/working)*100,2) if working else 0

        summary.append({
            "month": m,
            "P": v["P"],
            "A": v["A"],
            "L": v["L"],
            "H": v["H"],
            "percent": percent
        })

    return render_template(
        "attendance/student_yearly.html",
        student=student,
        summary=summary
    )


@attendance.route("/student/yearly/<int:student_id>/pdf")
@login_required
def student_yearly_pdf(student_id):

    student = Student.query.get_or_404(student_id)
    school = School.query.get(current_user.school_id)

    records = StudentAttendance.query.filter_by(
        student_id=student.id,
        school_id=current_user.school_id
    ).all()

    yearly = {}
    for r in records:
        key = r.attendance_date.strftime("%Y-%m")
        yearly.setdefault(key, {"P":0,"A":0,"L":0,"H":0})
        yearly[key][r.status] += 1

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    if school.logo:
        elements.append(Image(school.logo, 1*inch, 1*inch))

    elements.append(Paragraph(
        f"<b>{school.school_name}</b><br/>{school.address or ''}",
        styles["Title"]
    ))
    elements.append(Spacer(1, 12))

    elements.append(Paragraph(
        f"<b>Student:</b> {student.first_name} {student.last_name}<br/>"
        f"<b>Class:</b> {student.student_class} {student.section}",
        styles["Normal"]
    ))
    elements.append(Spacer(1, 12))

    table_data = [["Month", "P", "A", "L", "H", "%"]]

    for m, v in sorted(yearly.items()):
        working = v["P"] + v["A"] + v["L"] + v["H"]
        score = v["P"] + v["L"]*0.75 + v["H"]*0.5
        percent = round((score/working)*100, 2) if working else 0
        table_data.append([m, v["P"], v["A"], v["L"], v["H"], f"{percent}%"])

    table = Table(table_data)
    table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.5,colors.grey),
        ("BACKGROUND",(0,0),(-1,0),colors.lightgrey),
    ]))

    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Principal Signature & Stamp", styles["Normal"]))

    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name="student_yearly_attendance.pdf"
    )

@attendance.route("/student/yearly/<int:student_id>/excel")
@login_required
def student_yearly_excel(student_id):

    student = Student.query.get_or_404(student_id)

    records = StudentAttendance.query.filter_by(
        student_id=student.id,
        school_id=current_user.school_id
    ).all()

    yearly = {}
    for r in records:
        key = r.attendance_date.strftime("%Y-%m")
        yearly.setdefault(key, {"P":0,"A":0,"L":0,"H":0})
        yearly[key][r.status] += 1

    rows = []
    for m, v in yearly.items():
        working = v["P"] + v["A"] + v["L"] + v["H"]
        score = v["P"] + v["L"]*0.75 + v["H"]*0.5
        percent = round((score/working)*100, 2) if working else 0
        rows.append({
            "Month": m,
            "Present": v["P"],
            "Absent": v["A"],
            "Late": v["L"],
            "Half Day": v["H"],
            "Attendance %": percent
        })

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name="student_yearly_attendance.xlsx"
    )


@attendance.route("/student/yearly/<int:student_id>/analytics")
@login_required
def student_attendance_analytics(student_id):

    student = Student.query.get_or_404(student_id)

    records = StudentAttendance.query.filter_by(
        student_id=student.id,
        school_id=current_user.school_id
    ).all()

    monthly = {}
    for r in records:
        key = r.attendance_date.strftime("%Y-%m")
        monthly.setdefault(key, {"P":0,"A":0,"L":0,"H":0})
        monthly[key][r.status] += 1

    months = sorted(monthly.keys())
    percents = []

    for m in months:
        v = monthly[m]
        working = v["P"] + v["A"] + v["L"] + v["H"]
        score = v["P"] + v["L"]*0.75 + v["H"]*0.5
        percents.append((score/working)*100 if working else 0)

    plt.figure()
    plt.plot(months, percents)
    plt.xlabel("Month")
    plt.ylabel("Attendance %")
    plt.title("Attendance Trend")
    plt.xticks(rotation=45)

    img = io.BytesIO()
    plt.savefig(img, format="png", bbox_inches="tight")
    plt.close()
    img.seek(0)

    return send_file(img, mimetype="image/png")


@attendance.route("/teacher/register/edit", methods=["GET", "POST"])
@login_required
def teacher_register_edit():

    month = request.args.get("month")

    if not month:
        from datetime import datetime
        month = datetime.now().strftime("%Y-%m")

    year, mon = map(int, month.split("-"))

    days = [
        date(year, mon, d)
        for d in range(1, calendar.monthrange(year, mon)[1] + 1)
    ]

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).all()

    # ===== FETCH EXISTING =====
    records = TeacherAttendance.query.filter(
        TeacherAttendance.school_id == current_user.school_id,
        TeacherAttendance.attendance_date.between(days[0], days[-1])
    ).all()

    attendance = {}
    for r in records:
        attendance.setdefault(r.teacher_id, {})
        attendance[r.teacher_id][r.attendance_date] = r.status

    # ===== SAVE =====
    if request.method == "POST":

        for t in teachers:
            for d in days:

                key = f"att_{t.id}_{d}"

                status = request.form.get(key)

                if not status:
                    continue

                record = TeacherAttendance.query.filter_by(
                    school_id=current_user.school_id,
                    teacher_id=t.id,
                    attendance_date=d
                ).first()

                if record:
                    record.status = status
                else:
                    db.session.add(
                        TeacherAttendance(
                            school_id=current_user.school_id,
                            teacher_id=t.id,
                            attendance_date=d,
                            status=status
                        )
                    )

        db.session.commit()
        flash("✅ Monthly attendance saved", "success")
        return redirect(request.url)

    return render_template(
        "attendance/teacher_register_edit.html",
        teachers=teachers,
        days=days,
        attendance=attendance,
        month=month
    )

# ======================================================
# SUBJECT WISE ATTENDANCE
# ======================================================
@attendance.route(
    "/subject",
    methods=["GET", "POST"]
)
@login_required
def subject_attendance():

    today = date.today()

    teacher_subjects = TeacherSubject.query.filter_by(
    school_id=current_user.school_id
).all()

    selected_subject = request.args.get(
        "subject_id"
    )

    students = []

    subject_obj = None

    if selected_subject:

        subject_obj = Subject.query.filter_by(
            id=selected_subject,
            school_id=current_user.school_id
        ).first()

        allocations = StudentSubject.query.filter_by(
            school_id=current_user.school_id,
            subject_id=selected_subject
        ).all()

        student_ids = [
            a.student_id for a in allocations
        ]

        students = Student.query.filter(
            Student.id.in_(student_ids)
        ).all()

    if request.method == "POST":

        period_no = request.form.get(
            "period_no",
            1
        )

        for s in students:

            status = request.form.get(
                f"status_{s.id}",
                "P"
            )

            existing = SubjectAttendance.query.filter_by(

                school_id=current_user.school_id,

                teacher_id=current_user.id,

                student_id=s.id,

                subject_id=selected_subject,

                attendance_date=today,

                period_no=period_no

            ).first()

            if existing:

                existing.status = status

            else:

                db.session.add(

                    SubjectAttendance(

                        school_id=current_user.school_id,

                        teacher_id=current_user.id,

                        student_id=s.id,

                        subject_id=selected_subject,

                        class_name=s.student_class,

                        section=s.section,

                        attendance_date=today,

                        period_no=period_no,

                        status=status
                    )
                )

        db.session.commit()

        flash(
            "Subject attendance saved",
            "success"
        )

        return redirect(request.url)

    return render_template(

        "attendance/subject_attendance.html",

        teacher_subjects=teacher_subjects,

        students=students,

        subject_obj=subject_obj
    )


# ======================================================
# CHECK GPS SESSION
# ======================================================

@attendance.route(
    "/check-gps-session"
)
@login_required
def check_gps_session():

    pending = session.get(
        "gps_attendance_pending",
        False
    )

    return jsonify({
        "pending": pending
    })


# ======================================================
# AUTO GPS CHECK-IN
# ======================================================

@attendance.route(
    "/teacher/gps-checkin",
    methods=["POST"]
)
@login_required
def teacher_gps_checkin():

    latitude = float(
        request.json.get("latitude")
    )

    longitude = float(
        request.json.get("longitude")
    )

    teacher = Teacher.query.filter_by(

    school_id=current_user.school_id,

    id=current_user.employee_id

).first()

    if not teacher:

        return jsonify({
            "status": "error",
            "message": "Teacher not found"
        })

    school = School.query.get(
        current_user.school_id
    )

    if not school.latitude:

        return jsonify({
            "status": "error",
            "message": "School GPS not set"
        })

    allowed = inside_school(

        school.latitude,
        school.longitude,

        latitude,
        longitude,

        school.radius
    )

    if not allowed:

        return jsonify({
            "status": "error",
            "message":
            "Outside School Campus"
        })

    today = date.today()

    existing = TeacherAttendance.query.filter_by(

        school_id=current_user.school_id,

        teacher_id=teacher.id,

        attendance_date=today

    ).first()

    if existing:

        session[
            "gps_attendance_pending"
        ] = False

        return jsonify({
            "status": "success",
            "message":
            "Attendance Already Marked"
        })

    attendance_record = TeacherAttendance(

        school_id=current_user.school_id,

        teacher_id=teacher.id,

        attendance_date=today,

        status="P",

        method="gps",

        latitude=latitude,

        longitude=longitude,

        login_time=datetime.now()
    )

    db.session.add(
        attendance_record
    )

    db.session.commit()

    session[
        "gps_attendance_pending"
    ] = False

    return jsonify({

        "status": "success",

        "message":
        "Attendance Marked Successfully"
    })