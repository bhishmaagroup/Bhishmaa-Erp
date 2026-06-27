import os
import json
import uuid
import requests
import base64
import hashlib
import time
from datetime import datetime, date
from threading import Thread
from flask import current_app
from cryptography.fernet import Fernet
from sqlalchemy import event, inspect, text
from extensions import db, CustomModel
from models.sync import SyncQueue, ConflictLog, DeletedRecord
from models.school import School

# Tables to exclude from synchronization
EXCLUDE_TABLES = {'sync_queue', 'conflict_logs', 'deleted_records', 'super_admins', 'license_request', 'audit_logs'}

def get_fernet():
    secret_key = current_app.config.get('SECRET_KEY', 'secret-key')
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(key)

def encrypt_data(data_str):
    f = get_fernet()
    return f.encrypt(data_str.encode()).decode()

def decrypt_data(enc_str):
    f = get_fernet()
    return f.decrypt(enc_str.encode()).decode()

# =========================================================
# 🔄 SQLITE DATABASE SCHEMA MIGRATION
# =========================================================
def migrate_sqlite_db(app):
    """
    Dynamically migrates local SQLite tables to include tracking columns and UUIDs.
    """
    if os.environ.get("IS_ONLINE", "false").lower() == "true":
        return

    with app.app_context():
        engine = db.engine
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        # 1. Create any missing tables (like sync_queue, conflict_logs, deleted_records)
        db.create_all()

        columns_to_add = [
            ("uuid", "VARCHAR(36)"),
            ("school_id", "INTEGER"),
            ("created_at", "DATETIME"),
            ("updated_at", "DATETIME"),
            ("last_synced_at", "DATETIME"),
            ("sync_version", "INTEGER DEFAULT 1")
        ]

        connection = engine.connect()
        transaction = connection.begin()
        try:
            # 2. Add missing columns to existing tables
            for table_name in existing_tables:
                if table_name in EXCLUDE_TABLES:
                    continue
                current_columns = [col['name'] for col in inspector.get_columns(table_name)]
                for col_name, col_type in columns_to_add:
                    if col_name not in current_columns:
                        sql = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {col_type}"
                        connection.execute(text(sql))

            transaction.commit()
        except Exception as e:
            transaction.rollback()
            print(f"[Migration Error] Failed to alter tables: {e}")

        # 3. Generate UUIDs for existing rows and fix school_id values
        transaction = connection.begin()
        try:
            for table_name in existing_tables:
                if table_name in EXCLUDE_TABLES:
                    continue
                
                # Assign UUIDs
                res = connection.execute(text(f"SELECT rowid FROM {table_name} WHERE uuid IS NULL OR uuid = ''"))
                rows = res.fetchall()
                for r in rows:
                    new_uuid = str(uuid.uuid4())
                    connection.execute(text(f"UPDATE {table_name} SET uuid = :uuid WHERE rowid = :rowid"), {"uuid": new_uuid, "rowid": r[0]})

            # Backfill child tables' school_id if they are empty
            # - fee_discount
            if 'fee_discount' in existing_tables and 'students' in existing_tables:
                connection.execute(text(
                    "UPDATE fee_discount SET school_id = (SELECT school_id FROM students WHERE students.id = fee_discount.student_id) "
                    "WHERE school_id IS NULL"
                ))
            # - salary_payment
            if 'salary_payment' in existing_tables and 'salary_record' in existing_tables:
                connection.execute(text(
                    "UPDATE salary_payment SET school_id = (SELECT school_id FROM salary_record WHERE salary_record.id = salary_payment.salary_id) "
                    "WHERE school_id IS NULL"
                ))
            # - ticket_messages
            if 'ticket_messages' in existing_tables and 'tickets' in existing_tables:
                connection.execute(text(
                    "UPDATE ticket_messages SET school_id = (SELECT school_id FROM tickets WHERE tickets.id = ticket_messages.ticket_id) "
                    "WHERE school_id IS NULL"
                ))
            # - stops
            if 'stops' in existing_tables and 'routes' in existing_tables:
                connection.execute(text(
                    "UPDATE stops SET school_id = (SELECT school_id FROM routes WHERE routes.id = stops.route_id) "
                    "WHERE school_id IS NULL"
                ))

            transaction.commit()
            print("✅ SQLite database migration and UUID backfilling completed.")
        except Exception as e:
            transaction.rollback()
            print(f"[Migration Error] Failed to backfill values: {e}")
        finally:
            connection.close()

