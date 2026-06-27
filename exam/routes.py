import os
import io
from datetime import datetime, date, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, current_app
from flask_login import login_required, current_user
from extensions import db
from models.school import School
from models.student import Student
from models.subject import Subject
from models.teacher import Teacher
from models.holiday import Holiday
from models.attendance import StudentAttendance
from models.exam import Exam, ExamSubject, ExamMark, ExamResult, ClassTimetable

exam = Blueprint('exam', __name__, url_prefix='/exam')

# ==========================================
# HELPERS
# ==========================================
def get_grade_for_percentage(percent):
    if percent >= 91: return "A1"
    elif percent >= 81: return "A2"
    elif percent >= 71: return "B1"
    elif percent >= 61: return "B2"
    elif percent >= 51: return "C1"
    elif percent >= 41: return "C2"
    elif percent >= 33: return "D"
    else: return "F"

# ==========================================
# EXAM ROUTES
# ==========================================
@exam.route('/')
@login_required
def list_exams():
    exams = Exam.query.filter_by(school_id=current_user.school_id).order_by(Exam.created_at.desc()).all()
    # Distinct classes for the forms
    classes = db.session.query(Student.student_class).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.student_class).all()
    classes = [c[0] for c in classes if c[0]]

    sections = db.session.query(Student.section).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.section).all()
    sections = [s[0] for s in sections if s[0]]

    return render_template('exam/list.html', exams=exams, classes=classes, sections=sections)


@exam.route('/add', methods=['POST'])
@login_required
def add_exam():
    exam_name = request.form.get('exam_name')
    session = request.form.get('session')
    description = request.form.get('description')

    if not exam_name or not session:
        flash("Exam Name and Session are required", "danger")
        return redirect(url_for('exam.list_exams'))

    new_exam = Exam(
        school_id=current_user.school_id,
        exam_name=exam_name,
        session=session,
        description=description
    )
    db.session.add(new_exam)
    db.session.commit()
    flash("Exam created successfully!", "success")
    return redirect(url_for('exam.list_exams'))


@exam.route('/<int:exam_id>')
@login_required
def view_exam(exam_id):
    exam_obj = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    
    # Get all timetable entries
    timetable = ExamSubject.query.filter_by(exam_id=exam_obj.id, school_id=current_user.school_id).order_by(ExamSubject.exam_date).all()
    
    # Get distinct classes scheduled
    scheduled_classes = db.session.query(Subject.class_name, Subject.section).join(
        ExamSubject, ExamSubject.subject_id == Subject.id
    ).filter(ExamSubject.exam_id == exam_obj.id).distinct().all()

    # Get results if calculated
    results = ExamResult.query.filter_by(exam_id=exam_obj.id, school_id=current_user.school_id).all()

    return render_template(
        'exam/view.html',
        exam=exam_obj,
        timetable=timetable,
        scheduled_classes=scheduled_classes,
        results_count=len(results)
    )


@exam.route('/<int:exam_id>/delete', methods=['POST'])
@login_required
def delete_exam(exam_id):
    exam_obj = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    db.session.delete(exam_obj)
    db.session.commit()
    flash("Exam deleted successfully", "success")
    return redirect(url_for('exam.list_exams'))


