from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from extensions import db
from models.subject import Subject
from models.student import Student
from models.teacher import Teacher
from models.school import School
from models.user import User
from models.exam import ExamSession, ExamType, Exam, ExamSchedule, ExamMark, ExamAttendance, GradeRule, ExamResult
from models.timetable import Room, AcademicTimetable
from models.academics import AcademicClass, AcademicSection, Period, WorkingDay, ExamGroup, SeatingPlan, AcademicsAuditLog, AcademicPlannerSetting, SubjectWorkload
from models.student_subject import StudentSubject
from models.teacher_subject import TeacherSubject
from super.routes import subscription_required
from datetime import datetime, date, time, timedelta
import pandas as pd
import io
import os
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

# ReportLab Imports
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

academics_bp = Blueprint('academics', __name__, url_prefix='/academics')

# =========================================================
# 🔐 AUDIT & PERMISSION HELPER
# =========================================================
def log_academic_action(action, details):
    try:
        log = AcademicsAuditLog(
            school_id=current_user.school_id,
            user_id=current_user.id,
            action=action,
            details=details
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print("Academics audit log error:", e)

def check_permission(*allowed_roles):
    """Decorator-like validation helper inside route bodies."""
    if current_user.role not in allowed_roles:
        flash("Unauthorized Access: You do not have permission to view this resource.", "danger")
        return False
    return True

# =========================================================
# 🏠 MAIN DASHBOARD / MENU
# =========================================================
@academics_bp.route('/')
@login_required
@subscription_required
def index():
    if current_user.role == 'student':
        return redirect(url_for('academics.portal_student'))
    if current_user.role == 'parent':
        return redirect(url_for('academics.portal_parent'))
    
    return render_template('academics/dashboard.html')

# =========================================================
# 1. SUBJECT MANAGEMENT
# =========================================================
@academics_bp.route('/subjects', methods=['GET', 'POST'])
@login_required
@subscription_required
def subjects():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        class_name = request.form.get('class_name')
        section = request.form.get('section') or None
        subject_name = request.form.get('subject_name')
        subject_code = request.form.get('subject_code')
        subject_type = request.form.get('subject_type', 'Theory')
        is_optional = True if request.form.get('is_optional') else False

        if subject_name and class_name:
            sub = Subject(
                school_id=current_user.school_id,
                class_name=class_name,
                section=section,
                subject_name=subject_name,
                subject_code=subject_code,
                subject_type=subject_type,
                is_optional=is_optional,
                status=True
            )
            db.session.add(sub)
            db.session.commit()
            log_academic_action("Created Subject", f"Created subject: {subject_name} ({subject_code}) for Class {class_name}")
            flash('Subject created successfully!', 'success')
        return redirect(url_for('academics.subjects'))

    subjects = Subject.query.filter_by(school_id=current_user.school_id).all()
    teachers = Teacher.query.filter_by(school_id=current_user.school_id).all()
    return render_template('academics/subjects.html', subjects=subjects, teachers=teachers)

@academics_bp.route('/subjects/assign-teacher', methods=['POST'])
@login_required
@subscription_required
def subjects_assign_teacher():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))

    teacher_id = request.form.get('teacher_id')
    subject_id = request.form.get('subject_id')

    if teacher_id and subject_id:
        sub = Subject.query.filter_by(id=subject_id, school_id=current_user.school_id).first_or_404()
        
        # Check duplicate
        exists = TeacherSubject.query.filter_by(
            school_id=current_user.school_id,
            teacher_id=teacher_id,
            subject_id=subject_id
        ).first()

        if exists:
            flash("Teacher is already assigned to this subject.", "warning")
        else:
            assign = TeacherSubject(
                school_id=current_user.school_id,
                teacher_id=teacher_id,
                subject_id=subject_id,
                class_name=sub.class_name,
                section=sub.section
            )
            db.session.add(assign)
            db.session.commit()
            log_academic_action("Assigned Subject Teacher", f"Assigned teacher ID {teacher_id} to subject {sub.subject_name}")
            flash("Teacher assigned successfully!", "success")
            
    return redirect(url_for('academics.subjects'))

@academics_bp.route('/subjects/toggle-status/<int:id>')
@login_required
@subscription_required
def subjects_toggle_status(id):
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))

    sub = Subject.query.filter_by(id=id, school_id=current_user.school_id).first_or_404()
    sub.status = not sub.status
    db.session.commit()
    flash(f"Subject status updated to {'Active' if sub.status else 'Inactive'}.", "success")
    return redirect(url_for('academics.subjects'))

# =========================================================
# 2. CLASS & SECTION MANAGEMENT
# =========================================================
@academics_bp.route('/classes', methods=['GET', 'POST'])
@login_required
@subscription_required
def classes():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'class':
            class_name = request.form.get('class_name')
            stream = request.form.get('stream') or None
            
            # Check duplicate class
            existing = AcademicClass.query.filter_by(school_id=current_user.school_id, class_name=class_name).first()
            if existing:
                flash(f"Class {class_name} already exists", 'warning')
            else:
                c = AcademicClass(school_id=current_user.school_id, class_name=class_name, stream=stream)
                db.session.add(c)
                db.session.commit()
                log_academic_action("Created Class", f"Created class: {class_name}")
                flash('Class added successfully!', 'success')
        
        elif action == 'section':
            class_id = request.form.get('class_id')
            section_name = request.form.get('section_name')
            class_teacher_id = request.form.get('class_teacher_id') or None
            capacity = int(request.form.get('capacity', 40))
            acad_year = request.form.get('academic_year', '2026-2027')

            if class_id and section_name:
                # Check duplicate section
                exists = AcademicSection.query.filter_by(
                    school_id=current_user.school_id,
                    class_id=class_id,
                    section_name=section_name
                ).first()

                if exists:
                    flash(f"Section {section_name} already exists for this class.", "warning")
                else:
                    sec = AcademicSection(
                        school_id=current_user.school_id,
                        class_id=class_id,
                        section_name=section_name,
                        class_teacher_id=class_teacher_id,
                        capacity=capacity,
                        academic_year=acad_year
                    )
                    db.session.add(sec)
                    db.session.commit()
                    log_academic_action("Created Section", f"Created section: {section_name} under class ID {class_id}")
                    flash('Section added successfully!', 'success')
        return redirect(url_for('academics.classes'))

    classes = AcademicClass.query.filter_by(school_id=current_user.school_id).all()
    teachers = Teacher.query.filter_by(school_id=current_user.school_id).all()
    return render_template('academics/classes.html', classes=classes, teachers=teachers)


# =========================================================
# 3. TIMETABLE MANAGEMENT
# =========================================================
def detect_timetable_conflict(day_name, period_id, teacher_id, room_id, school_id, ignore_id=None):
    """Helper to detect double-booking overlaps for Timetable slots."""
    conflicts = []
    
    # Check if period exists
    period = Period.query.get(period_id)
    if not period or period.is_break:
        return conflicts  # Breaks can overlap

    # Check Teacher Overlap
    t_match = AcademicTimetable.query.filter(
        AcademicTimetable.school_id == school_id,
        AcademicTimetable.day_of_week == day_name,
        AcademicTimetable.period_no == period.period_no, # Maps period no
        AcademicTimetable.teacher_id == teacher_id
    )
    if ignore_id:
        t_match = t_match.filter(AcademicTimetable.id != ignore_id)
    t_res = t_match.first()
    if t_res:
        conflicts.append(f"Teacher is already teaching Class {t_res.class_name}-{t_res.section} in period {period.period_no}")

    # Check Room Overlap
    if room_id:
        r_match = AcademicTimetable.query.filter(
            AcademicTimetable.school_id == school_id,
            AcademicTimetable.day_of_week == day_name,
            AcademicTimetable.period_no == period.period_no,
            AcademicTimetable.room_id == room_id
        )
        if ignore_id:
            r_match = r_match.filter(AcademicTimetable.id != ignore_id)
        r_res = r_match.first()
        if r_res:
            conflicts.append(f"Room {r_res.room_ref.room_no} is already occupied by Class {r_res.class_name}-{r_res.section}")

    return conflicts

@academics_bp.route('/timetable', methods=['GET', 'POST'])
@login_required
@subscription_required
def timetable():
    if request.method == 'POST' and check_permission('admin', 'principal'):
        # Period configuration
        action = request.form.get('action')
        if action == 'period':
            name = request.form.get('period_name')
            p_no = int(request.form.get('period_no'))
            start = request.form.get('start_time')
            end = request.form.get('end_time')
            is_brk = True if request.form.get('is_break') else False

            start_t = datetime.strptime(start, '%H:%M').time() if start else None
            end_t = datetime.strptime(end, '%H:%M').time() if end else None

            if name and p_no and start_t and end_t:
                p = Period(
                    school_id=current_user.school_id,
                    period_name=name,
                    period_no=p_no,
                    start_time=start_t,
                    end_time=end_t,
                    is_break=is_brk
                )
                db.session.add(p)
                db.session.commit()
                log_academic_action("Created Period", f"Created school period: {name} ({start_t} - {end_t})")
                flash("School period created successfully!", "success")
        
        elif action == 'slot':
            # Allocate timetable slot
            class_name = request.form.get('class_name')
            section = request.form.get('section')
            day_name = request.form.get('day_name')
            period_id = int(request.form.get('period_id'))
            subject_id = int(request.form.get('subject_id'))
            teacher_id = int(request.form.get('teacher_id'))
            room_id = request.form.get('room_id')
            room_id = int(room_id) if room_id else None

            p = Period.query.get_or_404(period_id)
            sub = Subject.query.get_or_404(subject_id)

            # Check conflicts
            conflicts = detect_timetable_conflict(day_name, period_id, teacher_id, room_id, current_user.school_id)
            if conflicts:
                for c in conflicts:
                    flash(f"Conflict: {c}", "danger")
                return redirect(url_for('academics.timetable', class_name=class_name, section=section))

            # Add slot
            slot = AcademicTimetable(
                school_id=current_user.school_id,
                class_name=class_name,
                section=section,
                day_of_week=day_name,
                period_no=p.period_no,
                start_time=p.start_time,
                end_time=p.end_time,
                subject_id=subject_id,
                teacher_id=teacher_id,
                room_id=room_id
            )
            db.session.add(slot)
            db.session.commit()
            log_academic_action("Timetable Slot Created", f"Scheduled {sub.subject_name} for Class {class_name}-{section} on {day_name}")
            flash("Timetable period allocated successfully!", "success")

        return redirect(url_for('academics.timetable'))

    # Load filters
    class_name = request.args.get('class_name')
    section = request.args.get('section')

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    periods = Period.query.filter_by(school_id=current_user.school_id).order_by(Period.period_no).all()
    subjects = []
    if class_name:
        sub_query = Subject.query.filter_by(school_id=current_user.school_id, class_name=class_name, status=True)
        if section:
            sub_query = sub_query.filter((Subject.section == section) | (Subject.section == None) | (Subject.section == ''))
        subjects = sub_query.all()
    else:
        subjects = Subject.query.filter_by(school_id=current_user.school_id, status=True).all()
    teachers = Teacher.query.filter_by(school_id=current_user.school_id).all()
    rooms = Room.query.filter_by(school_id=current_user.school_id).all()

    timetable_grid = {}
    if class_name and section:
        records = AcademicTimetable.query.filter_by(
            school_id=current_user.school_id,
            class_name=class_name,
            section=section
        ).all()
        for r in records:
            if r.day_of_week not in timetable_grid:
                timetable_grid[r.day_of_week] = {}
            timetable_grid[r.day_of_week][r.period_no] = r

    return render_template(
        'academics/timetable.html',
        class_name=class_name,
        section=section,
        days=days,
        periods=periods,
        subjects=subjects,
        teachers=teachers,
        rooms=rooms,
        timetable_grid=timetable_grid
    )

@academics_bp.route('/timetable/pdf/<string:class_name>/<string:section>')
@login_required
@subscription_required
def export_timetable_pdf(class_name, section):
    """Compiles Class Timetable Grid into a printable PDF via ReportLab."""
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    periods = Period.query.filter_by(school_id=current_user.school_id).order_by(Period.period_no).all()

    if not periods:
        return "Configure periods first", 400

    records = AcademicTimetable.query.filter_by(
        school_id=current_user.school_id,
        class_name=class_name,
        section=section
    ).all()

    grid = {d: {} for d in days}
    for r in records:
        grid[r.day_of_week][r.period_no] = r

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TTableTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, alignment=1, spaceAfter=20
    )
    th_style = ParagraphStyle(
        'TTableTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.white, alignment=1
    )
    tb_style = ParagraphStyle(
        'TTableTB', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1
    )

    story = [Paragraph(f"ACADEMIC WEEKLY TIMETABLE - CLASS {class_name} ({section})", title_style)]

    # Build Grid Table
    header = [Paragraph("Day", th_style)]
    for p in periods:
        header.append(Paragraph(f"{p.period_name}<br/><font size=6>{p.start_time.strftime('%I:%M %p')} - {p.end_time.strftime('%I:%M %p')}</font>", th_style))
    
    table_data = [header]

    for d in days:
        row = [Paragraph(d, ParagraphStyle('TTableDay', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9))]
        for p in periods:
            slot = grid[d].get(p.period_no)
            if slot:
                txt = f"<b>{slot.subject.subject_name}</b><br/>{slot.teacher.first_name}<br/>{slot.room_ref.room_no if slot.room_id else 'N/A'}"
                row.append(Paragraph(txt, tb_style))
            else:
                row.append(Paragraph("-", tb_style))
        table_data.append(row)

    col_w = [1.0*inch] + [6.5*inch / len(periods)] * len(periods)
    t = Table(table_data, colWidths=col_w)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0b1e3c')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
    ]))
    story.append(t)

    doc.build(story)
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Timetable_Class_{class_name}_{section}.pdf",
        mimetype="application/pdf"
    )


