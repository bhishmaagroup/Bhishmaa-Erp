import os
import io
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from extensions import db
from models.school import School
from models.student import Student
from models.tc import TransferCertificate
from reportlab.platypus import Flowable, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors

tc_bp = Blueprint('tc', __name__, url_prefix='/tc')


def date_to_words_only(d):
    if not d:
        return ""
    day_words = {
        1: "FIRST", 2: "SECOND", 3: "THIRD", 4: "FOURTH", 5: "FIFTH",
        6: "SIXTH", 7: "SEVENTH", 8: "EIGHTH", 9: "NINTH", 10: "TENTH",
        11: "ELEVENTH", 12: "TWELFTH", 13: "THIRTEENTH", 14: "FOURTEENTH",
        15: "FIFTEENTH", 16: "SIXTEENTH", 17: "SEVENTEENTH", 18: "EIGHTEENTH",
        19: "NINETEENTH", 20: "TWENTIETH", 21: "TWENTY FIRST", 22: "TWENTY SECOND",
        23: "TWENTY THIRD", 24: "TWENTY FOURTH", 25: "TWENTY FIFTH", 26: "TWENTY SIXTH",
        27: "TWENTY SEVENTH", 28: "TWENTY EIGHTH", 29: "TWENTY NINTH", 30: "THIRTIETH",
        31: "THIRTY FIRST"
    }
    month_words = {
        1: "JANUARY", 2: "FEBRUARY", 3: "MARCH", 4: "APRIL", 5: "MAY", 6: "JUNE",
        7: "JULY", 8: "AUGUST", 9: "SEPTEMBER", 10: "OCTOBER", 11: "NOVEMBER", 12: "DECEMBER"
    }
    day_str = day_words.get(d.day, "")
    month_str = month_words.get(d.month, "")
    try:
        from num2words import num2words
        year_str = num2words(d.year).upper().replace("-", " ")
    except Exception:
        year_str = str(d.year)
    return f"{day_str} {month_str} {year_str}"


def format_class_in_words(class_name):
    class_name_upper = str(class_name).strip().upper()
    roman_to_words = {
        "I": "FIRST", "II": "SECOND", "III": "THIRD", "IV": "FOURTH", "V": "FIFTH",
        "VI": "SIXTH", "VII": "SEVENTH", "VIII": "EIGHTH", "IX": "NINTH", "X": "TENTH",
        "XI": "ELEVENTH", "XII": "TWELFTH"
    }
    num_to_roman = {
        "1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI",
        "7": "VII", "8": "VIII", "9": "IX", "10": "X", "11": "XI", "12": "XII"
    }
    
    roman = num_to_roman.get(class_name_upper, class_name_upper)
    word = roman_to_words.get(roman, "")
    
    if word:
        return f"CLASS {roman} ({word})"
    else:
        return f"CLASS {class_name_upper}"


@tc_bp.route('/')
@login_required
def list_tcs():
    tcs = TransferCertificate.query.filter_by(school_id=current_user.school_id).order_by(TransferCertificate.issue_date.desc()).all()
    return render_template('tc/list.html', tcs=tcs)


