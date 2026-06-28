"""
sync_engine.py — Bhishmaa ERP Sync Engine (No .env required)
=============================================================
- Local SQLite always available
- Cloud PostgreSQL sync when internet is available
- Bidirectional, automatic, no data loss
"""

import os
import sys
import json
import uuid
import logging
import threading
import time
from datetime import datetime, date
from threading import Thread, Lock
from flask import current_app
from cryptography.fernet import Fernet
from sqlalchemy import event, inspect, text, create_engine
from sqlalchemy.pool import NullPool
from extensions import db, CustomModel
from models.sync import SyncQueue, ConflictLog, DeletedRecord, SyncSession
from models.school import School

logger = logging.getLogger('sync')
logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')

# ══════════════════════════════════════════════════════════════
# Tables excluded from sync
# ══════════════════════════════════════════════════════════════
EXCLUDE_TABLES = {
    'sync_queue', 'conflict_logs', 'deleted_records',
    'sync_sessions', 'super_admins', 'audit_logs', 'license_request'
}

# ══════════════════════════════════════════════════════════════
# Global sync state (accessible by routes)
# ══════════════════════════════════════════════════════════════
sync_status = {}
# { school_id: {status, last_sync, pushed, pulled, conflicts, message} }

_sync_running = False
_was_online   = False

# ══════════════════════════════════════════════════════════════
# Encryption (for REST API mode — kept for backward compat)
# ══════════════════════════════════════════════════════════════
import base64, hashlib
def get_fernet():
    secret_key = current_app.config.get('SECRET_KEY', 'secret-key')
    key = base64.urlsafe_b64encode(hashlib.sha256(secret_key.encode()).digest())
    return Fernet(key)

def encrypt_data(data_str):
    return get_fernet().encrypt(data_str.encode()).decode()

def decrypt_data(enc_str):
    return get_fernet().decrypt(enc_str.encode()).decode()


# ══════════════════════════════════════════════════════════════
# 🌐 INTERNET / CLOUD CHECK
# ══════════════════════════════════════════════════════════════
_internet_cache = {'result': False, 'checked_at': None}
_internet_lock  = Lock()

def check_internet():
    """Check cloud DB availability. Cached 20 seconds."""
    global _internet_cache
    with _internet_lock:
        now = datetime.utcnow()
        if (_internet_cache['checked_at'] and
                (now - _internet_cache['checked_at']).total_seconds() < 20):
            return _internet_cache['result']
        result = _check_cloud_reachable()
        _internet_cache['result']     = result
        _internet_cache['checked_at'] = now
        return result

def _check_cloud_reachable():
    """Try connecting to cloud PostgreSQL."""
    from utils.dual_db import get_cloud_url
    url = get_cloud_url()
    if not url:
        return False
    try:
        engine = create_engine(url, poolclass=NullPool,
                               connect_args={"connect_timeout": 4})
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False

def _force_internet_check():
    """Bypass cache."""
    global _internet_cache
    _internet_cache['checked_at'] = None
    return check_internet()


# ══════════════════════════════════════════════════════════════
# 🔄 SQLITE WAL MODE + MIGRATION
# ══════════════════════════════════════════════════════════════
def migrate_sqlite_db(app):
    if os.environ.get("IS_ONLINE", "false").lower() == "true":
        return

    with app.app_context():
        engine = db.engine
        try:
            with engine.connect() as conn:
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA synchronous=NORMAL"))
                conn.execute(text("PRAGMA cache_size=-32000"))
                conn.commit()
        except Exception as e:
            logger.warning(f"WAL mode: {e}")

        db.create_all()
        inspector = inspect(engine)
        existing_tables = inspector.get_table_names()

        tracking_cols = [
            ("uuid",          "VARCHAR(36)"),
            ("school_id",     "INTEGER"),
            ("created_at",    "DATETIME"),
            ("updated_at",    "DATETIME"),
            ("last_synced_at","DATETIME"),
            ("sync_version",  "INTEGER DEFAULT 1"),
        ]

        with engine.begin() as conn:
            for tbl in existing_tables:
                if tbl in EXCLUDE_TABLES:
                    continue
                existing_cols = {c['name'] for c in inspector.get_columns(tbl)}
                for col_name, col_type in tracking_cols:
                    base = col_name.split()[0]
                    if base not in existing_cols:
                        try:
                            conn.execute(text(
                                f'ALTER TABLE "{tbl}" ADD COLUMN "{col_name}" {col_type}'
                            ))
                        except Exception:
                            pass

        # Backfill UUIDs
        with engine.begin() as conn:
            for tbl in existing_tables:
                if tbl in EXCLUDE_TABLES:
                    continue
                try:
                    rows = conn.execute(text(
                        f"SELECT rowid FROM \"{tbl}\" WHERE uuid IS NULL OR uuid = ''"
                    )).fetchall()
                    for r in rows:
                        conn.execute(text(
                            f'UPDATE "{tbl}" SET uuid = :u WHERE rowid = :rid'
                        ), {"u": str(uuid.uuid4()), "rid": r[0]})
                except Exception:
                    pass

        logger.info("✅ SQLite migration + WAL mode done")