# =========================================================
# 4. EXAMINATION MANAGEMENT
# =========================================================
@academics_bp.route('/exams', methods=['GET', 'POST'])
@login_required
@subscription_required
def exams():
    if request.method == 'POST' and check_permission('admin', 'principal'):
        action = request.form.get('action')
        if action == 'group':
            name = request.form.get('name')
            desc = request.form.get('description')
            if name:
                grp = ExamGroup(school_id=current_user.school_id, name=name, description=desc)
                db.session.add(grp)
                db.session.commit()
                flash('Exam group created successfully!', 'success')

        elif action == 'exam':
            name = request.form.get('name')
            session_id = request.form.get('session_id')
            exam_type_id = request.form.get('exam_type_id')
            exam_group_id = request.form.get('exam_group_id') or None
            class_name = request.form.get('class_name')
            section = request.form.get('section') or None
            start_str = request.form.get('start_date')
            end_str = request.form.get('end_date')

            start_date = datetime.strptime(start_str, '%Y-%m-%d').date() if start_str else None
            end_date = datetime.strptime(end_str, '%Y-%m-%d').date() if end_str else None

            if name and session_id and exam_type_id and class_name:
                ex = Exam(
                    school_id=current_user.school_id,
                    name=name,
                    session_id=session_id,
                    exam_type_id=exam_type_id,
                    exam_group_id=exam_group_id,
                    class_name=class_name,
                    section=section,
                    start_date=start_date,
                    end_date=end_date,
                    status="Draft"
                )
                db.session.add(ex)
                db.session.commit()
                log_academic_action("Created Exam Master", f"Created exam: {name} for class {class_name}")
                flash('Exam created successfully!', 'success')
        return redirect(url_for('academics.exams'))

    sessions = ExamSession.query.filter_by(school_id=current_user.school_id).all()
    types = ExamType.query.filter_by(school_id=current_user.school_id).all()
    groups = ExamGroup.query.filter_by(school_id=current_user.school_id).all()
    exams = Exam.query.filter_by(school_id=current_user.school_id).order_by(Exam.created_at.desc()).all()
    
    # Group unique exam combinations for bulk downloads
    unique_exam_groups = []
    seen = set()
    for e in exams:
        key = (e.session_id, e.exam_type_id)
        if key not in seen:
            seen.add(key)
            unique_exam_groups.append({
                'session_id': e.session_id,
                'exam_type_id': e.exam_type_id,
                'session_name': e.session_ref.name,
                'exam_type_name': e.type_ref.name
            })

    return render_template(
        'academics/exams.html',
        sessions=sessions,
        types=types,
        groups=groups,
        exams=exams,
        unique_exam_groups=unique_exam_groups
    )


