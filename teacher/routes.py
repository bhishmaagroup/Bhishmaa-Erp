import os, uuid, base64
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models.teacher import Teacher
from extensions import db
from datetime import datetime
from reportlab.platypus import Image, TableStyle, Paragraph
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import ParagraphStyle
import os
from flask import current_app
from sqlalchemy import extract
from models.teacher import SalaryStructure, SalaryRecord, SalaryPayment
from models.attendance import TeacherAttendance
from face_attendance.face_engine import encode_face

teacher = Blueprint('teacher', __name__, url_prefix='/teacher')

UPLOAD_TEACHER = 'teachers'
UPLOAD_DOCS = 'teacher_docs'


# ================= HELPERS =================

def pdf_image(path, width, height):
    if path and os.path.exists(path):
        return Image(path, width, height)
    return ""


def section_title(text):
    return Paragraph(
        f"<b><font size=12>{text}</font></b>",
        ParagraphStyle(
            name="section",
            spaceAfter=8,
            spaceBefore=12
        )
    )


def style_table(tbl):
    tbl.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('BACKGROUND', (0,0), (-1,0), colors.whitesmoke),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('FONT', (0,0), (-1,-1), 'Helvetica', 9),
    ]))


def save_file(file, folder, old_file=None):
    if file and file.filename:
        filename = f"{uuid.uuid4().hex}_{file.filename}"

        # ✅ absolute path (PythonAnywhere safe)
        upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
        os.makedirs(upload_path, exist_ok=True)

        full_path = os.path.join(upload_path, filename)
        file.save(full_path)

        # 🔥 OLD FILE DELETE
        if old_file:
            old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], old_file)
            if os.path.exists(old_path):
                try:
                    os.remove(old_path)
                except:
                    pass

        # ✅ DB me relative path
        return f"{folder}/{filename}"

    return None


def save_base64_image(data, folder, old_file=None):
    if not data:
        return None

    header, encoded = data.split(",", 1)
    filename = f"{uuid.uuid4().hex}.png"

    # ✅ absolute path
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(upload_path, exist_ok=True)

    full_path = os.path.join(upload_path, filename)

    with open(full_path, "wb") as f:
        f.write(base64.b64decode(encoded))

    # 🔥 OLD FILE DELETE
    if old_file:
        old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], old_file)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except:
                pass

    # ✅ DB me relative path
    return f"{folder}/{filename}"


def parse_date(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d")

# ================= HELPER =================
def get_structure(staff_id):
    s = SalaryStructure.query.filter_by(
        staff_id=staff_id,
        school_id=current_user.school_id
    ).first()

    if not s:
        s = SalaryStructure.query.filter_by(
            school_id=current_user.school_id,
            is_default=True
        ).first()

    return s


# ================= SALARY CALC =================
def calculate_salary(s, present, absent, late, half):

    gross = (
        s.basic + s.hra + s.da +
        s.ta + s.medical + s.other_allowance
    )

    per_day = s.per_day_salary or 0

    # ===== ATTENDANCE =====
    absent_cut = absent * (per_day * s.absent_cut_percent / 100)
    late_cut = late * (per_day * s.late_cut_percent / 100)
    half_cut = half * (per_day * s.half_day_cut_percent / 100)

    attendance_cut = absent_cut + late_cut + half_cut

    # ===== DEDUCTIONS =====
    deductions = (
        s.pf + s.pt + s.tds +
        s.esi + s.loan + attendance_cut
    )

    net = gross - deductions

    return {
        "gross": gross,
        "attendance_deduction": attendance_cut,
        "deduction": deductions,
        "net": net
    }

def generate_salary_for_month(month):

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).all()

    year, mon = map(int, month.split("-"))

    import calendar
    from datetime import date

    days_in_month = calendar.monthrange(year, mon)[1]
    start_date = date(year, mon, 1)
    end_date = date(year, mon, days_in_month)

    for t in teachers:

        structure = get_structure(t.id)
        if not structure:
            continue

        exists = SalaryRecord.query.filter_by(
            staff_id=t.id,
            school_id=current_user.school_id,
            month=month
        ).first()

        if exists:
            continue

        # ===== ATTENDANCE =====
        records = TeacherAttendance.query.filter(
            TeacherAttendance.teacher_id == t.id,
            TeacherAttendance.school_id == current_user.school_id,
            TeacherAttendance.attendance_date.between(start_date, end_date)
        ).all()

        P = sum(r.status == "P" for r in records)
        A = sum(r.status == "A" for r in records)
        L = sum(r.status == "L" for r in records)
        H = sum(r.status == "H" for r in records)

        # ===== SALARY =====
        gross = (
            structure.basic + structure.hra + structure.da +
            structure.ta + structure.medical + structure.other_allowance
        )

        per_day = gross / days_in_month

        absent_cut = A * (per_day * structure.absent_cut_percent / 100)
        late_cut = L * (per_day * structure.late_cut_percent / 100)
        half_cut = H * (per_day * structure.half_day_cut_percent / 100)

        attendance_cut = absent_cut + late_cut + half_cut

        deductions = (
            structure.pf + structure.pt + structure.tds +
            structure.esi + structure.loan + attendance_cut
        )

        net = gross - deductions

        db.session.add(SalaryRecord(
            school_id=current_user.school_id,
            staff_id=t.id,
            month=month,

            total_days=days_in_month,
            present=P,
            absent=A,
            late=L,
            half_day=H,

            basic=structure.basic,
            hra=structure.hra,
            da=structure.da,
            ta=structure.ta,
            medical=structure.medical,
            special=structure.other_allowance,

            pf=structure.pf,
            pt=structure.pt,
            tds=structure.tds,
            esi=structure.esi,
            loan=structure.loan,

            gross_salary=gross,
            attendance_deduction=attendance_cut,
            total_deduction=deductions,
            net_salary=net,

            status="Pending"
        ))

    db.session.commit()


