from extensions import db


class StudentSubject(db.Model):

    __tablename__ = "student_subject"

    id = db.Column(
        db.Integer,
        primary_key=True
    )

    school_id = db.Column(
        db.Integer
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

    