# =========================================================
# 5. ADMIT CARD MANAGEMENT
# =========================================================
@academics_bp.route('/admit-cards', methods=['GET', 'POST'])
@login_required
@subscription_required
def admit_cards():
    if not check_permission('admin', 'principal', 'teacher'):
        return redirect(url_for('dashboard.home'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    return render_template('academics/admit_cards.html', exams=exams)


# =========================================================
# 6. SEATING PLAN MANAGEMENT (AUTO ALLOCATION ENGINE)
# =========================================================
@academics_bp.route('/seating', methods=['GET', 'POST'])
@login_required
@subscription_required
def seating():
    if request.method == 'POST' and check_permission('admin', 'principal'):
        action = request.form.get('action')
        if action == 'allocate':
            exam_id = int(request.form.get('exam_id'))
            schedule_id = int(request.form.get('schedule_id'))
            room_ids = request.form.getlist('room_ids')

            exam = Exam.query.get_or_404(exam_id)
            sched = ExamSchedule.query.get_or_404(schedule_id)
            
            # Fetch Students registered to the schedule's subject
            students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
                Student.school_id == current_user.school_id,
                Student.student_class == exam.class_name,
                StudentSubject.subject_id == sched.subject_id
            )
            if exam.section:
                students = students.filter(Student.section == exam.section)
            students = students.order_by(Student.first_name).all()

            rooms = Room.query.filter(Room.id.in_([int(rid) for rid in room_ids])).all()
            
            # Clear previous seating allocation for this schedule
            SeatingPlan.query.filter_by(exam_schedule_id=schedule_id).delete()
            db.session.commit()

            student_idx = 0
            allocated_count = 0

            # Seat Allocation Engine loop
            for rm in rooms:
                if student_idx >= len(students):
                    break

                for seat in range(1, rm.capacity + 1):
                    if student_idx >= len(students):
                        break

                    st = students[student_idx]
                    seat_label = f"Desk-{seat}"

                    plan = SeatingPlan(
                        school_id=current_user.school_id,
                        exam_id=exam_id,
                        exam_schedule_id=schedule_id,
                        room_id=rm.id,
                        student_id=st.id,
                        seat_no=seat_label
                    )
                    db.session.add(plan)
                    
                    student_idx += 1
                    allocated_count += 1
            
            db.session.commit()
            log_academic_action("Auto Seat Allocation", f"Assigned {allocated_count} seats for schedule id {schedule_id}")
            flash(f"Auto seating successfully arranged for {allocated_count} students!", "success")

        return redirect(url_for('academics.seating'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    rooms = Room.query.filter_by(school_id=current_user.school_id).all()
    plans = SeatingPlan.query.filter_by(school_id=current_user.school_id).all()

    return render_template('academics/seating.html', exams=exams, rooms=rooms, plans=plans)


# =========================================================
# 7. EXAM ATTENDANCE
# =========================================================
@academics_bp.route('/attendance', methods=['GET', 'POST'])
@login_required
@subscription_required
def attendance():
    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    selected_exam_id = request.args.get('exam_id')
    selected_schedule_id = request.args.get('schedule_id')
    
    schedules = []
    if selected_exam_id:
        schedules = ExamSchedule.query.filter_by(exam_id=selected_exam_id).all()

    students = []
    attendance_map = {}

    if selected_schedule_id:
        sched = ExamSchedule.query.get_or_404(selected_schedule_id)
        exam = sched.exam_ref
        
        students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
            Student.school_id == current_user.school_id,
            Student.student_class == exam.class_name,
            StudentSubject.subject_id == sched.subject_id
        )
        if exam.section:
            students = students.filter(Student.section == exam.section)
        students = students.all()

        existing = ExamAttendance.query.filter_by(exam_schedule_id=selected_schedule_id).all()
        attendance_map = {att.student_id: att for att in existing}

    if request.method == 'POST' and selected_schedule_id:
        if not check_permission('admin', 'principal', 'teacher'):
            return redirect(url_for('dashboard.home'))

        for st in students:
            status = request.form.get(f'status_{st.id}', 'P')
            remarks = request.form.get(f'remarks_{st.id}', '')

            att_rec = ExamAttendance.query.filter_by(exam_schedule_id=selected_schedule_id, student_id=st.id).first()
            if not att_rec:
                att_rec = ExamAttendance(
                    school_id=current_user.school_id,
                    exam_schedule_id=selected_schedule_id,
                    student_id=st.id,
                    status=status,
                    remarks=remarks
                )
                db.session.add(att_rec)
            else:
                att_rec.status = status
                att_rec.remarks = remarks

        db.session.commit()
        log_academic_action("Recorded Attendance", f"Marked attendance sheets for schedule ID {selected_schedule_id}")
        flash("Exam attendance submitted successfully!", "success")
        return redirect(url_for('academics.attendance', exam_id=selected_exam_id, schedule_id=selected_schedule_id))

    return render_template(
        'academics/attendance.html',
        exams=exams,
        schedules=schedules,
        students=students,
        attendance_map=attendance_map,
        selected_exam_id=int(selected_exam_id) if selected_exam_id else None,
        selected_schedule_id=int(selected_schedule_id) if selected_schedule_id else None
    )


# =========================================================
# 8. MARKS ENTRY PORTAL & EXCEL CHANNELS (SPLIT CHANNELS)
# =========================================================
@academics_bp.route('/marks', methods=['GET', 'POST'])
@login_required
@subscription_required
def marks_entry():
    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    selected_exam_id = request.args.get('exam_id')
    selected_schedule_id = request.args.get('schedule_id')
    
    schedules = []
    if selected_exam_id:
        schedules = ExamSchedule.query.filter_by(exam_id=selected_exam_id).all()

    students = []
    marks_map = {}
    sched = None

    if selected_schedule_id:
        sched = ExamSchedule.query.get_or_404(selected_schedule_id)
        exam = sched.exam_ref
        
        students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
            Student.school_id == current_user.school_id,
            Student.student_class == exam.class_name,
            StudentSubject.subject_id == sched.subject_id
        )
        if exam.section:
            students = students.filter(Student.section == exam.section)
        students = students.all()

        existing = ExamMark.query.filter_by(exam_schedule_id=selected_schedule_id).all()
        marks_map = {m.student_id: m for m in existing}

    if request.method == 'POST' and selected_schedule_id:
        if not check_permission('admin', 'principal', 'teacher'):
            return redirect(url_for('dashboard.home'))

        sched = ExamSchedule.query.get_or_404(selected_schedule_id)
        if sched.exam_ref.status == 'Locked':
            flash("Error: This exam result is locked and marks cannot be modified.", "danger")
            return redirect(request.url)

        for st in students:
            is_abs = True if request.form.get(f'absent_{st.id}') else False
            
            t_obt = float(request.form.get(f'theory_{st.id}', 0.0))
            p_obt = float(request.form.get(f'practical_{st.id}', 0.0))
            v_obt = float(request.form.get(f'viva_{st.id}', 0.0))
            i_obt = float(request.form.get(f'internal_{st.id}', 0.0))
            grace = float(request.form.get(f'grace_{st.id}', 0.0))

            # Validate max values
            if t_obt > sched.max_theory or p_obt > sched.max_practical or v_obt > sched.max_viva or i_obt > sched.max_internal:
                flash(f"Error: Enter marks values within range for student {st.first_name}.", "danger")
                return redirect(request.url)

            total = t_obt + p_obt + v_obt + i_obt + grace

            mark_rec = ExamMark.query.filter_by(exam_schedule_id=selected_schedule_id, student_id=st.id).first()
            if not mark_rec:
                mark_rec = ExamMark(
                    school_id=current_user.school_id,
                    exam_schedule_id=selected_schedule_id,
                    student_id=st.id,
                    subject_id=sched.subject_id,
                    theory_obtained=t_obt,
                    practical_obtained=p_obt,
                    viva_obtained=v_obt,
                    internal_obtained=i_obt,
                    grace_marks=grace,
                    marks_obtained=total,
                    is_absent=is_abs,
                    teacher_id=current_user.employee_id if current_user.role == 'teacher' else None
                )
                db.session.add(mark_rec)
            else:
                mark_rec.theory_obtained = t_obt
                mark_rec.practical_obtained = p_obt
                mark_rec.viva_obtained = v_obt
                mark_rec.internal_obtained = i_obt
                mark_rec.grace_marks = grace
                mark_rec.marks_obtained = total
                mark_rec.is_absent = is_abs
                mark_rec.updated_at = datetime.utcnow()

        db.session.commit()
        log_academic_action("Entered Split Marks", f"Recorded exam marks for schedule id {selected_schedule_id}")
        flash("Marks saved successfully!", "success")
        return redirect(url_for('academics.marks_entry', exam_id=selected_exam_id, schedule_id=selected_schedule_id))

    return render_template(
        'academics/marks_entry.html',
        exams=exams,
        schedules=schedules,
        students=students,
        marks_map=marks_map,
        sched=sched,
        selected_exam_id=int(selected_exam_id) if selected_exam_id else None,
        selected_schedule_id=int(selected_schedule_id) if selected_schedule_id else None
    )


# =========================================================
# 9. RESULT GENERATION ENGINE & CALCULATOR
# =========================================================
@academics_bp.route('/results', methods=['GET', 'POST'])
@login_required
@subscription_required
def results():
    if request.method == 'POST' and check_permission('admin', 'principal'):
        action = request.form.get('action')
        exam_id = int(request.form.get('exam_id'))
        exam = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()

        if action == 'process':
            # Run Result Calculator
            schedules = ExamSchedule.query.filter_by(exam_id=exam.id).all()
            if not schedules:
                flash("No schedules found to process results.", "warning")
                return redirect(url_for('academics.results'))

            stud_query = Student.query.filter_by(school_id=current_user.school_id, student_class=exam.class_name)
            if exam.section:
                stud_query = stud_query.filter_by(section=exam.section)
            students = stud_query.all()

            grade_rules = GradeRule.query.filter_by(school_id=current_user.school_id).all()

            for student in students:
                total_obtained = 0.0
                total_max = 0.0
                has_failed = False
                attempted = False

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
                    if mark:
                        attempted = True
                        if not mark.is_absent:
                            # Verify splitting fail logic (fails if theory or practical fails)
                            theory_fail = mark.theory_obtained < sc.pass_theory
                            prac_fail = mark.practical_obtained < sc.pass_practical
                            if theory_fail or prac_fail or mark.marks_obtained < sc.passing_marks:
                                has_failed = True
                            total_obtained += mark.marks_obtained
                        else:
                            has_failed = True
                    else:
                        has_failed = True

                percentage = round((total_obtained / total_max) * 100, 2) if total_max else 0.0
                
                # Match Grade
                assigned_grade = "F"
                for rule in grade_rules:
                    if rule.min_percentage <= percentage <= rule.max_percentage:
                        assigned_grade = rule.grade_name
                        break

                gpa = round(percentage / 10.0, 1) # Simplistic GPA mapping
                cgpa = gpa

                status = "Fail" if has_failed else ("Pass" if attempted else "N/A")

                res_rec = ExamResult.query.filter_by(exam_id=exam.id, student_id=student.id).first()
                if not res_rec:
                    res_rec = ExamResult(
                        school_id=current_user.school_id,
                        exam_id=exam.id,
                        student_id=student.id,
                        total_marks_obtained=total_obtained,
                        total_max_marks=total_max,
                        percentage=percentage,
                        grade=assigned_grade,
                        gpa=gpa,
                        cgpa=cgpa,
                        status=status,
                        is_published=False
                    )
                    db.session.add(res_rec)
                else:
                    res_rec.total_marks_obtained = total_obtained
                    res_rec.total_max_marks = total_max
                    res_rec.percentage = percentage
                    res_rec.grade = assigned_grade
                    res_rec.gpa = gpa
                    res_rec.cgpa = cgpa
                    res_rec.status = status

            db.session.commit()

            # Rank Calculations
            # 1. Class Rank (Ranks across the class)
            class_res = ExamResult.query.join(Student).filter(
                ExamResult.exam_id == exam.id,
                Student.student_class == exam.class_name
            ).order_by(ExamResult.percentage.desc()).all()
            for rank, r in enumerate(class_res):
                r.rank = rank + 1

            # 2. Section Rank (Ranks inside own section)
            sections = db.session.query(Student.section).filter(Student.student_class == exam.class_name).distinct().all()
            for sec_name_tuple in sections:
                sec_name = sec_name_tuple[0]
                sec_res = ExamResult.query.join(Student).filter(
                    ExamResult.exam_id == exam.id,
                    Student.student_class == exam.class_name,
                    Student.section == sec_name
                ).order_by(ExamResult.percentage.desc()).all()
                for s_rank, sr in enumerate(sec_res):
                    sr.section_rank = s_rank + 1

            # 3. School-wide Rank
            school_res = ExamResult.query.filter_by(exam_id=exam.id).order_by(ExamResult.percentage.desc()).all()
            for sch_rank, sch_r in enumerate(school_res):
                sch_r.school_rank = sch_rank + 1

            db.session.commit()
            log_academic_action("Calculated Exam Results", f"Computed rankings for exam ID {exam_id}")
            flash("Result engine computed class, section, and school ranks successfully!", "success")

        elif action == 'lock':
            exam.status = "Locked"
            db.session.commit()
            log_academic_action("Locked Results", f"Locked marks editing for exam ID {exam_id}")
            flash("Exam result locked! Marks can no longer be edited.", "warning")

        elif action == 'publish':
            exam.is_published = True
            ExamResult.query.filter_by(exam_id=exam.id).update({"is_published": True})
            db.session.commit()
            log_academic_action("Published Results", f"Released results for exam ID {exam_id}")
            flash("Results successfully published to portals!", "success")

        return redirect(url_for('academics.results'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    return render_template('academics/results.html', exams=exams)


# =========================================================
# 10. REPORT CARDS
# =========================================================
@academics_bp.route('/report-cards')
@login_required
@subscription_required
def report_cards():
    if not check_permission('admin', 'principal', 'teacher'):
        return redirect(url_for('dashboard.home'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    selected_exam_id = request.args.get('exam_id')
    results = []
    
    if selected_exam_id:
        results = ExamResult.query.filter_by(exam_id=selected_exam_id).order_by(ExamResult.rank).all()

    return render_template('academics/report_cards.html', exams=exams, results=results, selected_exam_id=int(selected_exam_id) if selected_exam_id else None)


# =========================================================
# 11. ACADEMIC REPORTS (MATPLOTLIB ANALYTICS)
# =========================================================
@academics_bp.route('/reports')
@login_required
@subscription_required
def reports():
    if not check_permission('admin', 'principal', 'teacher'):
        return redirect(url_for('dashboard.home'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    selected_exam_id = request.args.get('exam_id')
    
    toppers = []
    pass_count = 0
    fail_count = 0
    
    if selected_exam_id:
        toppers = ExamResult.query.filter_by(exam_id=selected_exam_id, status="Pass").order_by(ExamResult.rank).limit(5).all()
        pass_count = ExamResult.query.filter_by(exam_id=selected_exam_id, status="Pass").count()
        fail_count = ExamResult.query.filter_by(exam_id=selected_exam_id, status="Fail").count()

    return render_template(
        'academics/reports.html',
        exams=exams,
        toppers=toppers,
        pass_count=pass_count,
        fail_count=fail_count,
        selected_exam_id=int(selected_exam_id) if selected_exam_id else None
    )

@academics_bp.route('/reports/chart/<int:exam_id>')
@login_required
@subscription_required
def get_report_chart(exam_id):
    """GeneratesMatplotlib in-memory chart showing Pass/Fail distribution."""
    pass_cnt = ExamResult.query.filter_by(exam_id=exam_id, status="Pass").count()
    fail_cnt = ExamResult.query.filter_by(exam_id=exam_id, status="Fail").count()

    fig, ax = plt.subplots(figsize=(4, 3))
    ax.bar(['Pass', 'Fail'], [pass_cnt, fail_cnt], color=['#28a745', '#dc3545'])
    ax.set_title("Result Pass/Fail Ratio")
    ax.set_ylabel("Count")

    buf = io.BytesIO()
    plt.savefig(buf, format='png', bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)

    return send_file(buf, mimetype='image/png')


# =========================================================
# 12. PARENT PORTAL VIEW
# =========================================================
@academics_bp.route('/portal/parent')
@login_required
@subscription_required
def portal_parent():
    if not check_permission('parent'):
        return redirect(url_for('dashboard.home'))

    # Retrieve linked student(s). Typically maps parent email or phone.
    students = Student.query.filter(
        (Student.school_id == current_user.school_id) &
        ((Student.father_email == current_user.username) | (Student.mother_email == current_user.username))
    ).all()

    return render_template('academics/portal_parent.html', students=students)


# =========================================================
# 13. TEACHER PORTAL VIEW
# =========================================================
@academics_bp.route('/portal/teacher')
@login_required
@subscription_required
def portal_teacher():
    if not check_permission('teacher'):
        return redirect(url_for('dashboard.home'))

    teacher = Teacher.query.filter_by(school_id=current_user.school_id, id=current_user.employee_id).first_or_404()
    
    # Timetable allocation for this teacher
    timetable = AcademicTimetable.query.filter_by(school_id=current_user.school_id, teacher_id=teacher.id).all()
    
    # Invigilation exam schedules
    exam_duties = ExamSchedule.query.filter_by(school_id=current_user.school_id, teacher_id=teacher.id).all()

    return render_template('academics/portal_teacher.html', teacher=teacher, timetable=timetable, exam_duties=exam_duties)


# =========================================================
# 14. STUDENT PORTAL VIEW
# =========================================================
@academics_bp.route('/portal/student')
@login_required
@subscription_required
def portal_student():
    if not check_permission('student'):
        return redirect(url_for('dashboard.home'))

    student = Student.query.filter_by(school_id=current_user.school_id, id=current_user.student_id).first_or_404()
    
    # Timetable grid
    timetable = AcademicTimetable.query.filter_by(school_id=current_user.school_id, class_name=student.student_class, section=student.section).all()
    
    # Exam schedules
    exams = Exam.query.filter_by(school_id=current_user.school_id, class_name=student.student_class).all()
    
    # Results
    results = ExamResult.query.filter_by(student_id=student.id, is_published=True).all()
    
    # Seating arrangements
    seating = SeatingPlan.query.filter_by(student_id=student.id).all()

    return render_template(
        'academics/portal_student.html',
        student=student,
        timetable=timetable,
        exams=exams,
        results=results,
        seating=seating
    )


# =========================================================
# 15. REST APIS FOR EXTERNAL / AJAX INTEGRATION
# =========================================================
@academics_bp.route('/api/timetable/conflict-check', methods=['GET'])
@login_required
def api_timetable_conflict_check():
    """API endpoint to query potential conflicts before scheduling slots."""
    day = request.args.get('day')
    period_id = request.args.get('period_id')
    teacher_id = request.args.get('teacher_id')
    room_id = request.args.get('room_id')

    if not (day and period_id and teacher_id):
        return jsonify({"status": "error", "message": "Missing parameters"}), 400

    conflicts = detect_timetable_conflict(day, int(period_id), int(teacher_id), int(room_id) if room_id else None, current_user.school_id)
    return jsonify({
        "status": "success",
        "has_conflicts": len(conflicts) > 0,
        "conflicts": conflicts
    })

@academics_bp.route('/api/exams/schedules/<int:exam_id>', methods=['GET'])
@login_required
def api_exam_schedules(exam_id):
    """API to load subject schedules for AJAX rendering in seating allocation."""
    schedules = ExamSchedule.query.filter_by(exam_id=exam_id, school_id=current_user.school_id).all()
    data = []
    for s in schedules:
        data.append({
            "id": s.id,
            "subject_name": s.subject.subject_name,
            "date": s.date.strftime('%Y-%m-%d'),
            "time": f"{s.start_time.strftime('%I:%M %p')} - {s.end_time.strftime('%I:%M %p')}"
        })
    return jsonify({"status": "success", "schedules": data})


# =========================================================
# ⚙️ AUTOMATED RESOURCE SEEDER & SCHEDULERS
# =========================================================
def ensure_default_resources(school_id):
    from models.academics import AcademicPlannerSetting, SubjectWorkload
    # 1. Classes & Sections
    cls_objs = AcademicClass.query.filter_by(school_id=school_id).all()
    if not cls_objs:
        for c_name in ["LKG", "UKG", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"]:
            cls = AcademicClass(school_id=school_id, class_name=c_name, status=True)
            db.session.add(cls)
            db.session.flush()
            sec = AcademicSection(school_id=school_id, class_id=cls.id, section_name="A", capacity=40)
            db.session.add(sec)
        db.session.commit()
        cls_objs = AcademicClass.query.filter_by(school_id=school_id).all()

    # 2. Rooms
    rooms = Room.query.filter_by(school_id=school_id).all()
    if not rooms:
        for r_num in [101, 102, 103, 104, 105, 106, 107, 108, 109, 110]:
            r = Room(school_id=school_id, room_no=f"Room {r_num}", capacity=40)
            db.session.add(r)
        db.session.commit()

    # 3. Teachers
    teachers = Teacher.query.filter_by(school_id=school_id).all()
    if not teachers:
        names = [("John", "Doe"), ("Jane", "Smith"), ("Robert", "Johnson"), ("Mary", "Williams"), ("Michael", "Brown")]
        for idx, (fn, ln) in enumerate(names):
            t = Teacher(
                school_id=school_id,
                teacher_code=f"TCH00{idx+1}",
                first_name=fn,
                last_name=ln,
                email=f"{fn.lower()}@school.com",
                is_active=True
            )
            db.session.add(t)
        db.session.commit()

    # 4. Subjects
    for cls in cls_objs:
        subs = Subject.query.filter_by(school_id=school_id, class_name=cls.class_name).all()
        if not subs:
            subjects_to_create = [
                ("English", "ENG"),
                ("Mathematics", "MTH"),
                ("Science", "SCI"),
                ("Social Studies", "SST")
            ]
            for s_name, s_code in subjects_to_create:
                sub = Subject(
                    school_id=school_id,
                    class_name=cls.class_name,
                    subject_name=s_name,
                    subject_code=f"{s_code}{cls.class_name}",
                    status=True
                )
                db.session.add(sub)
            db.session.commit()

    # 5. Periods
    periods = Period.query.filter_by(school_id=school_id).all()
    if not periods:
        p_times = [
            ("Period 1", time(8, 0), time(8, 45)),
            ("Period 2", time(8, 45), time(9, 30)),
            ("Period 3", time(9, 30), time(10, 15)),
            ("Interval", time(10, 15), time(10, 30)),
            ("Period 4", time(10, 30), time(11, 15)),
            ("Period 5", time(11, 15), time(12, 0)),
            ("Period 6", time(12, 0), time(12, 45))
        ]
        for idx, (name, st_t, end_t) in enumerate(p_times):
            p = Period(
                school_id=school_id,
                period_name=name,
                period_no=idx+1,
                start_time=st_t,
                end_time=end_t,
                is_break=(name == "Interval")
            )
            db.session.add(p)
        db.session.commit()

    # 6. Students & StudentSubject mapping
    students = Student.query.filter_by(school_id=school_id).all()
    if not students:
        for cls in cls_objs:
            for idx in [1, 2]:
                st = Student(
                    school_id=school_id,
                    admission_no=f"ADM{cls.class_name}{idx}",
                    first_name=f"Student {cls.class_name} {idx}",
                    session="2026-2027",
                    student_class=cls.class_name,
                    section="A",
                    father_email=f"father_adm{cls.class_name}_{idx}@school.com",
                    mother_email=f"mother_adm{cls.class_name}_{idx}@school.com"
                )
                db.session.add(st)
                db.session.flush()

                subs = Subject.query.filter_by(school_id=school_id, class_name=cls.class_name).all()
                for sub in subs:
                    ss = StudentSubject(
                        school_id=school_id,
                        student_id=st.id,
                        subject_id=sub.id
                    )
                    db.session.add(ss)
        db.session.commit()

    # 7. Seed Subject Workloads
    for cls in cls_objs:
        subs = Subject.query.filter_by(school_id=school_id, class_name=cls.class_name).all()
        for sub in subs:
            wl = SubjectWorkload.query.filter_by(school_id=school_id, class_name=cls.class_name, subject_id=sub.id).first()
            if not wl:
                name_lower = sub.subject_name.lower()
                if "math" in name_lower:
                    p_week = 6
                elif "science" in name_lower:
                    p_week = 5
                elif "english" in name_lower:
                    p_week = 5
                elif "social" in name_lower:
                    p_week = 4
                else:
                    p_week = 5
                wl = SubjectWorkload(
                    school_id=school_id,
                    class_name=cls.class_name,
                    subject_id=sub.id,
                    periods_per_week=p_week
                )
                db.session.add(wl)
        db.session.commit()

    # 8. Seed Academic Planner Settings
    settings = AcademicPlannerSetting.query.filter_by(school_id=school_id).first()
    if not settings:
        settings = AcademicPlannerSetting(
            school_id=school_id,
            academic_year="2026-2027",
            working_days="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday",
            start_time=time(8, 0),
            period_duration=45,
            break_duration=15,
            lunch_break_after_period=3,
            max_teacher_workload=5
        )
        db.session.add(settings)
        db.session.commit()


def generate_weekly_timetable_internal(school_id):
    from models.academics import AcademicPlannerSetting, SubjectWorkload
    
    settings = AcademicPlannerSetting.query.filter_by(school_id=school_id).first()
    if not settings:
        settings = AcademicPlannerSetting(
            school_id=school_id,
            academic_year="2026-2027",
            working_days="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday",
            start_time=time(8, 0),
            period_duration=45,
            break_duration=15,
            lunch_break_after_period=3,
            max_teacher_workload=5
        )
        db.session.add(settings)
        db.session.commit()

    days = settings.working_days.split(",")
    max_teacher_workload = settings.max_teacher_workload or 5

    periods = Period.query.filter_by(school_id=school_id, is_break=False).order_by(Period.period_no).all()
    if not periods:
        return

    classes = AcademicClass.query.filter_by(school_id=school_id, status=True).all()
    rooms = Room.query.filter_by(school_id=school_id).all()
    teachers = Teacher.query.filter_by(school_id=school_id, is_active=True).all()

    if not rooms or not teachers:
        return

    # Clear existing weekly timetables
    AcademicTimetable.query.filter_by(school_id=school_id).delete()
    db.session.commit()

    # In-memory allocation tracking
    allocated_rooms = set() # (day, period_no, room_id)
    allocated_teachers = set() # (day, period_no, teacher_id)
    
    # Track daily teacher workloads
    teacher_workloads = {day: {t.id: 0 for t in teachers} for day in days}

    heavy_subjects_keywords = ["math", "science", "physics", "chemistry", "biology"]

    for cls in classes:
        sections = AcademicSection.query.filter_by(school_id=school_id, class_id=cls.id).all()
        if not sections:
            continue

        for sec in sections:
            # Load workloads for this class
            workloads = SubjectWorkload.query.filter_by(school_id=school_id, class_name=cls.class_name).all()
            if not workloads:
                continue

            # Create the demand list of periods to schedule: list of subject_id
            periods_to_schedule = []
            for wl in workloads:
                periods_to_schedule.extend([wl.subject_id] * wl.periods_per_week)

            # Sort demand: put heavy subjects first
            def is_heavy_subject(sub_id):
                sub = Subject.query.get(sub_id)
                if sub:
                    name_lower = sub.subject_name.lower()
                    return any(kw in name_lower for kw in heavy_subjects_keywords)
                return False

            periods_to_schedule.sort(key=is_heavy_subject, reverse=True)

            # Schedule grid for this section: grid[(day, period_no)] = subject_id
            section_grid = {}
            
            # Track daily subject scheduling to avoid duplicate mapping on same day
            daily_subject_scheduling = {day: set() for day in days}

            for sub_id in periods_to_schedule:
                sub = Subject.query.get(sub_id)
                if not sub:
                    continue

                # Find preferred teachers
                pref_teachers = Teacher.query.join(TeacherSubject).filter(
                    Teacher.school_id == school_id,
                    TeacherSubject.subject_id == sub.id,
                    Teacher.is_active == True
                ).all()
                search_teachers = pref_teachers if pref_teachers else teachers

                placed = False

                # Pass 1: Try to place respecting all constraints (no overlap, heavy subject spacing, daily workload limit)
                for day in days:
                    if placed:
                        break
                    for p_idx, period in enumerate(periods):
                        p_no = period.period_no
                        
                        # Already scheduled this class slot?
                        if (day, p_no) in section_grid:
                            continue

                        # Daily spread rule: Has this subject already been scheduled today?
                        workload_item = next((w for w in workloads if w.subject_id == sub_id), None)
                        p_week = workload_item.periods_per_week if workload_item else 5
                        if p_week <= len(days) and sub_id in daily_subject_scheduling[day]:
                            continue

                        # Heavy subject rule: Is this a heavy subject, and was the previous slot heavy?
                        is_heavy = is_heavy_subject(sub_id)
                        if is_heavy and p_idx > 0:
                            prev_period_no = periods[p_idx - 1].period_no
                            prev_sub_id = section_grid.get((day, prev_period_no))
                            if prev_sub_id and is_heavy_subject(prev_sub_id):
                                continue

                        # Find a free teacher and room
                        selected_teacher = None
                        selected_room = None

                        for t in search_teachers:
                            if (day, p_no, t.id) not in allocated_teachers:
                                if teacher_workloads[day].get(t.id, 0) < max_teacher_workload:
                                    selected_teacher = t
                                    break

                        for r in rooms:
                            if (day, p_no, r.id) not in allocated_rooms and r.capacity >= sec.capacity:
                                selected_room = r
                                break

                        if selected_teacher and selected_room:
                            # Schedule it!
                            section_grid[(day, p_no)] = sub_id
                            daily_subject_scheduling[day].add(sub_id)
                            allocated_rooms.add((day, p_no, selected_room.id))
                            allocated_teachers.add((day, p_no, selected_teacher.id))
                            teacher_workloads[day][selected_teacher.id] = teacher_workloads[day].get(selected_teacher.id, 0) + 1

                            slot = AcademicTimetable(
                                school_id=school_id,
                                class_name=cls.class_name,
                                section=sec.section_name,
                                day_of_week=day,
                                period_no=p_no,
                                start_time=period.start_time,
                                end_time=period.end_time,
                                subject_id=sub_id,
                                teacher_id=selected_teacher.id,
                                room_id=selected_room.id
                            )
                            db.session.add(slot)
                            placed = True
                            break

                # Pass 2: Relaxed constraints (ignore heavy subject spacing and daily workload limits)
                if not placed:
                    for day in days:
                        if placed:
                            break
                        for period in periods:
                            p_no = period.period_no
                            if (day, p_no) in section_grid:
                                continue

                            selected_teacher = None
                            selected_room = None

                            for t in search_teachers:
                                if (day, p_no, t.id) not in allocated_teachers:
                                    selected_teacher = t
                                    break

                            for r in rooms:
                                if (day, p_no, r.id) not in allocated_rooms and r.capacity >= sec.capacity:
                                    selected_room = r
                                    break

                            if selected_teacher and selected_room:
                                section_grid[(day, p_no)] = sub_id
                                daily_subject_scheduling[day].add(sub_id)
                                allocated_rooms.add((day, p_no, selected_room.id))
                                allocated_teachers.add((day, p_no, selected_teacher.id))
                                teacher_workloads[day][selected_teacher.id] = teacher_workloads[day].get(selected_teacher.id, 0) + 1

                                slot = AcademicTimetable(
                                    school_id=school_id,
                                    class_name=cls.class_name,
                                    section=sec.section_name,
                                    day_of_week=day,
                                    period_no=p_no,
                                    start_time=period.start_time,
                                    end_time=period.end_time,
                                    subject_id=sub_id,
                                    teacher_id=selected_teacher.id,
                                    room_id=selected_room.id
                                )
                                db.session.add(slot)
                                placed = True
                                break

                # Pass 3: Fallback (absolute double-booking prevention, but force scheduling with first room/teacher)
                if not placed:
                    for day in days:
                        if placed:
                            break
                        for period in periods:
                            p_no = period.period_no
                            if (day, p_no) in section_grid:
                                continue
                            
                            t = search_teachers[0]
                            r = rooms[0]

                            section_grid[(day, p_no)] = sub_id
                            allocated_rooms.add((day, p_no, r.id))
                            allocated_teachers.add((day, p_no, t.id))

                            slot = AcademicTimetable(
                                school_id=school_id,
                                class_name=cls.class_name,
                                section=sec.section_name,
                                day_of_week=day,
                                period_no=p_no,
                                start_time=period.start_time,
                                end_time=period.end_time,
                                subject_id=sub_id,
                                teacher_id=t.id,
                                room_id=r.id
                            )
                            db.session.add(slot)
                            placed = True
                            break


# =========================================================
# ⚙️ AUTOMATED EXAMS SCHEDULER ENGINE
# =========================================================
@academics_bp.route('/exams/auto-schedule', methods=['POST'])
@login_required
@subscription_required
def auto_schedule_exams():
    if not check_permission('admin', 'principal'):
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('academics.exams'))

    exam_name = request.form.get('name')
    session_id = int(request.form.get('session_id'))
    exam_type_id = int(request.form.get('exam_type_id'))
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    start_time_str = request.form.get('start_time')
    end_time_str = request.form.get('end_time')

    start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
    end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
    start_time = datetime.strptime(start_time_str, '%H:%M').time()
    end_time = datetime.strptime(end_time_str, '%H:%M').time()

    school_id = current_user.school_id

    # Auto-seed default resources if anything is missing to guarantee instant generation
    ensure_default_resources(school_id)

    # Auto-generate regular weekly academic timetable by default
    generate_weekly_timetable_internal(school_id)

    # 1. Fetch resources
    classes = AcademicClass.query.filter_by(school_id=school_id, status=True).all()
    rooms = Room.query.filter_by(school_id=school_id).all()
    teachers = Teacher.query.filter_by(school_id=school_id, is_active=True).all()

    if not rooms or not teachers:
        flash("Error: At least one Room and one Teacher must be configured to run auto-allocation.", "danger")
        return redirect(url_for('academics.exams'))

    # Calculate valid dates (excluding Sundays)
    current_date = start_date
    available_dates = []
    while current_date <= end_date:
        if current_date.weekday() != 6:  # Skip Sunday
            available_dates.append(current_date)
        current_date += timedelta(days=1)

    if not available_dates:
        flash("Error: No working days available in the selected date range.", "danger")
        return redirect(url_for('academics.exams'))

    # Delete all existing schedules and exams of this session and type first to start clean and avoid conflicts with old run
    old_exams = Exam.query.filter_by(
        school_id=school_id,
        session_id=session_id,
        exam_type_id=exam_type_id
    ).all()
    
    old_exam_ids = [oe.id for oe in old_exams]
    if old_exam_ids:
        # Delete seating plans first (depends on exam)
        SeatingPlan.query.filter(SeatingPlan.exam_id.in_(old_exam_ids)).delete(synchronize_session=False)
        # Delete marks (depends on schedule)
        ExamMark.query.filter(ExamMark.exam_schedule_id.in_(
            db.session.query(ExamSchedule.id).filter(ExamSchedule.exam_id.in_(old_exam_ids))
        )).delete(synchronize_session=False)
        # Delete attendance
        ExamAttendance.query.filter(ExamAttendance.exam_schedule_id.in_(
            db.session.query(ExamSchedule.id).filter(ExamSchedule.exam_id.in_(old_exam_ids))
        )).delete(synchronize_session=False)
        # Delete schedules
        ExamSchedule.query.filter(ExamSchedule.exam_id.in_(old_exam_ids)).delete(synchronize_session=False)
        # Delete results
        ExamResult.query.filter(ExamResult.exam_id.in_(old_exam_ids)).delete(synchronize_session=False)
        # Delete exams
        Exam.query.filter(Exam.id.in_(old_exam_ids)).delete(synchronize_session=False)
        db.session.commit()

    # Now, track allocated rooms and teachers in-memory to prevent overlaps
    allocated_rooms = set() # elements: (date, room_no)
    allocated_teachers = set() # elements: (date, teacher_id)

    # Fetch any other existing schedules in the school to prevent overlap with them
    other_schedules = ExamSchedule.query.filter(
        ExamSchedule.school_id == school_id,
        ExamSchedule.date >= start_date,
        ExamSchedule.date <= end_date
    ).all()
    for osch in other_schedules:
        if osch.start_time < end_time and osch.end_time > start_time:
            allocated_rooms.add((osch.date, osch.room_no))
            if osch.teacher_id:
                allocated_teachers.add((osch.date, osch.teacher_id))

    schedule_count = 0

    for cls in classes:
        # Get active sections
        sections = AcademicSection.query.filter_by(school_id=school_id, class_id=cls.id).all()
        if not sections:
            continue

        # Get subjects for this class
        subjects = Subject.query.filter_by(school_id=school_id, class_name=cls.class_name, status=True).all()
        if not subjects:
            continue

        # Create the Exam Master for this class
        exam = Exam(
            school_id=school_id,
            session_id=session_id,
            exam_type_id=exam_type_id,
            name=f"{exam_name} - Class {cls.class_name}",
            class_name=cls.class_name,
            start_date=start_date,
            end_date=end_date,
            status="Draft"
        )
        db.session.add(exam)
        db.session.flush() # Populate exam.id

        # Allocate each subject to a date
        for date_idx, sub in enumerate(subjects):
            if date_idx >= len(available_dates):
                break # Not enough dates, stop scheduling
            
            exam_date = available_dates[date_idx]

            for sec in sections:
                # Find available room and teacher invigilator
                selected_room = None
                selected_teacher = None

                # Search room
                for r in rooms:
                    if (exam_date, r.room_no) not in allocated_rooms and r.capacity >= sec.capacity:
                        selected_room = r
                        break

                # Search teacher
                for t in teachers:
                    if (exam_date, t.id) not in allocated_teachers:
                        selected_teacher = t
                        break

                # Fallback to first room/teacher if none are free
                if not selected_room:
                    selected_room = rooms[0]
                if not selected_teacher:
                    selected_teacher = teachers[0]

                # Mark as allocated in memory
                allocated_rooms.add((exam_date, selected_room.room_no))
                allocated_teachers.add((exam_date, selected_teacher.id))

                # Create schedule slot
                sched = ExamSchedule(
                    school_id=school_id,
                    exam_id=exam.id,
                    subject_id=sub.id,
                    section=sec.section_name,
                    date=exam_date,
                    start_time=start_time,
                    end_time=end_time,
                    room_no=selected_room.room_no,
                    teacher_id=selected_teacher.id,
                    max_marks=100.0,
                    passing_marks=33.0
                )
                db.session.add(sched)
                schedule_count += 1

    db.session.commit()
    log_academic_action("Auto Scheduled Exams", f"Auto scheduled {schedule_count} exam subjects class-wise.")
    flash(f"Auto-Scheduling Engine completed: created/scheduled {schedule_count} exam schedules successfully!", "success")
    return redirect(url_for('academics.exams'))


# =========================================================
# 📅 WEEKLY ACADEMIC TIMETABLE AUTO-SCHEDULER ENGINE
# =========================================================
@academics_bp.route('/timetable/auto-schedule', methods=['POST'])
@login_required
@subscription_required
def auto_schedule_timetable():
    if not check_permission('admin', 'principal'):
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('academics.timetable'))

    school_id = current_user.school_id

    # Get working configuration
    periods = Period.query.filter_by(school_id=school_id, is_break=False).order_by(Period.period_no).all()
    if not periods:
        flash("Error: Please configure school periods first.", "danger")
        return redirect(url_for('academics.timetable'))

    classes = AcademicClass.query.filter_by(school_id=school_id, status=True).all()
    rooms = Room.query.filter_by(school_id=school_id).all()
    teachers = Teacher.query.filter_by(school_id=school_id, is_active=True).all()
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    if not rooms or not teachers:
        flash("Error: Rooms and Teachers must be configured to run auto-allocation.", "danger")
        return redirect(url_for('academics.timetable'))

    # Clear all existing weekly timetables to rebuild
    AcademicTimetable.query.filter_by(school_id=school_id).delete()
    db.session.commit()

    slot_count = 0

    allocated_rooms = set() # (day, period_no, room_id)
    allocated_teachers = set() # (day, period_no, teacher_id)

    for cls in classes:
        sections = AcademicSection.query.filter_by(school_id=school_id, class_id=cls.id).all()
        if not sections:
            continue

        subjects = Subject.query.filter_by(school_id=school_id, class_name=cls.class_name, status=True).all()
        if not subjects:
            continue

        for sec in sections:
            # Cycle through subjects to distribute them evenly across periods
            subject_cycle_idx = 0

            for day in days:
                for period in periods:
                    # Select subject from cycle
                    sub = subjects[subject_cycle_idx % len(subjects)]
                    subject_cycle_idx += 1

                    # Find available teacher and room for this day/period
                    selected_teacher = None
                    selected_room = None

                    # Check TeacherSubject mapping first, or fall back to any teacher
                    pref_teachers = Teacher.query.join(TeacherSubject).filter(
                        Teacher.school_id == school_id,
                        TeacherSubject.subject_id == sub.id,
                        Teacher.is_active == True
                    ).all()

                    # Find free teacher
                    search_list = pref_teachers if pref_teachers else teachers
                    for t in search_list:
                        if (day, period.period_no, t.id) not in allocated_teachers:
                            selected_teacher = t
                            break

                    # Find free room
                    for r in rooms:
                        if (day, period.period_no, r.id) not in allocated_rooms and r.capacity >= sec.capacity:
                            selected_room = r
                            break

                    # Fallbacks
                    if not selected_teacher:
                        selected_teacher = teachers[0]
                    if not selected_room:
                        selected_room = rooms[0]

                    # Track allocation
                    allocated_rooms.add((day, period.period_no, selected_room.id))
                    allocated_teachers.add((day, period.period_no, selected_teacher.id))

                    # Create timetable slot
                    slot = AcademicTimetable(
                        school_id=school_id,
                        class_name=cls.class_name,
                        section=sec.section_name,
                        day_of_week=day,
                        period_no=period.period_no,
                        start_time=period.start_time,
                        end_time=period.end_time,
                        subject_id=sub.id,
                        teacher_id=selected_teacher.id,
                        room_id=selected_room.id
                    )
                    db.session.add(slot)
                    slot_count += 1

    db.session.commit()
    log_academic_action("Auto Scheduled Timetable", f"Re-allocated {slot_count} timetable slots class-wide.")
    flash(f"Weekly Timetable Auto-Scheduling Engine complete: generated {slot_count} slots!", "success")
    return redirect(url_for('academics.timetable'))


# =========================================================
# 📄 BULK PDF / EXCEL DOWNLOAD CHANNELS
# =========================================================
@academics_bp.route('/exams/pdf/<int:exam_id>')
@login_required
@subscription_required
def export_exam_timetable_pdf(exam_id):
    exam = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    schedules = ExamSchedule.query.filter_by(exam_id=exam.id).order_by(ExamSchedule.date, ExamSchedule.start_time).all()

    if not schedules:
        return "No schedules found", 400

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'ExTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, alignment=1, spaceAfter=20
    )
    th_style = ParagraphStyle(
        'ExTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.white, alignment=1
    )
    tb_style = ParagraphStyle(
        'ExTB', parent=styles['Normal'], fontName='Helvetica', fontSize=9, alignment=1
    )

    story = [Paragraph(f"EXAMINATION TIMETABLE - {exam.name.upper()}", title_style)]

    table_data = [[
        Paragraph("Date", th_style),
        Paragraph("Subject", th_style),
        Paragraph("Section", th_style),
        Paragraph("Time", th_style),
        Paragraph("Room", th_style),
        Paragraph("Invigilator", th_style)
    ]]

    for sc in schedules:
        table_data.append([
            Paragraph(sc.date.strftime("%d %b %Y"), tb_style),
            Paragraph(sc.subject.subject_name, tb_style),
            Paragraph(sc.section or "All", tb_style),
            Paragraph(f"{sc.start_time.strftime('%I:%M %p')} - {sc.end_time.strftime('%I:%M %p')}", tb_style),
            Paragraph(sc.room_no or "N/A", tb_style),
            Paragraph(f"{sc.teacher.first_name} {sc.teacher.last_name or ''}" if sc.teacher_id else "N/A", tb_style)
        ])

    t = Table(table_data, colWidths=[1.1*inch, 1.8*inch, 0.8*inch, 1.5*inch, 0.8*inch, 1.5*inch])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0b1e3c')),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
    ]))
    story.append(t)

    doc.build(story)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Exam_Timetable_{exam.name.replace(' ', '_')}.pdf",
        mimetype="application/pdf"
    )

@academics_bp.route('/exams/pdf/all/<int:session_id>/<int:exam_type_id>')
@login_required
@subscription_required
def export_all_exam_timetable_pdf(session_id, exam_type_id):
    session = ExamSession.query.filter_by(id=session_id, school_id=current_user.school_id).first_or_404()
    etype = ExamType.query.filter_by(id=exam_type_id, school_id=current_user.school_id).first_or_404()
    
    exams = Exam.query.filter_by(
        school_id=current_user.school_id,
        session_id=session_id,
        exam_type_id=exam_type_id
    ).order_by(Exam.class_name).all()

    if not exams:
        flash("No exams found for this session and type.", "warning")
        return redirect(url_for('academics.exams'))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        'ExTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, alignment=1, spaceAfter=20
    )
    th_style = ParagraphStyle(
        'ExTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=10, textColor=colors.white, alignment=1
    )
    tb_style = ParagraphStyle(
        'ExTB', parent=styles['Normal'], fontName='Helvetica', fontSize=9, alignment=1
    )

    story = []
    
    first = True
    for exam in exams:
        schedules = ExamSchedule.query.filter_by(exam_id=exam.id).order_by(ExamSchedule.date, ExamSchedule.start_time).all()
        if not schedules:
            continue
            
        if not first:
            story.append(PageBreak())
        first = False

        story.append(Paragraph(f"EXAMINATION TIMETABLE - {exam.name.upper()}", title_style))
        story.append(Spacer(1, 10))

        table_data = [[
            Paragraph("Date", th_style),
            Paragraph("Subject", th_style),
            Paragraph("Section", th_style),
            Paragraph("Time", th_style),
            Paragraph("Room", th_style),
            Paragraph("Invigilator", th_style)
        ]]

        for sc in schedules:
            table_data.append([
                Paragraph(sc.date.strftime("%d %b %Y"), tb_style),
                Paragraph(sc.subject.subject_name, tb_style),
                Paragraph(sc.section or "All", tb_style),
                Paragraph(f"{sc.start_time.strftime('%I:%M %p')} - {sc.end_time.strftime('%I:%M %p')}", tb_style),
                Paragraph(sc.room_no or "N/A", tb_style),
                Paragraph(f"{sc.teacher.first_name} {sc.teacher.last_name or ''}" if sc.teacher_id else "N/A", tb_style)
            ])

        t = Table(table_data, colWidths=[1.1*inch, 1.8*inch, 0.8*inch, 1.5*inch, 0.8*inch, 1.5*inch])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0b1e3c')),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('BOTTOMPADDING', (0,0), (-1,-1), 6),
            ('TOPPADDING', (0,0), (-1,-1), 6),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
        ]))
        story.append(t)

    if not story:
        return "No schedules found", 400

    doc.build(story)
    buffer.seek(0)
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"All_Exams_Timetable_{session.name}_{etype.name.replace(' ', '_')}.pdf",
        mimetype="application/pdf"
    )

