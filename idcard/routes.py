import io
import os
import base64
from flask import Blueprint, render_template, request, send_file, current_app
from flask_login import login_required, current_user
from extensions import db
from models.student import Student
from models.school import School

from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle,
    Spacer, Image as RLImage, HRFlowable
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader

idcard_bp = Blueprint('idcard', __name__, url_prefix='/id-card')

# ─────────────────────────────────────────────
# HELPER: get school logo path
# ─────────────────────────────────────────────
def get_logo_path(school):
    if school.logo:
        return os.path.join(current_app.config['UPLOAD_FOLDER'], school.logo)
    return None

def get_photo_path(student):
    if student.photo:
        return os.path.join(current_app.config['UPLOAD_FOLDER'], student.photo)
    return None


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────
@idcard_bp.route('/')
@login_required
def dashboard():
    school = School.query.get_or_404(current_user.school_id)
    total_students = Student.query.filter_by(school_id=current_user.school_id).count()
    classes = db.session.query(Student.student_class).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.student_class).all()
    classes = [c[0] for c in classes]
    return render_template('idcard/dashboard.html',
                           school=school,
                           total_students=total_students,
                           classes=classes)


# ─────────────────────────────────────────────
# STUDENT SEARCH + LIST
# ─────────────────────────────────────────────
@idcard_bp.route('/students')
@login_required
def student_search():
    school = School.query.get_or_404(current_user.school_id)
    q = request.args.get('q', '').strip()
    cls = request.args.get('class', '').strip()
    section = request.args.get('section', '').strip()
    template_no = request.args.get('template', '1')

    query = Student.query.filter_by(school_id=current_user.school_id)

    if q:
        query = query.filter(
            db.or_(
                Student.first_name.ilike(f'%{q}%'),
                Student.last_name.ilike(f'%{q}%'),
                Student.admission_no.ilike(f'%{q}%')
            )
        )
    if cls:
        query = query.filter_by(student_class=cls)
    if section:
        query = query.filter_by(section=section)

    students = query.order_by(Student.student_class, Student.section, Student.first_name).all()

    # Distinct classes & sections for filter dropdowns
    all_classes = db.session.query(Student.student_class).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.student_class).all()
    all_classes = [c[0] for c in all_classes]

    return render_template('idcard/student_search.html',
                           students=students,
                           school=school,
                           all_classes=all_classes,
                           template_no=template_no)


# ─────────────────────────────────────────────
# SINGLE STUDENT ID CARD PDF
# ─────────────────────────────────────────────
@idcard_bp.route('/student/<int:student_id>/pdf')
@login_required
def single_idcard_pdf(student_id):
    student = Student.query.get_or_404(student_id)
    school = School.query.get_or_404(current_user.school_id)
    template_no = request.args.get('template', '1')
    return generate_pdf([student], school, template_no)


# ─────────────────────────────────────────────
# BULK ID CARD PDF
# ─────────────────────────────────────────────
@idcard_bp.route('/bulk/pdf', methods=['POST'])
@login_required
def bulk_idcard_pdf():
    student_ids = request.form.getlist('student_ids')
    template_no = request.form.get('template', '1')

    if not student_ids:
        # If no selection → all filtered students
        cls = request.form.get('class', '')
        section = request.form.get('section', '')
        query = Student.query.filter_by(school_id=current_user.school_id)
        if cls:
            query = query.filter_by(student_class=cls)
        if section:
            query = query.filter_by(section=section)
        students = query.all()
    else:
        students = Student.query.filter(
            Student.id.in_(student_ids),
            Student.school_id == current_user.school_id
        ).all()

    school = School.query.get_or_404(current_user.school_id)
    return generate_pdf(students, school, template_no)


# ─────────────────────────────────────────────
# PREVIEW (HTML) - for browser print
# ─────────────────────────────────────────────
@idcard_bp.route('/preview/<int:student_id>')
@login_required
def preview_card(student_id):
    student = Student.query.get_or_404(student_id)
    school = School.query.get_or_404(current_user.school_id)
    template_no = request.args.get('template', '1')
    template_map = {
        '1': 'idcard/templates/template_1.html',
        '2': 'idcard/templates/template_2.html',
        '3': 'idcard/templates/template_3.html',
        '4': 'idcard/templates/template_4.html',
        '5': 'idcard/templates/template_5.html',
    }
    tmpl = template_map.get(template_no, 'idcard/templates/template_1.html')
    return render_template(tmpl, student=student, school=school)


