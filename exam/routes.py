from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from extensions import db
from models.exam import ExamSession, ExamType, Exam, ExamSchedule, ExamAttendance, ExamMark, ExamAuditLog
from models.student import Student
from models.subject import Subject
from models.teacher import Teacher
from models.user import User
from models.student_subject import StudentSubject
from super.routes import subscription_required
from datetime import datetime, date, time
import pandas as pd
import io
import os

# ReportLab Imports for PDF generation
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

exam_bp = Blueprint('exam', __name__, url_prefix='/exam')

def log_exam_action(action, details):
    """Utility to log administrative and teaching activities in exams."""
    try:
        log = ExamAuditLog(
            school_id=current_user.school_id,
            user_id=current_user.id,
            action=action,
            details=details
        )
        db.session.add(log)
        db.session.commit()
    except Exception as e:
        print("Audit logging failed:", e)

# =========================================================
# 📅 EXAM SESSIONS MANAGEMENT
# =========================================================
@exam_bp.route('/sessions', methods=['GET', 'POST'])
@login_required
@subscription_required
def sessions_list():
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        name = request.form.get('name')
        if name:
            # Check duplicate
            existing = ExamSession.query.filter_by(school_id=current_user.school_id, name=name).first()
            if existing:
                flash('Session name already exists', 'warning')
            else:
                # Deactivate others if this is set active
                is_active = True if request.form.get('is_active') else False
                if is_active:
                    ExamSession.query.filter_by(school_id=current_user.school_id).update({"is_active": False})
                
                sess = ExamSession(school_id=current_user.school_id, name=name, is_active=is_active)
                db.session.add(sess)
                db.session.commit()
                log_exam_action("Created Session", f"Created exam session: {name}")
                flash('Exam session added successfully', 'success')
        return redirect(url_for('exam.sessions_list'))

    sessions = ExamSession.query.filter_by(school_id=current_user.school_id).all()
    return render_template('exam/sessions.html', sessions=sessions)

@exam_bp.route('/sessions/toggle/<int:id>')
@login_required
@subscription_required
def toggle_session(id):
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    sess = ExamSession.query.filter_by(id=id, school_id=current_user.school_id).first_or_404()
    # Deactivate all others first
    ExamSession.query.filter_by(school_id=current_user.school_id).update({"is_active": False})
    sess.is_active = True
    db.session.commit()
    log_exam_action("Activated Session", f"Activated exam session: {sess.name}")
    flash(f'Exam session {sess.name} set as Active', 'success')
    return redirect(url_for('exam.sessions_list'))

@exam_bp.route('/sessions/delete/<int:id>')
@login_required
@subscription_required
def delete_session(id):
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    sess = ExamSession.query.filter_by(id=id, school_id=current_user.school_id).first_or_404()
    db.session.delete(sess)
    db.session.commit()
    log_exam_action("Deleted Session", f"Deleted session: {sess.name}")
    flash('Exam session deleted successfully', 'success')
    return redirect(url_for('exam.sessions_list'))


# =========================================================
# 🏷️ EXAM TYPES MANAGEMENT
# =========================================================
@exam_bp.route('/types', methods=['GET', 'POST'])
@login_required
@subscription_required
def types_list():
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description')
        if name:
            existing = ExamType.query.filter_by(school_id=current_user.school_id, name=name).first()
            if existing:
                flash('Exam type already exists', 'warning')
            else:
                etype = ExamType(school_id=current_user.school_id, name=name, description=description)
                db.session.add(etype)
                db.session.commit()
                log_exam_action("Created Exam Type", f"Created type: {name}")
                flash('Exam type added successfully', 'success')
        return redirect(url_for('exam.types_list'))

    types = ExamType.query.filter_by(school_id=current_user.school_id).all()
    return render_template('exam/types.html', types=types)

