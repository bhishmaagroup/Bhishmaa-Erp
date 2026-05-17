from extensions import db
from flask_login import UserMixin
from datetime import datetime


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    username = db.Column(db.String(100), nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20))

    student_id = db.Column(db.Integer, nullable=True)
    employee_id = db.Column(db.Integer, nullable=True)

    force_password_change = db.Column(db.Boolean, default=True)

    # 🔥 ADD THIS
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime)

    otp = db.Column(db.String(6), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    otp_attempts = db.Column(db.Integer, default=0)
    

    __table_args__ = (
        db.UniqueConstraint('school_id', 'username', name='uq_school_user'),
    )