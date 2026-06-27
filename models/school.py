from extensions import db
from datetime import datetime


class School(db.Model):
    __tablename__ = 'schools'

    id = db.Column(db.Integer, primary_key=True)
    school_code = db.Column(db.String(20), unique=True, nullable=False)
    school_name = db.Column(db.String(200), nullable=False)
    is_active = db.Column(db.Boolean, default=True)

    address = db.Column(db.Text)
    city = db.Column(db.String(100))
    state = db.Column(db.String(100))
    pincode = db.Column(db.String(10))

    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))

    logo = db.Column(db.String(300))
    affiliation_no = db.Column(db.String(100))
    website = db.Column(db.String(200))

    # 🔥 ADD THIS (Subscription + Analytics)
    plan = db.Column(db.String(50), default="free")
    expiry_date = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')
    verification_code = db.Column(db.String(10))
    is_verified = db.Column(db.Boolean, default=False)
    otp_created_at = db.Column(db.DateTime)
    otp_attempts = db.Column(db.Integer, default=0)
    otp_blocked_until = db.Column(db.DateTime)
    license_key = db.Column(db.String(100))

        # FACE ATTENDANCE GEO LOCATION
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    radius = db.Column(db.Integer, default=100)
    
    users = db.relationship(
        'User',
        backref='school',
        cascade='all, delete-orphan'
    )