@exam_bp.route('/types/delete/<int:id>')
@login_required
@subscription_required
def delete_type(id):
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    etype = ExamType.query.filter_by(id=id, school_id=current_user.school_id).first_or_404()
    db.session.delete(etype)
    db.session.commit()
    log_exam_action("Deleted Exam Type", f"Deleted type: {etype.name}")
    flash('Exam type deleted successfully', 'success')
    return redirect(url_for('exam.types_list'))


# =========================================================
# 🎓 EXAM MASTER MANAGEMENT
# =========================================================
@exam_bp.route('/', methods=['GET', 'POST'])
@login_required
@subscription_required
def exam_list():
    if current_user.role not in ['admin', 'teacher']:
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    sessions = ExamSession.query.filter_by(school_id=current_user.school_id).all()
    types = ExamType.query.filter_by(school_id=current_user.school_id).all()

    if request.method == 'POST' and current_user.role == 'admin':
        name = request.form.get('name')
        session_id = request.form.get('session_id')
        exam_type_id = request.form.get('exam_type_id')
        class_name = request.form.get('class_name')
        section = request.form.get('section') or None
        
        start_date_str = request.form.get('start_date')
        end_date_str = request.form.get('end_date')
        
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date() if start_date_str else None
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date() if end_date_str else None

        if name and session_id and exam_type_id and class_name:
            exam = Exam(
                school_id=current_user.school_id,
                name=name,
                session_id=session_id,
                exam_type_id=exam_type_id,
                class_name=class_name,
                section=section,
                start_date=start_date,
                end_date=end_date
            )
            db.session.add(exam)
            db.session.commit()
            log_exam_action("Created Exam", f"Created Exam: {name} for Class {class_name}")
            flash('Exam created successfully', 'success')
        return redirect(url_for('exam.exam_list'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).order_by(Exam.created_at.desc()).all()
    return render_template('exam/list.html', exams=exams, sessions=sessions, types=types)

@exam_bp.route('/delete/<int:id>')
@login_required
@subscription_required
def delete_exam(id):
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    exam = Exam.query.filter_by(id=id, school_id=current_user.school_id).first_or_404()
    db.session.delete(exam)
    db.session.commit()
    log_exam_action("Deleted Exam", f"Deleted exam id {id}")
    flash('Exam deleted successfully', 'success')
    return redirect(url_for('exam.exam_list'))


# =========================================================
# 📅 EXAM SCHEDULING (SUBJECT MAPPING + DATES)
# =========================================================
@exam_bp.route('/schedule/<int:exam_id>', methods=['GET', 'POST'])
@login_required
@subscription_required
def schedule(exam_id):
    if current_user.role not in ['admin', 'teacher']:
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    exam = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    
    # Subjects available for this class and section
    sub_query = Subject.query.filter_by(school_id=current_user.school_id, class_name=exam.class_name)
    if exam.section:
        sub_query = sub_query.filter((Subject.section == exam.section) | (Subject.section == None) | (Subject.section == ''))
    subjects = sub_query.all()
    teachers = Teacher.query.filter_by(school_id=current_user.school_id).all()

    if request.method == 'POST' and current_user.role == 'admin':
        subject_id = request.form.get('subject_id')
        exam_date_str = request.form.get('date')
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        room_no = request.form.get('room_no')
        max_marks = float(request.form.get('max_marks', 100))
        passing_marks = float(request.form.get('passing_marks', 33))
        teacher_id = request.form.get('teacher_id') or None

        exam_date = datetime.strptime(exam_date_str, '%Y-%m-%d').date() if exam_date_str else None
        start_time = datetime.strptime(start_time_str, '%H:%M').time() if start_time_str else None
        end_time = datetime.strptime(end_time_str, '%H:%M').time() if end_time_str else None

        if subject_id and exam_date and start_time and end_time:
            # Conflict Check: Check if invigilator or room is already booked at the same date & time range
            conflict = ExamSchedule.query.filter(
                ExamSchedule.school_id == current_user.school_id,
                ExamSchedule.date == exam_date,
                ExamSchedule.id != exam_id # Not same record
            ).all()

            for c in conflict:
                # Overlap calculation
                latest_start = max(start_time, c.start_time)
                earliest_end = min(end_time, c.end_time)
                if latest_start < earliest_end:
                    # Time overlaps! Check resource
                    if teacher_id and c.teacher_id == int(teacher_id):
                        flash(f"Conflict: Invigilator is already assigned to another exam at this time ({c.exam_ref.name})!", 'danger')
                        return redirect(url_for('exam.schedule', exam_id=exam_id))
                    if room_no and c.room_no == room_no:
                        flash(f"Conflict: Room {room_no} is already booked for another exam at this time ({c.exam_ref.name})!", 'danger')
                        return redirect(url_for('exam.schedule', exam_id=exam_id))

            # Check if this subject is already scheduled in this exam
            existing_sched = ExamSchedule.query.filter_by(exam_id=exam_id, subject_id=subject_id).first()
            if existing_sched:
                flash("This subject is already scheduled for this exam", "warning")
                return redirect(url_for('exam.schedule', exam_id=exam_id))

            sched = ExamSchedule(
                school_id=current_user.school_id,
                exam_id=exam_id,
                subject_id=subject_id,
                date=exam_date,
                start_time=start_time,
                end_time=end_time,
                room_no=room_no,
                max_marks=max_marks,
                passing_marks=passing_marks,
                teacher_id=teacher_id
            )
            db.session.add(sched)
            db.session.commit()
            log_exam_action("Scheduled Exam Subject", f"Scheduled subject {subject_id} for exam {exam.name}")
            flash('Exam subject scheduled successfully', 'success')

        return redirect(url_for('exam.schedule', exam_id=exam_id))

    schedules = ExamSchedule.query.filter_by(exam_id=exam_id).order_by(ExamSchedule.date, ExamSchedule.start_time).all()
    return render_template('exam/schedule.html', exam=exam, subjects=subjects, teachers=teachers, schedules=schedules)

@exam_bp.route('/schedule/delete/<int:schedule_id>')
@login_required
@subscription_required
def delete_schedule(schedule_id):
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    sched = ExamSchedule.query.filter_by(id=schedule_id, school_id=current_user.school_id).first_or_404()
    exam_id = sched.exam_id
    db.session.delete(sched)
    db.session.commit()
    log_exam_action("Deleted Exam Subject Schedule", f"Removed schedule id {schedule_id}")
    flash('Subject schedule removed successfully', 'success')
    return redirect(url_for('exam.schedule', exam_id=exam_id))


# =========================================================
# 📝 EXAM ATTENDANCE
# =========================================================
@exam_bp.route('/attendance', methods=['GET', 'POST'])
@login_required
@subscription_required
def attendance():
    if current_user.role not in ['admin', 'teacher']:
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    schedules = []
    selected_exam_id = request.args.get('exam_id')
    selected_schedule_id = request.args.get('schedule_id')

    if selected_exam_id:
        schedules = ExamSchedule.query.filter_by(exam_id=selected_exam_id).all()

    students = []
    attendance_map = {}

    if selected_schedule_id:
        sched = ExamSchedule.query.get_or_404(selected_schedule_id)
        exam = sched.exam_ref
        
        # Get students of this class and section registered to the scheduled subject
        students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
            Student.school_id == current_user.school_id,
            Student.student_class == exam.class_name,
            StudentSubject.subject_id == sched.subject_id
        )
        if exam.section:
            students = students.filter(Student.section == exam.section)
        students = students.all()

        # Load existing attendance
        existing = ExamAttendance.query.filter_by(exam_schedule_id=selected_schedule_id).all()
        attendance_map = {att.student_id: att for att in existing}

    if request.method == 'POST' and selected_schedule_id:
        sched = ExamSchedule.query.get_or_404(selected_schedule_id)
        exam = sched.exam_ref
        curr_students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
            Student.school_id == current_user.school_id,
            Student.student_class == exam.class_name,
            StudentSubject.subject_id == sched.subject_id
        )
        if exam.section:
            curr_students = curr_students.filter(Student.section == exam.section)
        curr_students = curr_students.all()

        for st in curr_students:
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
        log_exam_action("Marked Exam Attendance", f"Marked attendance for schedule id {selected_schedule_id}")
        flash('Exam Attendance saved successfully', 'success')
        return redirect(url_for('exam.attendance', exam_id=selected_exam_id, schedule_id=selected_schedule_id))

    return render_template(
        'exam/attendance.html',
        exams=exams,
        schedules=schedules,
        students=students,
        attendance_map=attendance_map,
        selected_exam_id=int(selected_exam_id) if selected_exam_id else None,
        selected_schedule_id=int(selected_schedule_id) if selected_schedule_id else None
    )