# ─────────────────────────────────────────────
# BULK PRINT PAGE (HTML, browser print)
# ─────────────────────────────────────────────
@idcard_bp.route('/bulk/print', methods=['POST'])
@login_required
def bulk_print():
    student_ids = request.form.getlist('student_ids')
    template_no = request.form.get('template', '1')

    students = Student.query.filter(
        Student.id.in_(student_ids),
        Student.school_id == current_user.school_id
    ).all()

    school = School.query.get_or_404(current_user.school_id)

    template_map = {
        '1': 'idcard/templates/template_1.html',
        '2': 'idcard/templates/template_2.html',
        '3': 'idcard/templates/template_3.html',
        '4': 'idcard/templates/template_4.html',
        '5': 'idcard/templates/template_5.html',
    }
    tmpl = template_map.get(template_no, 'idcard/templates/template_1.html')
    return render_template('idcard/bulk_print.html',
                           students=students,
                           school=school,
                           card_template=tmpl)


# ═══════════════════════════════════════════════════════════
# PDF GENERATION ENGINE - 5 TEMPLATES
# ═══════════════════════════════════════════════════════════

CR80 = (85.6 * mm, 53.98 * mm)   # Horizontal card
CR80_V = (53.98 * mm, 85.6 * mm) # Vertical card


def generate_pdf(students, school, template_no='1'):
    buffer = io.BytesIO()

    generators = {
        '1': gen_template_1,
        '2': gen_template_2,
        '3': gen_template_3,
        '4': gen_template_4,
        '5': gen_template_5,
    }
    gen_fn = generators.get(template_no, gen_template_1)

    # For canvas-based templates (3,4,5)
    if template_no in ('3', '4', '5'):
        gen_fn(buffer, students, school)
    else:
        # Platypus-based (1, 2)
        gen_fn(buffer, students, school)

    buffer.seek(0)
    filename = f"idcards_template{template_no}.pdf"
    return send_file(buffer, as_attachment=True, download_name=filename,
                     mimetype='application/pdf')


# ─────────────────────────────────────────────
# TEMPLATE 1 – Horizontal Classic Blue
# ─────────────────────────────────────────────
def gen_template_1(buffer, students, school):
    """Horizontal CR80, blue header, photo left, details right"""
    from reportlab.pdfgen import canvas as cv

    c = cv.Canvas(buffer, pagesize=CR80)
    W, H = CR80
    logo_path = get_logo_path(school)

    for i, student in enumerate(students):
        if i > 0:
            c.showPage()

        # Background
        c.setFillColorRGB(0.10, 0.28, 0.60)
        c.rect(0, H - 18*mm, W, 18*mm, fill=1, stroke=0)

        # School name
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 7)
        name = school.school_name.upper()
        c.drawCentredString(W/2, H - 8*mm, name)
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(W/2, H - 13*mm, f"{school.city} | Ph: {school.phone}")

        # Logo
        if logo_path and os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, 3*mm, H - 16*mm, 12*mm, 12*mm,
                           preserveAspectRatio=True, mask='auto')
            except:
                pass

        # Photo box
        photo_path = get_photo_path(student)
        c.setFillColorRGB(0.88, 0.88, 0.88)
        c.rect(4*mm, 8*mm, 22*mm, 26*mm, fill=1, stroke=0)
        if photo_path and os.path.exists(photo_path):
            try:
                c.drawImage(photo_path, 4*mm, 8*mm, 22*mm, 26*mm,
                           preserveAspectRatio=False, mask='auto')
            except:
                pass
        else:
            c.setFillColorRGB(0.6, 0.6, 0.6)
            c.setFont("Helvetica", 6)
            c.drawCentredString(15*mm, 20*mm, "Photo")

        # Student details
        full_name = " ".join(filter(None, [
            student.first_name, getattr(student, 'middle_name', None), student.last_name
        ]))

        rows = [
            ("Name", full_name),
            ("Class", f"{student.student_class} - {student.section}"),
            ("Adm No", student.admission_no),
            ("DOB", str(getattr(student, 'dob', 'N/A') or 'N/A')),
            ("Session", str(getattr(student, 'session', '') or '')),
        ]

        c.setFont("Helvetica-Bold", 6)
        c.setFillColorRGB(0, 0, 0)
        y = H - 24*mm
        for label, val in rows:
            c.setFont("Helvetica-Bold", 5.8)
            c.setFillColorRGB(0.10, 0.28, 0.60)
            c.drawString(30*mm, y, f"{label}:")
            c.setFont("Helvetica", 5.8)
            c.setFillColorRGB(0.1, 0.1, 0.1)
            c.drawString(46*mm, y, str(val)[:20])
            y -= 5*mm

        # Footer
        c.setFillColorRGB(0.10, 0.28, 0.60)
        c.rect(0, 0, W, 6*mm, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 5)
        c.drawString(4*mm, 2*mm, "Principal Sign: _______________")
        c.drawRightString(W - 4*mm, 2*mm, "Class Teacher: ___________")

    c.save()