# ══════════════════════════════════════════════════════════════
# 📢 ORM EVENT LISTENERS — Track all local changes
# ══════════════════════════════════════════════════════════════
_PRIORITY = {'schools': 1, 'students': 2}

def init_sync_engine(app):
    @event.listens_for(db.Session, "before_flush")
    def track_changes(session, flush_context, instances):
        # Only log in offline (SQLite) mode
        if os.environ.get("IS_ONLINE", "false").lower() == "true":
            # On server: track deletes for sync
            if getattr(session, "no_sync_logging", False):
                return
            for obj in session.deleted:
                if isinstance(obj, CustomModel):
                    tbl = obj.__class__.__tablename__
                    if tbl in EXCLUDE_TABLES:
                        continue
                    rec_uuid = getattr(obj, 'uuid', None)
                    if rec_uuid:
                        dr = DeletedRecord(
                            school_id=getattr(obj, 'school_id', None),
                            table_name=tbl,
                            record_uuid=rec_uuid
                        )
                        session.add(dr)
            return

        if getattr(session, "no_sync_logging", False):
            return

        def _q(obj, op):
            tbl = obj.__class__.__tablename__
            if tbl in EXCLUDE_TABLES:
                return
            rec_id = getattr(obj, 'uuid', None) or str(uuid.uuid4())
            if not getattr(obj, 'uuid', None):
                obj.uuid = rec_id
            school_id = getattr(obj, 'school_id', None)
            if not school_id:
                try:
                    from flask_login import current_user
                    school_id = current_user.school_id
                    obj.school_id = school_id
                except Exception:
                    pass
            payload = obj.to_dict() if op in ('CREATE', 'UPDATE') else None
            session.add(SyncQueue(
                school_id=school_id,
                table_name=tbl,
                record_id=rec_id,
                operation_type=op,
                payload_json=json.dumps(payload, default=str) if payload else None,
                status='PENDING',
                priority=_PRIORITY.get(tbl, 5),
            ))
            # Immediate background sync trigger (non-blocking)
            _schedule_immediate_sync(school_id, obj._sa_class_manager.mapper.class_.__module__)

        for obj in session.new:
            if isinstance(obj, CustomModel): _q(obj, 'CREATE')
        for obj in session.dirty:
            if isinstance(obj, CustomModel) and session.is_modified(obj): _q(obj, 'UPDATE')
        for obj in session.deleted:
            if isinstance(obj, CustomModel):
                _q(obj, 'DELETE')
                # Also log to deleted_records
                tbl = obj.__class__.__tablename__
                if tbl not in EXCLUDE_TABLES and getattr(obj, 'uuid', None):
                    session.add(DeletedRecord(
                        school_id=getattr(obj, 'school_id', None),
                        table_name=tbl, record_uuid=obj.uuid
                    ))


# ══════════════════════════════════════════════════════════════
# ⚡ IMMEDIATE SYNC TRIGGER (non-blocking)
# ══════════════════════════════════════════════════════════════
_immediate_sync_timer = None
_immediate_sync_lock  = Lock()