# =========================================================
# 📝 MARKS ENTRY & EXCEL CHANNELS
# =========================================================
@exam_bp.route('/marks', methods=['GET', 'POST'])
@login_required
@subscription_required
def marks_entry():
    if current_user.role not in ['admin', 'teacher']:
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    schedules = []
    selected_exam_id = request.args.get('exam_id')
    selected_schedule_id = request.args.get('schedule_id')

    if selected_exam_id:
        schedules = ExamSchedule.query.filter_by(exam_id=selected_exam_id).all()

    students = []
    marks_map = {}
    sched = None

    if selected_schedule_id:
        sched = ExamSchedule.query.get_or_404(selected_schedule_id)
        exam = sched.exam_ref
        
        # Get students registered to the scheduled subject
        students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
            Student.school_id == current_user.school_id,
            Student.student_class == exam.class_name,
            StudentSubject.subject_id == sched.subject_id
        )
        if exam.section:
            students = students.filter(Student.section == exam.section)
        students = students.all()

        # Load existing marks
        existing = ExamMark.query.filter_by(exam_schedule_id=selected_schedule_id).all()
        marks_map = {m.student_id: m for m in existing}

    if request.method == 'POST' and selected_schedule_id:
        sched = ExamSchedule.query.get_or_404(selected_schedule_id)
        exam = sched.exam_ref
        curr_students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
            Student.school_id == current_user.school_id,
            Student.student_class == exam.class_name,
            StudentSubject.subject_id == sched.subject_id
        )
        if exam.section:
            curr_students = curr_students.filter(Student.section == exam.section)
        curr_students = curr_students.all()

        for st in curr_students:
            is_absent = True if request.form.get(f'absent_{st.id}') else False
            val_str = request.form.get(f'marks_{st.id}', '0')
            remarks = request.form.get(f'remarks_{st.id}', '')
            
            try:
                marks_val = float(val_str) if not is_absent else 0.0
            except ValueError:
                marks_val = 0.0

            # Check boundaries
            if marks_val > sched.max_marks:
                flash(f"Error: Marks entered ({marks_val}) exceeds Maximum Marks ({sched.max_marks}) for {st.first_name}.", 'danger')
                return redirect(url_for('exam.marks_entry', exam_id=selected_exam_id, schedule_id=selected_schedule_id))

            mark_rec = ExamMark.query.filter_by(exam_schedule_id=selected_schedule_id, student_id=st.id).first()
            if not mark_rec:
                mark_rec = ExamMark(
                    school_id=current_user.school_id,
                    exam_schedule_id=selected_schedule_id,
                    student_id=st.id,
                    subject_id=sched.subject_id,
                    marks_obtained=marks_val,
                    is_absent=is_absent,
                    remarks=remarks,
                    teacher_id=current_user.employee_id if current_user.role == 'teacher' else None
                )
                db.session.add(mark_rec)
            else:
                mark_rec.marks_obtained = marks_val
                mark_rec.is_absent = is_absent
                mark_rec.remarks = remarks
                mark_rec.updated_at = datetime.utcnow()

        db.session.commit()
        log_exam_action("Entered Marks", f"Recorded exam marks for schedule id {selected_schedule_id}")
        flash('Exam marks saved successfully', 'success')
        return redirect(url_for('exam.marks_entry', exam_id=selected_exam_id, schedule_id=selected_schedule_id))

    return render_template(
        'exam/marks_entry.html',
        exams=exams,
        schedules=schedules,
        students=students,
        marks_map=marks_map,
        sched=sched,
        selected_exam_id=int(selected_exam_id) if selected_exam_id else None,
        selected_schedule_id=int(selected_schedule_id) if selected_schedule_id else None
    )

