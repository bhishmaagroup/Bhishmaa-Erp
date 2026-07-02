from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.exam import Exam, ExamSchedule, ExamMark, GradeRule, ExamResult, ExamSession, ExamType
from models.student import Student
from models.school import School
from models.subject import Subject
from models.student_subject import StudentSubject
from super.routes import subscription_required
from datetime import datetime
import io

# ReportLab Imports
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

result_bp = Blueprint('result', __name__, url_prefix='/result')

# =========================================================
# 🏷️ GRADE RULES CONFIGURATION
# =========================================================
@result_bp.route('/grades', methods=['GET', 'POST'])
@login_required
@subscription_required
def grade_rules():
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        grade_name = request.form.get('grade_name')
        min_pct = float(request.form.get('min_percentage', 0))
        max_pct = float(request.form.get('max_percentage', 100))
        grade_point = float(request.form.get('grade_point', 0.0))
        remarks = request.form.get('remarks', '')

        if grade_name:
            # Overlap check
            overlap = GradeRule.query.filter(
                GradeRule.school_id == current_user.school_id,
                ((GradeRule.min_percentage <= min_pct) & (GradeRule.max_percentage >= min_pct)) |
                ((GradeRule.min_percentage <= max_pct) & (GradeRule.max_percentage >= max_pct))
            ).first()

            if overlap:
                flash(f"Warning: Percentage range overlaps with existing grade {overlap.grade_name}", 'warning')

            rule = GradeRule(
                school_id=current_user.school_id,
                grade_name=grade_name,
                min_percentage=min_pct,
                max_percentage=max_pct,
                grade_point=grade_point,
                remarks=remarks
            )
            db.session.add(rule)
            db.session.commit()
            flash('Grade rule added successfully', 'success')
        return redirect(url_for('result.grade_rules'))

    rules = GradeRule.query.filter_by(school_id=current_user.school_id).order_by(GradeRule.min_percentage.desc()).all()
    
    # Auto-seed basic rules if empty
    if not rules:
        seeds = [
            ("A+", 90, 100, 10, "Excellent"),
            ("A", 80, 89.9, 9, "Very Good"),
            ("B+", 70, 79.9, 8, "Good"),
            ("B", 60, 69.9, 7, "Above Average"),
            ("C", 50, 59.9, 6, "Average"),
            ("D", 33, 49.9, 4, "Pass"),
            ("E/F", 0, 32.9, 0, "Fail")
        ]
        for name, mn, mx, gp, rem in seeds:
            rule = GradeRule(school_id=current_user.school_id, grade_name=name, min_percentage=mn, max_percentage=mx, grade_point=gp, remarks=rem)
            db.session.add(rule)
        db.session.commit()
        rules = GradeRule.query.filter_by(school_id=current_user.school_id).order_by(GradeRule.min_percentage.desc()).all()

    return render_template('result/grades.html', rules=rules)

@result_bp.route('/grades/delete/<int:id>')
@login_required
@subscription_required
def delete_grade_rule(id):
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    rule = GradeRule.query.filter_by(id=id, school_id=current_user.school_id).first_or_404()
    db.session.delete(rule)
    db.session.commit()
    flash('Grade rule deleted successfully', 'success')
    return redirect(url_for('result.grade_rules'))