def _schedule_immediate_sync(school_id, _module=None):
    """Debounced: trigger sync 2 seconds after last change."""
    global _immediate_sync_timer
    with _immediate_sync_lock:
        if _immediate_sync_timer:
            _immediate_sync_timer.cancel()
        try:
            app = current_app._get_current_object()
            _immediate_sync_timer = threading.Timer(
                2.0, _run_sync_in_thread, args=(school_id, app, 'change')
            )
            _immediate_sync_timer.daemon = True
            _immediate_sync_timer.start()
        except Exception:
            pass  # Outside app context — scheduler will pick it up

def _run_sync_in_thread(school_id, app, trigger='auto'):
    def _run():
        try:
            with app.app_context():
                _do_sync(school_id, trigger)
        except Exception as e:
            logger.error(f"[Thread Sync] {e}")
    t = Thread(target=_run, name=f"SyncThread-{trigger}-{school_id}", daemon=True)
    t.start()


# ══════════════════════════════════════════════════════════════
# 🔄 CORE SYNC FUNCTION
# ══════════════════════════════════════════════════════════════
_sync_lock = Lock()

def _do_sync(school_id, trigger='auto'):
    global _sync_running

    if _sync_lock.locked():
        return  # Already running

    with _sync_lock:
        _sync_running = True

        # Update status
        sync_status[school_id] = {
            **sync_status.get(school_id, {}),
            "status": "syncing",
            "message": f"Syncing... ({trigger})"
        }

        # Create session record
        session_obj = SyncSession(school_id=school_id, trigger=trigger, status='running')
        try:
            db.session.add(session_obj)
            db.session.commit()
        except Exception:
            try: db.session.rollback()
            except Exception: pass

        try:
            from utils.dual_db import run_full_sync
            pushed, pulled, conflicts, errors = run_full_sync(
                db.engine, school_id=school_id, trigger=trigger
            )

            now = datetime.utcnow()
            sync_status[school_id] = {
                "status": "success",
                "last_sync": now.isoformat(),
                "pushed": pushed,
                "pulled": pulled,
                "conflicts": conflicts,
                "message": f"Synced {now.strftime('%H:%M:%S')} — ↑{pushed} ↓{pulled}"
            }
            try:
                session_obj.completed_at = now
                session_obj.pushed_count  = pushed
                session_obj.pulled_count  = pulled
                session_obj.conflict_count = conflicts
                session_obj.failed_count  = len(errors)
                session_obj.status = 'success' if not errors else 'partial'
                db.session.commit()
            except Exception: pass

            logger.info(f"[Sync] ✅ {trigger}: ↑{pushed} ↓{pulled} conflicts={conflicts}")

        except Exception as e:
            logger.error(f"[Sync] ❌ {trigger}: {e}")
            sync_status[school_id] = {
                **sync_status.get(school_id, {}),
                "status": "failed",
                "message": f"Sync failed: {str(e)[:80]}"
            }
            try:
                session_obj.status    = 'failed'
                session_obj.error_log = str(e)
                session_obj.completed_at = datetime.utcnow()
                db.session.commit()
            except Exception: pass
        finally:
            _sync_running = False


# ══════════════════════════════════════════════════════════════
# 🚀 LOGIN SYNC
# ══════════════════════════════════════════════════════════════
def sync_on_login(school_id, app):
    _run_sync_in_thread(school_id, app, 'login')


# ══════════════════════════════════════════════════════════════
# 🌐 INTERNET MONITOR — detects reconnection, triggers sync
# ══════════════════════════════════════════════════════════════
def internet_monitor_thread(app):
    global _was_online

    def _run():
        global _was_online
        time.sleep(5)  # App settle
        while True:
            try:
                with app.app_context():
                    _internet_cache['checked_at'] = None  # Force fresh check
                    online = check_internet()

                    if online and not _was_online:
                        logger.info("🟢 Internet CONNECTED — syncing all schools")
                        schools = School.query.all()
                        for s in schools:
                            sync_status[s.id] = {**sync_status.get(s.id, {}), "status": "syncing"}
                        for s in schools:
                            _do_sync(s.id, 'internet_detect')

                    elif not online and _was_online:
                        logger.info("🔴 Internet DISCONNECTED — offline mode")
                        try:
                            schools = School.query.all()
                        except Exception:
                            schools = []
                        for s in schools:
                            sync_status[s.id] = {
                                **sync_status.get(s.id, {}),
                                "status": "offline",
                                "message": "Working offline"
                            }

                    _was_online = online

            except Exception as e:
                logger.error(f"[Monitor] {e}")

            time.sleep(15)

    t = Thread(target=_run, name="InternetMonitor", daemon=True)
    t.start()