# =========================================================
# 📢 SYNC QUEUE EVENT LISTENERS
# =========================================================
def init_sync_engine(app):
    """
    Registers ORM event listeners to track changes.
    """
    @event.listens_for(db.Session, "before_flush")
    def track_sync_queue(session, flush_context, instances):
        # 1. Local changes logged to local queue
        if os.environ.get("IS_ONLINE", "false").lower() != "true":
            if getattr(session, "no_sync_logging", False):
                return

            def queue_op(obj, op_type):
                tbl_name = obj.__class__.__tablename__
                if tbl_name in EXCLUDE_TABLES:
                    return

                # Get record ID (uuid)
                rec_id = getattr(obj, 'uuid', None)
                if not rec_id:
                    rec_id = str(uuid.uuid4())
                    obj.uuid = rec_id

                school_id = getattr(obj, 'school_id', None)
                # If school_id not set on object, check if we can resolve it
                if not school_id:
                    # Default to current_user school_id or search DB
                    try:
                        from flask_login import current_user
                        school_id = current_user.school_id
                        obj.school_id = school_id
                    except Exception:
                        pass

                payload = None
                if op_type in ('CREATE', 'UPDATE'):
                    payload = obj.to_dict()

                sq = SyncQueue(
                    school_id=school_id,
                    table_name=tbl_name,
                    record_id=rec_id,
                    operation_type=op_type,
                    payload_json=json.dumps(payload) if payload else None,
                    status='PENDING'
                )
                session.add(sq)

            for obj in session.new:
                if isinstance(obj, CustomModel):
                    queue_op(obj, 'CREATE')

            for obj in session.dirty:
                if isinstance(obj, CustomModel):
                    if session.is_modified(obj):
                        queue_op(obj, 'UPDATE')

            for obj in session.deleted:
                if isinstance(obj, CustomModel):
                    queue_op(obj, 'DELETE')

        # 2. Server changes logged to DeletedRecord
        else:
            if getattr(session, "no_sync_logging", False):
                return

            for obj in session.deleted:
                if isinstance(obj, CustomModel):
                    tbl_name = obj.__class__.__tablename__
                    if tbl_name in EXCLUDE_TABLES:
                        continue
                    rec_uuid = getattr(obj, 'uuid', None)
                    school_id = getattr(obj, 'school_id', None)
                    if rec_uuid:
                        dr = DeletedRecord(
                            school_id=school_id,
                            table_name=tbl_name,
                            record_uuid=rec_uuid
                        )
                        session.add(dr)

# =========================================================
# 🌐 BIDIRECTIONAL SYNC ENGINE METHODS
# =========================================================
def check_internet():
    """
    Checks connection to the cloud server.
    """
    cloud_url = os.environ.get("CLOUD_SERVER_URL", "http://localhost:5000")
    try:
        res = requests.get(f"{cloud_url}/api/sync/status", timeout=5)
        return res.status_code == 200
    except Exception:
        return False

def generate_client_token(school_id):
    """
    Generates a secure token using itsdangerous serializer.
    """
    from itsdangerous import URLSafeSerializer
    secret_key = current_app.config.get('SECRET_KEY', 'secret-key')
    s = URLSafeSerializer(secret_key)
    return s.dumps({"school_id": school_id, "role": "sync_client"})

