from extensions import db

class Holiday(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=False)
    holiday_date = db.Column(db.Date, nullable=False)
    title = db.Column(db.String(100))
