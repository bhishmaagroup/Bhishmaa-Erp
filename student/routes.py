import os, base64, uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash
from models.student import Student
from extensions import db
from datetime import datetime
from flask import send_file
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
import io
from reportlab.platypus import Image
from reportlab.lib.units import inch
from models.school import School
from flask_login import current_user
from werkzeug.utils import secure_filename
from models.fee import StudentFeeLedger, FeeDiscount # Inhe import karna hoga
from flask import current_app
from models.transport import  Route, Stop
from models.transport import TransportAssignment
from models.super import Plan
from utils.email import send_system_email
send_professional_email = send_system_email

def pdf_image(path, w=1.2*inch, h=1.4*inch):
    """
    Safely load image for PDF (NO CRASH).
    """
    if path and os.path.exists(path):
        return Image(path, width=w, height=h)
    return ""


student = Blueprint('student', __name__, url_prefix='/student')

UPLOAD_STUDENT = 'uploads/students'
UPLOAD_PARENT = 'uploads/parents'
UPLOAD_DOC = 'uploads/documents'


from flask import current_app
import os, base64, uuid

def save_base64_image(data, folder, old_file=None):
    if not data:
        return None

    header, encoded = data.split(",", 1)
    filename = f"{uuid.uuid4()}.png"

    # ✅ Absolute path
    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(upload_path, exist_ok=True)

    full_path = os.path.join(upload_path, filename)

    # ✅ Save new file
    with open(full_path, "wb") as f:
        f.write(base64.b64decode(encoded))

    # 🔥 OLD FILE DELETE (IMPORTANT)
    if old_file:
        old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], old_file)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except:
                pass

    # ✅ Return relative path
    return f"{folder}/{filename}"


def save_file(field, folder, old_file=None):
    file = request.files.get(field)

    if file and file.filename:
        filename = secure_filename(file.filename)

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

        return f"{folder}/{filename}"

    return None