# ==========================================
# AUTO EXAM TIMETABLE ROUTE
# ==========================================
@exam.route('/<int:exam_id>/auto-schedule', methods=['POST'])
@login_required
def auto_schedule(exam_id):
    exam_obj = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    
    class_name = request.form.get('class_name')
    section = request.form.get('section')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')  # Optional constraint
    start_time = request.form.get('start_time', '10:00 AM')
    end_time = request.form.get('end_time', '01:00 PM')
    max_marks = int(request.form.get('max_marks', 100))
    min_marks = int(request.form.get('min_marks', 33))

    if not class_name or not section or not start_date_str:
        flash("Class, Section, and Start Date are required", "danger")
        return redirect(url_for('exam.view_exam', exam_id=exam_id))

    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date() if end_date_str else None

    # Fetch subjects assigned to class
    subjects = Subject.query.filter_by(
        school_id=current_user.school_id,
        class_name=class_name,
        section=section
    ).all()

    if not subjects:
        flash("No subjects found assigned to this Class and Section.", "danger")
        return redirect(url_for('exam.view_exam', exam_id=exam_id))

    # Fetch school holidays
    holidays = Holiday.query.filter_by(school_id=current_user.school_id).all()
    holiday_dates = {h.holiday_date for h in holidays}

    # Delete existing schedules for this specific class and exam first
    existing_entries = ExamSubject.query.filter_by(exam_id=exam_obj.id, school_id=current_user.school_id).join(Subject).filter(
        Subject.class_name == class_name,
        Subject.section == section
    ).all()
    
    for entry in existing_entries:
        db.session.delete(entry)

    # Schedule subjects
    current_date = start_date
    scheduled_entries = []

    for sub in subjects:
        # Find next valid day (skipping Sundays and holidays)
        while True:
            # Check Sunday (weekday == 6 in Python date)
            if current_date.weekday() == 6:
                current_date += timedelta(days=1)
                continue
            # Check Holiday
            if current_date in holiday_dates:
                current_date += timedelta(days=1)
                continue
            break

        # Check end date constraint
        if end_date and current_date > end_date:
            db.session.rollback()
            flash("Validation Error: Insufficient dates to schedule all subjects before end date.", "danger")
            return redirect(url_for('exam.view_exam', exam_id=exam_id))

        es = ExamSubject(
            school_id=current_user.school_id,
            exam_id=exam_obj.id,
            subject_id=sub.id,
            exam_date=current_date,
            start_time=start_time,
            end_time=end_time,
            max_marks=max_marks,
            min_marks=min_marks
        )
        db.session.add(es)
        scheduled_entries.append(es)
        current_date += timedelta(days=1)

    db.session.commit()
    flash(f"Successfully auto-scheduled {len(scheduled_entries)} subjects for {class_name} - {section}!", "success")
    return redirect(url_for('exam.view_exam', exam_id=exam_id))


