from datetime import datetime
from extensions import db

class PromotionHistory(db.Model):
    __tablename__ = 'promotion_histories'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    from_class = db.Column(db.String(20), nullable=False)
    to_class = db.Column(db.String(20), nullable=False)
    from_session = db.Column(db.String(20), nullable=False)
    to_session = db.Column(db.String(20), nullable=False)
    status = db.Column(db.String(20), nullable=False)  # Promoted / Retained
    promoted_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    school = db.relationship('School')
    student = db.relationship('Student')
    user = db.relationship('User')
