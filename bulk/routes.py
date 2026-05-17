from flask import Blueprint, render_template, request, redirect, flash, Response
from flask_login import login_required, current_user
from models.student import Student
from models.teacher import Teacher
from models.user import User
from extensions import db
from werkzeug.security import generate_password_hash
import csv
import io

bulk_bp = Blueprint('bulk', __name__, url_prefix='/bulk')


# ===============================
# MAIN PAGE
# ===============================
@bulk_bp.route('/assign-login', methods=['GET', 'POST'])
@login_required
def assign_login():

    if current_user.role != "admin":
        return "Unauthorized", 403

    students = Student.query.filter_by(
        school_id=current_user.school_id
    ).all()

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).all()

    # 🔥 Mark already created users
    student_user_ids = {
        u.student_id for u in User.query.filter(
            User.student_id.isnot(None),
            User.school_id == current_user.school_id
        )
    }

    teacher_user_ids = {
        u.employee_id for u in User.query.filter(
            User.employee_id.isnot(None),
            User.school_id == current_user.school_id
        )
    }

    if request.method == "POST":

        # 🔥 Generate ALL
        if request.form.get("generate_all"):
            selected_students = [str(s.id) for s in students]
            selected_teachers = [str(t.id) for t in teachers]
        else:
            selected_students = request.form.getlist("students")
            selected_teachers = request.form.getlist("teachers")

        school_name = current_user.school.school_name.replace(" ", "").lower()

        created_data = []

        # ================= STUDENTS =================
        for sid in selected_students:

            if int(sid) in student_user_ids:
                continue

            student = Student.query.get(int(sid))
            username = f"anps_stu_{student.id}"

            user = User(
                school_id=current_user.school_id,
                username=username,
                password=generate_password_hash("student"),
                role="student",
                student_id=student.id
            )

            db.session.add(user)

            created_data.append({
                "name": f"{student.first_name} {student.middle_name or ''} {student.last_name or ''}".strip(),
                "username": username,
                "password": "student"
            })

        # ================= EMPLOYEES =================
        for tid in selected_teachers:

            if int(tid) in teacher_user_ids:
                continue

            teacher = Teacher.query.get(int(tid))
            username = f"anps_emp_{teacher.id}"

            user = User(
                school_id=current_user.school_id,
                username=username,
                password=generate_password_hash("employee"),
                role="teacher",
                employee_id=teacher.id
            )

            db.session.add(user)

            created_data.append({
                "name": f"{teacher.first_name} {teacher.middle_name or ''} {teacher.last_name or ''}".strip(),
                "username": username,
                "password": "employee"
            })

        db.session.commit()

        # 🔥 Save in session for CSV
        request.environ['created_data'] = created_data

        flash(f"{len(created_data)} users created successfully")
        return render_template(
            "bulk/assign_login.html",
            students=students,
            teachers=teachers,
            student_user_ids=student_user_ids,
            teacher_user_ids=teacher_user_ids,
            created_data=created_data
        )

    return render_template(
        "bulk/assign_login.html",
        students=students,
        teachers=teachers,
        student_user_ids=student_user_ids,
        teacher_user_ids=teacher_user_ids
    )


# ===============================
# CSV DOWNLOAD
# ===============================
@bulk_bp.route('/download-csv')
@login_required
def download_csv():

    created_data = request.args.get("data")

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["Name", "Username", "Password"])

    # ⚠️ Normally use session/db, simplified here
    for row in eval(created_data):
        writer.writerow([row['name'], row['username'], row['password']])

    output.seek(0)

    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=logins.csv"}
    )