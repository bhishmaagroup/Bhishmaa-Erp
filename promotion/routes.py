from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from extensions import db
from models.student import Student
from models.exam import ExamResult, Exam
from models.promotion import PromotionHistory

promotion_bp = Blueprint('promotion', __name__, url_prefix='/promotion')

@promotion_bp.route('/', methods=['GET', 'POST'])
@login_required
def manage_promotions():
    # Fetch distinct classes and sections
    classes = db.session.query(Student.student_class).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.student_class).all()
    classes = [c[0] for c in classes if c[0]]

    sections = db.session.query(Student.section).filter_by(
        school_id=current_user.school_id
    ).distinct().order_by(Student.section).all()
    sections = [s[0] for s in sections if s[0]]

    selected_class = request.args.get('class_name')
    selected_section = request.args.get('section')
    
    students = []
    exams = []

    if selected_class and selected_section:
        # Load students of class
        students = Student.query.filter_by(
            school_id=current_user.school_id,
            student_class=selected_class,
            section=selected_section
        ).order_by(Student.first_name).all()

        # Fetch active exams to check results
        exams = Exam.query.filter_by(school_id=current_user.school_id).all()
        exam_ids = [e.id for e in exams]

        # Fetch latest results of these students to map to view
        if exam_ids:
            results = ExamResult.query.filter(
                ExamResult.school_id == current_user.school_id,
                ExamResult.student_id.in_([s.id for s in students])
            ).order_by(ExamResult.created_at.desc()).all()
            
            # Map student_id -> latest result
            result_map = {}
            for r in results:
                if r.student_id not in result_map:
                    result_map[r.student_id] = r
            
            for s in students:
                s.latest_result = result_map.get(s.id)

    # POST mapping for bulk promotion
    if request.method == 'POST':
        student_ids = request.form.getlist('student_ids')
        to_class = request.form.get('to_class')
        to_section = request.form.get('to_section')
        to_session = request.form.get('to_session')
        promotion_status = request.form.get('status')  # Promoted / Retained

        current_class = request.form.get('current_class')
        current_section = request.form.get('current_section')
        current_session = request.form.get('current_session')

        if not student_ids or not to_class or not to_session or not to_section:
            flash("Please fill in target Class, Section, Session, and select at least one student.", "danger")
            return redirect(url_for('promotion.manage_promotions', class_name=current_class, section=current_section))

        try:
            # Wrap promotion execution inside database transaction
            promoted_count = 0
            for sid in student_ids:
                student = Student.query.filter_by(id=int(sid), school_id=current_user.school_id).first()
                if student:
                    # Log Promotion History
                    log = PromotionHistory(
                        school_id=current_user.school_id,
                        student_id=student.id,
                        from_class=student.student_class,
                        to_class=to_class,
                        from_session=student.session,
                        to_session=to_session,
                        status=promotion_status,
                        promoted_by=current_user.id
                    )
                    db.session.add(log)

                    # Update Student class, section, session
                    student.student_class = to_class
                    student.section = to_section
                    student.session = to_session
                    promoted_count += 1

            db.session.commit()
            flash(f"Successfully processed {promoted_count} students as '{promotion_status}'!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Error processing promotions: {str(e)}", "danger")

        return redirect(url_for('promotion.manage_promotions', class_name=to_class, section=to_section))

    return render_template(
        'promotion/bulk_promote.html',
        classes=classes,
        sections=sections,
        selected_class=selected_class,
        selected_section=selected_section,
        students=students
    )


@promotion_bp.route('/history')
@login_required
def view_history():
    history = PromotionHistory.query.filter_by(school_id=current_user.school_id).order_by(PromotionHistory.created_at.desc()).all()
    return render_template('promotion/history.html', history=history)