@exam_bp.route('/marks/export/<int:schedule_id>')
@login_required
@subscription_required
def export_marks_template(schedule_id):
    if current_user.role not in ['admin', 'teacher']:
        return "Unauthorized", 403

    sched = ExamSchedule.query.filter_by(id=schedule_id, school_id=current_user.school_id).first_or_404()
    exam = sched.exam_ref
    
    students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
        Student.school_id == current_user.school_id,
        Student.student_class == exam.class_name,
        StudentSubject.subject_id == sched.subject_id
    )
    if exam.section:
        students = students.filter(Student.section == exam.section)
    students = students.all()

    existing_marks = {m.student_id: m for m in ExamMark.query.filter_by(exam_schedule_id=schedule_id).all()}

    data = []
    for s in students:
        rec = existing_marks.get(s.id)
        data.append({
            "Admission No": s.admission_no,
            "Student Name": f"{s.first_name} {s.last_name or ''}".strip(),
            "Max Marks": sched.max_marks,
            "Marks Obtained": rec.marks_obtained if rec and not rec.is_absent else (0 if rec and rec.is_absent else ""),
            "Is Absent (Yes/No)": "Yes" if rec and rec.is_absent else "No",
            "Remarks": rec.remarks if rec else ""
        })

    df = pd.DataFrame(data)
    
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name="Marks Entry")
    output.seek(0)

    filename = f"Marks_Template_Exam_{exam.name.replace(' ', '_')}_{sched.subject.subject_name}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

