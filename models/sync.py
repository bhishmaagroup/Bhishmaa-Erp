from datetime import datetime
from extensions import db


class SyncQueue(db.Model):
    __tablename__ = 'sync_queue'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=True)
    table_name = db.Column(db.String(100), nullable=False)
    record_id = db.Column(db.String(100), nullable=False)
    operation_type = db.Column(db.String(20), nullable=False)  # CREATE, UPDATE, DELETE
    payload_json = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), default='PENDING')  # PENDING, SYNCED, FAILED, PERMANENTLY_FAILED
    error_message = db.Column(db.Text, nullable=True)
    retry_count = db.Column(db.Integer, default=0)
    priority = db.Column(db.Integer, default=5)  # 1=highest (schools), 2=students, 5=rest
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    synced_at = db.Column(db.DateTime, nullable=True)


class ConflictLog(db.Model):
    __tablename__ = 'conflict_logs'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=True)
    table_name = db.Column(db.String(100), nullable=False)
    record_uuid = db.Column(db.String(50), nullable=False)
    local_payload = db.Column(db.Text, nullable=True)
    cloud_payload = db.Column(db.Text, nullable=True)
    local_updated_at = db.Column(db.DateTime, nullable=True)
    cloud_updated_at = db.Column(db.DateTime, nullable=True)
    resolution = db.Column(db.String(100))
    resolved = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class DeletedRecord(db.Model):
    __tablename__ = 'deleted_records'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=True)
    table_name = db.Column(db.String(100), nullable=False)
    record_uuid = db.Column(db.String(50), nullable=False)
    deleted_at = db.Column(db.DateTime, default=datetime.utcnow)


class SyncSession(db.Model):
    __tablename__ = 'sync_sessions'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=True)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime, nullable=True)
    trigger = db.Column(db.String(50))  # login, scheduler, manual, internet_detect
    pushed_count = db.Column(db.Integer, default=0)
    pulled_count = db.Column(db.Integer, default=0)
    conflict_count = db.Column(db.Integer, default=0)
    failed_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='running')  # running/success/failed/partial
    error_log = db.Column(db.Text, nullable=True)