@academics_bp.route('/exams/excel/<int:exam_id>')
@login_required
@subscription_required
def export_exam_timetable_excel(exam_id):
    exam = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    schedules = ExamSchedule.query.filter_by(exam_id=exam.id).order_by(ExamSchedule.date, ExamSchedule.start_time).all()

    data = []
    for sc in schedules:
        data.append({
            "Date": sc.date.strftime("%Y-%m-%d"),
            "Subject Code": sc.subject.subject_code or "",
            "Subject Name": sc.subject.subject_name,
            "Class": exam.class_name,
            "Section": sc.section or "All",
            "Start Time": sc.start_time.strftime("%I:%M %p"),
            "End Time": sc.end_time.strftime("%I:%M %p"),
            "Room": sc.room_no or "",
            "Invigilator": f"{sc.teacher.first_name} {sc.teacher.last_name or ''}".strip() if sc.teacher_id else ""
        })

    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Exam Timetable")
    output.seek(0)

    filename = f"Exam_Timetable_{exam.name.replace(' ', '_')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@academics_bp.route('/exams/excel/all/<int:session_id>/<int:exam_type_id>')
@login_required
@subscription_required
def export_all_exam_timetable_excel(session_id, exam_type_id):
    session = ExamSession.query.filter_by(id=session_id, school_id=current_user.school_id).first_or_404()
    etype = ExamType.query.filter_by(id=exam_type_id, school_id=current_user.school_id).first_or_404()

    exams = Exam.query.filter_by(
        school_id=current_user.school_id,
        session_id=session_id,
        exam_type_id=exam_type_id
    ).order_by(Exam.class_name).all()

    if not exams:
        flash("No exams found for this session and type.", "warning")
        return redirect(url_for('academics.exams'))

    output = io.BytesIO()
    has_data = False
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for exam in exams:
            schedules = ExamSchedule.query.filter_by(exam_id=exam.id).order_by(ExamSchedule.date, ExamSchedule.start_time).all()
            if not schedules:
                continue
                
            data = []
            for sc in schedules:
                data.append({
                    "Date": sc.date.strftime("%Y-%m-%d"),
                    "Subject Code": sc.subject.subject_code or "",
                    "Subject Name": sc.subject.subject_name,
                    "Class": exam.class_name,
                    "Section": sc.section or "All",
                    "Start Time": sc.start_time.strftime("%I:%M %p"),
                    "End Time": sc.end_time.strftime("%I:%M %p"),
                    "Room": sc.room_no or "",
                    "Invigilator": f"{sc.teacher.first_name} {sc.teacher.last_name or ''}".strip() if sc.teacher_id else ""
                })
            
            if data:
                df = pd.DataFrame(data)
                sheet_name = f"Class {exam.class_name}"[:31]
                df.to_excel(writer, index=False, sheet_name=sheet_name)
                has_data = True

    if not has_data:
        flash("No exam schedules found to export.", "warning")
        return redirect(url_for('academics.exams'))

    output.seek(0)
    filename = f"All_Exams_Timetable_{session.name}_{etype.name.replace(' ', '_')}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@academics_bp.route('/timetable/excel/<string:class_name>/<string:section>')