@exam_bp.route('/marks/import/<int:schedule_id>', methods=['POST'])
@login_required
@subscription_required
def import_marks(schedule_id):
    if current_user.role not in ['admin', 'teacher']:
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    sched = ExamSchedule.query.filter_by(id=schedule_id, school_id=current_user.school_id).first_or_404()
    file = request.files.get('excel_file')
    if not file or not file.filename.endswith(('.xls', '.xlsx')):
        flash('Please upload a valid Excel file', 'danger')
        return redirect(url_for('exam.marks_entry', exam_id=sched.exam_id, schedule_id=schedule_id))

    try:
        df = pd.read_excel(file)
        required_cols = ["Admission No", "Marks Obtained", "Is Absent (Yes/No)", "Remarks"]
        for col in required_cols:
            if col not in df.columns:
                flash(f"Missing required column in Excel: {col}", 'danger')
                return redirect(url_for('exam.marks_entry', exam_id=sched.exam_id, schedule_id=schedule_id))

        count = 0
        for index, row in df.iterrows():
            adm_no = str(row["Admission No"]).strip()
            # Find student
            student = Student.query.filter_by(school_id=current_user.school_id, admission_no=adm_no).first()
            if not student:
                continue

            marks_obtained_raw = row["Marks Obtained"]
            is_absent_raw = str(row["Is Absent (Yes/No)"]).strip().lower()
            remarks = str(row["Remarks"]).strip() if pd.notna(row["Remarks"]) else ""

            is_absent = True if is_absent_raw in ['yes', 'y', 'true', '1'] else False
            
            try:
                marks_obtained = float(marks_obtained_raw) if pd.notna(marks_obtained_raw) and not is_absent else 0.0
            except ValueError:
                marks_obtained = 0.0

            if marks_obtained > sched.max_marks:
                flash(f"Error at row {index+2}: Marks ({marks_obtained}) exceeds Max Marks ({sched.max_marks}) for admission no {adm_no}.", 'danger')
                return redirect(url_for('exam.marks_entry', exam_id=sched.exam_id, schedule_id=schedule_id))

            mark_rec = ExamMark.query.filter_by(exam_schedule_id=schedule_id, student_id=student.id).first()
            if not mark_rec:
                mark_rec = ExamMark(
                    school_id=current_user.school_id,
                    exam_schedule_id=schedule_id,
                    student_id=student.id,
                    subject_id=sched.subject_id,
                    marks_obtained=marks_obtained,
                    is_absent=is_absent,
                    remarks=remarks,
                    teacher_id=current_user.employee_id if current_user.role == 'teacher' else None
                )
                db.session.add(mark_rec)
            else:
                mark_rec.marks_obtained = marks_obtained
                mark_rec.is_absent = is_absent
                mark_rec.remarks = remarks
                mark_rec.updated_at = datetime.utcnow()
            count += 1

        db.session.commit()
        log_exam_action("Imported Marks via Excel", f"Imported {count} student marks for schedule {schedule_id}")
        flash(f"Successfully imported marks for {count} students", "success")

    except Exception as e:
        flash(f"Failed to import Excel: {str(e)}", "danger")

    return redirect(url_for('exam.marks_entry', exam_id=sched.exam_id, schedule_id=schedule_id))