@teacher.route("/dashboard")
@login_required
def teacher_dashboard():

    

    # Cards
    total_teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).count()

    active_teachers = Teacher.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).count()

  

    return render_template(
        "teacher/dashboard.html",
        total_teachers=total_teachers,
        active_teachers=active_teachers
        
    )


# ================= ADD TEACHER =================
@teacher.route('/add', methods=['GET', 'POST'])
@login_required
def add_teacher():

    if request.method == 'POST':

        last = Teacher.query.filter_by(
            school_id=current_user.school_id
        ).order_by(Teacher.id.desc()).first()

        next_no = (last.id + 1) if last else 1
        teacher_code = f"TCH-{datetime.now().year}-{next_no:03d}"

        photo_path = save_base64_image(
            request.form.get('photo'),
            'teachers'
)

        t = Teacher(
            school_id=current_user.school_id,
            teacher_code=teacher_code,

            # BASIC
            first_name=request.form.get('first_name'),
            middle_name=request.form.get('middle_name'),
            last_name=request.form.get('last_name'),
            gender=request.form.get('gender'),
            dob=parse_date(request.form.get('dob')),
            joining_date=parse_date(request.form.get('joining_date')),
            mobile=request.form.get('mobile'),
            email=request.form.get('email'),

            # EMPLOYMENT
            designation=request.form.get('designation'),
            employment_type=request.form.get('employment_type'),
            salary=request.form.get('salary'),
            experience=request.form.get('experience'),

            # QUALIFICATION
            qualification=request.form.get('qualification'),
            specialization=request.form.get('subject'),   # ✅ FIX
            pan=request.form.get('pan_no'),                # ✅ FIX
            aadhaar=request.form.get('aadhaar'),

            # ADDRESS
            address=request.form.get('address'),
            permanent_address=request.form.get('permanent_address'),

            # FILE PATHS
            photo=photo_path,
            resume=save_file(request.files.get('resume'), UPLOAD_DOCS),
            aadhaar_doc=save_file(request.files.get('aadhaar_doc'), UPLOAD_DOCS),
            pass_doc=save_file(request.files.get('pan_doc'), UPLOAD_DOCS),
            qualification_doc=save_file(request.files.get('qualification_doc'), UPLOAD_DOCS)
        )

        db.session.add(t)
        db.session.commit()

        flash("Teacher added successfully", "success")
        return redirect(url_for('teacher.list_teachers'))

    return render_template('teacher/add.html')


# ================= LIST =================
@teacher.route('/list')
@login_required
def list_teachers():
    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).order_by(Teacher.id.desc()).all()
    return render_template('teacher/list.html', teachers=teachers)


