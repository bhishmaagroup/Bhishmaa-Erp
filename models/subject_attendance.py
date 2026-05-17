from extensions import db
from datetime import date


class SubjectAttendance(db.Model):

    __tablename__ = "subject_attendance"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    school_id = db.Column(
        db.Integer,
        nullable=False
    )

    teacher_id = db.Column(
        db.Integer,
        db.ForeignKey("teacher.id"),
        nullable=False
    )

    student_id = db.Column(
        db.Integer,
        db.ForeignKey("students.id"),
        nullable=False
    )

    subject_id = db.Column(
        db.Integer,
        db.ForeignKey("subject.id"),
        nullable=False
    )

    class_name = db.Column(
        db.String(20)
    )

    section = db.Column(
        db.String(10)
    )

    attendance_date = db.Column(
        db.Date,
        default=date.today
    )

    period_no = db.Column(
        db.Integer,
        default=1
    )

    status = db.Column(
        db.String(2),
        default="P"
    )