# =========================================================
# 📄 ADMIT CARDS GENERATION (PDF)
# =========================================================
@exam_bp.route('/admit-cards', methods=['GET', 'POST'])
@login_required
@subscription_required
def admit_cards():
    if current_user.role not in ['admin', 'teacher', 'student']:
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    if current_user.role == 'student':
        # Direct download for self
        student = Student.query.filter_by(id=current_user.student_id, school_id=current_user.school_id).first_or_404()
        exams = Exam.query.filter_by(school_id=current_user.school_id, class_name=student.student_class).all()
        return render_template('exam/student_admit_card.html', student=student, exams=exams)

    # Admin/Teacher Filter
    exams = Exam.query.filter_by(school_id=current_user.school_id).all()
    
    if request.method == 'POST':
        exam_id = request.form.get('exam_id')
        section = request.form.get('section') or None
        
        exam = Exam.query.get_or_404(exam_id)
        
        # Build PDF
        buffer = generate_admit_cards_pdf(exam, section)
        if not buffer:
            flash("No students or schedule found to generate admit cards.", "warning")
            return redirect(url_for('exam.admit_cards'))

        filename = f"Admit_Cards_Class_{exam.class_name}_{exam.name.replace(' ', '_')}.pdf"
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype="application/pdf"
        )

    return render_template('exam/admit_card_filter.html', exams=exams)

@exam_bp.route('/admit-cards/student/<int:exam_id>/<int:student_id>')
@login_required
@subscription_required
def student_admit_card_pdf(exam_id, student_id):
    # Authorization checks
    if current_user.role == 'student' and current_user.student_id != student_id:
        return "Unauthorized", 403

    exam = Exam.query.get_or_404(exam_id)
    student = Student.query.get_or_404(student_id)

    buffer = generate_single_admit_card_pdf(exam, student)
    if not buffer:
        flash("Exam schedule not found.", "warning")
        if current_user.role == 'student':
            return redirect(url_for('exam.admit_cards'))
        return redirect(url_for('exam.admit_cards'))

    filename = f"Admit_Card_{student.first_name}_{exam.name.replace(' ', '_')}.pdf"
    return send_file(
        buffer,
        as_attachment=True,
        download_name=filename,
        mimetype="application/pdf"
    )