# =========================================================
# ⚙️ MARKS PROCESSING ENGINE
# =========================================================
@result_bp.route('/process', methods=['GET', 'POST'])
@login_required
@subscription_required
def process_results():
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).all()

    if request.method == 'POST':
        exam_id = request.form.get('exam_id')
        exam = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()

        # 1. Fetch schedules for this exam
        schedules = ExamSchedule.query.filter_by(exam_id=exam.id).all()
        if not schedules:
            flash("Cannot process result: No subjects scheduled for this exam yet.", "warning")
            return redirect(url_for('result.process_results'))

        schedule_ids = [sc.id for sc in schedules]

        # 2. Get students of this class & section
        stud_query = Student.query.filter_by(school_id=current_user.school_id, student_class=exam.class_name)
        if exam.section:
            stud_query = stud_query.filter_by(section=exam.section)
        students = stud_query.all()

        if not students:
            flash("No students found in this class/section to process.", "warning")
            return redirect(url_for('result.process_results'))

        # Fetch Grade rules
        grade_rules = GradeRule.query.filter_by(school_id=current_user.school_id).all()

        processed_records = []

        # 3. Calculate marks for each student
        for student in students:
            total_obtained = 0.0
            total_max = 0.0
            has_failed = False
            attempted_any = False

            for sc in schedules:
                # Check if student is allocated to this subject
                allocated = StudentSubject.query.filter_by(
                    school_id=current_user.school_id,
                    student_id=student.id,
                    subject_id=sc.subject_id
                ).first()
                if not allocated:
                    continue

                total_max += sc.max_marks
                mark = ExamMark.query.filter_by(exam_schedule_id=sc.id, student_id=student.id).first()
                
                obtained = 0.0
                if mark:
                    attempted_any = True
                    if not mark.is_absent:
                        obtained = mark.marks_obtained
                        if obtained < sc.passing_marks:
                            has_failed = True
                    else:
                        has_failed = True
                else:
                    # Absent by default if no mark sheet entered
                    has_failed = True

                total_obtained += obtained

            # Percentage
            percentage = round((total_obtained / total_max) * 100, 2) if total_max else 0.0

            # Match grade rule
            assigned_grade = "N/A"
            for rule in grade_rules:
                if rule.min_percentage <= percentage <= rule.max_percentage:
                    assigned_grade = rule.grade_name
                    break

            status = "Fail" if has_failed else ("Pass" if attempted_any else "N/A")

            # Check if ExamResult already exists
            res = ExamResult.query.filter_by(exam_id=exam.id, student_id=student.id).first()
            if not res:
                res = ExamResult(
                    school_id=current_user.school_id,
                    exam_id=exam.id,
                    student_id=student.id,
                    total_marks_obtained=total_obtained,
                    total_max_marks=total_max,
                    percentage=percentage,
                    grade=assigned_grade,
                    status=status,
                    is_published=exam.is_published,
                    processed_at=datetime.utcnow()
                )
                db.session.add(res)
            else:
                res.total_marks_obtained = total_obtained
                res.total_max_marks = total_max
                res.percentage = percentage
                res.grade = assigned_grade
                res.status = status
                res.processed_at = datetime.utcnow()

            processed_records.append(res)

        db.session.commit()

        # 4. Rank Calculation (Class-wise order)
        # Fetch processed results for sorting
        sorted_results = ExamResult.query.filter_by(exam_id=exam.id).order_by(ExamResult.percentage.desc()).all()
        for idx, res_record in enumerate(sorted_results):
            res_record.rank = idx + 1
        
        db.session.commit()

        flash(f"Successfully processed results and rankings for {len(students)} students in {exam.name}!", "success")
        return redirect(url_for('result.process_results'))

    return render_template('result/process.html', exams=exams)