def perform_push(school_id):
    """
    Pushes local SyncQueue pending operations to the cloud server.
    """
    cloud_url = os.environ.get("CLOUD_SERVER_URL", "http://localhost:5000")
    
    # Get pending sync queue items
    pending = SyncQueue.query.filter_by(status='PENDING', school_id=school_id).order_by(SyncQueue.created_at.asc()).all()
    if not pending:
        return 0, []

    # Format payload
    ops = []
    for item in pending:
        ops.append({
            "queue_id": item.id,
            "table_name": item.table_name,
            "record_id": item.record_id,
            "operation_type": item.operation_type,
            "payload_json": item.payload_json,
            "created_at": item.created_at.isoformat()
        })

    payload = {"school_id": school_id, "operations": ops}
    enc_data = encrypt_data(json.dumps(payload))
    token = generate_client_token(school_id)

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    try:
        res = requests.post(f"{cloud_url}/api/sync/push", json={"payload": enc_data}, headers=headers, timeout=15)
        if res.status_code == 200:
            res_decrypted = decrypt_data(res.json()["payload"])
            res_data = json.loads(res_decrypted)
            
            synced_ids = res_data.get("synced_ids", [])
            failed_ops = res_data.get("failed_ops", []) # list of dict with queue_id and error

            # Mark synced items
            for item in pending:
                if item.id in synced_ids:
                    item.status = 'SYNCED'
                    item.synced_at = datetime.utcnow()
                elif item.id in [f["queue_id"] for f in failed_ops]:
                    err_msg = next((f["error"] for f in failed_ops if f["queue_id"] == item.id), "Unknown server error")
                    item.status = 'FAILED'
                    item.error_message = err_msg

            db.session.commit()
            return len(synced_ids), failed_ops
    except Exception as e:
        print(f"[Sync Push Error] {e}")
        return 0, [{"queue_id": None, "error": str(e)}]
    return 0, []

def perform_pull(school_id):
    """
    Pulls cloud database updates/deletes and applies them locally.
    """
    cloud_url = os.environ.get("CLOUD_SERVER_URL", "http://localhost:5000")
    
    # Find last successful sync timestamp
    last_sync = db.session.query(db.func.max(SyncQueue.synced_at)).filter_by(status='SYNCED', school_id=school_id).scalar()
    last_sync_str = last_sync.isoformat() if last_sync else "1970-01-01T00:00:00"

    token = generate_client_token(school_id)
    headers = {
        "Authorization": f"Bearer {token}"
    }

    try:
        res = requests.get(f"{cloud_url}/api/sync/pull?last_sync_time={last_sync_str}&school_id={school_id}", headers=headers, timeout=15)
        if res.status_code == 200:
            res_decrypted = decrypt_data(res.json()["payload"])
            res_data = json.loads(res_decrypted)

            updates = res_data.get("updates", {})
            deletions = res_data.get("deletions", [])
            server_time = res_data.get("server_time")

            # Temporarily disable sync triggers so pulled writes don't end up back in sync_queue
            db.session.no_sync_logging = True

            # Get subclass maps by tablename
            subclasses = db.Model.__subclasses__()
            subclass_map = {cls.__tablename__: cls for cls in subclasses if hasattr(cls, '__tablename__')}

            applied_count = 0
            conflict_count = 0

            # 1. Apply deletions
            for d in deletions:
                tbl_name = d["table_name"]
                rec_uuid = d["record_uuid"]
                cls = subclass_map.get(tbl_name)
                if cls:
                    rec = cls.query.filter_by(uuid=rec_uuid).first()
                    if rec:
                        db.session.delete(rec)
                        applied_count += 1

            # 2. Apply updates
            for tbl_name, records in updates.items():
                cls = subclass_map.get(tbl_name)
                if not cls:
                    continue

                for r in records:
                    rec_uuid = r["uuid"]
                    rec = cls.query.filter_by(uuid=rec_uuid).first()
                    server_updated_at = datetime.fromisoformat(r["updated_at"])

                    if rec:
                        # Conflict Check (Newest Wins)
                        local_updated_at = rec.updated_at
                        if server_updated_at > local_updated_at:
                            # Server wins
                            rec.update_from_dict(r)
                            rec.last_synced_at = datetime.fromisoformat(server_time)
                            applied_count += 1
                            
                            # Log conflict if local changes were overwritten
                            if rec.sync_version > r.get("sync_version", 0):
                                conflict = ConflictLog(
                                    school_id=school_id,
                                    table_name=tbl_name,
                                    record_uuid=rec_uuid,
                                    local_updated_at=local_updated_at,
                                    cloud_updated_at=server_updated_at,
                                    resolution='Cloud Won (Newer)'
                                )
                                db.session.add(conflict)
                                conflict_count += 1
                        else:
                            # Local is newer! Keep local, conflict resolved as local won
                            # It is already in SyncQueue and will be pushed to the server next push
                            if local_updated_at > server_updated_at:
                                conflict = ConflictLog(
                                    school_id=school_id,
                                    table_name=tbl_name,
                                    record_uuid=rec_uuid,
                                    local_updated_at=local_updated_at,
                                    cloud_updated_at=server_updated_at,
                                    resolution='Local Won (Newer)'
                                )
                                db.session.add(conflict)
                                conflict_count += 1
                    else:
                        # New record locally
                        new_obj = cls()
                        new_obj.update_from_dict(r)
                        new_obj.last_synced_at = datetime.fromisoformat(server_time)
                        db.session.add(new_obj)
                        applied_count += 1

            db.session.commit()
            
            # Send Acknowledge back to server
            requests.post(f"{cloud_url}/api/sync/ack", json={"payload": encrypt_data(json.dumps({"school_id": school_id, "server_time": server_time}))}, headers=headers, timeout=5)

            return applied_count, conflict_count
    except Exception as e:
        print(f"[Sync Pull Error] {e}")
        return 0, 0
    finally:
        db.session.no_sync_logging = False
    return 0, 0