@tc_bp.route('/issue', methods=['GET', 'POST'])
@login_required
def issue_tc():
    students = Student.query.filter_by(school_id=current_user.school_id).order_by(Student.first_name).all()
    
    for s in students:
        s.dob_words_str = date_to_words_only(s.dob) if s.dob else ""
        s.class_words_str = format_class_in_words(s.student_class) if s.student_class else ""
        
        # Fetch allocated subjects
        subjects = [alloc.subject.subject_name.upper() for alloc in s.subject_allocations if alloc.subject]
        if not subjects:
            subjects = ["ENGLISH", "HINDI", "MATHEMATICS", "SCIENCE", "SOCIAL SCIENCE", "SANSKRIT", "COMPUTER"]
        s.subjects_str = ", ".join(subjects)

    if request.method == 'POST':
        student_id = request.form.get('student_id')
        leave_date_str = request.form.get('leave_date')
        application_date_str = request.form.get('application_date')
        reason = request.form.get('reason_for_leaving')
        conduct = request.form.get('conduct', 'Good')
        academic_status = request.form.get('academic_status')
        fee_status = request.form.get('fee_status', 'All Dues Cleared')
        remarks = request.form.get('remarks')
        
        nationality = request.form.get('nationality', 'INDIAN')
        caste_category = request.form.get('caste_category', 'GENERAL')
        birth_words = request.form.get('birth_words')
        class_in_words = request.form.get('class_in_words')
        last_exam_result = request.form.get('last_exam_result')
        whether_failed = request.form.get('whether_failed', 'NO')
        subjects_studied = request.form.get('subjects_studied')
        promotion_status = request.form.get('promotion_status', 'YES')
        dues_paid_upto = request.form.get('dues_paid_upto')
        fee_concession = request.form.get('fee_concession', 'NO')
        total_working_days = int(request.form.get('total_working_days', 220) or 220)
        days_present = int(request.form.get('days_present', 198) or 198)
        ncc_scout_guide = request.form.get('ncc_scout_guide', 'NO')

        if not student_id or not leave_date_str:
            flash("Student and Leaving Date are required", "danger")
            return redirect(url_for('tc.issue_tc'))

        student = Student.query.filter_by(id=student_id, school_id=current_user.school_id).first_or_404()
        
        # Check if already issued
        existing = TransferCertificate.query.filter_by(student_id=student.id, school_id=current_user.school_id).first()
        if existing:
            flash(f"TC already issued for {student.first_name} {student.last_name} with serial {existing.tc_number}!", "warning")
            return redirect(url_for('tc.list_tcs'))

        # Auto TC Serial
        year = datetime.utcnow().year
        count = TransferCertificate.query.filter_by(school_id=current_user.school_id).count()
        tc_number = f"TC/{year}/{count + 1:04d}"

        # Parse dates
        leave_date = datetime.strptime(leave_date_str, "%Y-%m-%d").date() if leave_date_str else None
        application_date = datetime.strptime(application_date_str, "%Y-%m-%d").date() if application_date_str else datetime.utcnow().date()

        tc = TransferCertificate(
            school_id=current_user.school_id,
            student_id=student.id,
            tc_number=tc_number,
            admission_date=student.created_at, # Student creation date as admission date
            leave_date=leave_date,
            reason_for_leaving=reason,
            conduct=conduct,
            academic_status=academic_status,
            fee_status=fee_status,
            remarks=remarks,
            nationality=nationality,
            caste_category=caste_category,
            birth_words=birth_words,
            class_in_words=class_in_words,
            last_exam_result=last_exam_result,
            whether_failed=whether_failed,
            subjects_studied=subjects_studied,
            promotion_status=promotion_status,
            dues_paid_upto=dues_paid_upto,
            fee_concession=fee_concession,
            total_working_days=total_working_days,
            days_present=days_present,
            ncc_scout_guide=ncc_scout_guide,
            application_date=application_date
        )
        db.session.add(tc)
        db.session.commit()
        flash("Transfer Certificate issued successfully!", "success")
        return redirect(url_for('tc.list_tcs'))

    return render_template('tc/issue.html', students=students)


class OrnateDivider(Flowable):
    def __init__(self, width, height=12):
        Flowable.__init__(self)
        self.width = width
        self.height = height
    def draw(self):
        self.canv.saveState()
        self.canv.setStrokeColor(colors.HexColor("#d4af37"))
        self.canv.setLineWidth(0.8)
        y = self.height / 2.0
        # Draw elegant double ornament line
        self.canv.line(30, y - 1, self.width - 30, y - 1)
        self.canv.line(30, y + 1, self.width - 30, y + 1)
        # Center decoration
        self.canv.setFillColor(colors.HexColor("#d4af37"))
        self.canv.circle(self.width / 2.0, y, 2.5, fill=True, stroke=True)
        self.canv.circle(self.width / 2.0 - 12, y, 1.2, fill=True, stroke=True)
        self.canv.circle(self.width / 2.0 + 12, y, 1.2, fill=True, stroke=True)
        self.canv.restoreState()


class RoundedTextBox(Flowable):
    def __init__(self, width, height, title, value, title_color=colors.HexColor("#555555"), value_color=colors.HexColor("#a91b22")):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.title = title
        self.value = value
        self.title_color = title_color
        self.value_color = value_color
    def draw(self):
        self.canv.saveState()
        self.canv.setStrokeColor(colors.HexColor("#a0a0a0"))
        self.canv.setLineWidth(0.75)
        self.canv.roundRect(0, 0, self.width, self.height, 4, stroke=True, fill=False)
        
        # Title text (top half)
        self.canv.setFont("Helvetica-Bold", 7)
        self.canv.setFillColor(self.title_color)
        self.canv.drawCentredString(self.width / 2.0, self.height - 10, self.title.upper())
        
        # Divider line
        self.canv.setStrokeColor(colors.HexColor("#dddddd"))
        self.canv.setLineWidth(0.5)
        self.canv.line(0, self.height - 14, self.width, self.height - 14)
        
        # Value text (bottom half)
        self.canv.setFont("Helvetica-Bold", 8)
        self.canv.setFillColor(self.value_color)
        self.canv.drawCentredString(self.width / 2.0, 4, str(self.value))
        self.canv.restoreState()


