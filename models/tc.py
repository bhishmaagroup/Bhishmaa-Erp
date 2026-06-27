from datetime import datetime
from extensions import db

class TransferCertificate(db.Model):
    __tablename__ = 'transfer_certificates'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    tc_number = db.Column(db.String(50), unique=True, nullable=False)
    admission_date = db.Column(db.Date)
    leave_date = db.Column(db.Date)
    reason_for_leaving = db.Column(db.String(255))
    conduct = db.Column(db.String(100), default="Good")
    academic_status = db.Column(db.String(255))
    fee_status = db.Column(db.String(100), default="All Dues Cleared")
    remarks = db.Column(db.Text)
    issue_date = db.Column(db.Date, default=datetime.utcnow().date)
    
    # CBSE standard TC fields
    nationality = db.Column(db.String(100), default="INDIAN")
    caste_category = db.Column(db.String(100), default="GENERAL")
    birth_words = db.Column(db.String(255))
    class_in_words = db.Column(db.String(255))
    last_exam_result = db.Column(db.String(255))
    whether_failed = db.Column(db.String(100), default="NO")
    subjects_studied = db.Column(db.String(255), default="ENGLISH, HINDI, MATHEMATICS, SCIENCE, SOCIAL SCIENCE, SANSKRIT, COMPUTER")
    promotion_status = db.Column(db.String(100), default="YES")
    dues_paid_upto = db.Column(db.String(100), default="MARCH")
    fee_concession = db.Column(db.String(100), default="NO")
    total_working_days = db.Column(db.Integer, default=220)
    days_present = db.Column(db.Integer, default=198)
    ncc_scout_guide = db.Column(db.String(100), default="NO")
    application_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    school = db.relationship('School')
    student = db.relationship('Student')