# ─────────────────────────────────────────────
# TEMPLATE 2 – Vertical Green Modern
# ─────────────────────────────────────────────
def gen_template_2(buffer, students, school):
    """Vertical CR80, green accent, centered photo"""
    from reportlab.pdfgen import canvas as cv

    c = cv.Canvas(buffer, pagesize=CR80_V)
    W, H = CR80_V
    logo_path = get_logo_path(school)

    for i, student in enumerate(students):
        if i > 0:
            c.showPage()

        # Top green band
        c.setFillColorRGB(0.05, 0.60, 0.35)
        c.rect(0, H - 22*mm, W, 22*mm, fill=1, stroke=0)

        # Logo
        if logo_path and os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, 3*mm, H - 14*mm, 10*mm, 10*mm,
                           preserveAspectRatio=True, mask='auto')
            except:
                pass

        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 7.5)
        c.drawCentredString(W/2, H - 9*mm, school.school_name.upper())
        c.setFont("Helvetica", 5.5)
        c.drawCentredString(W/2, H - 14*mm, school.city)

        # ID label
        c.setFillColorRGB(0.05, 0.60, 0.35)
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(W/2, H - 25*mm, "STUDENT IDENTITY CARD")

        # Photo
        photo_x = (W - 22*mm) / 2
        photo_y = H - 50*mm
        c.setFillColorRGB(0.88, 0.95, 0.90)
        c.roundRect(photo_x - 1*mm, photo_y - 1*mm, 24*mm, 24*mm, 2*mm, fill=1, stroke=0)
        c.setFillColorRGB(0.05, 0.60, 0.35)
        c.roundRect(photo_x - 1*mm, photo_y - 1*mm, 24*mm, 24*mm, 2*mm, fill=0, stroke=1)

        photo_path = get_photo_path(student)
        if photo_path and os.path.exists(photo_path):
            try:
                c.drawImage(photo_path, photo_x, photo_y, 22*mm, 22*mm,
                           preserveAspectRatio=False, mask='auto')
            except:
                pass

        # Details
        full_name = " ".join(filter(None, [
            student.first_name, getattr(student, 'middle_name', None), student.last_name
        ]))

        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(0.05, 0.40, 0.25)
        c.drawCentredString(W/2, H - 57*mm, full_name[:22])

        details = [
            ("Class", f"{student.student_class} - {student.section}"),
            ("Adm No", student.admission_no),
            ("DOB", str(getattr(student, 'dob', '') or '')),
        ]

        y = H - 63*mm
        for label, val in details:
            # Divider line
            c.setStrokeColorRGB(0.8, 0.9, 0.85)
            c.line(5*mm, y + 3*mm, W - 5*mm, y + 3*mm)
            c.setFont("Helvetica-Bold", 5.5)
            c.setFillColorRGB(0.05, 0.60, 0.35)
            c.drawString(5*mm, y, label)
            c.setFont("Helvetica", 5.5)
            c.setFillColorRGB(0.2, 0.2, 0.2)
            c.drawRightString(W - 5*mm, y, str(val)[:20])
            y -= 7*mm

        # Bottom
        c.setFillColorRGB(0.05, 0.60, 0.35)
        c.rect(0, 0, W, 8*mm, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 5)
        c.drawCentredString(W/2, 3*mm, "Principal Signature: _______________")

    c.save()