# ================= VIEW =================
@teacher.route('/view/<int:id>')
@login_required
def view_teacher(id):
    t = Teacher.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()
    return render_template('teacher/view.html', t=t)


# ================= EDIT =================
@teacher.route('/edit/<int:id>', methods=['GET','POST'])
@login_required
def edit_teacher(id):

    t = Teacher.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()

    if request.method == 'POST':

        for field in [
            'first_name','middle_name','last_name','gender',
            'mobile','email','designation','employment_type',
            'salary','experience','qualification',
            'address','permanent_address'
        ]:
            setattr(t, field, request.form.get(field))

        t.specialization = request.form.get('subject')
        t.pan = request.form.get('pan_no')
        t.aadhaar = request.form.get('aadhaar')
        t.dob = parse_date(request.form.get('dob'))
        t.joining_date = parse_date(request.form.get('joining_date'))

        # ✅ PHOTO FIX (IMPORTANT)
        if request.form.get('photo'):
            t.photo = save_base64_image(
                request.form.get('photo'),
                'teachers',
                t.photo   # 🔥 add this
                )

        # ✅ DOCUMENT FIX
        for f, attr in [
            ('resume','resume'),
            ('aadhaar_doc','aadhaar_doc'),
            ('pass_doc','pass_doc'),
            ('qualification_doc','qualification_doc')
        ]:
            file = request.files.get(f)
            if file and file.filename:
                setattr(t, attr, save_file(file, 'teacher_docs'))  # ✅ FIXED

        db.session.commit()
        flash("Teacher updated successfully", "success")
        return redirect(url_for('teacher.view_teacher', id=id))

    return render_template('teacher/edit.html', t=t)


# ================= DELETE =================
@teacher.route('/delete/<int:id>')
@login_required
def delete_teacher(id):
    t = Teacher.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()

    db.session.delete(t)
    db.session.commit()
    flash("Teacher deleted", "danger")
    return redirect(url_for('teacher.list_teachers'))

@teacher.route('/toggle-status/<int:id>', methods=['POST'])
@login_required
def toggle_teacher_status(id):

    t = Teacher.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()

    t.is_active = not t.is_active
    db.session.commit()

    status = "Activated" if t.is_active else "Deactivated"
    flash(f"Teacher {status} successfully", "success")

    return redirect(url_for('teacher.view_teacher', id=id))

