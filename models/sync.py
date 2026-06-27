from datetime import datetime
from extensions import db

class SyncQueue(db.Model):
    __tablename__ = 'sync_queue'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=True)
    table_name = db.Column(db.String(100), nullable=False)
    record_id = db.Column(db.String(100), nullable=False)  # stores the record UUID
    operation_type = db.Column(db.String(20), nullable=False)  # CREATE, UPDATE, DELETE
    payload_json = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='PENDING')  # PENDING, SYNCED, FAILED
    error_message = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    synced_at = db.Column(db.DateTime, nullable=True)

class ConflictLog(db.Model):
    __tablename__ = 'conflict_logs'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=True)
    table_name = db.Column(db.String(100), nullable=False)
    record_uuid = db.Column(db.String(50), nullable=False)
    local_updated_at = db.Column(db.DateTime, nullable=True)
    cloud_updated_at = db.Column(db.DateTime, nullable=True)
    resolution = db.Column(db.String(100))  # e.g., 'Cloud Won (Newer)', 'Local Won (Newer)'
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DeletedRecord(db.Model):
    __tablename__ = 'deleted_records'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=True)
    table_name = db.Column(db.String(100), nullable=False)
    record_uuid = db.Column(db.String(50), nullable=False)
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow)