# =========================================================
# 📢 RESULT PUBLISHING WORKFLOW
# =========================================================
@result_bp.route('/publish', methods=['GET', 'POST'])
@login_required
@subscription_required
def publish_results():
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        exam_id = request.form.get('exam_id')
        publish_action = request.form.get('action') # 'publish' or 'unpublish'

        exam = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
        is_published = True if publish_action == 'publish' else False
        
        exam.is_published = is_published
        
        # Update in processed ExamResults
        ExamResult.query.filter_by(exam_id=exam.id).update({"is_published": is_published})
        db.session.commit()

        msg = f"Results for {exam.name} are now PUBLISHED and visible to students!" if is_published else f"Results for {exam.name} are now UNPUBLISHED."
        flash(msg, 'success')
        return redirect(url_for('result.publish_results'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).order_by(Exam.created_at.desc()).all()
    return render_template('result/publish.html', exams=exams)


# =========================================================
# 📄 VIEW RESULTS & PDF REPORT CARD
# =========================================================
@result_bp.route('/report-cards')
@login_required
@subscription_required
def report_cards_list():
    if current_user.role not in ['admin', 'teacher', 'student']:
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    if current_user.role == 'student':
        # Student views own published results
        student = Student.query.filter_by(id=current_user.student_id, school_id=current_user.school_id).first_or_404()
        results = ExamResult.query.filter_by(student_id=student.id, is_published=True).all()
        return render_template('result/student_results.html', student=student, results=results)

    # Admin/Teacher Filter
    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    
    selected_exam_id = request.args.get('exam_id')
    results = []
    
    if selected_exam_id:
        results = ExamResult.query.filter_by(exam_id=selected_exam_id).order_by(ExamResult.rank).all()

    return render_template(
        'result/report_cards.html',
        exams=exams,
        results=results,
        selected_exam_id=int(selected_exam_id) if selected_exam_id else None
    )

@result_bp.route('/report-card/pdf/<int:result_id>')
@login_required
@subscription_required
def download_report_card_pdf(result_id):
    res = ExamResult.query.filter_by(id=result_id, school_id=current_user.school_id).first_or_404()

    # Student security check
    if current_user.role == 'student' and current_user.student_id != res.student_id:
        return "Unauthorized", 403
    
    if current_user.role == 'student' and not res.is_published:
        return "Results not published yet", 403

    # Generate PDF buffer
    buffer = generate_report_card_pdf_data(res)
    if not buffer:
        return "Failed to generate Report Card", 500

    filename = f"Report_Card_{res.student.first_name}_{res.exam_ref.name.replace(' ', '_')}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )

def generate_report_card_pdf_data(res):
    """ReportLab function to render a beautiful Report Card PDF."""
    student = res.student
    exam = res.exam_ref
    school = School.query.get(res.school_id)

    # Fetch marks
    schedules = ExamSchedule.query.filter_by(exam_id=exam.id).order_by(ExamSchedule.date).all()
    marks = ExamMark.query.filter_by(student_id=student.id).all()
    marks_dict = {m.exam_schedule_id: m for m in marks}

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    # Styling colors
    primary_color = colors.HexColor('#0b1e3c')
    secondary_color = colors.HexColor('#ffc107')

    school_title_style = ParagraphStyle(
        'RC_SchoolName',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=20,
        alignment=1,
        textColor=primary_color,
        spaceAfter=3
    )

    school_sub_style = ParagraphStyle(
        'RC_SchoolSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        alignment=1,
        textColor=colors.HexColor('#555555'),
        spaceAfter=15
    )

    exam_title_style = ParagraphStyle(
        'RC_ExamTitle',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=14,
        alignment=1,
        textColor=secondary_color,
        spaceAfter=20
    )

    label_style = ParagraphStyle(
        'RC_Label',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=primary_color
    )

    value_style = ParagraphStyle(
        'RC_Value',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10
    )

    th_style = ParagraphStyle(
        'RC_TH',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white
    )

    tb_style = ParagraphStyle(
        'RC_TB',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9
    )

    tb_bold_style = ParagraphStyle(
        'RC_TBBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=primary_color
    )

    story = []

    # School Details
    story.append(Paragraph(school.school_name.upper(), school_title_style))
    story.append(Paragraph(f"{school.address or ''}, {school.city or ''}, {school.state or ''} - Pin: {school.pincode or ''}", school_sub_style))
    story.append(Paragraph(f"REPORT CARD - {exam.name.upper()}", exam_title_style))

    # Student metadata table
    stud_meta = [
        [Paragraph("Student Name:", label_style), Paragraph(f"{student.first_name} {student.middle_name or ''} {student.last_name or ''}".replace('  ',' '), value_style),
         Paragraph("Admission No:", label_style), Paragraph(student.admission_no, value_style)],
        
        [Paragraph("Class & Section:", label_style), Paragraph(f"{student.student_class} - {student.section or 'N/A'}", value_style),
         Paragraph("Roll No / Session:", label_style), Paragraph(f"{exam.session_ref.name}", value_style)],
        
        [Paragraph("Father's Name:", label_style), Paragraph(student.father_name or 'N/A', value_style),
         Paragraph("Mother's Name:", label_style), Paragraph(student.mother_name or 'N/A', value_style)]
    ]
    t_meta = Table(stud_meta, colWidths=[1.5*inch, 2.0*inch, 1.5*inch, 2.0*inch])
    t_meta.setStyle(TableStyle([
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('LINEBELOW', (0,0), (-1,-1), 0.5, colors.HexColor('#eeeeee')),
    ]))
    story.append(t_meta)
    story.append(Spacer(1, 20))

    # Subject performance table
    subject_table_data = [[
        Paragraph("Subject Code", th_style),
        Paragraph("Subject Name", th_style),
        Paragraph("Max Marks", th_style),
        Paragraph("Passing Marks", th_style),
        Paragraph("Marks Obtained", th_style),
        Paragraph("Status", th_style)
    ]]

    for sc in schedules:
        # Check if student is allocated to this subject
        allocated = StudentSubject.query.filter_by(
            school_id=res.school_id,
            student_id=student.id,
            subject_id=sc.subject_id
        ).first()
        if not allocated:
            continue

        m = marks_dict.get(sc.id)
        if m:
            if m.is_absent:
                obt = "ABS"
                status = "Fail"
            else:
                obt = str(m.marks_obtained)
                status = "Pass" if m.marks_obtained >= sc.passing_marks else "Fail"
        else:
            obt = "-"
            status = "N/A"

        subject_table_data.append([
            Paragraph(sc.subject.subject_code or "N/A", tb_style),
            Paragraph(sc.subject.subject_name, tb_style),
            Paragraph(str(sc.max_marks), tb_style),
            Paragraph(str(sc.passing_marks), tb_style),
            Paragraph(obt, tb_bold_style if status=="Pass" else ParagraphStyle('rc_fail', parent=tb_bold_style, textColor=colors.red)),
            Paragraph(status, tb_bold_style if status=="Pass" else ParagraphStyle('rc_fail', parent=tb_bold_style, textColor=colors.red))
        ])

    t_subjects = Table(subject_table_data, colWidths=[1.2*inch, 2.3*inch, 1.0*inch, 1.0*inch, 1.0*inch, 1.0*inch])
    t_subjects.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), primary_color),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#dddddd')),
    ]))
    story.append(t_subjects)
    story.append(Spacer(1, 20))

    # Performance summary cards
    summary_data = [
        [Paragraph("Total Max Marks:", label_style), Paragraph(str(res.total_max_marks), value_style),
         Paragraph("Total Obtained:", label_style), Paragraph(str(res.total_marks_obtained), value_style)],
        
        [Paragraph("Overall Percentage:", label_style), Paragraph(f"{res.percentage}%", value_style),
         Paragraph("Calculated Grade:", label_style), Paragraph(res.grade or "N/A", value_style)],
        
        [Paragraph("Class Rank:", label_style), Paragraph(str(res.rank) if res.rank else "N/A", value_style),
         Paragraph("Final Result Status:", label_style), Paragraph(res.status, tb_bold_style if res.status=="Pass" else ParagraphStyle('rc_f', parent=tb_bold_style, textColor=colors.red))]
    ]
    t_summary = Table(summary_data, colWidths=[1.8*inch, 1.7*inch, 1.8*inch, 1.7*inch])
    t_summary.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor('#f9fbfd')),
        ('BOX', (0,0), (-1,-1), 1, primary_color),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('LINEBELOW', (0,0), (-1,-2), 0.5, colors.HexColor('#e1e8ed')),
    ]))
    story.append(t_summary)
    story.append(Spacer(1, 40))

    # Signatures
    sig_data = [
        ["", "", ""],
        ["_________________________", "_________________________", "_________________________"],
        ["Class Teacher Signature", "Invigilator Signature", "Principal / Director"]
    ]
    t_sig = Table(sig_data, colWidths=[2.3*inch, 2.3*inch, 2.4*inch])
    t_sig.setStyle(TableStyle([
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,2), (-1,2), 'Helvetica-Bold'),
        ('FONTSIZE', (0,2), (-1,2), 9),
        ('BOTTOMPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t_sig)

    doc.build(story)
    buffer.seek(0)
    return buffer