@teacher.route('/profile-pdf/<int:id>')
@login_required
def teacher_profile_pdf(id):

    import io
    from flask import send_file
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, Spacer
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from models.school import School
    

    t = Teacher.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()

    school = School.query.get(current_user.school_id)

    buffer = io.BytesIO()

    pdf = SimpleDocTemplate(
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
    header = Table([
        [
            pdf_image(school.logo, 1*inch, 1*inch) if school and school.logo else "",
            Paragraph(
                f"""
                <para align="center">
                <b><font size=22>{school.school_name}</font></b><br/>
                <font size=10>{school.address}, {school.city}</font><br/><br/>
                <font size=13><b>TEACHER PROFILE</b></font>
                </para>
                """,
                styles["Normal"]
            ),
            pdf_image(t.photo, 0.9*inch, 1.1*inch) if t.photo else ""
        ]
    ], colWidths=[90, 330, 110])

    elements.append(header)
    elements.append(Spacer(1, 14))

    # ================= BASIC INFO =================
    info = Table([
        ["Teacher Code", t.teacher_code, "Employment Type", t.employment_type],
        ["Joining Date", t.joining_date.strftime('%d-%m-%Y') if t.joining_date else "",
         "Status", "Active" if t.is_active else "Inactive"]
    ], colWidths=[80, 170, 80, 170])

    style_table(info)
    elements.append(info)
    elements.append(Spacer(1, 14))

    # ================= PERSONAL DETAILS =================
    elements.append(section_title("Personal Details"))

    personal = Table([
        ["Name", f"{t.first_name} {t.middle_name or ''} {t.last_name}", "Gender", t.gender],
        ["DOB", t.dob.strftime('%d-%m-%Y') if t.dob else "", "Mobile", t.mobile],
        ["Email", t.email, "Aadhaar", t.aadhaar],
        ["PAN", t.pan, "Address", t.address],
        
    ], colWidths=[80, 170, 80, 170])

    style_table(personal)
    elements.append(personal)
    elements.append(Spacer(1, 14))

    # ================= ACADEMIC DETAILS =================
    elements.append(section_title("Academic & Employment Details"))

    academic = Table([
        ["Qualification", t.qualification, "Specialization", t.specialization],
        ["Experience", f"{t.experience} Years", "Salary", f"Rs. {t.salary}"]
    ], colWidths=[80, 170, 80, 170])

    style_table(academic)
    elements.append(academic)
    elements.append(Spacer(1, 16))

    # ================= DOCUMENT STATUS =================
    elements.append(section_title("Documents Submitted"))

    docs = Table([
        ["Document", "Status"],
        ["Resume", "Submitted" if t.resume else "Not Submitted"],
        ["Aadhaar", "Submitted" if t.aadhaar_doc else "Not Submitted"],
         ["PassBook", "Submitted" if t.pass_doc else "Not Submitted"],
        ["Qualification Certificate", "Submitted" if t.qualification_doc else "Not Submitted"],
    ], colWidths=[250, 250])

    style_table(docs)
    elements.append(docs)

    # ================= SIGNATURE =================
    elements.append(Spacer(1, 50))

    sign = Table([
        ["Teacher Signature", "", "Principal Signature"]
    ], colWidths=[200, 100, 200])

    sign.setStyle([
        ('LINEABOVE', (0,0), (0,0), 0.5, colors.black),
        ('LINEABOVE', (2,0), (2,0), 0.5, colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('TOPPADDING', (0,0), (-1,-1), 12),
        ('FONT', (0,0), (-1,-1), 'Helvetica', 9)
    ])

    elements.append(sign)

    # ================= BUILD PDF =================
    pdf.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Teacher_Profile_{t.teacher_code}.pdf",
        mimetype="application/pdf"
    )


# salary 

# ================= GENERATE ALL (ADVANCED AUTO) =================
@teacher.route('/generate-all-salary/<string:month>')
@login_required
def generate_all_salary(month):

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).all()

    year, mon = map(int, month.split("-"))

    import calendar
    from datetime import date

    days_in_month = calendar.monthrange(year, mon)[1]
    start_date = date(year, mon, 1)
    end_date = date(year, mon, days_in_month)

    for t in teachers:

        structure = get_structure(t.id)
        if not structure:
            continue

        exists = SalaryRecord.query.filter_by(
            staff_id=t.id,
            school_id=current_user.school_id,
            month=month
        ).first()

        if exists:
            continue

        # ===== ATTENDANCE =====
        records = TeacherAttendance.query.filter(
            TeacherAttendance.teacher_id == t.id,
            TeacherAttendance.school_id == current_user.school_id,
            TeacherAttendance.attendance_date.between(start_date, end_date)
        ).all()

        P = sum(r.status == "P" for r in records)
        A = sum(r.status == "A" for r in records)
        L = sum(r.status == "L" for r in records)
        H = sum(r.status == "H" for r in records)

        # ===== PER DAY FIX =====
        gross = (
            structure.basic + structure.hra + structure.da +
            structure.ta + structure.medical + structure.other_allowance
        )

        per_day = gross / days_in_month

        # ===== CUTS =====
        absent_cut = A * (per_day * structure.absent_cut_percent / 100)
        late_cut = L * (per_day * structure.late_cut_percent / 100)
        half_cut = H * (per_day * structure.half_day_cut_percent / 100)

        attendance_cut = absent_cut + late_cut + half_cut

        deductions = (
            structure.pf + structure.pt + structure.tds +
            structure.esi + structure.loan + attendance_cut
        )

        net = gross - deductions

        db.session.add(SalaryRecord(
            school_id=current_user.school_id,
            staff_id=t.id,
            month=month,

            total_days=days_in_month,
            present=P,
            absent=A,
            late=L,
            half_day=H,

            # 🔥 FREEZE DATA
            basic=structure.basic,
            hra=structure.hra,
            da=structure.da,
            ta=structure.ta,
            medical=structure.medical,
            special=structure.other_allowance,

            pf=structure.pf,
            pt=structure.pt,
            tds=structure.tds,
            esi=structure.esi,
            loan=structure.loan,

            gross_salary=gross,
            attendance_deduction=attendance_cut,
            total_deduction=deductions,
            net_salary=net,

            status="Pending"
        ))

    db.session.commit()

    flash("✅ Salary Generated Successfully", "success")
    return redirect(url_for('teacher.salary_panel', month=month))