# ─────────────────────────────────────────────
# TEMPLATE 3 – Horizontal Red Premium
# ─────────────────────────────────────────────
def gen_template_3(buffer, students, school):
    """Horizontal, red+gold, premium look"""
    from reportlab.pdfgen import canvas as cv

    c = cv.Canvas(buffer, pagesize=CR80)
    W, H = CR80
    logo_path = get_logo_path(school)

    for i, student in enumerate(students):
        if i > 0:
            c.showPage()

        # Background gradient sim
        c.setFillColorRGB(0.95, 0.95, 0.95)
        c.rect(0, 0, W, H, fill=1, stroke=0)

        # Red left strip
        c.setFillColorRGB(0.75, 0.08, 0.08)
        c.rect(0, 0, 28*mm, H, fill=1, stroke=0)

        # Gold top line
        c.setFillColorRGB(0.85, 0.65, 0.10)
        c.rect(0, H - 1.5*mm, W, 1.5*mm, fill=1, stroke=0)
        c.rect(0, 0, W, 1.5*mm, fill=1, stroke=0)

        # School name on red strip (vertical)
        c.saveState()
        c.translate(7*mm, H/2)
        c.rotate(90)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawCentredString(0, 0, school.school_name.upper()[:25])
        c.restoreState()

        # Logo on red
        if logo_path and os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, 4*mm, H - 16*mm, 20*mm, 12*mm,
                           preserveAspectRatio=True, mask='auto')
            except:
                pass

        # Photo
        photo_path = get_photo_path(student)
        c.setFillColorRGB(1, 1, 1)
        c.rect(5*mm, 8*mm, 18*mm, 22*mm, fill=1, stroke=0)
        c.setStrokeColorRGB(0.85, 0.65, 0.10)
        c.setLineWidth(1)
        c.rect(5*mm, 8*mm, 18*mm, 22*mm, fill=0, stroke=1)

        if photo_path and os.path.exists(photo_path):
            try:
                c.drawImage(photo_path, 5*mm, 8*mm, 18*mm, 22*mm,
                           preserveAspectRatio=False, mask='auto')
            except:
                pass

        # Details
        full_name = " ".join(filter(None, [
            student.first_name, getattr(student, 'middle_name', None), student.last_name
        ]))

        c.setFillColorRGB(0.75, 0.08, 0.08)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(31*mm, H - 10*mm, full_name[:18])

        c.setFillColorRGB(0.85, 0.65, 0.10)
        c.rect(30*mm, H - 13*mm, W - 32*mm, 0.5*mm, fill=1, stroke=0)

        rows = [
            ("Class", f"{student.student_class} - {student.section}"),
            ("Adm No", student.admission_no),
            ("DOB", str(getattr(student, 'dob', '') or '')),
            ("Session", str(getattr(student, 'session', '') or '')),
        ]

        y = H - 18*mm
        for label, val in rows:
            c.setFont("Helvetica-Bold", 5.5)
            c.setFillColorRGB(0.75, 0.08, 0.08)
            c.drawString(31*mm, y, f"{label}:")
            c.setFont("Helvetica", 5.5)
            c.setFillColorRGB(0.2, 0.2, 0.2)
            c.drawString(48*mm, y, str(val)[:18])
            y -= 5.5*mm

        # Sign line
        c.setStrokeColorRGB(0.4, 0.4, 0.4)
        c.line(31*mm, 5*mm, W - 4*mm, 5*mm)
        c.setFont("Helvetica", 4.5)
        c.setFillColorRGB(0.4, 0.4, 0.4)
        c.drawCentredString((31*mm + W - 4*mm)/2, 2*mm, "Authorised Signature")

    c.save()


