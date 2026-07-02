from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models.timetable import Room, AcademicTimetable
from models.exam import ExamSchedule
from models.subject import Subject
from models.teacher import Teacher
from super.routes import subscription_required
from datetime import datetime, time

timetable_bp = Blueprint('timetable', __name__, url_prefix='/timetable')

def detect_academic_conflict(class_name, section, day_of_week, period_no, teacher_id, room_id, school_id, ignore_id=None):
    """
    Validates academic timetable conflicts:
    1. Teacher Conflict: Is the teacher assigned to another class during the same day and period?
    2. Room Conflict: Is the room booked for another class during the same day and period?
    3. Student Conflict: Does this class/section already have a subject scheduled during this day and period?
    """
    conflicts = []

    # 1. Teacher Check
    t_conflict = AcademicTimetable.query.filter(
        AcademicTimetable.school_id == school_id,
        AcademicTimetable.day_of_week == day_of_week,
        AcademicTimetable.period_no == period_no,
        AcademicTimetable.teacher_id == teacher_id
    )
    if ignore_id:
        t_conflict = t_conflict.filter(AcademicTimetable.id != ignore_id)
    t_match = t_conflict.first()
    if t_match:
        conflicts.append(f"Teacher is already assigned to Class {t_match.class_name}-{t_match.section} in period {period_no}")

    # 2. Room Check
    if room_id:
        r_conflict = AcademicTimetable.query.filter(
            AcademicTimetable.school_id == school_id,
            AcademicTimetable.day_of_week == day_of_week,
            AcademicTimetable.period_no == period_no,
            AcademicTimetable.room_id == room_id
        )
        if ignore_id:
            r_conflict = r_conflict.filter(AcademicTimetable.id != ignore_id)
        r_match = r_conflict.first()
        if r_match:
            conflicts.append(f"Room {r_match.room_ref.room_no} is already occupied by Class {r_match.class_name}-{r_match.section} in period {period_no}")

    # 3. Class/Section check (Student double booking)
    s_conflict = AcademicTimetable.query.filter(
        AcademicTimetable.school_id == school_id,
        AcademicTimetable.class_name == class_name,
        AcademicTimetable.section == section,
        AcademicTimetable.day_of_week == day_of_week,
        AcademicTimetable.period_no == period_no
    )
    if ignore_id:
        s_conflict = s_conflict.filter(AcademicTimetable.id != ignore_id)
    s_match = s_conflict.first()
    if s_match:
        conflicts.append(f"Class {class_name}-{section} already has {s_match.subject.subject_name} scheduled in period {period_no}")

    return conflicts

# =========================================================
# 🏫 ROOM MANAGEMENT
# =========================================================
@timetable_bp.route('/rooms', methods=['GET', 'POST'])
@login_required
@subscription_required
def rooms_list():
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    if request.method == 'POST':
        room_no = request.form.get('room_no')
        building = request.form.get('building')
        capacity = int(request.form.get('capacity', 40))

        if room_no:
            existing = Room.query.filter_by(school_id=current_user.school_id, room_no=room_no).first()
            if existing:
                flash(f"Room {room_no} already exists", "warning")
            else:
                room = Room(school_id=current_user.school_id, room_no=room_no, building=building, capacity=capacity)
                db.session.add(room)
                db.session.commit()
                flash('Room added successfully', 'success')
        return redirect(url_for('timetable.rooms_list'))

    rooms = Room.query.filter_by(school_id=current_user.school_id).all()
    return render_template('timetable/rooms.html', rooms=rooms)

@timetable_bp.route('/rooms/delete/<int:id>')
@login_required
@subscription_required
def delete_room(id):
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    room = Room.query.filter_by(id=id, school_id=current_user.school_id).first_or_404()
    db.session.delete(room)
    db.session.commit()
    flash('Room deleted successfully', 'success')
    return redirect(url_for('timetable.rooms_list'))


# =========================================================
# 📅 ACADEMIC TIMETABLE
# =========================================================
@timetable_bp.route('/', methods=['GET'])
@login_required
@subscription_required
def academic_list():
    class_name = request.args.get('class_name')
    section = request.args.get('section')
    
    timetable_data = {}
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]
    periods = range(1, 9) # 8 periods a day

    if class_name and section:
        records = AcademicTimetable.query.filter_by(
            school_id=current_user.school_id,
            class_name=class_name,
            section=section
        ).all()

        # Map to day_of_week and period_no
        for r in records:
            if r.day_of_week not in timetable_data:
                timetable_data[r.day_of_week] = {}
            timetable_data[r.day_of_week][r.period_no] = r

    return render_template(
        'timetable/academic_list.html',
        class_name=class_name,
        section=section,
        days=days,
        periods=periods,
        timetable_data=timetable_data
    )