class CertificateTitleBar(Flowable):
    def __init__(self, width, height, text, bg_color=colors.HexColor("#0f2a4a"), text_color=colors.white, border_color=colors.HexColor("#d4af37")):
        Flowable.__init__(self)
        self.width = width
        self.height = height
        self.text = text
        self.bg_color = bg_color
        self.text_color = text_color
        self.border_color = border_color
    def draw(self):
        self.canv.saveState()
        bar_width = self.width - 160
        bar_x = 80
        
        # Main bar
        self.canv.setFillColor(self.bg_color)
        self.canv.setStrokeColor(self.border_color)
        self.canv.setLineWidth(1.5)
        self.canv.roundRect(bar_x, 0, bar_width, self.height, 3, fill=True, stroke=True)
        
        # Title text
        self.canv.setFont("Helvetica-Bold", 11.5)
        self.canv.setFillColor(self.text_color)
        self.canv.drawCentredString(self.width / 2.0, (self.height - 8) / 2.0 + 1, self.text)
        
        # Ornate wings
        self.canv.setStrokeColor(self.border_color)
        self.canv.setLineWidth(0.8)
        # Left Wing
        self.canv.line(30, self.height / 2.0, bar_x - 10, self.height / 2.0)
        self.canv.circle(30, self.height / 2.0, 1.8, fill=True, stroke=True)
        self.canv.line(40, self.height / 2.0 - 2, bar_x - 15, self.height / 2.0 - 2)
        # Right Wing
        self.canv.line(bar_x + bar_width + 10, self.height / 2.0, self.width - 30, self.height / 2.0)
        self.canv.circle(self.width - 30, self.height / 2.0, 1.8, fill=True, stroke=True)
        self.canv.line(bar_x + bar_width + 15, self.height / 2.0 - 2, self.width - 40, self.height / 2.0 - 2)
        
        self.canv.restoreState()


class RoundedDeclarationBox(Flowable):
    def __init__(self, width, text, bg_color=colors.HexColor("#f4f5f6"), border_color=colors.HexColor("#dcdde1")):
        Flowable.__init__(self)
        self.width = width
        self.text = text
        self.bg_color = bg_color
        self.border_color = border_color
        self.style = ParagraphStyle(
            name="TCDeclBoxText",
            fontName="Helvetica",
            fontSize=8,
            leading=11,
            alignment=1, # Centered
            textColor=colors.HexColor("#2f3640")
        )
        self.p = Paragraph(self.text, self.style)
    def wrap(self, availWidth, availHeight):
        w, h = self.p.wrap(self.width - 20, availHeight)
        self.height = h + 10
        return self.width, self.height
    def draw(self):
        self.canv.saveState()
        self.canv.setFillColor(self.bg_color)
        self.canv.setStrokeColor(self.border_color)
        self.canv.setLineWidth(0.6)
        self.canv.roundRect(0, 0, self.width, self.height, 4, fill=True, stroke=True)
        self.canv.restoreState()
        self.p.drawOn(self.canv, 10, 5)


# GoldStamp class removed as requested