@login_required
@subscription_required
def export_timetable_excel(class_name, section):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    periods = Period.query.filter_by(school_id=current_user.school_id).order_by(Period.period_no).all()

    if not periods:
        return "Configure periods first", 400

    records = AcademicTimetable.query.filter_by(
        school_id=current_user.school_id,
        class_name=class_name,
        section=section
    ).all()

    grid = {d: {} for d in days}
    for r in records:
        grid[r.day_of_week][r.period_no] = r

    rows = []
    for d in days:
        row = {"Day": d}
        for p in periods:
            slot = grid[d].get(p.period_no)
            if slot:
                row[p.period_name] = f"{slot.subject.subject_name} ({slot.teacher.first_name}) - Room {slot.room_ref.room_no if slot.room_id else 'N/A'}"
            else:
                row[p.period_name] = "-"
        rows.append(row)

    df = pd.DataFrame(rows)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Timetable")
    output.seek(0)

    filename = f"Timetable_Class_{class_name}_{section}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@academics_bp.route('/timetable/pdf/all')
@login_required
@subscription_required
def export_all_timetable_pdf():
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    periods = Period.query.filter_by(school_id=current_user.school_id).order_by(Period.period_no).all()

    if not periods:
        return "Configure periods first", 400

    classes = AcademicClass.query.filter_by(school_id=current_user.school_id, status=True).all()
    
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'TTableTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, alignment=1, spaceAfter=20
    )
    th_style = ParagraphStyle(
        'TTableTH', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9, textColor=colors.white, alignment=1
    )
    tb_style = ParagraphStyle(
        'TTableTB', parent=styles['Normal'], fontName='Helvetica', fontSize=8, alignment=1
    )

    story = []
    first = True

    for cls in classes:
        sections = AcademicSection.query.filter_by(school_id=current_user.school_id, class_id=cls.id).all()
        for sec in sections:
            records = AcademicTimetable.query.filter_by(
                school_id=current_user.school_id,
                class_name=cls.class_name,
                section=sec.section_name
            ).all()

            if not records:
                continue

            if not first:
                story.append(PageBreak())
            first = False

            story.append(Paragraph(f"ACADEMIC WEEKLY TIMETABLE - CLASS {cls.class_name} ({sec.section_name})", title_style))
            story.append(Spacer(1, 10))

            grid = {d: {} for d in days}
            for r in records:
                grid[r.day_of_week][r.period_no] = r

            header = [Paragraph("Day", th_style)]
            for p in periods:
                header.append(Paragraph(f"{p.period_name}<br/><font size=6>{p.start_time.strftime('%I:%M %p')} - {p.end_time.strftime('%I:%M %p')}</font>", th_style))
            
            table_data = [header]

            for d in days:
                row = [Paragraph(d, ParagraphStyle('TTableDay', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=9))]
                for p in periods:
                    slot = grid[d].get(p.period_no)
                    if slot:
                        txt = f"<b>{slot.subject.subject_name}</b><br/>{slot.teacher.first_name}<br/>{slot.room_ref.room_no if slot.room_id else 'N/A'}"
                        row.append(Paragraph(txt, tb_style))
                    else:
                        row.append(Paragraph("-", tb_style))
                table_data.append(row)

            col_w = [1.0*inch] + [6.5*inch / len(periods)] * len(periods)
            t = Table(table_data, colWidths=col_w)
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0b1e3c')),
                ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                ('TOPPADDING', (0,0), (-1,-1), 6),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cccccc')),
            ]))
            story.append(t)

    if not story:
        return "No timetables found to export", 400

    doc.build(story)
    buffer.seek(0)
    
    return send_file(
        buffer,
        as_attachment=True,
        download_name="School_All_Timetables.pdf",
        mimetype="application/pdf"
    )