@teacher.route('/generate-current-month-salary')
@login_required
def generate_current_salary():

    from datetime import datetime
    month = datetime.now().strftime("%Y-%m")

    return redirect(url_for('teacher.generate_all_salary', month=month))


# ================= SALARY STRUCTURE FINAL =================
@teacher.route('/salary-structure/<int:id>', methods=['GET', 'POST'])
@login_required
def salary_structure(id):

    t = Teacher.query.get_or_404(id)
    s = get_structure(t.id)

    # ===== AUTO FETCH =====
    if not s or (s.basic == 0 and t.salary):

        base_salary = float(t.salary or 0)

        if not s:
            s = SalaryStructure(
                school_id=current_user.school_id,
                staff_id=t.id
            )

        s.basic = base_salary * 0.5
        s.hra = base_salary * 0.2
        s.da = base_salary * 0.15
        s.ta = base_salary * 0.05
        s.medical = base_salary * 0.05
        s.other_allowance = base_salary * 0.05

        # 🔥 ATTENDANCE RULES
        s.absent_cut_percent = 100   # NEW
        s.late_cut_percent = 25
        s.half_day_cut_percent = 50
        s.grace_minutes = 10

        db.session.add(s)
        db.session.commit()

    if request.method == 'POST':

        # ===== EARNINGS =====
        s.basic = int(request.form.get('basic') or 0)
        s.hra = float(request.form.get('hra') or 0)
        s.da = float(request.form.get('da') or 0)
        s.ta = float(request.form.get('ta') or 0)
        s.medical = float(request.form.get('medical') or 0)
        s.other_allowance = float(request.form.get('special') or 0)

        # ===== DEDUCTIONS =====
        s.pf = float(request.form.get('pf') or 0)
        s.pt = float(request.form.get('pt') or 0)
        s.tds = float(request.form.get('tds') or 0)
        s.esi = float(request.form.get('esi') or 0)
        s.loan = float(request.form.get('loan') or 0)

        # ===== ATTENDANCE =====
        s.absent_cut_percent = int(request.form.get('absent_cut') or 100)
        s.late_cut_percent = int(request.form.get('late_cut') or 25)
        s.half_day_cut_percent = int(request.form.get('half_cut') or 50)
        s.grace_minutes = int(request.form.get('grace') or 10)

        # ===== CALC =====
        gross = (
            s.basic + s.hra + s.da +
            s.ta + s.medical + s.other_allowance
        )

        import calendar
        from datetime import datetime

        now = datetime.now()
        days = calendar.monthrange(now.year, now.month)[1]

        s.per_day_salary = gross / days

        db.session.commit()

        flash("✅ Structure Saved", "success")
        return redirect(url_for('teacher.salary_panel'))

    return render_template('teacher/salary_structure.html', t=t, s=s)