from datetime import datetime
@student.route('/admission', methods=['GET', 'POST'])
def admission():
    # --- Auto Session Logic ---
    now = datetime.now()

    if now.month >= 4:
        current_s = f"{now.year}-{str(now.year + 1)[2:]}"
    else:
        current_s = f"{now.year - 1}-{str(now.year)[2:]}"

    years = [f"{y}-{str(y+1)[2:]}" for y in range(2020, 2036)]

    # =========================
    # POST (SAVE DATA)
    # =========================
    if request.method == 'POST':
        school = School.query.get(current_user.school_id)

        current_count = Student.query.filter_by(
            school_id=school.id
        ).count()

        plan = Plan.query.filter_by(name=school.plan).first()

        if plan and current_count >= plan.student_limit:
            flash("🚫 Student limit reached! Upgrade your plan.", "danger")
            return redirect(url_for('super_admin.select_plan'))

        last = Student.query.filter_by(
            school_id=current_user.school_id
        ).order_by(Student.id.desc()).first()

        next_no = (last.id + 1) if last else 1
        admission_no = f"ADM-{now.year}-{next_no:04d}"

        dob_str = request.form.get('dob')
        dob = datetime.strptime(dob_str, "%Y-%m-%d").date() if dob_str else None

        # 🔥 TRANSPORT DATA
        transport_required = request.form.get('transport_required') == 'yes'
        route_id = request.form.get('transport_route')
        stop_id = request.form.get('pickup_point')

        # 🔥 EMAIL VALIDATION
        father_email = request.form.get('father_email')
        mother_email = request.form.get('mother_email')

        if not father_email or not mother_email:
            flash("❌ Father & Mother email are required", "danger")
            return redirect(request.url)

        s = Student(
            school_id=current_user.school_id,
            admission_no=admission_no,

            # BASIC
            first_name=request.form['first_name'],
            middle_name=request.form.get('middle_name'),
            last_name=request.form.get('last_name'),
            gender=request.form.get('gender'),
            dob=dob,
            religion=request.form.get('religion'),
            caste=request.form.get('caste'),
            aadhaar=request.form.get('aadhaar'),
            pen_no=request.form.get('pen_no'),
            blood_group=request.form.get('blood_group'),

            # ACADEMIC
            session=request.form.get('session'),
            student_class=request.form.get('class'),
            section=request.form.get('section'),

            # FAMILY
            father_name=request.form.get('father_name'),
            father_mobile=request.form.get('father_mobile'),
            father_email=father_email,
            father_aadhaar=request.form.get('father_aadhaar'),

            mother_name=request.form.get('mother_name'),
            mother_mobile=request.form.get('mother_mobile'),
            mother_email=mother_email,
            mother_aadhaar=request.form.get('mother_aadhaar'),

            # ADDRESS
            present_address=request.form.get('present_address'),
            permanent_address=request.form.get('permanent_address'),

            guardian_name=request.form.get('guardian_name'),
            guardian_relation=request.form.get('guardian_relation'),
            guardian_mobile=request.form.get('guardian_mobile'),
            guardian_address=request.form.get('guardian_address'),

            # TRANSPORT
            transport_required=transport_required,
            transport_route=route_id,
            pickup_point=stop_id,

            # HOSTEL
            hostel_required=request.form.get('hostel_required') == 'yes',
            hostel_block=request.form.get('hostel_block'),
            hostel_room=request.form.get('hostel_room'),
        )

        # FILES
        s.student_photo = save_base64_image(request.form.get('student_photo'), UPLOAD_STUDENT)
        s.father_photo = save_base64_image(request.form.get('father_photo'), UPLOAD_PARENT)
        s.mother_photo = save_base64_image(request.form.get('mother_photo'), UPLOAD_PARENT)

        s.dob_certificate = save_file(request.files.get('dob_certificate'), UPLOAD_DOC)
        s.aadhaar_doc = save_file(request.files.get('aadhaar_doc'), UPLOAD_DOC)
        s.tc = save_file(request.files.get('tc'), UPLOAD_DOC)
        s.marksheet = save_file(request.files.get('marksheet'), UPLOAD_DOC)

        db.session.add(s)
        db.session.commit()

        # ================= EMAIL CONFIRMATION =================
        try:
            subject = f"🎓 Admission Confirmed - {school.school_name}"

            html = f"""
            <div style="font-family:Arial;background:#f4f6f9;padding:20px">
              <div style="max-width:550px;margin:auto;background:#ffffff;
                          border-radius:12px;padding:24px;box-shadow:0 4px 10px rgba(0,0,0,0.05)">

                <h2 style="color:#0d6efd;">{school.school_name}</h2>

                <p>Dear Parent,</p>

                <p>Admission successfully completed.</p>

                <div style="background:#f8f9fa;padding:15px;border-radius:8px">
                  <p><b>Student:</b> {s.first_name} {s.last_name}</p>
                  <p><b>Class:</b> {s.student_class}</p>
                  <p><b>Admission No:</b> {s.admission_no}</p>
                </div>

                <p>Welcome to {school.school_name} family.</p>

                <p>Regards,<br><b>Admin</b></p>
              </div>
            </div>
            """

            for email in [s.father_email, s.mother_email]:
                if email:
                    send_professional_email(email, subject, html,is_html=True)

        except Exception as e:
            print("Email Error:", e)

        # ================= WHATSAPP =================
        try:
            import pywhatkit as kit
            import pyautogui
            import time

            message = f"""
🎓 Admission Confirmed

Student: {s.first_name} {s.last_name}
Class: {s.student_class}
Admission No: {s.admission_no}

Welcome to {school.school_name}.
"""

            for mobile in [s.father_mobile, s.mother_mobile]:
                if mobile and len(mobile) >= 10:
                    mobile = "+91" + mobile[-10:]

                    kit.sendwhatmsg_instantly(mobile, message, wait_time=15, tab_close=False)

                    time.sleep(5)
                    pyautogui.press("enter")
                    time.sleep(5)
                    pyautogui.hotkey("ctrl", "w")

        except Exception as e:
            print("WhatsApp Error:", e)

        # ================= TRANSPORT =================
        if s.transport_required:
            route = Route.query.get(s.transport_route)

            assignment = TransportAssignment(
                school_id=s.school_id,
                student_id=s.id,
                route_id=s.transport_route,
                stop_id=s.pickup_point,
                bus_id=route.bus_id if route else None
            )

            db.session.add(assignment)
            db.session.commit()

        flash("Admission submitted successfully", "success")
        return redirect(url_for('student.admission_receipt', id=s.id))

    # ================= GET =================
    routes = Route.query.filter_by(
        school_id=current_user.school_id
    ).all()

    return render_template(
        'student/admission.html',
        years=years,
        current_s=current_s,
        routes=routes
    )
    