@academics_bp.route('/timetable/excel/all')
@login_required
@subscription_required
def export_all_timetable_excel():
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    periods = Period.query.filter_by(school_id=current_user.school_id).order_by(Period.period_no).all()

    if not periods:
        return "Configure periods first", 400

    classes = AcademicClass.query.filter_by(school_id=current_user.school_id, status=True).all()
    
    output = io.BytesIO()
    has_sheets = False
    
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        for cls in classes:
            sections = AcademicSection.query.filter_by(school_id=current_user.school_id, class_id=cls.id).all()
            for sec in sections:
                records = AcademicTimetable.query.filter_by(
                    school_id=current_user.school_id,
                    class_name=cls.class_name,
                    section=sec.section_name
                ).all()

                if not records:
                    continue

                grid = {d: {} for d in days}
                for r in records:
                    grid[r.day_of_week][r.period_no] = r

                rows = []
                for d in days:
                    row = {"Day": d}
                    for p in periods:
                        slot = grid[d].get(p.period_no)
                        if slot:
                            row[p.period_name] = f"{slot.subject.subject_name} ({slot.teacher.first_name}) - Room {slot.room_ref.room_no if slot.room_id else 'N/A'}"
                        else:
                            row[p.period_name] = "-"
                    rows.append(row)

                df = pd.DataFrame(rows)
                sheet_name = f"{cls.class_name}-{sec.section_name}"[:31]
                df.to_excel(writer, index=False, sheet_name=sheet_name)
                has_sheets = True

    if not has_sheets:
        return "No timetables found to export", 400

    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name="School_All_Timetables.xlsx",
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# =========================================================
# ⚙️ ACADEMIC MASTER PLANNER & SETTINGS ROUTES
# =========================================================
@academics_bp.route('/settings', methods=['GET'])
@login_required
@subscription_required
def settings():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))
    return render_template('academics/settings.html')


@academics_bp.route('/planner', methods=['GET', 'POST'])
@login_required
@subscription_required
def planner():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))
    
    school_id = current_user.school_id
    
    # Get or create planner settings
    settings = AcademicPlannerSetting.query.filter_by(school_id=school_id).first()
    if not settings:
        settings = AcademicPlannerSetting(
            school_id=school_id,
            academic_year="2026-2027",
            working_days="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday",
            start_time=time(8, 0),
            period_duration=45,
            break_duration=15,
            lunch_break_after_period=3,
            max_teacher_workload=5
        )
        db.session.add(settings)
        db.session.commit()

    if request.method == 'POST':
        settings.academic_year = request.form.get('academic_year', '2026-2027')
        
        # Handle working days checkboxes
        days_list = request.form.getlist('working_days')
        if days_list:
            settings.working_days = ",".join(days_list)
        else:
            settings.working_days = "Monday,Tuesday,Wednesday,Thursday,Friday,Saturday"
            
        start_time_str = request.form.get('start_time', '08:00')
        try:
            settings.start_time = datetime.strptime(start_time_str, '%H:%M').time()
        except ValueError:
            settings.start_time = time(8, 0)
            
        settings.period_duration = int(request.form.get('period_duration', 45))
        settings.break_duration = int(request.form.get('break_duration', 15))
        settings.lunch_break_after_period = int(request.form.get('lunch_break_after_period', 3))
        settings.max_teacher_workload = int(request.form.get('max_teacher_workload', 5))
        
        db.session.commit()
        log_academic_action("Updated Planner Settings", f"Academic Year: {settings.academic_year}, Workload Limit: {settings.max_teacher_workload}")
        flash("Academic Planner Settings updated successfully!", "success")
        return redirect(url_for('academics.planner'))

    # Load resources for cockpit display
    sessions = ExamSession.query.filter_by(school_id=school_id).all()
    exam_types = ExamType.query.filter_by(school_id=school_id).all()
    classes = AcademicClass.query.filter_by(school_id=school_id, status=True).all()
    
    # Group subjects and workloads by class
    class_subjects = {}
    for cls in classes:
        subs = Subject.query.filter_by(school_id=school_id, class_name=cls.class_name, status=True).all()
        workloads = {}
        for sub in subs:
            wl = SubjectWorkload.query.filter_by(school_id=school_id, class_name=cls.class_name, subject_id=sub.id).first()
            workloads[sub.id] = wl.periods_per_week if wl else 5
        class_subjects[cls.class_name] = {
            'subjects': subs,
            'workloads': workloads
        }

    return render_template(
        'academics/planner.html',
        settings=settings,
        sessions=sessions,
        exam_types=exam_types,
        classes=classes,
        class_subjects=class_subjects
    )


@academics_bp.route('/planner/workload', methods=['POST'])
@login_required
@subscription_required
def planner_workload():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))
        
    school_id = current_user.school_id
    
    class_name = request.form.get('class_name')
    if not class_name:
        flash("Invalid Class Name provided", "danger")
        return redirect(url_for('academics.planner'))
        
    subs = Subject.query.filter_by(school_id=school_id, class_name=class_name, status=True).all()
    for sub in subs:
        wl_val = request.form.get(f'workload_{sub.id}')
        if wl_val is not None:
            try:
                periods = int(wl_val)
            except ValueError:
                periods = 5
                
            wl = SubjectWorkload.query.filter_by(school_id=school_id, class_name=class_name, subject_id=sub.id).first()
            if not wl:
                wl = SubjectWorkload(
                    school_id=school_id,
                    class_name=class_name,
                    subject_id=sub.id,
                    periods_per_week=periods
                )
                db.session.add(wl)
            else:
                wl.periods_per_week = periods
                
    db.session.commit()
    log_academic_action("Updated Subject Workloads", f"Configured workloads for Class {class_name}")
    flash(f"Workloads for Class {class_name} updated successfully!", "success")
    return redirect(url_for('academics.planner'))


@academics_bp.route('/planner/generate', methods=['POST'])
@login_required
@subscription_required
def planner_generate():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))

    school_id = current_user.school_id
    
    exam_name = request.form.get('exam_name')
    session_id_val = request.form.get('session_id')
    exam_type_id_val = request.form.get('exam_type_id')
    start_date_str = request.form.get('start_date')
    end_date_str = request.form.get('end_date')
    start_time_str = request.form.get('start_time', '09:00')
    end_time_str = request.form.get('end_time', '12:00')

    if not all([exam_name, session_id_val, exam_type_id_val, start_date_str, end_date_str]):
        flash("Error: Missing required parameters for scheduling.", "danger")
        return redirect(url_for('academics.planner'))

    try:
        session_id = int(session_id_val)
        exam_type_id = int(exam_type_id_val)
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        start_time = datetime.strptime(start_time_str, '%H:%M').time()
        end_time = datetime.strptime(end_time_str, '%H:%M').time()
    except Exception as e:
        flash(f"Error parsing date/time parameters: {e}", "danger")
        return redirect(url_for('academics.planner'))

    # 1. Zero-Configuration Seeder: ensure all required structures exist
    ensure_default_resources(school_id)

    # 2. Re-generate regular weekly academic timetable
    generate_weekly_timetable_internal(school_id)

    # 3. Fetch resources for Exams & Seating
    classes = AcademicClass.query.filter_by(school_id=school_id, status=True).all()
    rooms = Room.query.filter_by(school_id=school_id).all()
    teachers = Teacher.query.filter_by(school_id=school_id, is_active=True).all()

    if not rooms or not teachers:
        flash("Error: At least one Room and one Teacher must be configured to run auto-allocation.", "danger")
        return redirect(url_for('academics.planner'))

    # Calculate valid dates (excluding Sundays)
    current_date = start_date
    available_dates = []
    while current_date <= end_date:
        if current_date.weekday() != 6:  # Skip Sunday
            available_dates.append(current_date)
        current_date += timedelta(days=1)

    if not available_dates:
        flash("Error: No working days available in the selected date range.", "danger")
        return redirect(url_for('academics.planner'))

    # 4. Clean old exam data for this session and type to avoid conflicts
    old_exams = Exam.query.filter_by(
        school_id=school_id,
        session_id=session_id,
        exam_type_id=exam_type_id
    ).all()
    
    old_exam_ids = [oe.id for oe in old_exams]
    if old_exam_ids:
        SeatingPlan.query.filter(SeatingPlan.exam_id.in_(old_exam_ids)).delete(synchronize_session=False)
        ExamMark.query.filter(ExamMark.exam_schedule_id.in_(
            db.session.query(ExamSchedule.id).filter(ExamSchedule.exam_id.in_(old_exam_ids))
        )).delete(synchronize_session=False)
        ExamAttendance.query.filter(ExamAttendance.exam_schedule_id.in_(
            db.session.query(ExamSchedule.id).filter(ExamSchedule.exam_id.in_(old_exam_ids))
        )).delete(synchronize_session=False)
        ExamSchedule.query.filter(ExamSchedule.exam_id.in_(old_exam_ids)).delete(synchronize_session=False)
        ExamResult.query.filter(ExamResult.exam_id.in_(old_exam_ids)).delete(synchronize_session=False)
        Exam.query.filter(Exam.id.in_(old_exam_ids)).delete(synchronize_session=False)
        db.session.commit()

    # Track allocated rooms and teachers in-memory to prevent overlaps
    allocated_rooms = set() # elements: (date, room_no)
    allocated_teachers = set() # elements: (date, teacher_id)

    # Fetch any other existing schedules in the school to prevent overlap
    other_schedules = ExamSchedule.query.filter(
        ExamSchedule.school_id == school_id,
        ExamSchedule.date >= start_date,
        ExamSchedule.date <= end_date
    ).all()
    for osch in other_schedules:
        if osch.start_time < end_time and osch.end_time > start_time:
            allocated_rooms.add((osch.date, osch.room_no))
            if osch.teacher_id:
                allocated_teachers.add((osch.date, osch.teacher_id))

    exam_count = 0
    schedule_count = 0
    seating_count = 0
    result_count = 0

    # Process each class
    for cls in classes:
        sections = AcademicSection.query.filter_by(school_id=school_id, class_id=cls.id).all()
        if not sections:
            continue

        subjects = Subject.query.filter_by(school_id=school_id, class_name=cls.class_name, status=True).all()
        if not subjects:
            continue

        # Create Exam Master
        exam = Exam(
            school_id=school_id,
            session_id=session_id,
            exam_type_id=exam_type_id,
            name=f"{exam_name} - Class {cls.class_name}",
            class_name=cls.class_name,
            start_date=start_date,
            end_date=end_date,
            status="Draft"
        )
        db.session.add(exam)
        db.session.flush() # populate exam.id
        exam_count += 1

        # Allocate each subject to a date
        for date_idx, sub in enumerate(subjects):
            if date_idx >= len(available_dates):
                break
            
            exam_date = available_dates[date_idx]

            for sec in sections:
                # Find room & teacher invigilator
                selected_room = None
                selected_teacher = None

                for r in rooms:
                    if (exam_date, r.room_no) not in allocated_rooms and r.capacity >= sec.capacity:
                        selected_room = r
                        break

                for t in teachers:
                    if (exam_date, t.id) not in allocated_teachers:
                        selected_teacher = t
                        break

                if not selected_room:
                    selected_room = rooms[0]
                if not selected_teacher:
                    selected_teacher = teachers[0]

                # Book room & teacher in memory
                allocated_rooms.add((exam_date, selected_room.room_no))
                allocated_teachers.add((exam_date, selected_teacher.id))

                # Create Schedule
                sched = ExamSchedule(
                    school_id=school_id,
                    exam_id=exam.id,
                    subject_id=sub.id,
                    section=sec.section_name,
                    date=exam_date,
                    start_time=start_time,
                    end_time=end_time,
                    room_no=selected_room.room_no,
                    teacher_id=selected_teacher.id,
                    max_marks=100.0,
                    passing_marks=33.0
                )
                db.session.add(sched)
                db.session.flush() # populate sched.id
                schedule_count += 1

                # 5. Seating Plan: Allocate desk numbers sequentially
                students_in_subject = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
                    Student.school_id == school_id,
                    Student.student_class == cls.class_name,
                    Student.section == sec.section_name,
                    StudentSubject.subject_id == sub.id
                ).order_by(Student.first_name).all()

                student_idx = 0
                all_rooms = [selected_room] + [r for r in rooms if r.id != selected_room.id]
                
                for rm in all_rooms:
                    if student_idx >= len(students_in_subject):
                        break
                    for seat in range(1, rm.capacity + 1):
                        if student_idx >= len(students_in_subject):
                            break
                        st = students_in_subject[student_idx]
                        plan = SeatingPlan(
                            school_id=school_id,
                            exam_id=exam.id,
                            exam_schedule_id=sched.id,
                            room_id=rm.id,
                            student_id=st.id,
                            seat_no=f"Desk-{seat}"
                        )
                        db.session.add(plan)
                        student_idx += 1
                        seating_count += 1

        # 6. Seed Empty Exam Results for all students in this class/sections
        student_query = Student.query.filter_by(school_id=school_id, student_class=cls.class_name)
        students = student_query.all()
        for st in students:
            res_rec = ExamResult(
                school_id=school_id,
                exam_id=exam.id,
                student_id=st.id,
                total_marks_obtained=0.0,
                total_max_marks=0.0,
                percentage=0.0,
                grade="-",
                status="Draft"
            )
            db.session.add(res_rec)
            result_count += 1

    # 7. Seed Default Grade Rules if missing
    grade_rules_count = GradeRule.query.filter_by(school_id=school_id).count()
    if grade_rules_count == 0:
        default_rules = [
            ("A+", 90.0, 100.0, 10.0, "Outstanding"),
            ("A", 80.0, 89.99, 9.0, "Excellent"),
            ("B", 70.0, 79.99, 8.0, "Very Good"),
            ("C", 60.0, 69.99, 7.0, "Good"),
            ("D", 50.0, 59.99, 6.0, "Above Average"),
            ("E", 33.0, 49.99, 5.0, "Pass"),
            ("F", 0.0, 32.99, 0.0, "Fail")
        ]
        for g_name, min_p, max_p, g_pt, rem in default_rules:
            gr = GradeRule(
                school_id=school_id,
                grade_name=g_name,
                min_percentage=min_p,
                max_percentage=max_p,
                grade_point=g_pt,
                remarks=rem
            )
            db.session.add(gr)

    db.session.commit()
    log_academic_action("Unified Planning Engine Run", f"Generated regular timetables, {exam_count} exams, {schedule_count} exam schedules, {seating_count} seat bookings, and {result_count} result sheets.")
    flash(f"Success! Unified Planning Engine generated: regular weekly timetables, {exam_count} exam classes, {schedule_count} exam schedules, {seating_count} seat allocations, and {result_count} result card sheets.", "success")

    return redirect(url_for('academics.planner'))