# ==========================================
# BULK MARKS ENTRY ROUTES
# ==========================================
@exam.route('/marks/bulk', methods=['GET', 'POST'])
@login_required
def bulk_marks():
    classes = db.session.query(Student.student_class).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.student_class).all()
    classes = [c[0] for c in classes if c[0]]

    sections = db.session.query(Student.section).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.section).all()
    sections = [s[0] for s in sections if s[0]]

    exams = Exam.query.filter_by(school_id=current_user.school_id).order_by(Exam.created_at.desc()).all()
    
    # If selected class, section, subject and exam
    exam_id = request.args.get('exam_id')
    class_name = request.args.get('class_name')
    section = request.args.get('section')
    subject_id = request.args.get('subject_id')

    students = []
    subject_obj = None
    exam_subject_obj = None
    subjects_list = []

    if class_name and section:
        # Load subjects list for dropdown
        subjects_list = Subject.query.filter_by(
            school_id=current_user.school_id,
            class_name=class_name,
            section=section
        ).all()

    if exam_id and class_name and section and subject_id:
        subject_obj = Subject.query.filter_by(id=subject_id, school_id=current_user.school_id).first_or_404()
        exam_subject_obj = ExamSubject.query.filter_by(
            exam_id=exam_id,
            subject_id=subject_id,
            school_id=current_user.school_id
        ).first()

        if not exam_subject_obj:
            flash("Selected subject is not scheduled in this exam's timetable.", "warning")
        else:
            students = Student.query.filter_by(
                school_id=current_user.school_id,
                student_class=class_name,
                section=section
            ).order_by(Student.first_name).all()

            # Pre-load existing marks
            existing_marks = ExamMark.query.filter_by(
                exam_id=exam_id,
                subject_id=subject_id,
                school_id=current_user.school_id
            ).all()
            marks_dict = {m.student_id: m for m in existing_marks}
            
            for s in students:
                s.mark_rec = marks_dict.get(s.id)

    # Post processing bulk save
    if request.method == 'POST':
        post_exam_id = request.form.get('post_exam_id')
        post_subject_id = request.form.get('post_subject_id')
        post_class = request.form.get('post_class')
        post_section = request.form.get('post_section')

        students_list = Student.query.filter_by(
            school_id=current_user.school_id,
            student_class=post_class,
            section=post_section
        ).all()

        try:
            for s in students_list:
                marks_val = request.form.get(f'marks_{s.id}')
                is_absent = request.form.get(f'absent_{s.id}') == '1'

                mark_rec = ExamMark.query.filter_by(
                    exam_id=post_exam_id,
                    subject_id=post_subject_id,
                    student_id=s.id,
                    school_id=current_user.school_id
                ).first()

                if not mark_rec:
                    mark_rec = ExamMark(
                        school_id=current_user.school_id,
                        exam_id=post_exam_id,
                        subject_id=post_subject_id,
                        student_id=s.id
                    )
                    db.session.add(mark_rec)

                mark_rec.is_absent = is_absent
                if is_absent:
                    mark_rec.marks_obtained = 0.0
                else:
                    mark_rec.marks_obtained = float(marks_val) if marks_val else 0.0

            db.session.commit()
            flash("Marks updated successfully!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error saving marks: {str(e)}", "danger")

        return redirect(url_for('exam.bulk_marks', exam_id=post_exam_id, class_name=post_class, section=post_section, subject_id=post_subject_id))

    return render_template(
        'exam/marks_bulk.html',
        exams=exams,
        classes=classes,
        sections=sections,
        subjects_list=subjects_list,
        students=students,
        subject_obj=subject_obj,
        exam_subject_obj=exam_subject_obj,
        selected_exam_id=exam_id,
        selected_class=class_name,
        selected_section=section,
        selected_subject_id=subject_id
    )


# ==========================================
# RESULT CALCULATION ROUTE
# ==========================================
@exam.route('/<int:exam_id>/calculate-results', methods=['POST'])
@login_required
def calculate_results(exam_id):
    exam_obj = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    class_name = request.form.get('class_name')
    section = request.form.get('section')

    if not class_name or not section:
        flash("Class and Section are required for calculation", "danger")
        return redirect(url_for('exam.view_exam', exam_id=exam_id))

    # Fetch students
    students = Student.query.filter_by(
        school_id=current_user.school_id,
        student_class=class_name,
        section=section
    ).all()

    # Get exam subjects for class
    exam_subjects = ExamSubject.query.filter_by(exam_id=exam_obj.id, school_id=current_user.school_id).join(Subject).filter(
        Subject.class_name == class_name,
        Subject.section == section
    ).all()

    if not exam_subjects:
        flash("No subjects scheduled for this exam and class.", "danger")
        return redirect(url_for('exam.view_exam', exam_id=exam_id))

    try:
        # Delete existing results for the target parameters in transaction
        existing_results = ExamResult.query.filter_by(exam_id=exam_obj.id, school_id=current_user.school_id).join(Student).filter(
            Student.student_class == class_name,
            Student.section == section
        ).all()
        for r in existing_results:
            db.session.delete(r)

        student_scores = []
        for s in students:
            # Query student marks
            marks = ExamMark.query.filter_by(exam_id=exam_obj.id, student_id=s.id, school_id=current_user.school_id).all()
            marks_dict = {m.subject_id: m for m in marks}

            total_max = 0.0
            total_obtained = 0.0
            failed_count = 0

            for es in exam_subjects:
                total_max += es.max_marks
                mark_rec = marks_dict.get(es.subject_id)
                if mark_rec:
                    if not mark_rec.is_absent:
                        total_obtained += mark_rec.marks_obtained
                        if mark_rec.marks_obtained < es.min_marks:
                            failed_count += 1
                    else:
                        failed_count += 1
                else:
                    failed_count += 1  # No marks record = Failed

            percent = (total_obtained / total_max * 100) if total_max > 0 else 0
            grade = get_grade_for_percentage(percent)
            
            # Status CBSE pattern
            if failed_count == 0:
                status = "Pass"
            elif failed_count <= 2:
                status = "Compartment"
            else:
                status = "Fail"

            student_scores.append({
                'student_id': s.id,
                'total_marks': total_max,
                'obtained_marks': total_obtained,
                'percentage': percent,
                'grade': grade,
                'status': status
            })

        # Rank logic based on percentage descending
        student_scores.sort(key=lambda x: x['percentage'], reverse=True)
        for index, sc in enumerate(student_scores):
            res = ExamResult(
                school_id=current_user.school_id,
                exam_id=exam_obj.id,
                student_id=sc['student_id'],
                total_marks=sc['total_marks'],
                obtained_marks=sc['obtained_marks'],
                percentage=round(sc['percentage'], 2),
                grade=sc['grade'],
                rank=index + 1,
                result_status=sc['status']
            )
            db.session.add(res)

        db.session.commit()
        flash("Results and Ranks calculated successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error calculating results: {str(e)}", "danger")

    return redirect(url_for('exam.view_exam', exam_id=exam_id))


