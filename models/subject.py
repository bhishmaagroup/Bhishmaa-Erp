from extensions import db


class Subject(db.Model):

    __tablename__ = "subject"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    school_id = db.Column(
        db.Integer,
        nullable=False
    )

    class_name = db.Column(
        db.String(20)
    )

    section = db.Column(
        db.String(10)
    )

    subject_name = db.Column(
        db.String(100),
        nullable=False
    )

    subject_code = db.Column(
        db.String(20)
    )

    is_optional = db.Column(
        db.Boolean,
        default=False
    )

    subject_type = db.Column(
        db.String(50),
        default="Theory"
    )

    status = db.Column(
        db.Boolean,
        default=True
    )

    teacher_assignments = db.relationship(
        "TeacherSubject",
        backref="subject",
        lazy=True
    )

    student_allocations = db.relationship(
        "StudentSubject",
        backref="subject",
        lazy=True
    )