def generate_admit_cards_pdf(exam, section=None):
    """Generates PDF of admit cards for all students in a class/section using ReportLab."""
    stud_query = Student.query.filter_by(school_id=current_user.school_id, student_class=exam.class_name)
    if section:
        stud_query = stud_query.filter_by(section=section)
    elif exam.section:
        stud_query = stud_query.filter_by(section=exam.section)
    students = stud_query.order_by(Student.first_name).all()

    schedules = ExamSchedule.query.filter_by(exam_id=exam.id).order_by(ExamSchedule.date, ExamSchedule.start_time).all()

    if not students or not schedules:
        return None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'AdmitTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        alignment=1, # Center
        spaceAfter=5,
        textColor=colors.HexColor('#0b1e3c')
    )
    
    subtitle_style = ParagraphStyle(
        'AdmitSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        alignment=1, # Center
        spaceAfter=15,
        textColor=colors.HexColor('#ffc107')
    )

    label_style = ParagraphStyle(
        'AdmitLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#0b1e3c')
    )

    value_style = ParagraphStyle(
        'AdmitValue',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10
    )

    th_style = ParagraphStyle(
        'TableHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white
    )

    tb_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9
    )

    story = []

    for index, student in enumerate(students):
        # Header Info Table
        header_data = [
            [Paragraph("SCHOOL ERP SYSTEMS", title_style), ""],
            [Paragraph(f"ADMIT CARD - {exam.name.upper()}", subtitle_style), ""],
            [Paragraph("Student Name:", label_style), Paragraph(f"{student.first_name} {student.last_name or ''}", value_style)],
            [Paragraph("Admission No:", label_style), Paragraph(student.admission_no, value_style)],
            [Paragraph("Class / Section:", label_style), Paragraph(f"{student.student_class} - {student.section or 'N/A'}", value_style)],
            [Paragraph("Academic Session:", label_style), Paragraph(exam.session_ref.name, value_style)]
        ]
        
        t_header = Table(header_data, colWidths=[2.0*inch, 5.0*inch])
        t_header.setStyle(TableStyle([
            ('SPAN', (0, 0), (1, 0)),
            ('SPAN', (0, 1), (1, 1)),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))

        # Schedule Table
        table_data = [[
            Paragraph("Date", th_style),
            Paragraph("Subject", th_style),
            Paragraph("Time", th_style),
            Paragraph("Room", th_style),
        ]]

        for sc in schedules:
            # Check if student is allocated to this subject
            allocated = StudentSubject.query.filter_by(
                school_id=student.school_id,
                student_id=student.id,
                subject_id=sc.subject_id
            ).first()
            if not allocated:
                continue

            table_data.append([
                Paragraph(sc.date.strftime("%d %b %Y"), tb_style),
                Paragraph(sc.subject.subject_name, tb_style),
                Paragraph(f"{sc.start_time.strftime('%I:%M %p')} - {sc.end_time.strftime('%I:%M %p')}", tb_style),
                Paragraph(sc.room_no or "N/A", tb_style)
            ])

        t_schedule = Table(table_data, colWidths=[1.5*inch, 2.5*inch, 2.0*inch, 1.2*inch])
        t_schedule.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0b1e3c')),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
        ]))

        # Footer Signatures
        sig_data = [
            ["", ""],
            ["__________________________", "__________________________"],
            ["Class Teacher Signature", "Principal / Controller of Exams"]
        ]
        t_sig = Table(sig_data, colWidths=[3.5*inch, 3.5*inch])
        t_sig.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 2), (-1, 2), 9),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
        ]))

        # Container card style using ReportLab KeepTogether
        elements = [
            Spacer(1, 10),
            t_header,
            Spacer(1, 15),
            Paragraph("EXAM SCHEDULE DETAILS", ParagraphStyle('SectionHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, spaceAfter=8, textColor=colors.HexColor('#0b1e3c'))),
            t_schedule,
            Spacer(1, 30),
            t_sig,
            Spacer(1, 20)
        ]
        
        story.append(KeepTogether(elements))
        
        # Add Page Break except for the last student
        if index < len(students) - 1:
            story.append(PageBreak())

    doc.build(story)
    buffer.seek(0)
    return buffer

def generate_single_admit_card_pdf(exam, student):
    """Helper to generate a PDF admit card for a single student."""
    schedules = ExamSchedule.query.filter_by(exam_id=exam.id).order_by(ExamSchedule.date, ExamSchedule.start_time).all()
    if not schedules:
        return None

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'AdmitTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        alignment=1,
        spaceAfter=5,
        textColor=colors.HexColor('#0b1e3c')
    )
    
    subtitle_style = ParagraphStyle(
        'AdmitSubtitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=12,
        alignment=1,
        spaceAfter=15,
        textColor=colors.HexColor('#ffc107')
    )

    label_style = ParagraphStyle(
        'AdmitLabel',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        textColor=colors.HexColor('#0b1e3c')
    )

    value_style = ParagraphStyle(
        'AdmitValue',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10
    )

    th_style = ParagraphStyle(
        'TableHead',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        textColor=colors.white
    )

    tb_style = ParagraphStyle(
        'TableBody',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9
    )

    story = []

    header_data = [
        [Paragraph("SCHOOL ERP SYSTEMS", title_style), ""],
        [Paragraph(f"ADMIT CARD - {exam.name.upper()}", subtitle_style), ""],
        [Paragraph("Student Name:", label_style), Paragraph(f"{student.first_name} {student.last_name or ''}", value_style)],
        [Paragraph("Admission No:", label_style), Paragraph(student.admission_no, value_style)],
        [Paragraph("Class / Section:", label_style), Paragraph(f"{student.student_class} - {student.section or 'N/A'}", value_style)],
        [Paragraph("Academic Session:", label_style), Paragraph(exam.session_ref.name, value_style)]
    ]
    
    t_header = Table(header_data, colWidths=[2.0*inch, 5.0*inch])
    t_header.setStyle(TableStyle([
        ('SPAN', (0, 0), (1, 0)),
        ('SPAN', (0, 1), (1, 1)),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
    ]))

    table_data = [[
        Paragraph("Date", th_style),
        Paragraph("Subject", th_style),
        Paragraph("Time", th_style),
        Paragraph("Room", th_style),
    ]]

    for sc in schedules:
        # Check if student is allocated to this subject
        allocated = StudentSubject.query.filter_by(
            school_id=student.school_id,
            student_id=student.id,
            subject_id=sc.subject_id
        ).first()
        if not allocated:
            continue

        table_data.append([
            Paragraph(sc.date.strftime("%d %b %Y"), tb_style),
            Paragraph(sc.subject.subject_name, tb_style),
            Paragraph(f"{sc.start_time.strftime('%I:%M %p')} - {sc.end_time.strftime('%I:%M %p')}", tb_style),
            Paragraph(sc.room_no or "N/A", tb_style)
        ])

    t_schedule = Table(table_data, colWidths=[1.5*inch, 2.5*inch, 2.0*inch, 1.2*inch])
    t_schedule.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0b1e3c')),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cccccc')),
    ]))

    sig_data = [
        ["", ""],
        ["__________________________", "__________________________"],
        ["Class Teacher Signature", "Principal / Controller of Exams"]
    ]
    t_sig = Table(sig_data, colWidths=[3.5*inch, 3.5*inch])
    t_sig.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 2), (-1, 2), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
    ]))

    story.extend([
        Spacer(1, 10),
        t_header,
        Spacer(1, 15),
        Paragraph("EXAM SCHEDULE DETAILS", ParagraphStyle('SectionHeader', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=11, spaceAfter=8, textColor=colors.HexColor('#0b1e3c'))),
        t_schedule,
        Spacer(1, 30),
        t_sig
    ])

    doc.build(story)
    buffer.seek(0)
    return buffer
