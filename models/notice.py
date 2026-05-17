from extensions import db
from datetime import datetime

class NoticeLog(db.Model):
    __tablename__ = "notice_log"

    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(db.Integer, nullable=False)
    notice_type = db.Column(db.String(50))  # HOLIDAY, EMERGENCY etc.

    title = db.Column(db.String(200))
    message_en = db.Column(db.Text)
    message_hi = db.Column(db.Text)

    target_group = db.Column(db.String(20))  # parents / teachers
    sent_status = db.Column(db.Boolean, default=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    hindi_only = db.Column(db.Boolean, default=False)