# ══════════════════════════════════════════════════════════════
# ⏰ BACKGROUND SCHEDULER — runs sync every N seconds
# ══════════════════════════════════════════════════════════════
def start_sync_scheduler(app):
    interval = int(os.environ.get("SYNC_INTERVAL_SECONDS", "60"))

    def _run():
        time.sleep(15)  # Initial delay
        while True:
            try:
                with app.app_context():
                    if check_internet():
                        schools = School.query.all()
                        for s in schools:
                            _do_sync(s.id, 'scheduler')
            except Exception as e:
                logger.error(f"[Scheduler] {e}")
            time.sleep(interval)

    t = Thread(target=_run, name="SyncScheduler", daemon=True)
    t.daemon = True
    t.start()
    logger.info(f"⏰ Sync scheduler started (every {interval}s)")


# ══════════════════════════════════════════════════════════════
# 🔁 RETRY FAILED ITEMS
# ══════════════════════════════════════════════════════════════
def retry_failed_sync_items(school_id):
    try:
        failed = SyncQueue.query.filter(
            SyncQueue.status == 'FAILED',
            SyncQueue.school_id == school_id,
            SyncQueue.retry_count < 3
        ).all()
        for item in failed:
            item.status = 'PENDING'
        perm = SyncQueue.query.filter(
            SyncQueue.status == 'FAILED',
            SyncQueue.school_id == school_id,
            SyncQueue.retry_count >= 3
        ).all()
        for item in perm:
            item.status = 'PERMANENTLY_FAILED'
        db.session.commit()
    except Exception as e:
        logger.error(f"[Retry] {e}")


# ══════════════════════════════════════════════════════════════
# 📋 SEED LOCAL DATA TO SYNC QUEUE
# ══════════════════════════════════════════════════════════════
def seed_sync_queue_from_existing_data():
    if os.environ.get("IS_ONLINE", "false").lower() == "true":
        return
    from utils.auto_migrate import import_all_models, get_all_subclasses
    import_all_models()
    subclasses = get_all_subclasses(db.Model)
    count = 0
    try:
        for cls in subclasses:
            tbl = getattr(cls, '__tablename__', None)
            if not tbl or tbl in EXCLUDE_TABLES:
                continue
            try:
                recs = cls.query.filter(cls.last_synced_at.is_(None)).all()
            except Exception:
                continue
            for r in recs:
                if not getattr(r, 'uuid', None):
                    r.uuid = str(uuid.uuid4())
                    db.session.add(r)
                exists = SyncQueue.query.filter_by(
                    table_name=tbl, record_id=r.uuid, status='PENDING'
                ).first()
                if not exists:
                    payload = r.to_dict() if hasattr(r, 'to_dict') else {}
                    db.session.add(SyncQueue(
                        school_id=getattr(r, 'school_id', None),
                        table_name=tbl, record_id=r.uuid,
                        operation_type='CREATE',
                        payload_json=json.dumps(payload, default=str),
                        status='PENDING',
                        priority=_PRIORITY.get(tbl, 5),
                    ))
                    count += 1
        if count:
            db.session.commit()
            logger.info(f"[Seed] {count} records queued for initial sync")
    except Exception as e:
        logger.error(f"[Seed] {e}")
        try: db.session.rollback()
        except Exception: pass


# ══════════════════════════════════════════════════════════════
# Backward-compat stubs (used by sync/routes.py)
# ══════════════════════════════════════════════════════════════
def perform_push(school_id):
    return 0, []

def perform_pull(school_id):
    return 0, 0

def perform_direct_db_sync(school_id):
    with current_app.app_context():
        return _do_sync(school_id, 'manual')

def perform_full_initial_sync(school_id):
    from utils.dual_db import run_full_sync
    p, pu, c, e = run_full_sync(db.engine, school_id=school_id, trigger='initial')
    return {"total_pulled": pu, "tables_synced": [], "errors": e}