# ==========================================
# REPORT CARD PDF GENERATION
# ==========================================
@exam.route('/report-card/<int:exam_id>/<int:student_id>/pdf')
@login_required
def report_card_pdf(exam_id, student_id):
    student = Student.query.filter_by(id=student_id, school_id=current_user.school_id).first_or_404()
    exam_obj = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    school = School.query.get_or_404(current_user.school_id)

    # Fetch results
    result_obj = ExamResult.query.filter_by(
        exam_id=exam_id,
        student_id=student_id,
        school_id=current_user.school_id
    ).first()

    if not result_obj:
        flash("Results not calculated for this student yet. Calculate class results first.", "warning")
        return redirect(url_for('exam.view_exam', exam_id=exam_id))

    # Fetch marks and details
    exam_subjects = ExamSubject.query.filter_by(exam_id=exam_id, school_id=current_user.school_id).join(Subject).filter(
        Subject.class_name == student.student_class,
        Subject.section == student.section
    ).all()

    marks = ExamMark.query.filter_by(exam_id=exam_id, student_id=student.id, school_id=current_user.school_id).all()
    marks_dict = {m.subject_id: m for m in marks}

    # Fetch attendance
    attendance_records = StudentAttendance.query.filter_by(
        student_id=student.id,
        school_id=current_user.school_id
    ).all()
    total_days = len(attendance_records)
    present_days = sum(1 for r in attendance_records if r.status == 'P')
    attendance_pct = round((present_days / total_days * 100), 2) if total_days > 0 else 0.0

    # Build ReportLab PDF
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=25,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        name="RepTitle",
        fontName="Helvetica-Bold",
        fontSize=14,
        alignment=1, # Center
        spaceAfter=15
    )
    school_header_style = ParagraphStyle(
        name="RepSchool",
        fontName="Helvetica-Bold",
        fontSize=12,
        alignment=1,
        spaceAfter=4
    )
    school_sub_style = ParagraphStyle(
        name="RepSubSchool",
        fontName="Helvetica",
        fontSize=9,
        alignment=1,
        spaceAfter=15
    )
    body_style = ParagraphStyle(
        name="RepBody",
        fontName="Helvetica",
        fontSize=10,
        spaceAfter=6
    )
    bold_body_style = ParagraphStyle(
        name="RepBoldBody",
        fontName="Helvetica-Bold",
        fontSize=10,
        spaceAfter=6
    )

    elements = []

    # Top strip
    elements.append(Table([[""]], colWidths=[doc.width], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#0e2fa3")),
        ("ROWHEIGHT", (0, 0), (-1, -1), 8),
    ])))
    elements.append(Spacer(1, 10))

    # Header section with Logo
    logo_cell = ""
    if school.logo:
        logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], school.logo)
        if os.path.exists(logo_path):
            try:
                from reportlab.platypus import Image as RLImage
                logo_cell = RLImage(logo_path, width=65, height=65)
            except:
                pass

    school_block = (
        f"<b>{school.school_name.upper()}</b><br/>"
        f"{school.address or ''}, {school.city or ''}, {school.state or ''} – {school.pincode or ''}<br/>"
        f"Phone: {school.phone or ''} | Email: {school.email or ''}"
    )
    
    header_table = Table(
        [[logo_cell, Paragraph(school_block, school_header_style)]],
        colWidths=[80, doc.width - 80]
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 15))

    # Report Title
    elements.append(Paragraph(f"<b>PROGRESS REPORT CARD</b><br/><font size=10>Session: {exam_obj.session} | {exam_obj.exam_name.upper()}</font>", title_style))
    elements.append(Spacer(1, 10))

    # Student Details Box
    stud_data = [
        [Paragraph("<b>Student Name:</b>", body_style), Paragraph(f"{student.first_name} {student.last_name}", body_style),
         Paragraph("<b>Admission No:</b>", body_style), Paragraph(student.admission_no, body_style)],
        [Paragraph("<b>Class:</b>", body_style), Paragraph(student.student_class, body_style),
         Paragraph("<b>Section:</b>", body_style), Paragraph(student.section, body_style)],
        [Paragraph("<b>Date of Birth:</b>", body_style), Paragraph(str(student.dob or 'N/A'), body_style),
         Paragraph("<b>Father's Name:</b>", body_style), Paragraph(student.father_name or 'N/A', body_style)]
    ]
    stud_table = Table(stud_data, colWidths=[90, doc.width/2 - 90, 95, doc.width/2 - 95])
    stud_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#ccc")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8f9fa")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    elements.append(stud_table)
    elements.append(Spacer(1, 20))

    # Marks Grid
    marks_header = [
        Paragraph("<b>Subject Code</b>", bold_body_style),
        Paragraph("<b>Subject Name</b>", bold_body_style),
        Paragraph("<b>Max Marks</b>", bold_body_style),
        Paragraph("<b>Min Marks</b>", bold_body_style),
        Paragraph("<b>Obtained Marks</b>", bold_body_style),
        Paragraph("<b>Grade</b>", bold_body_style),
        Paragraph("<b>Remarks</b>", bold_body_style)
    ]
    marks_table_data = [marks_header]

    for es in exam_subjects:
        m_rec = marks_dict.get(es.subject_id)
        if m_rec:
            if m_rec.is_absent:
                obt = "AB"
                grd = "F"
                rem = "Absent"
            else:
                obt = str(m_rec.marks_obtained)
                grd = get_grade_for_percentage((m_rec.marks_obtained / es.max_marks * 100) if es.max_marks > 0 else 0)
                rem = "Pass" if m_rec.marks_obtained >= es.min_marks else "Fail"
        else:
            obt = "-"
            grd = "-"
            rem = "No record"

        marks_table_data.append([
            Paragraph(es.subject.subject_code or "-", body_style),
            Paragraph(es.subject.subject_name, body_style),
            Paragraph(str(es.max_marks), body_style),
            Paragraph(str(es.min_marks), body_style),
            Paragraph(obt, body_style),
            Paragraph(grd, body_style),
            Paragraph(rem, body_style)
        ])

    marks_grid = Table(marks_table_data, colWidths=[80, doc.width - 340, 60, 60, 60, 40, 40])
    marks_grid.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#777")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f3f7")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(marks_grid)
    elements.append(Spacer(1, 20))

    # Summary Stats & Attendance Box
    summary_data = [
        [Paragraph("<b>Total Maximum Marks:</b>", body_style), Paragraph(str(result_obj.total_marks), body_style),
         Paragraph("<b>Obtained Marks:</b>", body_style), Paragraph(str(result_obj.obtained_marks), body_style)],
        [Paragraph("<b>Percentage:</b>", body_style), Paragraph(f"{result_obj.percentage}%", body_style),
         Paragraph("<b>Class Rank:</b>", body_style), Paragraph(f"{result_obj.rank} / {len(ExamResult.query.filter_by(exam_id=exam_id, school_id=current_user.school_id).all())}", body_style)],
        [Paragraph("<b>Attendance:</b>", body_style), Paragraph(f"{present_days} / {total_days} ({attendance_pct}%)", body_style),
         Paragraph("<b>Result Status:</b>", bold_body_style), Paragraph(f"<b>{result_obj.result_status}</b>", bold_body_style)]
    ]
    summary_table = Table(summary_data, colWidths=[130, doc.width/2 - 130, 120, doc.width/2 - 120])
    summary_table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#0e2fa3")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0f4ff")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 40))

    # Signature Block
    sig_data = [
        ["Class Teacher Signature", "Exam Controller Signature", "Principal Signature"],
        ["", "", ""],  # Spacer for physical signature
        ["_________________________", "_________________________", "_________________________"]
    ]
    sig_table = Table(sig_data, colWidths=[doc.width/3, doc.width/3, doc.width/3])
    sig_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 25),
    ]))
    elements.append(sig_table)

    doc.build(elements)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"ReportCard_{student.admission_no}.pdf",
        mimetype="application/pdf"
    )