@timetable_bp.route('/create', methods=['GET', 'POST'])
@login_required
@subscription_required
def academic_create():
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    class_name = request.args.get('class_name')
    section = request.args.get('section')
    day = request.args.get('day')
    period = request.args.get('period')

    subjects = Subject.query.filter_by(school_id=current_user.school_id, class_name=class_name).all()
    teachers = Teacher.query.filter_by(school_id=current_user.school_id).all()
    rooms = Room.query.filter_by(school_id=current_user.school_id).all()

    if request.method == 'POST':
        class_name = request.form.get('class_name')
        section = request.form.get('section')
        day_of_week = request.form.get('day_of_week')
        period_no = int(request.form.get('period_no'))
        
        start_time_str = request.form.get('start_time')
        end_time_str = request.form.get('end_time')
        subject_id = int(request.form.get('subject_id'))
        teacher_id = int(request.form.get('teacher_id'))
        room_id = request.form.get('room_id')
        room_id = int(room_id) if room_id else None

        start_time = datetime.strptime(start_time_str, '%H:%M').time() if start_time_str else None
        end_time = datetime.strptime(end_time_str, '%H:%M').time() if end_time_str else None

        # Verify Conflicts
        conflicts = detect_academic_conflict(class_name, section, day_of_week, period_no, teacher_id, room_id, current_user.school_id)
        if conflicts:
            for conf in conflicts:
                flash(conf, 'danger')
            return redirect(url_for('timetable.academic_create', class_name=class_name, section=section, day=day_of_week, period=period_no))

        # Check existing and overwrite or add
        existing = AcademicTimetable.query.filter_by(
            school_id=current_user.school_id,
            class_name=class_name,
            section=section,
            day_of_week=day_of_week,
            period_no=period_no
        ).first()

        if existing:
            existing.start_time = start_time
            existing.end_time = end_time
            existing.subject_id = subject_id
            existing.teacher_id = teacher_id
            existing.room_id = room_id
        else:
            sched = AcademicTimetable(
                school_id=current_user.school_id,
                class_name=class_name,
                section=section,
                day_of_week=day_of_week,
                period_no=period_no,
                start_time=start_time,
                end_time=end_time,
                subject_id=subject_id,
                teacher_id=teacher_id,
                room_id=room_id
            )
            db.session.add(sched)
        
        db.session.commit()
        flash('Timetable slot saved successfully', 'success')
        return redirect(url_for('timetable.academic_list', class_name=class_name, section=section))

    return render_template(
        'timetable/academic_create.html',
        class_name=class_name,
        section=section,
        day=day,
        period=period,
        subjects=subjects,
        teachers=teachers,
        rooms=rooms
    )

@timetable_bp.route('/delete/<int:id>')
@login_required
@subscription_required
def delete_timetable_slot(id):
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    slot = AcademicTimetable.query.filter_by(id=id, school_id=current_user.school_id).first_or_404()
    class_name = slot.class_name
    section = slot.section
    db.session.delete(slot)
    db.session.commit()
    flash('Timetable slot deleted successfully', 'success')
    return redirect(url_for('timetable.academic_list', class_name=class_name, section=section))


# =========================================================
# 📅 EXAM TIMETABLE VIEWER
# =========================================================
@timetable_bp.route('/exam/<int:exam_id>')
@login_required
@subscription_required
def exam_timetable(exam_id):
    from models.exam import Exam
    exam = Exam.query.filter_by(id=exam_id, school_id=current_user.school_id).first_or_404()
    schedules = ExamSchedule.query.filter_by(exam_id=exam_id).order_by(ExamSchedule.date, ExamSchedule.start_time).all()
    
    return render_template('timetable/exam_timetable.html', exam=exam, schedules=schedules)


# =========================================================
# 🚨 CONFLICT DETECTION BOARD
# =========================================================
@timetable_bp.route('/conflicts')
@login_required
@subscription_required
def check_all_conflicts():
    if current_user.role != 'admin':
        flash('Unauthorized Access', 'danger')
        return redirect(url_for('dashboard.home'))

    # Run check across all academic schedules
    all_slots = AcademicTimetable.query.filter_by(school_id=current_user.school_id).all()
    conflicts = []

    for index, slot in enumerate(all_slots):
        issues = detect_academic_conflict(
            slot.class_name,
            slot.section,
            slot.day_of_week,
            slot.period_no,
            slot.teacher_id,
            slot.room_id,
            current_user.school_id,
            ignore_id=slot.id
        )
        if issues:
            conflicts.append({
                "slot": f"{slot.class_name}-{slot.section} ({slot.day_of_week}, Period {slot.period_no}) - {slot.subject.subject_name}",
                "reasons": issues
            })

    return render_template('timetable/conflict_check.html', conflicts=conflicts)