# =========================================================
# ⏰ BACKGROUND SYNC SCHEDULER
# =========================================================
_sync_running = False

def start_sync_scheduler(app):
    """
    Starts a background thread that executes synchronization every 2 minutes.
    """
    if os.environ.get("IS_ONLINE", "false").lower() == "true":
        return

    def run_loop():
        global _sync_running
        time.sleep(10)  # Wait for startup to settle
        while True:
            try:
                with app.app_context():
                    # Find current school (in single school local setup)
                    school = School.query.first()
                    if school and check_internet():
                        print(f"[Sync Scheduler] internet detected. Starting sync for school {school.id}")
                        _sync_running = True
                        
                        push_count, failed_ops = perform_push(school.id)
                        pull_count, conflict_count = perform_pull(school.id)
                        
                        print(f"[Sync Scheduler] Synced: pushed {push_count} ops, pulled {pull_count} updates. Conflicts: {conflict_count}")
                        _sync_running = False
            except Exception as e:
                print(f"[Sync Scheduler Error] {e}")
                _sync_running = False
            
            # Sleep for 2 minutes (120s)
            time.sleep(120)

    t = Thread(target=run_loop, daemon=True)
    t.start()
    print("⏰ Background sync scheduler thread started (2-minute intervals).")

def generate_receipt_number(school_id, school_code=None):
    from models.school import School
    from models.fee import StudentFeeLedger
    from datetime import datetime
    
    if not school_code:
        school = School.query.get(school_id)
        school_code = school.school_code if school else "SCH"
        
    year = datetime.utcnow().year
    prefix = f"{school_code}-{year}-"
    
    # Find max receipt number with this prefix
    max_ledger = db.session.query(StudentFeeLedger.receipt_no).filter(
        StudentFeeLedger.school_id == school_id,
        StudentFeeLedger.receipt_no.like(f"{prefix}%")
    ).order_by(StudentFeeLedger.receipt_no.desc()).first()
    
    seq = 1
    if max_ledger and max_ledger[0]:
        try:
            parts = max_ledger[0].split('-')
            if len(parts) >= 3:
                seq = int(parts[-1]) + 1
        except Exception:
            pass
            
    return f"{prefix}{seq:06d}"