# ─────────────────────────────────────────────
# TEMPLATE 4 – Vertical Dark (Night Mode)
# ─────────────────────────────────────────────
def gen_template_4(buffer, students, school):
    """Vertical dark theme, modern minimal"""
    from reportlab.pdfgen import canvas as cv

    c = cv.Canvas(buffer, pagesize=CR80_V)
    W, H = CR80_V
    logo_path = get_logo_path(school)

    for i, student in enumerate(students):
        if i > 0:
            c.showPage()

        # Dark background
        c.setFillColorRGB(0.10, 0.10, 0.15)
        c.rect(0, 0, W, H, fill=1, stroke=0)

        # Cyan accent top
        c.setFillColorRGB(0.0, 0.75, 0.85)
        c.rect(0, H - 1.5*mm, W, 1.5*mm, fill=1, stroke=0)
        c.rect(0, 0, W, 1.5*mm, fill=1, stroke=0)

        # Header band
        c.setFillColorRGB(0.15, 0.15, 0.22)
        c.rect(0, H - 20*mm, W, 20*mm, fill=1, stroke=0)

        # Logo
        if logo_path and os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, 3*mm, H - 15*mm, 11*mm, 11*mm,
                           preserveAspectRatio=True, mask='auto')
            except:
                pass

        c.setFillColorRGB(0.0, 0.75, 0.85)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(16*mm, H - 9*mm, school.school_name.upper()[:20])
        c.setFillColorRGB(0.6, 0.6, 0.7)
        c.setFont("Helvetica", 5.5)
        c.drawString(16*mm, H - 14*mm, school.city)

        # STUDENT ID label
        c.setFillColorRGB(0.0, 0.75, 0.85)
        c.setFont("Helvetica-Bold", 5.5)
        c.drawCentredString(W/2, H - 23*mm, "◆  STUDENT IDENTITY CARD  ◆")

        # Photo circle/rounded
        photo_x = (W - 24*mm) / 2
        photo_y = H - 50*mm
        c.setFillColorRGB(0.2, 0.2, 0.28)
        c.roundRect(photo_x - 1*mm, photo_y - 1*mm, 26*mm, 26*mm, 3*mm, fill=1, stroke=0)
        c.setStrokeColorRGB(0.0, 0.75, 0.85)
        c.setLineWidth(0.8)
        c.roundRect(photo_x - 1*mm, photo_y - 1*mm, 26*mm, 26*mm, 3*mm, fill=0, stroke=1)

        photo_path = get_photo_path(student)
        if photo_path and os.path.exists(photo_path):
            try:
                c.drawImage(photo_path, photo_x, photo_y, 24*mm, 24*mm,
                           preserveAspectRatio=False, mask='auto')
            except:
                pass

        # Name
        full_name = " ".join(filter(None, [
            student.first_name, getattr(student, 'middle_name', None), student.last_name
        ]))
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 8)
        c.drawCentredString(W/2, H - 56*mm, full_name[:22])

        # Details
        details = [
            ("CLASS", f"{student.student_class} - {student.section}"),
            ("ADM NO", student.admission_no),
            ("DOB", str(getattr(student, 'dob', '') or '')),
        ]

        y = H - 64*mm
        for label, val in details:
            # Subtle line
            c.setStrokeColorRGB(0.25, 0.25, 0.35)
            c.setLineWidth(0.3)
            c.line(4*mm, y + 3.5*mm, W - 4*mm, y + 3.5*mm)

            c.setFillColorRGB(0.0, 0.75, 0.85)
            c.setFont("Helvetica-Bold", 5)
            c.drawString(4*mm, y, label)
            c.setFillColorRGB(0.85, 0.85, 0.95)
            c.setFont("Helvetica", 5.5)
            c.drawRightString(W - 4*mm, y, str(val)[:20])
            y -= 7*mm

        # Bottom
        c.setFillColorRGB(0.15, 0.15, 0.22)
        c.rect(0, 0, W, 9*mm, fill=1, stroke=0)
        c.setFillColorRGB(0.6, 0.6, 0.7)
        c.setFont("Helvetica", 4.5)
        c.drawCentredString(W/2, 3.5*mm, "Principal Signature: _______________")

    c.save()