# ==========================================
# HALL TICKET PDF GENERATION
# ==========================================
@exam.route('/hall-ticket/<int:exam_id>/<int:student_id>/pdf')
@login_required
def hall_ticket_pdf(exam_id, student_id):
    student = Student.query.filter_by(id=student_id, school_id=current_user.school_id).first_or_404()
    exam_obj = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    school = School.query.get_or_404(current_user.school_id)

    # Get exam subjects for class
    exam_subjects = ExamSubject.query.filter_by(exam_id=exam_id, school_id=current_user.school_id).join(Subject).filter(
        Subject.class_name == student.student_class,
        Subject.section == student.section
    ).order_by(ExamSubject.exam_date).all()

    if not exam_subjects:
        flash("No exam timetable scheduled for this class.", "warning")
        return redirect(url_for('exam.view_exam', exam_id=exam_id))

    # Build ReportLab PDF
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=45,
        leftMargin=45,
        topMargin=30,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        name="HTTitle",
        fontName="Helvetica-Bold",
        fontSize=12,
        alignment=1,
        spaceAfter=15
    )
    school_title_style = ParagraphStyle(
        name="HTSchool",
        fontName="Helvetica-Bold",
        fontSize=12,
        alignment=1,
        spaceAfter=4
    )
    body_style = ParagraphStyle(
        name="HTBody",
        fontName="Helvetica",
        fontSize=9.5,
        spaceAfter=5
    )
    rule_style = ParagraphStyle(
        name="HTRule",
        fontName="Helvetica",
        fontSize=8,
        spaceAfter=4,
        textColor=colors.HexColor("#555")
    )

    elements = []

    # Card border container simulation by Table
    card_elements = []

    # School Details with Logo
    logo_cell = ""
    if school.logo:
        logo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], school.logo)
        if os.path.exists(logo_path):
            try:
                from reportlab.platypus import Image as RLImage
                logo_cell = RLImage(logo_path, width=50, height=50)
            except:
                pass

    school_block = (
        f"<b>{school.school_name.upper()}</b><br/>"
        f"Phone: {school.phone or ''} | Email: {school.email or ''}"
    )
    header_table = Table(
        [[logo_cell, Paragraph(school_block, school_title_style)]],
        colWidths=[70, doc.width - 90]
    )
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "CENTER"),
    ]))
    card_elements.append(header_table)
    card_elements.append(Spacer(1, 10))

    # Hall Ticket Title
    card_elements.append(Paragraph(f"<b>EXAMINATION ADMIT CARD / HALL TICKET</b><br/>Session: {exam_obj.session} | {exam_obj.exam_name.upper()}", title_style))
    card_elements.append(Spacer(1, 10))

    # Student Image & Details
    photo_cell = ""
    if student.student_photo:
        photo_path = os.path.join(current_app.config['UPLOAD_FOLDER'], student.student_photo)
        if os.path.exists(photo_path):
            try:
                from reportlab.platypus import Image as RLImage
                photo_cell = RLImage(photo_path, width=70, height=85)
            except:
                pass
    if not photo_cell:
        # Placeholder box for photo
        photo_cell = Table([["Photo"]], colWidths=[70], rowHeights=[85], style=TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#777")),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
        ]))

    stud_info = [
        [Paragraph("<b>Candidate Name:</b>", body_style), Paragraph(f"{student.first_name} {student.last_name}", body_style)],
        [Paragraph("<b>Admission No:</b>", body_style), Paragraph(student.admission_no, body_style)],
        [Paragraph("<b>Class / Section:</b>", body_style), Paragraph(f"{student.student_class} - {student.section}", body_style)],
        [Paragraph("<b>Father's Name:</b>", body_style), Paragraph(student.father_name or 'N/A', body_style)]
    ]
    stud_info_table = Table(stud_info, colWidths=[110, doc.width - 210])
    stud_info_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    info_photo_table = Table([[stud_info_table, photo_cell]], colWidths=[doc.width - 90, 80])
    info_photo_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    card_elements.append(info_photo_table)
    card_elements.append(Spacer(1, 15))

    # Timetable Header & List
    tt_header = [
        Paragraph("<b>Subject Code</b>", body_style),
        Paragraph("<b>Subject Name</b>", body_style),
        Paragraph("<b>Exam Date</b>", body_style),
        Paragraph("<b>Timing</b>", body_style),
        Paragraph("<b>Invigilator Sign</b>", body_style)
    ]
    tt_data = [tt_header]
    for es in exam_subjects:
        tt_data.append([
            Paragraph(es.subject.subject_code or "-", body_style),
            Paragraph(es.subject.subject_name, body_style),
            Paragraph(es.exam_date.strftime("%d/%m/%Y"), body_style),
            Paragraph(f"{es.start_time} - {es.end_time}", body_style),
            Paragraph("", body_style)
        ])

    tt_table = Table(tt_data, colWidths=[70, doc.width - 320, 80, 110, 60])
    tt_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#555")),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f8f9fa")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (2, 0), (3, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
    ]))
    card_elements.append(tt_table)
    card_elements.append(Spacer(1, 15))

    # Instructions Block
    card_elements.append(Paragraph("<b>CANDIDATE INSTRUCTIONS:</b>", body_style))
    card_elements.append(Paragraph("1. Candidates must carry this admit card to the examination hall.", rule_style))
    card_elements.append(Paragraph("2. Please report to the examination center at least 15 minutes before exam start.", rule_style))
    card_elements.append(Paragraph("3. Electronic devices, mobile phones, or smartwatches are strictly prohibited.", rule_style))
    card_elements.append(Paragraph("4. Any candidate using unfair means will be summarily disqualified.", rule_style))
    card_elements.append(Spacer(1, 20))

    # Signatures
    sig_data = [
        ["_________________________", "_________________________"],
        ["Candidate Signature", "Principal / Controller Signature"]
    ]
    sig_table = Table(sig_data, colWidths=[doc.width/2 - 10, doc.width/2 - 10])
    sig_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
    ]))
    card_elements.append(sig_table)

    # Wrap inside double border A4 page
    card_box = Table([[card_elements]], colWidths=[doc.width - 10])
    card_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 2, colors.HexColor("#0e2fa3")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#ffc107")),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
        ("TOPPADDING", (0, 0), (-1, -1), 15),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 15),
    ]))

    elements.append(card_box)
    doc.build(elements)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"HallTicket_{student.admission_no}.pdf",
        mimetype="application/pdf"
    )