# =========================================================
# 🏛️ MULTI-CAMPUS & PHYSICAL INFRASTRUCTURE MANAGEMENT
# =========================================================
@academics_bp.route('/campus', methods=['GET', 'POST'])
@login_required
@subscription_required
def manage_campuses():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))
    school_id = current_user.school_id
    if request.method == 'POST':
        name = request.form.get('name')
        code = request.form.get('code')
        if name and code:
            campus = Campus(school_id=school_id, name=name, code=code)
            db.session.add(campus)
            db.session.commit()
            log_academic_action("Created Campus", f"Created campus branch: {name} ({code})")
            flash("Campus branch created successfully!", "success")
        return redirect(url_for('academics.manage_campuses'))
    campuses = Campus.query.filter_by(school_id=school_id).all()
    return render_template('academics/campuses.html', campuses=campuses)


@academics_bp.route('/buildings', methods=['GET', 'POST'])
@login_required
@subscription_required
def manage_buildings():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))
    school_id = current_user.school_id
    if request.method == 'POST':
        campus_id = int(request.form.get('campus_id'))
        name = request.form.get('name')
        if campus_id and name:
            b = Building(school_id=school_id, campus_id=campus_id, name=name)
            db.session.add(b)
            db.session.commit()
            log_academic_action("Created Building", f"Created building block {name} on campus ID {campus_id}")
            flash("Building Block created successfully!", "success")
        return redirect(url_for('academics.manage_buildings'))
    campuses = Campus.query.filter_by(school_id=school_id).all()
    buildings = Building.query.filter_by(school_id=school_id).all()
    return render_template('academics/buildings.html', campuses=campuses, buildings=buildings)


@academics_bp.route('/laboratories', methods=['GET', 'POST'])
@login_required
@subscription_required
def manage_laboratories():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))
    school_id = current_user.school_id
    if request.method == 'POST':
        building_id = int(request.form.get('building_id'))
        name = request.form.get('name')
        lab_type = request.form.get('lab_type', 'General')
        capacity = int(request.form.get('capacity', 30))
        equipment = request.form.get('equipment_list', '')
        eq_list = [e.strip() for e in equipment.split(',') if e.strip()]
        
        if building_id and name:
            lab = Laboratory(
                school_id=school_id,
                building_id=building_id,
                name=name,
                lab_type=lab_type,
                capacity=capacity,
                equipment_json=eq_list
            )
            db.session.add(lab)
            db.session.commit()
            log_academic_action("Created Laboratory", f"Created laboratory: {name} ({lab_type})")
            flash("Laboratory created successfully!", "success")
        return redirect(url_for('academics.manage_laboratories'))
    buildings = Building.query.filter_by(school_id=school_id).all()
    laboratories = Laboratory.query.filter_by(school_id=school_id).all()
    return render_template('academics/laboratories.html', buildings=buildings, laboratories=laboratories)


# =========================================================
# ⚙️ ADVANCED SOLVER SCHEDULING CONSTRAINTS
# =========================================================
@academics_bp.route('/timetable/constraints', methods=['GET', 'POST'])
@login_required
@subscription_required
def timetable_constraints():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))
    school_id = current_user.school_id
    
    if request.method == 'POST':
        c_type = request.form.get('constraint_type')
        if c_type == 'teacher':
            teacher_id = int(request.form.get('teacher_id'))
            max_day = int(request.form.get('max_periods_day', 5))
            max_week = int(request.form.get('max_periods_week', 25))
            pref = request.form.get('preferred_slots', '')
            unavail = request.form.get('unavailable_slots', '')
            
            tc = TeacherConstraint.query.filter_by(school_id=school_id, teacher_id=teacher_id).first()
            if not tc:
                tc = TeacherConstraint(school_id=school_id, teacher_id=teacher_id)
                db.session.add(tc)
            tc.max_periods_day = max_day
            tc.max_periods_week = max_week
            tc.preferred_slots = pref
            tc.unavailable_slots = unavail
            db.session.commit()
            flash("Teacher constraint profile saved!", "success")
        
        elif c_type == 'subject':
            subject_id = int(request.form.get('subject_id'))
            is_heavy = True if request.form.get('is_heavy') else False
            req_lab = True if request.form.get('requires_lab') else False
            lab_type = request.form.get('lab_type_required', '')
            
            sc = SubjectConstraint.query.filter_by(school_id=school_id, subject_id=subject_id).first()
            if not sc:
                sc = SubjectConstraint(school_id=school_id, subject_id=subject_id)
                db.session.add(sc)
            sc.is_heavy = is_heavy
            sc.requires_lab = req_lab
            sc.lab_type_required = lab_type
            db.session.commit()
            flash("Subject constraint profile saved!", "success")
        return redirect(url_for('academics.timetable_constraints'))

    teachers = Teacher.query.filter_by(school_id=school_id, is_active=True).all()
    subjects = Subject.query.filter_by(school_id=school_id, status=True).all()
    t_constraints = {c.teacher_id: c for c in TeacherConstraint.query.filter_by(school_id=school_id).all()}
    s_constraints = {c.subject_id: c for c in SubjectConstraint.query.filter_by(school_id=school_id).all()}
    return render_template('academics/constraints.html', teachers=teachers, subjects=subjects, t_constraints=t_constraints, s_constraints=s_constraints)


# =========================================================
# 🔄 SMART SUBSTITUTE TEACHER ASSIGNMENT ENGINE
# =========================================================
@academics_bp.route('/substitute', methods=['GET', 'POST'])
@login_required
@subscription_required
def substitute_cockpit():
    if not check_permission('admin', 'principal', 'teacher'):
        return redirect(url_for('dashboard.home'))
    school_id = current_user.school_id
    
    selected_teacher_id = request.args.get('absent_teacher_id')
    selected_date_str = request.args.get('date', date.today().strftime('%Y-%m-%d'))
    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    
    recommendations = {}
    periods = Period.query.filter_by(school_id=school_id, is_break=False).order_by(Period.period_no).all()
    
    if selected_teacher_id:
        absent_teacher_id = int(selected_teacher_id)
        day_of_week = selected_date.strftime('%A')
        absent_slots = AcademicTimetable.query.filter_by(
            school_id=school_id,
            teacher_id=absent_teacher_id,
            day_of_week=day_of_week
        ).all()
        
        all_teachers = Teacher.query.filter(Teacher.school_id == school_id, Teacher.id != absent_teacher_id, Teacher.is_active == True).all()
        
        for slot in absent_slots:
            p_no = slot.period_no
            free_teachers = []
            for t in all_teachers:
                is_busy = AcademicTimetable.query.filter_by(
                    school_id=school_id,
                    day_of_week=day_of_week,
                    period_no=p_no,
                    teacher_id=t.id
                ).first()
                is_sub = SubstituteAssignment.query.filter_by(
                    school_id=school_id,
                    date=selected_date,
                    period_id=p_no,
                    substitute_teacher_id=t.id,
                    status="Assigned"
                ).first()
                
                if not is_busy and not is_sub:
                    is_qualified = TeacherSubject.query.filter_by(
                        school_id=school_id,
                        teacher_id=t.id,
                        subject_id=slot.subject_id
                    ).first() is not None
                    
                    weekday_workload = AcademicTimetable.query.filter_by(
                        school_id=school_id,
                        day_of_week=day_of_week,
                        teacher_id=t.id
                    ).count()
                    sub_workload = SubstituteAssignment.query.filter_by(
                        school_id=school_id,
                        date=selected_date,
                        substitute_teacher_id=t.id,
                        status="Assigned"
                    ).count()
                    total_workload = weekday_workload + sub_workload
                    
                    free_teachers.append({
                        'teacher': t,
                        'is_qualified': is_qualified,
                        'workload': total_workload
                    })
            free_teachers.sort(key=lambda x: (not x['is_qualified'], x['workload']))
            recommendations[p_no] = {
                'slot': slot,
                'candidates': free_teachers[:5]
            }
            
    if request.method == 'POST':
        absent_teacher_id = int(request.form.get('absent_teacher_id'))
        substitute_teacher_id = int(request.form.get('substitute_teacher_id'))
        period_no = int(request.form.get('period_no'))
        reason = request.form.get('reason', 'Sick Leave')
        
        period = Period.query.filter_by(school_id=school_id, period_no=period_no).first()
        if period:
            sub_assign = SubstituteAssignment(
                school_id=school_id,
                date=selected_date,
                period_id=period.id,
                absent_teacher_id=absent_teacher_id,
                substitute_teacher_id=substitute_teacher_id,
                reason=reason,
                status="Assigned"
            )
            db.session.add(sub_assign)
            db.session.commit()
            
            log_academic_action("Substitute Assigned", f"Assigned Teacher ID {substitute_teacher_id} for absent Teacher ID {absent_teacher_id} on period {period_no}")
            flash("Substitute teacher assigned successfully!", "success")
        return redirect(url_for('academics.substitute_cockpit', absent_teacher_id=absent_teacher_id, date=selected_date_str))

    teachers = Teacher.query.filter_by(school_id=school_id, is_active=True).all()
    assignments = SubstituteAssignment.query.filter_by(school_id=school_id, date=selected_date).all()
    return render_template(
        'academics/substitute.html',
        teachers=teachers,
        assignments=assignments,
        selected_teacher_id=int(selected_teacher_id) if selected_teacher_id else None,
        selected_date_str=selected_date_str,
        recommendations=recommendations,
        periods=periods
    )