def draw_page_decorations(canvas, doc):
    school = doc.school
    canvas.saveState()
    
    # 1. Page background (faint cream color)
    canvas.setFillColor(colors.HexColor("#fdfcf7"))
    canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=True, stroke=False)
    
    # 2. Outer border (Navy blue)
    canvas.setStrokeColor(colors.HexColor("#0f2a4a"))
    canvas.setLineWidth(1.5)
    canvas.rect(20, 20, doc.pagesize[0] - 40, doc.pagesize[1] - 40)
    
    # 3. Inner border (Gold)
    canvas.setStrokeColor(colors.HexColor("#d4af37"))
    canvas.setLineWidth(0.6)
    canvas.rect(23, 23, doc.pagesize[0] - 46, doc.pagesize[1] - 46)
    
    # 4. Corner Ornaments (Gold & Navy)
    corners = [
        (23, 23, 1, 1),
        (doc.pagesize[0] - 23, 23, -1, 1),
        (23, doc.pagesize[1] - 23, 1, -1),
        (doc.pagesize[0] - 23, doc.pagesize[1] - 23, -1, -1)
    ]
    for cx, cy, dx, dy in corners:
        canvas.setStrokeColor(colors.HexColor("#d4af37"))
        canvas.setLineWidth(0.8)
        canvas.line(cx, cy, cx + dx * 16, cy)
        canvas.line(cx, cy, cx, cy + dy * 16)
        canvas.line(cx + dx * 4, cy + dy * 4, cx + dx * 20, cy + dy * 4)
        canvas.line(cx + dx * 4, cy + dy * 4, cx + dx * 4, cy + dy * 20)
        canvas.circle(cx + dx * 4, cy + dy * 4, 1.2, fill=True, stroke=True)
        
    # 5. Watermark School Logo
    logo_path = None
    if school.logo:
        p = os.path.join(current_app.config['UPLOAD_FOLDER'], school.logo)
        if os.path.exists(p):
            logo_path = p
                
    if logo_path:
        canvas.saveState()
        canvas.setFillAlpha(0.04)
        canvas.setStrokeAlpha(0.04)
        canvas.drawImage(
            logo_path,
            doc.pagesize[0]/2.0 - 130,
            doc.pagesize[1]/2.0 - 130,
            width=260,
            height=260,
            mask='auto'
        )
        canvas.restoreState()
        
    canvas.restoreState()


