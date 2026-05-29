from extensions import db
from datetime import date

# =========================
# TEACHER ATTENDANCE
# =========================
class TeacherAttendance(db.Model):
    __tablename__ = "teacher_attendance"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=False)
    teacher_id = db.Column(db.Integer, nullable=False)
    attendance_date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(10), nullable=False)  # Present / Absent
    login_time = db.Column(db.DateTime)
    logout_time = db.Column(db.DateTime)
    working_hours = db.Column(db.Float, default=0)

    attendance_type = db.Column(db.String(20))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)

    photo = db.Column(db.String(255))

    method = db.Column(db.String(50), default="manual")

    created_at = db.Column(db.DateTime, server_default=db.func.now())


# =========================
# STUDENT ATTENDANCE
# =========================
class StudentAttendance(db.Model):
    __tablename__ = "student_attendance"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=False)
    student_id = db.Column(db.Integer, nullable=False)

    student_class = db.Column(db.String(20))
    section = db.Column(db.String(10))

    attendance_date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(5), nullable=False)  # P / A

    created_at = db.Column(db.DateTime, server_default=db.func.now())