# =========================
# STUDENT LIST
# =========================
@student.route('/list')
def student_list():
    q = request.args.get('q')

    query = Student.query.filter_by(
        school_id=current_user.school_id
    )

    if q:
        query = query.filter(
            (Student.first_name.ilike(f'%{q}%')) |
            (Student.last_name.ilike(f'%{q}%')) |
            (Student.student_class.ilike(f'%{q}%'))
        )

    students = query.order_by(Student.id.desc()).all()

    return render_template('student/list.html', students=students, q=q)

# =========================
# STUDENT PROFILE
# =========================
@student.route('/view/<int:id>')
def view_student(id):
    student = Student.query.filter_by(
    id=id,
    school_id=current_user.school_id
).first_or_404()
    return render_template('student/view.html', s=student)


# =========================
# EDIT STUDENT
# =========================
@student.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_student(id):
    s = Student.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()

    if request.method == 'POST':

        # ---------- BASIC ----------
        s.first_name = request.form.get('first_name')
        s.middle_name = request.form.get('middle_name')
        s.last_name = request.form.get('last_name')
        s.gender = request.form.get('gender')
        s.dob = datetime.strptime(
            request.form.get('dob'), "%Y-%m-%d"
        ).date() if request.form.get('dob') else None
        s.religion = request.form.get('religion')
        s.caste = request.form.get('caste')
        s.blood_group = request.form.get('blood_group')
        s.aadhaar = request.form.get('aadhaar')
        s.pen_no = request.form.get('pen_no')

        # ---------- ACADEMIC ----------
        s.student_class = request.form.get('student_class')
        s.section = request.form.get('section')
        s.transport_required = request.form.get('transport_required') == 'yes'
        s.hostel_required = request.form.get('hostel_required') == 'yes'
        s.session = request.form.get('session')

        # 🔥 NEW (TRANSPORT DATA ADD)
        s.transport_route = request.form.get('transport_route')
        s.pickup_point = request.form.get('pickup_point')

        # ---------- ADDRESS ----------
        s.present_address = request.form.get('present_address')
        s.permanent_address = request.form.get('permanent_address')

        # ---------- FATHER ----------
        s.father_name = request.form.get('father_name')
        s.father_mobile = request.form.get('father_mobile')
        s.father_aadhaar = request.form.get('father_aadhaar')
        s.father_email = request.form.get('father_email')

        # ---------- MOTHER ----------
        s.mother_name = request.form.get('mother_name')
        s.mother_mobile = request.form.get('mother_mobile')
        s.mother_aadhaar = request.form.get('mother_aadhaar')
        s.mother_email = request.form.get('mother_email')

        # ---------- GUARDIAN ----------
        s.guardian_name = request.form.get('guardian_name')
        s.guardian_relation = request.form.get('guardian_relation')
        s.guardian_mobile = request.form.get('guardian_mobile')
        s.guardian_address = request.form.get('guardian_address')

        # ---------- FILE UPLOAD HELPERS ----------
        def save_file(field, folder, old_file=None):
            file = request.files.get(field)

            if file and file.filename:
                filename = secure_filename(file.filename)

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

                return f"{folder}/{filename}"

            return None

        # ---------- PHOTOS ----------
        new_student_photo = save_file('student_photo_new', 'students', s.student_photo)
        if new_student_photo:
            s.student_photo = new_student_photo

        new_father_photo = save_file('father_photo_new', 'parents', s.father_photo)
        if new_father_photo:
            s.father_photo = new_father_photo

        new_mother_photo = save_file('mother_photo_new', 'parents', s.mother_photo)
        if new_mother_photo:
            s.mother_photo = new_mother_photo

        # ---------- DOCUMENTS ----------
        for field, attr in [
            ('dob_certificate_new', 'dob_certificate'),
            ('aadhaar_doc_new', 'aadhaar_doc'),
            ('tc_new', 'tc'),
            ('marksheet_new', 'marksheet')
        ]:
            new_file = save_file(field, 'documents', getattr(s, attr))
            if new_file:
                setattr(s, attr, new_file)

        # 🔥 NEW (TRANSPORT ASSIGNMENT UPDATE)
        from models.transport import TransportAssignment, Route

        # Old delete
        TransportAssignment.query.filter_by(student_id=s.id).delete()

        # New create
        if s.transport_required:
            route = Route.query.get(s.transport_route)

            assignment = TransportAssignment(
                school_id=s.school_id,
                student_id=s.id,
                route_id=s.transport_route,
                stop_id=s.pickup_point,
                bus_id=route.bus_id if route else None
            )

            db.session.add(assignment)

        db.session.commit()
        flash("Student updated successfully", "success")
        return redirect(url_for('student.view_student', id=s.id))

    # 🔥 NEW (ROUTES SEND FOR DROPDOWN)
    from models.transport import Route

    routes = Route.query.filter_by(
        school_id=current_user.school_id
    ).all()

    return render_template(
        'student/edit.html',
        s=s,
        routes=routes
    )