# ─────────────────────────────────────────────
# TEMPLATE 5 – Horizontal Gradient Purple
# ─────────────────────────────────────────────
def gen_template_5(buffer, students, school):
    """Horizontal, purple gradient, bold modern style"""
    from reportlab.pdfgen import canvas as cv

    c = cv.Canvas(buffer, pagesize=CR80)
    W, H = CR80
    logo_path = get_logo_path(school)

    for i, student in enumerate(students):
        if i > 0:
            c.showPage()

        # White base
        c.setFillColorRGB(0.98, 0.97, 1.0)
        c.rect(0, 0, W, H, fill=1, stroke=0)

        # Purple diagonal block
        from reportlab.graphics.shapes import Polygon
        p = c.beginPath()
        p.moveTo(0, H)
        p.lineTo(40*mm, H)
        p.lineTo(24*mm, 0)
        p.lineTo(0, 0)
        p.close()
        c.setFillColorRGB(0.38, 0.12, 0.65)
        c.drawPath(p, fill=1, stroke=0)

        # Accent diagonal
        p2 = c.beginPath()
        p2.moveTo(40*mm, H)
        p2.lineTo(43*mm, H)
        p2.lineTo(27*mm, 0)
        p2.lineTo(24*mm, 0)
        p2.close()
        c.setFillColorRGB(0.78, 0.50, 1.0)
        c.drawPath(p2, fill=1, stroke=0)

        # School name on purple
        c.saveState()
        c.translate(8*mm, H/2)
        c.rotate(90)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 6)
        c.drawCentredString(0, 0, school.school_name.upper()[:22])
        c.restoreState()

        # Logo
        if logo_path and os.path.exists(logo_path):
            try:
                c.drawImage(logo_path, 2*mm, H - 15*mm, 14*mm, 11*mm,
                           preserveAspectRatio=True, mask='auto')
            except:
                pass

        # Photo
        photo_path = get_photo_path(student)
        c.setFillColorRGB(0.85, 0.80, 0.95)
        c.roundRect(47*mm, 8*mm, 20*mm, 24*mm, 2*mm, fill=1, stroke=0)
        c.setStrokeColorRGB(0.38, 0.12, 0.65)
        c.setLineWidth(0.8)
        c.roundRect(47*mm, 8*mm, 20*mm, 24*mm, 2*mm, fill=0, stroke=1)

        if photo_path and os.path.exists(photo_path):
            try:
                c.drawImage(photo_path, 47*mm, 8*mm, 20*mm, 24*mm,
                           preserveAspectRatio=False, mask='auto')
            except:
                pass

        # Student info
        full_name = " ".join(filter(None, [
            student.first_name, getattr(student, 'middle_name', None), student.last_name
        ]))

        c.setFillColorRGB(0.38, 0.12, 0.65)
        c.setFont("Helvetica-Bold", 8)
        # Truncate long names
        c.drawString(45*mm, H - 10*mm, full_name[:16])

        # Thin purple rule
        c.setFillColorRGB(0.78, 0.50, 1.0)
        c.rect(45*mm, H - 12.5*mm, W - 47*mm, 0.8*mm, fill=1, stroke=0)

        rows = [
            ("Class", f"{student.student_class} - {student.section}"),
            ("Adm No", student.admission_no),
            ("DOB", str(getattr(student, 'dob', '') or '')),
        ]

        y = H - 18*mm
        for label, val in rows:
            c.setFont("Helvetica-Bold", 5.5)
            c.setFillColorRGB(0.38, 0.12, 0.65)
            c.drawString(45*mm, y, f"{label}:")
            c.setFont("Helvetica", 5.5)
            c.setFillColorRGB(0.2, 0.2, 0.2)
            c.drawString(58*mm, y, str(val)[:12])
            y -= 5.5*mm

        # Bottom strip
        c.setFillColorRGB(0.38, 0.12, 0.65)
        c.rect(0, 0, W, 5*mm, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica", 4.5)
        c.drawString(45*mm, 1.5*mm, "Sign: _________________________")

    c.save()