# =========================================================
# 🛡️ ADVANCED ANTI-CHEATING SEATING SOLVER
# =========================================================
@academics_bp.route('/seating/generate-advanced', methods=['POST'])
@login_required
@subscription_required
def seating_generate_advanced():
    if not check_permission('admin', 'principal'):
        return redirect(url_for('dashboard.home'))
        
    school_id = current_user.school_id
    exam_id = int(request.form.get('exam_id'))
    schedule_id = int(request.form.get('schedule_id'))
    room_ids = request.form.getlist('room_ids')
    mode = request.form.get('mode', 'sequential') # sequential, randomized, mixed_sections, mixed_classes
    
    exam = Exam.query.get_or_404(exam_id)
    sched = ExamSchedule.query.get_or_404(schedule_id)
    
    SeatingPlan.query.filter_by(exam_schedule_id=schedule_id).delete()
    db.session.commit()
    
    students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
        Student.school_id == school_id,
        Student.student_class == exam.class_name,
        StudentSubject.subject_id == sched.subject_id
    )
    if exam.section:
        students = students.filter(Student.section == exam.section)
    
    if mode == 'randomized':
        import random
        students = students.all()
        random.shuffle(students)
    elif mode == 'mixed_sections':
        students = students.all()
        sec_a = [s for s in students if s.section == 'A']
        sec_b = [s for s in students if s.section != 'A']
        mixed = []
        i, j = 0, 0
        while i < len(sec_a) or j < len(sec_b):
            if i < len(sec_a):
                mixed.append(sec_a[i])
                i += 1
            if j < len(sec_b):
                mixed.append(sec_b[j])
                j += 1
        students = mixed
    elif mode == 'mixed_classes':
        other_exam = Exam.query.filter(
            Exam.school_id == school_id,
            Exam.id != exam_id,
            Exam.session_id == exam.session_id,
            Exam.exam_type_id == exam.exam_type_id
        ).first()
        students = students.order_by(Student.first_name).all()
        if other_exam:
            other_students = Student.query.filter_by(school_id=school_id, student_class=other_exam.class_name).order_by(Student.first_name).all()
            mixed = []
            i, j = 0, 0
            while i < len(students) or j < len(other_students):
                if i < len(students):
                    mixed.append(students[i])
                    i += 1
                if j < len(other_students):
                    mixed.append(other_students[j])
                    j += 1
            students = mixed
    else:
        students = students.order_by(Student.admission_no).all()
        
    rooms = Room.query.filter(Room.id.in_([int(rid) for rid in room_ids])).all()
    
    student_idx = 0
    allocated_count = 0
    
    for rm in rooms:
        if student_idx >= len(students):
            break
            
        for seat in range(1, rm.capacity + 1):
            if student_idx >= len(students):
                break
                
            st = students[student_idx]
            plan = SeatingPlan(
                school_id=school_id,
                exam_id=exam_id,
                exam_schedule_id=schedule_id,
                room_id=rm.id,
                student_id=st.id,
                seat_no=f"Desk-{seat}"
            )
            db.session.add(plan)
            student_idx += 1
            allocated_count += 1
            
    db.session.commit()
    log_academic_action("Advanced Seat Allocation", f"Arranged {allocated_count} seats using mode {mode}")
    flash(f"Advanced seating ({mode}) successfully arranged for {allocated_count} students!", "success")
    return redirect(url_for('academics.seating'))


# =========================================================
# 📝 QUESTION BANK & AUTO PAPER GENERATION
# =========================================================
@academics_bp.route('/questions', methods=['GET', 'POST'])
@login_required
@subscription_required
def manage_questions():
    if not check_permission('admin', 'principal', 'teacher'):
        return redirect(url_for('dashboard.home'))
    school_id = current_user.school_id
    
    if request.method == 'POST':
        subject_id = int(request.form.get('subject_id'))
        chapter = request.form.get('chapter')
        topic = request.form.get('topic')
        difficulty = request.form.get('difficulty', 'Medium')
        cognitive = request.form.get('cognitive_level', 'Remember')
        q_text = request.form.get('question_text')
        correct = request.form.get('correct_answer')
        
        options = request.form.getlist('options')
        opt_json = options if options and any(options) else None
        
        if subject_id and chapter and q_text:
            qb = QuestionBank(
                school_id=school_id,
                subject_id=subject_id,
                chapter=chapter,
                topic=topic,
                difficulty=difficulty,
                cognitive_level=cognitive,
                question_text=q_text,
                options_json=opt_json,
                correct_answer=correct
            )
            db.session.add(qb)
            db.session.commit()
            flash("Question added to Question Bank!", "success")
        return redirect(url_for('academics.manage_questions'))
        
    subjects = Subject.query.filter_by(school_id=school_id, status=True).all()
    questions = QuestionBank.query.filter_by(school_id=school_id).all()
    return render_template('academics/questions.html', subjects=subjects, questions=questions)


@academics_bp.route('/questions/generate-paper', methods=['POST'])
@login_required
@subscription_required
def generate_question_paper():
    if not check_permission('admin', 'principal', 'teacher'):
        return redirect(url_for('dashboard.home'))
    school_id = current_user.school_id
    
    subject_id = int(request.form.get('subject_id'))
    easy_count = int(request.form.get('easy_count', 3))
    medium_count = int(request.form.get('medium_count', 5))
    hard_count = int(request.form.get('hard_count', 2))
    
    import random
    
    easy_qs = QuestionBank.query.filter_by(school_id=school_id, subject_id=subject_id, difficulty="Easy").all()
    med_qs = QuestionBank.query.filter_by(school_id=school_id, subject_id=subject_id, difficulty="Medium").all()
    hard_qs = QuestionBank.query.filter_by(school_id=school_id, subject_id=subject_id, difficulty="Hard").all()
    
    selected_qs = []
    selected_qs.extend(random.sample(easy_qs, min(easy_count, len(easy_qs))))
    selected_qs.extend(random.sample(med_qs, min(medium_count, len(med_qs))))
    selected_qs.extend(random.sample(hard_qs, min(hard_count, len(hard_qs))))
    
    if not selected_qs:
        flash("Error: No questions found in the Question Bank for this subject to generate a paper.", "danger")
        return redirect(url_for('academics.manage_questions'))
        
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=40, leftMargin=40, topMargin=40, bottomMargin=40)
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'PaperTitle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=18, alignment=1, spaceAfter=20
    )
    q_style = ParagraphStyle(
        'QStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=10, spaceAfter=10
    )
    
    sub_obj = Subject.query.get(subject_id)
    story = [
        Paragraph(f"AUTOGENERATED QUESTION PAPER", title_style),
        Paragraph(f"<b>Subject:</b> {sub_obj.subject_name} | <b>Max Marks:</b> 100", styles['Normal']),
        Spacer(1, 15)
    ]
    
    for idx, q in enumerate(selected_qs):
        txt = f"<b>Q{idx+1}.</b> {q.question_text} <font color='grey'>[{q.difficulty} | {q.cognitive_level}]</font>"
        story.append(Paragraph(txt, q_style))
        if q.options_json:
            opts = ""
            for o_idx, opt in enumerate(q.options_json):
                opts += f"&nbsp;&nbsp;&nbsp;&nbsp;{chr(65+o_idx)}) {opt}<br/>"
            story.append(Paragraph(opts, ParagraphStyle('OptsStyle', parent=styles['Normal'], fontName='Helvetica', fontSize=9, leftIndent=20, spaceAfter=10)))
            
    doc.build(story)
    buffer.seek(0)
    
    log_academic_action("Generated Question Paper", f"Auto-generated test paper for subject ID {subject_id}")
    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Question_Paper_{sub_obj.subject_name}.pdf",
        mimetype="application/pdf"
    )


# =========================================================
# 📑 OMR SHEET UPLOAD & RESULTS AUTO-PROCESSING
# =========================================================
@academics_bp.route('/omr/upload', methods=['GET', 'POST'])
@login_required
@subscription_required
def omr_upload():
    if not check_permission('admin', 'principal', 'teacher'):
        return redirect(url_for('dashboard.home'))
    school_id = current_user.school_id
    
    layouts = OMRLayout.query.filter_by(school_id=school_id).all()
    exams = Exam.query.filter_by(school_id=school_id).all()
    
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'layout':
            name = request.form.get('name')
            t_qs = int(request.form.get('total_questions', 50))
            ans_keys = request.form.get('answer_key')
            ans_dict = {}
            if ans_keys:
                for item in ans_keys.split(','):
                    if ':' in item:
                        k, v = item.split(':')
                        ans_dict[k.strip()] = v.strip()
            
            layout = OMRLayout(school_id=school_id, name=name, total_questions=t_qs, answer_key_json=ans_dict)
            db.session.add(layout)
            db.session.commit()
            flash("OMR layout answer key saved!", "success")
            
        elif action == 'evaluate':
            layout_id = int(request.form.get('layout_id'))
            exam_id = int(request.form.get('exam_id'))
            schedule_id = int(request.form.get('schedule_id'))
            
            csv_file = request.files.get('omr_csv')
            if not csv_file:
                flash("Please upload an OMR CSV sheet", "danger")
                return redirect(url_for('academics.omr_upload'))
                
            layout = OMRLayout.query.get_or_404(layout_id)
            sched = ExamSchedule.query.get_or_404(schedule_id)
            
            try:
                df = pd.read_csv(csv_file)
                evaluated_count = 0
                for _, row in df.iterrows():
                    adm = str(row['admission_no']).strip()
                    student = Student.query.filter_by(school_id=school_id, admission_no=adm).first()
                    if not student:
                        continue
                        
                    score = 0.0
                    for q_no, correct_ans in layout.answer_key_json.items():
                        col_name = f"q{q_no}"
                        if col_name in row:
                            student_ans = str(row[col_name]).strip()
                            if student_ans == correct_ans:
                                score += 1.0
                                
                    final_marks = (score / layout.total_questions) * sched.max_marks
                    
                    mark_rec = ExamMark.query.filter_by(exam_schedule_id=schedule_id, student_id=student.id).first()
                    if not mark_rec:
                        mark_rec = ExamMark(
                            school_id=school_id,
                            exam_schedule_id=schedule_id,
                            student_id=student.id,
                            subject_id=sched.subject_id,
                            theory_obtained=final_marks,
                            marks_obtained=final_marks
                        )
                        db.session.add(mark_rec)
                    else:
                        mark_rec.theory_obtained = final_marks
                        mark_rec.marks_obtained = final_marks
                    evaluated_count += 1
                db.session.commit()
                log_academic_action("Evaluated OMR Sheets", f"Uploaded and evaluated {evaluated_count} student OMR sheets for schedule {schedule_id}")
                flash(f"OMR grading complete! Evaluated and imported marks for {evaluated_count} students.", "success")
            except Exception as e:
                flash(f"Error parsing OMR file: {e}", "danger")
        return redirect(url_for('academics.omr_upload'))
        
    schedules = ExamSchedule.query.filter_by(school_id=school_id).all()
    return render_template('academics/omr.html', layouts=layouts, exams=exams, schedules=schedules)


# =========================================================
# 📊 ACADEMIC ANALYTICS & PREDICTIVE RISK COCKPIT
# =========================================================
@academics_bp.route('/analytics', methods=['GET'])
@login_required
@subscription_required
def analytics_dashboard():
    if not check_permission('admin', 'principal', 'teacher'):
        return redirect(url_for('dashboard.home'))
    school_id = current_user.school_id
    
    students = Student.query.filter_by(school_id=school_id).all()
    at_risk_students = []
    
    for st in students:
        from models.subject_attendance import SubjectAttendance
        total_days = SubjectAttendance.query.filter_by(school_id=school_id, student_id=st.id).count()
        present_days = SubjectAttendance.query.filter_by(school_id=school_id, student_id=st.id, status='Present').count()
        att_rate = (present_days / total_days * 100.0) if total_days > 0 else 100.0
        
        results = ExamResult.query.filter_by(school_id=school_id, student_id=st.id).all()
        failing_exams = [r for r in results if r.status == 'Fail']
        avg_percentage = sum([r.percentage for r in results]) / len(results) if results else 100.0
        
        risk_score = 0
        reasons = []
        if att_rate < 75.0:
            risk_score += 40
            reasons.append(f"Low Attendance: {att_rate:.1f}%")
        if failing_exams:
            risk_score += 40
            reasons.append(f"Failed {len(failing_exams)} past exams")
        if avg_percentage < 45.0:
            risk_score += 20
            reasons.append(f"Low overall grade average: {avg_percentage:.1f}%")
            
        if risk_score >= 40:
            at_risk_students.append({
                'student': st,
                'attendance_rate': att_rate,
                'performance_avg': avg_percentage,
                'risk_score': risk_score,
                'reasons': reasons
            })
            
    at_risk_students.sort(key=lambda x: x['risk_score'], reverse=True)
    
    teachers = Teacher.query.filter_by(school_id=school_id, is_active=True).all()
    teacher_performance = []
    for t in teachers:
        marks = ExamMark.query.filter_by(school_id=school_id, teacher_id=t.id).all()
        if marks:
            total_students = len(marks)
            failed = sum([1 for m in marks if m.marks_obtained < 33.0])
            pass_rate = ((total_students - failed) / total_students) * 100.0
            teacher_performance.append({
                'teacher': t,
                'total_graded': total_students,
                'pass_rate': pass_rate
            })
            
    return render_template(
        'academics/analytics.html',
        at_risk_students=at_risk_students[:10],
        teacher_performance=teacher_performance
    )



