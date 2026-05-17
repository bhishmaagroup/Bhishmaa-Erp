from extensions import db
from datetime import datetime

class LicenseRequest(db.Model):
    __tablename__ = 'license_request'   # 🔥 add this

    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))

    plan = db.Column(db.String(20))
    status = db.Column(db.String(20), default="pending")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)