from flask import Blueprint
from flask import render_template
from flask import request
from flask import redirect
from flask import flash

from flask_login import login_required
from flask_login import current_user

from extensions import db

from models.subject import Subject
from models.teacher_subject import TeacherSubject
from models.student_subject import StudentSubject

from models.teacher import Teacher
from models.student import Student


subject = Blueprint(
    "subject",
    __name__,
    url_prefix="/subject"
)


DEFAULT_SUBJECTS = {

    "PREPRIMARY": [
        "English",
        "Hindi",
        "Math",
        "Drawing",
        "Rhymes",
        "GK"
    ],

    "PRIMARY": [
        "English",
        "Hindi",
        "Mathematics",
        "EVS",
        "Computer",
        "GK",
        "Drawing",
        "Moral Science"
    ],

    "MIDDLE": [
        "English",
        "Hindi",
        "Mathematics",
        "Science",
        "Social Science",
        "Computer",
        "GK",
        "Sanskrit",
        "Drawing",
        "Physical Education"
    ],

    "SECONDARY": [
        "English",
        "Hindi",
        "Mathematics",
        "Science",
        "Social Science",
        "Computer",
        "Sanskrit",
        "Physical Education",
        "Artificial Intelligence",
        "Information Technology"
    ],

    "HIGHER": [

        "Physics",
        "Chemistry",
        "Mathematics",
        "Biology",
        "English",
        "Computer Science",
        "Physical Education",
        "Economics",
        "Business Studies",
        "Accountancy",
        "Political Science",
        "History",
        "Geography",
        "Psychology",
        "Sociology",
        "Hindi",
        "Painting",
        "Entrepreneurship",
        "IP",
        "Applied Math"
    ]
}

# =========================================================
# SUBJECT MASTER
# =========================================================
@subject.route("/", methods=["GET", "POST"])
@login_required
def subject_list():

    if request.method == "POST":

        sub = Subject(

            school_id=current_user.school_id,

            class_name=request.form.get("class_name"),

            section=request.form.get("section"),

            subject_name=request.form.get("subject_name"),

            subject_code=request.form.get("subject_code"),

            is_optional=True if request.form.get("is_optional") else False
        )

        db.session.add(sub)

        db.session.commit()

        flash(
            "Subject added successfully",
            "success"
        )

        return redirect(request.url)

    subjects = Subject.query.filter_by(
        school_id=current_user.school_id
    ).order_by(
        Subject.class_name
    ).all()

    return render_template(
        "subject/list.html",
        subjects=subjects
    )


# =========================================================
# TEACHER ASSIGN
# =========================================================
@subject.route(
    "/teacher-assign",
    methods=["GET", "POST"]
)
@login_required
def teacher_assign():

    subjects = Subject.query.filter_by(
        school_id=current_user.school_id
    ).all()

    teachers = Teacher.query.filter_by(
        school_id=current_user.school_id
    ).all()

    if request.method == "POST":

        teacher_id = request.form.get(
            "teacher_id"
        )

        subject_ids = request.form.getlist(
            "subject_ids"
        )

        for sub_id in subject_ids:

            already = TeacherSubject.query.filter_by(
                school_id=current_user.school_id,
                teacher_id=teacher_id,
                subject_id=sub_id
            ).first()

            if already:
                continue

            sub = Subject.query.get(sub_id)

            assign = TeacherSubject(

                school_id=current_user.school_id,

                teacher_id=teacher_id,

                subject_id=sub_id,

                class_name=sub.class_name,

                section=sub.section
            )

            db.session.add(assign)

        db.session.commit()

        flash(
            "Teacher assigned successfully",
            "success"
        )

        return redirect(request.url)

    assignments = TeacherSubject.query.filter_by(
        school_id=current_user.school_id
    ).all()

    return render_template(
        "subject/teacher_assign.html",
        subjects=subjects,
        teachers=teachers,
        assignments=assignments
    )


# =========================================================
# STUDENT SUBJECT ALLOCATION
# =========================================================
@subject.route(
    "/student-allocation",
    methods=["GET", "POST"]
)
@login_required
def student_allocation():

    subjects = []

    students = []

    class_name = request.args.get(
        "class"
    )

    section = request.args.get(
        "section"
    )

    if class_name and section:

        subjects = Subject.query.filter_by(
            school_id=current_user.school_id,
            class_name=class_name,
            section=section
        ).all()

        students = Student.query.filter_by(
            school_id=current_user.school_id,
            student_class=class_name,
            section=section
        ).all()

    if request.method == "POST":

        for student in students:

            for subject in subjects:

                already = StudentSubject.query.filter_by(
                    school_id=current_user.school_id,
                    student_id=student.id,
                    subject_id=subject.id
                ).first()

                if already:
                    continue

                alloc = StudentSubject(

                    school_id=current_user.school_id,

                    student_id=student.id,

                    subject_id=subject.id
                )

                db.session.add(alloc)

        db.session.commit()

        flash(
            "Subjects allocated successfully",
            "success"
        )

        return redirect(request.url)

    return render_template(
        "subject/student_allocation.html",
        subjects=subjects,
        students=students
    )

@subject.route("/generate-default", methods=["POST"])
@login_required
def generate_default_subjects():

    class_name = request.form.get("class_name")

    section = request.form.get("section")

    if class_name in ["Nursery", "LKG", "UKG"]:

        subjects = DEFAULT_SUBJECTS["PREPRIMARY"]

    elif class_name in [
        "I", "II", "III", "IV", "V"
    ]:

        subjects = DEFAULT_SUBJECTS["PRIMARY"]

    elif class_name in [
        "VI", "VII", "VIII"
    ]:

        subjects = DEFAULT_SUBJECTS["MIDDLE"]

    elif class_name in [
        "IX", "X"
    ]:

        subjects = DEFAULT_SUBJECTS["SECONDARY"]

    else:

        subjects = DEFAULT_SUBJECTS["HIGHER"]

    for sub_name in subjects:

        already = Subject.query.filter_by(
            school_id=current_user.school_id,
            class_name=class_name,
            section=section,
            subject_name=sub_name
        ).first()

        if already:
            continue

        code = sub_name[:3].upper()

        db.session.add(

            Subject(

                school_id=current_user.school_id,

                class_name=class_name,

                section=section,

                subject_name=sub_name,

                subject_code=code
            )
        )

    db.session.commit()

    flash(
        "Default subjects generated successfully",
        "success"
    )

    return redirect("/subject/")

@subject.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit_subject(id):

    sub = Subject.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()

    if request.method == "POST":

        sub.class_name = request.form.get(
            "class_name"
        )

        sub.section = request.form.get(
            "section"
        )

        sub.subject_name = request.form.get(
            "subject_name"
        )

        sub.subject_code = request.form.get(
            "subject_code"
        )

        sub.is_optional = True if request.form.get(
            "is_optional"
        ) else False

        db.session.commit()

        flash(
            "Subject updated successfully",
            "success"
        )

        return redirect("/subject/")

    return render_template(
        "subject/edit.html",
        sub=sub
    )

@subject.route("/delete/<int:id>")
@login_required
def delete_subject(id):

    sub = Subject.query.filter_by(
        id=id,
        school_id=current_user.school_id
    ).first_or_404()

    db.session.delete(sub)

    db.session.commit()

    flash(
        "Subject deleted successfully",
        "success"
    )

    return redirect("/subject/")