# =========================
# DELETE STUDENT
# =========================


@student.route('/delete/<int:id>')
def delete_student(id):
    s = Student.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()

    # Manual Clean-up (Agar Cascade kaam nahi kar raha)
    StudentFeeLedger.query.filter_by(student_id=id).delete()
    FeeDiscount.query.filter_by(student_id=id).delete()

    db.session.delete(s)
    db.session.commit()

    flash("Student and all related fee records deleted permanently.")
    return redirect(url_for('student.student_list'))
@student.route('/promote/<int:id>', methods=['POST'])
def promote_student(id):
    s = Student.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()

    next_class = request.form.get('next_class')
    next_section = request.form.get('next_section')
    next_session = request.form.get('next_session')

    # AUTO ROLL NO (next class)
    last = Student.query.filter_by(
    school_id=current_user.school_id,
    student_class=next_class,
    section=next_section,
    session=next_session
).first()

    s.student_class = next_class
    s.section = next_section
    s.session = next_session
    

    db.session.commit()
    flash("Student promoted successfully", "success")
    return redirect(url_for('student.view_student', id=id))

# ✅ KEEP THESE FUNCTIONS ABOVE THE ROUTE

def style_table(table):
    table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('FONT', (0,0), (-1,-1), 'Helvetica', 9),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 6),
        ('RIGHTPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 5),
        ('BOTTOMPADDING', (0,0), (-1,-1), 5),
    ]))


def section_title(text):
    return Paragraph(
        f"<b>{text}</b>",
        ParagraphStyle(
            name="section",
            backColor=colors.lightblue,
            fontSize=10,
            spaceBefore=6,
            spaceAfter=6,
            leftIndent=4
        )
    )


