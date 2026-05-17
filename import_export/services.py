import pandas as pd
from extensions import db
from sqlalchemy.exc import IntegrityError
from models.student import Student
from models.teacher import Teacher
from models.fee import StudentFeeLedger


def read_file(file):
    ext = file.filename.rsplit(".", 1)[1].lower()
    if ext == "csv":
        return pd.read_csv(file)
    elif ext in ["xlsx", "xls"]:
        return pd.read_excel(file)
    else:
        raise ValueError("Only CSV or Excel allowed")


# =========================
# IMPORT DATA
# =========================
def import_data(file, module, school_id):
    df = read_file(file)
    success, skipped = 0, 0

    if module == "student":
        for _, r in df.iterrows():
            try:
                s = Student(
                    school_id=school_id,

                    admission_no=r.get("admission_no"),
                    first_name=r.get("first_name"),
                    middle_name=r.get("middle_name"),
                    last_name=r.get("last_name"),
                    gender=r.get("gender"),
                    dob=r.get("dob"),
                    religion=r.get("religion"),
                    caste=r.get("caste"),
                    blood_group=r.get("blood_group"),

                    guardian_name=r.get("guardian_name"),
                    guardian_relation=r.get("guardian_relation"),
                    guardian_mobile=r.get("guardian_mobile"),
                    guardian_address=r.get("guardian_address"),

                    present_address=r.get("present_address"),
                    permanent_address=r.get("permanent_address"),

                    aadhaar=r.get("aadhaar"),
                    pen_no=r.get("pen_no"),

                    session=r.get("session"),
                    student_class=r.get("student_class"),
                    section=r.get("section"),

                    father_name=r.get("father_name"),
                    father_mobile=r.get("father_mobile"),
                    father_aadhaar=r.get("father_aadhaar"),

                    mother_name=r.get("mother_name"),
                    mother_mobile=r.get("mother_mobile"),
                    mother_aadhaar=r.get("mother_aadhaar"),

                    transport_required=r.get("transport_required", False),
                    transport_route=r.get("transport_route"),
                    pickup_point=r.get("pickup_point"),

                    hostel_required=r.get("hostel_required", False),
                    hostel_block=r.get("hostel_block"),
                    hostel_room=r.get("hostel_room"),
                )
                db.session.add(s)
                db.session.commit()
                success += 1

            except IntegrityError:
                db.session.rollback()
                skipped += 1

    elif module == "teacher":
        for _, r in df.iterrows():
            try:
                t = Teacher(
                    school_id=school_id,
                    teacher_code=r.get("teacher_code"),
                    first_name=r.get("first_name"),
                    middle_name=r.get("middle_name"),
                    last_name=r.get("last_name"),
                    gender=r.get("gender"),
                    dob=r.get("dob"),
                    mobile=r.get("mobile"),
                    email=r.get("email"),
                    address=r.get("address"),
                    permanent_address=r.get("permanent_address"),
                    qualification=r.get("qualification"),
                    experience=r.get("experience"),
                    specialization=r.get("specialization"),
                    employment_type=r.get("employment_type"),
                    joining_date=r.get("joining_date"),
                    salary=r.get("salary"),
                    designation=r.get("designation"),
                    aadhaar=r.get("aadhaar"),
                    pan=r.get("pan"),
                )
                db.session.add(t)
                db.session.commit()
                success += 1

            except IntegrityError:
                db.session.rollback()
                skipped += 1

    elif module == "fee":
        for _, r in df.iterrows():
            f = StudentFeeLedger(
                school_id=school_id,
                student_id=r.get("student_id"),
                month=r.get("month"),
                fee_type=r.get("fee_type"),
                total_amount=r.get("total_amount", 0),
                paid_amount=r.get("paid_amount", 0),
                balance_amount=(
                    r.get("total_amount", 0) - r.get("paid_amount", 0)
                ),
                receipt_no=r.get("receipt_no")
            )
            db.session.add(f)

        db.session.commit()

    return {
        "imported": success,
        "skipped": skipped
    }


# =========================
# EXPORT DATA (ALL COLUMNS)
# =========================
def export_data(module, school_id):
    import io
    from flask import send_file

    if module == "student":
        rows = Student.query.filter_by(school_id=school_id).all()
        data = [{c.name: getattr(r, c.name) for c in Student.__table__.columns} for r in rows]

    elif module == "teacher":
        rows = Teacher.query.filter_by(school_id=school_id).all()
        data = [{c.name: getattr(r, c.name) for c in Teacher.__table__.columns} for r in rows]

    elif module == "fee":
        rows = StudentFeeLedger.query.filter_by(school_id=school_id).all()
        data = [{c.name: getattr(r, c.name) for c in StudentFeeLedger.__table__.columns} for r in rows]

    else:
        data = []

    df = pd.DataFrame(data)
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)

    return send_file(
        output,
        download_name=f"{module}_full_export.xlsx",
        as_attachment=True
    )