# ================= PAYMENT =================
@teacher.route('/salary-payment/<int:salary_id>', methods=['GET', 'POST'])
@login_required
def salary_payment(salary_id):

    from datetime import datetime, date
    import calendar

    salary = SalaryRecord.query.get_or_404(salary_id)
    teacher = Teacher.query.get(salary.staff_id)

    # ================= PAYMENTS =================
    payments = SalaryPayment.query.filter_by(
        salary_id=salary.id
    ).all()

    paid = sum(p.paid_amount for p in payments)
    remaining = max(salary.net_salary - paid, 0)

    prev_advance = max(paid - salary.net_salary, 0)
    adjusted_salary = salary.net_salary - prev_advance

    # ================= STATUS UPDATE =================
    if paid == 0:
        salary.status = "Pending"
    elif paid < salary.net_salary:
        salary.status = "Partial"
    else:
        salary.status = "Paid"

    db.session.commit()

    # ================= EARNINGS =================
    earnings = {
        "Basic": salary.basic,
        "HRA": salary.hra,
        "DA": salary.da,
        "TA": salary.ta,
        "Medical": salary.medical,
        "Special": salary.special
    }

    # ================= DEDUCTIONS =================
    deductions = {
        "PF": salary.pf,
        "PT": salary.pt,
        "TDS": salary.tds,
        "ESI": salary.esi,
        "Loan": salary.loan,
        "Attendance Cut": salary.attendance_deduction
    }

    # ================= ATTENDANCE (FULL MONTH) =================
    year, mon = map(int, salary.month.split("-"))
    days_in_month = calendar.monthrange(year, mon)[1]

    start_date = date(year, mon, 1)
    end_date = date(year, mon, days_in_month)

    records = TeacherAttendance.query.filter(
        TeacherAttendance.teacher_id == teacher.id,
        TeacherAttendance.school_id == current_user.school_id,
        TeacherAttendance.attendance_date.between(start_date, end_date)
    ).all()

    attendance_map = {r.attendance_date: r.status for r in records}

    attendance_days = []

    P = A = L = H = 0

    for d in range(1, days_in_month + 1):
        dt = date(year, mon, d)
        status = attendance_map.get(dt, "-")

        if status == "P": P += 1
        elif status == "A": A += 1
        elif status == "L": L += 1
        elif status == "H": H += 1

        attendance_days.append({
            "date": dt,
            "status": status
        })

    # ================= PAYMENT =================
    if request.method == 'POST':

        amount = float(request.form.get('amount') or 0)

        db.session.add(SalaryPayment(
            salary_id=salary.id,
            paid_amount=amount,
            payment_mode=request.form.get('mode'),
            transaction_id=request.form.get('txnid'),
            payment_date=datetime.now()
        ))

        db.session.commit()

        return redirect(url_for('teacher.salary_payment', salary_id=salary.id))

    return render_template(
        'teacher/salary_payment.html',
        salary=salary,
        teacher=teacher,
        payments=payments,
        paid=paid,
        remaining=remaining,
        prev_advance=prev_advance,
        adjusted_salary=adjusted_salary,
        earnings=earnings,
        deductions=deductions,

        # 🔥 NEW
        attendance_days=attendance_days,
        total_P=P,
        total_A=A,
        total_L=L,
        total_H=H
    )
# ================= PANEL =================
@teacher.route('/salary-panel')
@login_required
def salary_panel():

    from datetime import datetime

    month = request.args.get("month")
    if not month:
        month = datetime.now().strftime("%Y-%m")

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id,
        is_active=True
    ).all()

    # ================= AUTO GENERATE (NO REDIRECT) =================
    missing = False

    for t in teachers:
        exists = SalaryRecord.query.filter_by(
            school_id=current_user.school_id,
            staff_id=t.id,
            month=month
        ).first()

        if not exists:
            missing = True
            break

    if missing:
        generate_salary_for_month(month)   # 🔥 direct call (NO REDIRECT)

    # ================= FETCH =================
    records = SalaryRecord.query.filter_by(
        school_id=current_user.school_id,
        month=month
    ).all()

    salary_map = {}

    total_paid = 0
    total_due = 0
    total_salary = 0

    chart_labels = []
    chart_data = []

    for r in records:

        payments = SalaryPayment.query.filter_by(
            salary_id=r.id
        ).all()

        paid = sum(p.paid_amount for p in payments)

        r.paid_amount = paid
        r.due_amount = max(r.net_salary - paid, 0)

        # ===== STATUS =====
        if paid == 0:
            r.status = "Pending"
        elif paid < r.net_salary:
            r.status = "Partial"
        else:
            r.status = "Paid"

        salary_map[r.staff_id] = r

        total_paid += paid
        total_due += r.due_amount
        total_salary += r.net_salary

        teacher = Teacher.query.get(r.staff_id)
        if teacher:
            chart_labels.append(teacher.first_name)
            chart_data.append(r.net_salary)

    db.session.commit()

    return render_template(
        'teacher/salary_panel.html',
        teachers=teachers,
        salary_map=salary_map,
        month=month,
        total_paid=total_paid,
        total_due=total_due,
        total_salary=total_salary,
        chart_labels=chart_labels,
        chart_data=chart_data
    )


@teacher_bp.route("/register-face/<int:id>", methods=["POST"])
def register_face(id):

    teacher = Teacher.query.get_or_404(id)

    image = request.files.get("image")

    filepath = f"uploads/{image.filename}"

    image.save(filepath)

    encoding = encode_face(filepath)

    if not encoding:
        return "No face detected"

    teacher.face_encoding = encoding

    db.session.commit()

    return "Face Registered"