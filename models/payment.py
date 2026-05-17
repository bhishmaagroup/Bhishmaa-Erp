from extensions import db
from datetime import datetime

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))

    amount = db.Column(db.Integer, default=0)
    method = db.Column(db.String(50))

    screenshot = db.Column(db.String(200))

    status = db.Column(db.String(20), default="pending")  # pending / approved

    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    school = db.relationship('School')