@tc_bp.route('/<int:tc_id>/pdf')
@login_required
def tc_pdf(tc_id):
    tc = TransferCertificate.query.filter_by(id=tc_id, school_id=current_user.school_id).first_or_404()
    student = tc.student
    school = School.query.get_or_404(current_user.school_id)

    # Build ReportLab PDF
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Flowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics.barcode.qr import QrCodeWidget

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=35,
        leftMargin=35,
        topMargin=35,
        bottomMargin=35
    )
    doc.school = school

    elements = []

    # 1. School Logo image
    logo_cell = ""
    if school.logo:
        logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], school.logo)
        if os.path.exists(logo_path):
            try:
                from reportlab.platypus import Image as RLImage
                logo_cell = RLImage(logo_path, width=60, height=60)
            except:
                pass
    if not logo_cell:
        logo_cell = Spacer(60, 60)

    # 2. Center Text (School details)
    school_name_style = ParagraphStyle(
        name="SchoolName",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=17,
        alignment=1,
        textColor=colors.HexColor("#0f2a4a")
    )
    school_sub_style = ParagraphStyle(
        name="SchoolSub",
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=10,
        alignment=1,
        textColor=colors.HexColor("#0f2a4a")
    )
    school_info_style = ParagraphStyle(
        name="SchoolInfo",
        fontName="Helvetica",
        fontSize=7,
        leading=9.5,
        alignment=1,
        textColor=colors.HexColor("#444444")
    )

    school_block = [
        Paragraph(school.school_name.upper(), school_name_style),
        Spacer(1, 1),
        Paragraph("AFFILIATED TO CBSE" if school.affiliation_no else "", school_sub_style),
        Paragraph(f"Affiliation No.: {school.affiliation_no or 'N/A'} | School Code: {school.school_code or 'N/A'}", school_sub_style),
        Spacer(1, 1),
        Paragraph(f"{school.address or ''}, {school.city or ''}, {school.state or ''} - {school.pincode or ''}", school_info_style),
        Paragraph(f"Phone: {school.phone or ''} | Email: {school.email or ''} | Website: {school.website or ''}", school_info_style)
    ]

    # 3. Right side rounded boxes (TC No and Admission No)
    right_boxes = [
        RoundedTextBox(110, 26, "TC No.", tc.tc_number),
        Spacer(1, 4),
        RoundedTextBox(110, 26, "Admission No.", student.admission_no)
    ]

    # Header Table
    header_table = Table(
        [[logo_cell, school_block, right_boxes]],
        colWidths=[65, doc.width - 180, 115]
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 6))

    # Decorative Ornament Divider
    elements.append(OrnateDivider(doc.width))
    elements.append(Spacer(1, 6))

    # Main Title Bar "TRANSFER CERTIFICATE"
    elements.append(CertificateTitleBar(doc.width, 18, "TRANSFER CERTIFICATE"))
    elements.append(Spacer(1, 4))

    # Under title text
    under_title_style = ParagraphStyle(
        name="TCUnderTitle",
        fontName="Helvetica-Oblique",
        fontSize=7,
        alignment=1,
        textColor=colors.HexColor("#0f2a4a")
    )
    elements.append(Paragraph("(ISSUED UNDER RULE 13(1) OF THE EDUCATION RULES)", under_title_style))
    elements.append(Spacer(1, 10))

    # 20 Fields Table
    lbl_style = ParagraphStyle(
        name="TCLbl",
        fontName="Helvetica",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#333333")
    )
    val_style = ParagraphStyle(
        name="TCVal",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#111111")
    )

    pupil_name = f"{student.first_name} {student.middle_name or ''} {student.last_name or ''}".strip().upper()
    
    father_name = student.father_name or student.guardian_name or "N/A"
    father_name = father_name.upper()
    if not father_name.startswith("MR"):
        father_name = f"MR. {father_name}"
        
    mother_name = student.mother_name or "N/A"
    mother_name = mother_name.upper()
    if not mother_name.startswith("MRS") and not mother_name.startswith("MR"):
        mother_name = f"MRS. {mother_name}"
        
    nationality = tc.nationality.upper() if tc.nationality else "INDIAN"
    caste_cat = tc.caste_category.upper() if tc.caste_category else "GENERAL"
    
    dob_val = ""
    if student.dob:
        dob_words_str = tc.birth_words.upper() if tc.birth_words else date_to_words_only(student.dob).upper()
        dob_val = f"{student.dob.strftime('%d/%m/%Y')} ({dob_words_str})"
    else:
        dob_val = "N/A"
        
    class_last = tc.class_in_words.upper() if tc.class_in_words else format_class_in_words(student.student_class).upper()
    exam_result = tc.last_exam_result.upper() if tc.last_exam_result else tc.academic_status.upper()
    failed_val = tc.whether_failed.upper() if tc.whether_failed else "NO"
    subjects_val = tc.subjects_studied.upper() if tc.subjects_studied else "ENGLISH, HINDI, MATHEMATICS, SCIENCE, SOCIAL SCIENCE, SANSKRIT, COMPUTER"
    promoted_val = tc.promotion_status.upper() if tc.promotion_status else "YES"
    dues_paid = tc.dues_paid_upto.upper() if tc.dues_paid_upto else "MARCH"
    concession_val = tc.fee_concession.upper() if tc.fee_concession else "NO"
    working_days = str(tc.total_working_days or 220)
    days_pres = str(tc.days_present or 198)
    ncc_val = tc.ncc_scout_guide.upper() if tc.ncc_scout_guide else "NO"
    
    app_date_val = tc.application_date.strftime('%d/%m/%Y') if tc.application_date else tc.issue_date.strftime('%d/%m/%Y')
    issue_date_val = tc.issue_date.strftime('%d/%m/%Y')
    reason_val = tc.reason_for_leaving.upper() if tc.reason_for_leaving else "PARENTS' TRANSFER"
    remarks_val = tc.remarks.upper() if tc.remarks else "GOOD CONDUCT"

    fields_list = [
        ("Name of Pupil", pupil_name),
        ("Father's / Guardian's Name", father_name),
        ("Mother's Name", mother_name),
        ("Nationality", nationality),
        ("Whether the candidate belongs to SC / ST / OBC / General", caste_cat),
        ("Date of Birth (in Christian Era) according to Admission & Withdrawal Register", dob_val),
        ("Class in which the pupil last studied (in words)", class_last),
        ("School / Board Annual Examination last taken with result", exam_result),
        ("Whether failed, if so once / twice in the same class", failed_val),
        ("Subject Studied", subjects_val),
        ("Whether qualified for promotion to the higher class", promoted_val),
        ("Month upto which the pupil has paid school dues", dues_paid),
        ("Any fee concession availed of : if so, the nature of such concession", concession_val),
        ("Total No. of working days in the academic session", working_days),
        ("Total No. of working days pupil present in the academic session", days_pres),
        ("Whether NCC Cadet / Boy Scout / Girl Guide (details may be given)", ncc_val),
        ("Date of application for certificate", app_date_val),
        ("Date of issue of certificate", issue_date_val),
        ("Reason for leaving the school", reason_val),
        ("Any other remarks", remarks_val)
    ]

    details_data = [
        [
            Paragraph(f"<b>{i+1}.</b> {label}", lbl_style),
            Paragraph("<b>:</b>", lbl_style),
            Paragraph(f"<b>{value}</b>", val_style)
        ]
        for i, (label, value) in enumerate(fields_list)
    ]

    details_table = Table(details_data, colWidths=[265, 10, doc.width - 275])
    details_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(details_table)
    elements.append(Spacer(1, 10))

    # Declaration note box
    declaration_text = (
        "Certified that the above information including Name, Father's Name, Mother's Name "
        "and Date of Birth furnished above is correct as per school records."
    )
    elements.append(RoundedDeclarationBox(doc.width, declaration_text))
    elements.append(Spacer(1, 10))

    # Bottom elements (Stamp, QR Code, Signatures)
    # QR Code drawing
    qr_url = f"{request.host_url}verify/tc/{tc.tc_number}"
    qr_code = QrCodeWidget(qr_url)
    bounds = qr_code.getBounds()
    qr_w = bounds[2] - bounds[0]
    qr_h = bounds[3] - bounds[1]
    
    qr_drawing = Drawing(44, 44, transform=[44.0/qr_w, 0, 0, 44.0/qr_h, 0, 0])
    qr_drawing.add(qr_code)

    qr_text_style = ParagraphStyle(
        name="TCQrText",
        fontName="Helvetica",
        fontSize=5.5,
        leading=7,
        alignment=1,
        textColor=colors.HexColor("#555555")
    )
    qr_link_style = ParagraphStyle(
        name="TCQrLink",
        fontName="Helvetica-Bold",
        fontSize=6,
        leading=7.5,
        alignment=1,
        textColor=colors.HexColor("#0f2a4a")
    )
    
    domain = school.website or request.host
    qr_col = [
        qr_drawing,
        Spacer(1, 3),
        Paragraph("For verification, scan QR code or visit", qr_text_style),
        Paragraph(f"{domain}/verify" if domain else "", qr_link_style)
    ]

    # Signature column
    sig_line_style = ParagraphStyle(
        name="TCSigLine",
        fontName="Helvetica",
        fontSize=6.5,
        leading=8,
        alignment=1,
        textColor=colors.HexColor("#666666")
    )
    sig_title_style = ParagraphStyle(
        name="TCSigTitle",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=9.5,
        alignment=1,
        textColor=colors.HexColor("#0f2a4a")
    )
    
    sig_image_cell = ""
    # Optional Principal Signature image load
    sig_path = os.path.join(current_app.config['UPLOAD_FOLDER'], "signature.png")
    if not os.path.exists(sig_path):
        sig_path = os.path.join("static", "logo", "signature.png")
    if os.path.exists(sig_path):
        try:
            from reportlab.platypus import Image as RLImage
            sig_image_cell = RLImage(sig_path, width=70, height=20)
        except:
            pass

    sig_col = [
        sig_image_cell if sig_image_cell else Spacer(1, 20),
        Spacer(1, 1),
        Table([[""]], colWidths=[120], style=TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#888888"))])),
        Spacer(1, 3),
        Paragraph("PRINCIPAL", sig_title_style),
        Paragraph("(Signature with School Seal)", sig_line_style)
    ]

    footer_table = Table(
        [["", qr_col, sig_col]],
        colWidths=[140, doc.width - 280, 140]
    )
    footer_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(footer_table)
    elements.append(Spacer(1, 8))

    # Date and Place Footer
    date_place_style = ParagraphStyle(
        name="TCDatePlace",
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#333333")
    )
    place_parts = []
    if school.city:
        place_parts.append(school.city)
    if school.state:
        place_parts.append(school.state)
    place_str = ", ".join(place_parts)

    date_place_table = Table([
        [
            Paragraph(f"Date : {tc.issue_date.strftime('%d/%m/%Y')}", date_place_style),
            Paragraph(f"Place : {place_str}", ParagraphStyle(name="TCPlace", parent=date_place_style, alignment=2))
        ]
    ], colWidths=[doc.width/2.0, doc.width/2.0])
    date_place_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    elements.append(date_place_table)

    # Build the document
    doc.build(elements, onFirstPage=draw_page_decorations)
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"TransferCertificate_{student.admission_no}.pdf",
        mimetype="application/pdf"
    )