# ==========================================
# CLASS TIMETABLE ROUTES
# ==========================================
@exam.route('/timetable/class', methods=['GET', 'POST'])
@login_required
def class_timetable():
    # Load distinct class & sections
    classes = db.session.query(Student.student_class).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.student_class).all()
    classes = [c[0] for c in classes if c[0]]

    sections = db.session.query(Student.section).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.section).all()
    sections = [s[0] for s in sections if s[0]]

    # Filters
    selected_class = request.args.get('class_name')
    selected_section = request.args.get('section')

    timetable_matrix = {}
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    periods = list(range(1, 9)) # 8 periods a day

    subjects = []
    teachers = []

    if selected_class and selected_section:
        subjects = Subject.query.filter_by(
            school_id=current_user.school_id,
            class_name=selected_class,
            section=selected_section
        ).all()
        
        teachers = Teacher.query.filter_by(
            school_id=current_user.school_id,
            is_active=True
        ).all()

        # Query existing period matrix
        records = ClassTimetable.query.filter_by(
            school_id=current_user.school_id,
            class_name=selected_class,
            section=selected_section
        ).all()

        # Build lookup dict: (day, period) -> record
        matrix_lookup = {(r.day_of_week, r.period_no): r for r in records}
        
        for d in days:
            timetable_matrix[d] = {}
            for p in periods:
                timetable_matrix[d][p] = matrix_lookup.get((d, p))

    # Save Class Period mapping
    if request.method == 'POST':
        post_class = request.form.get('post_class')
        post_section = request.form.get('post_section')
        day = request.form.get('day_of_week')
        period = int(request.form.get('period_no'))
        sub_id = request.form.get('subject_id')
        teach_id = request.form.get('teacher_id')
        r_no = request.form.get('room_no')
        s_time = request.form.get('start_time')
        e_time = request.form.get('end_time')

        if not post_class or not post_section or not day or not period:
            flash("Missing primary parameters", "danger")
            return redirect(url_for('exam.class_timetable'))

        # Check existing mapping
        t_record = ClassTimetable.query.filter_by(
            school_id=current_user.school_id,
            class_name=post_class,
            section=post_section,
            day_of_week=day,
            period_no=period
        ).first()

        if sub_id == "":  # Deleting/clearing cell
            if t_record:
                db.session.delete(t_record)
                db.session.commit()
                flash("Period cleared successfully", "success")
        else:
            if not t_record:
                t_record = ClassTimetable(
                    school_id=current_user.school_id,
                    class_name=post_class,
                    section=post_section,
                    day_of_week=day,
                    period_no=period
                )
                db.session.add(t_record)

            t_record.subject_id = int(sub_id)
            t_record.teacher_id = int(teach_id) if teach_id else None
            t_record.room_no = r_no
            t_record.start_time = s_time
            t_record.end_time = e_time
            
            db.session.commit()
            flash("Period scheduled successfully", "success")

        return redirect(url_for('exam.class_timetable', class_name=post_class, section=post_section))

    return render_template(
        'exam/class_timetable.html',
        classes=classes,
        sections=sections,
        selected_class=selected_class,
        selected_section=selected_section,
        days=days,
        periods=periods,
        matrix=timetable_matrix,
        subjects=subjects,
        teachers=teachers
    )


@exam.route('/api/students')
@login_required
def api_class_students():
    class_name = request.args.get('class_name')
    section = request.args.get('section')
    if not class_name or not section:
        return {"students": []}
    
    students = Student.query.filter_by(
        school_id=current_user.school_id,
        student_class=class_name,
        section=section
    ).order_by(Student.first_name).all()
    
    return {
        "students": [{
            "id": s.id,
            "admission_no": s.admission_no,
            "name": f"{s.first_name} {s.last_name}"
        } for s in students]
    }