@student.route('/admission-receipt/<int:id>')
def admission_receipt(id):

    student = Student.query.filter_by(
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
            pdf_image(school.logo, 1.0*inch, 1.0*inch) if school else "",
            Paragraph(
                f"""
                <para align="center">
                <b><font size=25>{school.school_name if school else ''}</font></b><br/><br/>
                <font size=10>{school.address if school else ''}, {school.city if school else ''}</font><br/><br/>
                <font size=12><b>ADMISSION FORM  – {student.session}</b></font><br/><br/><br/>
                </para>
                """,
                styles["Normal"]
            ),
            pdf_image(student.student_photo, 0.8*inch, 0.9*inch)
        ]
    ], colWidths=[90, 330, 110])

    elements.append(header)
    elements.append(Spacer(1, 12))

    # ================= BASIC INFO =================
    info_table = Table([
        ["Admission No", student.admission_no, "Session", student.session],
        ["Class", f"{student.student_class} {student.section}",
         "Admission Date", student.created_at.strftime('%d-%m-%Y')]
    ], colWidths=[80, 170, 80, 170])

    style_table(info_table)
    elements.append(info_table)
    elements.append(Spacer(1, 12))

    # ================= STUDENT DETAILS =================
    elements.append(section_title("Student Personal Details"))

    student_table = Table([
        ["Student Name", f"{student.first_name} {student.last_name}", "Gender", student.gender],
        ["DOB", student.dob.strftime('%d-%m-%Y'), "Religion", student.religion],
        ["Caste", student.caste, "Blood Group", student.blood_group],
        ["Aadhaar", student.aadhaar, "PEN No", student.pen_no],
        ["Address", student.present_address, "", ""]
    ], colWidths=[80, 170, 80, 170])

    style_table(student_table)
    elements.append(student_table)
    elements.append(Spacer(1, 14))

    # ================= FAMILY DETAILS =================
    elements.append(section_title("Student Family Details"))

    family_table = Table([
        [
            pdf_image(student.father_photo, 1.0*inch, 1.0*inch),
            Paragraph(
                f"<b>Father Name:</b> {student.father_name}<br/>"
                f"<b>Mobile:</b> {student.father_mobile}<br/>"
                f"<b>Aadhaar:</b> {student.father_aadhaar}",
                styles["Normal"]
            ),
            pdf_image(student.mother_photo, 1.0*inch, 1.0*inch),
            Paragraph(
                f"<b>Mother Name:</b> {student.mother_name}<br/>"
                f"<b>Mobile:</b> {student.mother_mobile}<br/>"
                f"<b>Aadhaar:</b> {student.mother_aadhaar}",
                styles["Normal"]
            ),
        ]
    ], colWidths=[80, 170, 80, 170])

    family_table.setStyle(TableStyle([
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('ALIGN', (0,0), (0,-1), 'CENTER'),
        ('ALIGN', (2,0), (2,-1), 'CENTER'),
    ]))

    elements.append(family_table)
    elements.append(Spacer(1, 16))

    # ================= SERVICES =================
    elements.append(section_title("School Services"))

    services = Table([
        ["Service", "Status"],
        ["Transport", "Granted" if student.transport_required else "Not Granted"],
        ["Hostel", "Granted" if student.hostel_required else "Not Granted"]
    ], colWidths=[250, 250])

    style_table(services)

    elements.append(services)

    # ================= DECLARATION =================
    elements.append(Spacer(1, 15))

    elements.append(Paragraph(
        "I hereby declare that the above information is true and correct. "
        "Any false information may lead to cancellation of admission.",
        ParagraphStyle(
            name="declaration",
            fontSize=9.5,
            leading=11
        )
    ))

    elements.append(Spacer(1, 50))

    # ================= SIGNATURE =================
    sign = Table([
        ["Signature of Guardian", "", "Signature of Principal"]
    ], colWidths=[200, 100, 200])

    sign.setStyle(TableStyle([
        ('LINEABOVE', (0,0), (0,0), 0.5, colors.black),
        ('LINEABOVE', (2,0), (2,0), 0.5, colors.black),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONT', (0,0), (-1,-1), 'Helvetica', 9),
        ('TOPPADDING', (0,0), (-1,-1), 12),
    ]))

    elements.append(sign)

    # ================= BUILD PDF =================
    pdf.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Admission_Receipt_{student.admission_no}.pdf",
        mimetype="application/pdf"
    )

    