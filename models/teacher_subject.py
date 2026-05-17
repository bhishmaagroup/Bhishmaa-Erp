from extensions import db


class TeacherSubject(db.Model):

    __tablename__ = "teacher_subject"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    school_id = db.Column(
        db.Integer
    )

    teacher_id = db.Column(
        db.Integer,
        db.ForeignKey("teacher.id"),
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

    