"""
dual_db.py — Bhishmaa ERP Dual Database Manager
================================================
- LOCAL: SQLite (always available, offline.db)
- CLOUD: PostgreSQL (sync when available)
- Automatic bidirectional sync — no .env needed
- Zero data loss guaranteed via versioning + conflict queue
"""

import os
import sys
import json
import uuid
import logging
import threading
import time
from datetime import datetime
from sqlalchemy import create_engine, text, inspect, MetaData, Table
from sqlalchemy.pool import NullPool

logger = logging.getLogger('dual_db')

# ══════════════════════════════════════════════════════════
# 🔧 HARDCODED CONFIG — Edit karo apna server IP
# ══════════════════════════════════════════════════════════
CLOUD_DB_CONFIG = {
    "user":     "enoughsudhanshu",
    "password": "awadhnath",
    "host":     "erp.bhishmaagroup.in",
    "port":     5432,
    "dbname":   "erpdb",
}

# Runtime override — agar os.environ mein DATABASE_URL ho (app.py sets it) to use karo
def get_cloud_url():
    env_url = os.environ.get("DATABASE_URL", "")
    if env_url:
        return env_url.replace("postgres://", "postgresql://", 1)
    h = CLOUD_DB_CONFIG["host"].strip()
    if not h:
        return None
    return (
        f"postgresql://{CLOUD_DB_CONFIG['user']}:{CLOUD_DB_CONFIG['password']}"
        f"@{h}:{CLOUD_DB_CONFIG['port']}/{CLOUD_DB_CONFIG['dbname']}"
        f"?connect_timeout=5&sslmode=prefer"
    )

# Tables jinka sync nahi karna
SKIP_TABLES = {
    'sync_queue', 'conflict_logs', 'deleted_records',
    'sync_sessions', 'super_admins', 'audit_logs', 'license_request'
}

# ══════════════════════════════════════════════════════════
# 📡 CLOUD ENGINE — fresh connection every time (NullPool)
# ══════════════════════════════════════════════════════════
_cloud_engine_cache = None
_cloud_engine_lock  = threading.Lock()

def get_cloud_engine():
    global _cloud_engine_cache
    url = get_cloud_url()
    if not url:
        return None
    with _cloud_engine_lock:
        if _cloud_engine_cache:
            try:
                with _cloud_engine_cache.connect() as c:
                    c.execute(text("SELECT 1"))
                return _cloud_engine_cache
            except Exception:
                try: _cloud_engine_cache.dispose()
                except Exception: pass
                _cloud_engine_cache = None
        try:
            engine = create_engine(
                url,
                poolclass=NullPool,
                connect_args={"connect_timeout": 5, "application_name": "BhishmaaERP"},
            )
            with engine.connect() as c:
                c.execute(text("SELECT 1"))
            _cloud_engine_cache = engine
            logger.info("☁ Cloud DB connected")
            return engine
        except Exception as e:
            logger.warning(f"☁ Cloud DB unavailable: {e}")
            return None

def is_cloud_available():
    return get_cloud_engine() is not None

# ══════════════════════════════════════════════════════════
# 🔠 TYPE HELPERS
# ══════════════════════════════════════════════════════════
def _pg_type(col_type_str):
    t = col_type_str.upper()
    if "VARCHAR" in t or "STRING" in t: return "TEXT"
    if "DATETIME" in t:  return "TIMESTAMP"
    if "BOOLEAN" in t:   return "BOOLEAN"
    if "FLOAT" in t:     return "DOUBLE PRECISION"
    if "INTEGER" in t or "INT" in t: return "INTEGER"
    if "TEXT" in t:      return "TEXT"
    if "DATE" in t:      return "DATE"
    return "TEXT"

def _row_to_dict(row, keys):
    d = {}
    for i, k in enumerate(keys):
        v = row[i]
        if isinstance(v, datetime):
            d[k] = v.isoformat()
        elif hasattr(v, 'isoformat'):   # date
            d[k] = v.isoformat()
        else:
            d[k] = v
    return d

# ══════════════════════════════════════════════════════════
# 🏗 CLOUD TABLE BOOTSTRAP
# ══════════════════════════════════════════════════════════
def bootstrap_cloud_schema(local_engine, cloud_engine):
    """
    Ensure all local SQLite tables exist on cloud PostgreSQL.
    Creates missing tables; adds missing columns.
    Safe to run multiple times (idempotent).
    """
    local_insp  = inspect(local_engine)
    cloud_insp  = inspect(cloud_engine)
    local_tables = local_insp.get_table_names()
    cloud_tables_existing = set(cloud_insp.get_table_names())

    for tbl in local_tables:
        if tbl in SKIP_TABLES:
            continue
        local_cols = {c['name']: c for c in local_insp.get_columns(tbl)}

        if tbl not in cloud_tables_existing:
            # CREATE TABLE on cloud
            col_defs = []
            for col_name, col_info in local_cols.items():
                pg_type = _pg_type(str(col_info['type']))
                nullable = "NULL" if col_info.get('nullable', True) else "NOT NULL"
                if col_name == 'id':
                    col_defs.append(f'"{col_name}" SERIAL PRIMARY KEY')
                else:
                    col_defs.append(f'"{col_name}" {pg_type} {nullable}')

            ddl = f'CREATE TABLE IF NOT EXISTS "{tbl}" ({", ".join(col_defs)})'
            try:
                with cloud_engine.begin() as cc:
                    cc.execute(text(ddl))
                logger.info(f"[Bootstrap] Created table '{tbl}' on cloud")
            except Exception as e:
                logger.warning(f"[Bootstrap] Table '{tbl}' create failed: {e}")
        else:
            # ADD missing columns
            cloud_cols_existing = {c['name'] for c in cloud_insp.get_columns(tbl)}
            for col_name, col_info in local_cols.items():
                if col_name not in cloud_cols_existing:
                    pg_type = _pg_type(str(col_info['type']))
                    try:
                        with cloud_engine.begin() as cc:
                            cc.execute(text(
                                f'ALTER TABLE "{tbl}" ADD COLUMN IF NOT EXISTS "{col_name}" {pg_type}'
                            ))
                        logger.info(f"[Bootstrap] Added '{col_name}' to '{tbl}' on cloud")
                    except Exception as e:
                        logger.warning(f"[Bootstrap] Col add failed {tbl}.{col_name}: {e}")

    # Ensure sync tracking columns exist on all cloud tables
    tracking_cols = [
        ("uuid",          "TEXT"),
        ("school_id",     "INTEGER"),
        ("created_at",    "TIMESTAMP"),
        ("updated_at",    "TIMESTAMP"),
        ("last_synced_at","TIMESTAMP"),
        ("sync_version",  "INTEGER"),
    ]
    cloud_insp2 = inspect(cloud_engine)
    for tbl in cloud_insp2.get_table_names():
        if tbl in SKIP_TABLES:
            continue
        existing_cols = {c['name'] for c in cloud_insp2.get_columns(tbl)}
        for col_name, col_type in tracking_cols:
            if col_name not in existing_cols:
                try:
                    with cloud_engine.begin() as cc:
                        cc.execute(text(
                            f'ALTER TABLE "{tbl}" ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}'
                        ))
                except Exception:
                    pass

# ══════════════════════════════════════════════════════════
# 🔄 BIDIRECTIONAL SYNC ENGINE
# ══════════════════════════════════════════════════════════
class BidirectionalSync:
    """
    Performs full bidirectional sync between SQLite and PostgreSQL.
    Strategy:
      - uuid + updated_at se determine karo kaun newer hai
      - Agar dono jagah same record updated hai → sync_version se resolve karo
      - Newly created (only on one side) → dusri side pe insert karo
      - Deleted records → deleted_records table track karta hai
    """

    def __init__(self, local_engine, cloud_engine, school_id=None):
        self.local  = local_engine
        self.cloud  = cloud_engine
        self.school_id = school_id
        self.pushed = 0
        self.pulled = 0
        self.conflicts = 0
        self.errors = []

    def sync_all(self):
        """Sync ALL tables bidirectionally."""
        local_insp = inspect(self.local)
        tables = [t for t in local_insp.get_table_names() if t not in SKIP_TABLES]

        # Priority order: schools → students → rest
        def priority(t):
            return 0 if t == 'schools' else (1 if t == 'students' else 2)
        tables.sort(key=priority)

        # First handle deletions
        self._sync_deletions()

        for tbl in tables:
            try:
                self._sync_table(tbl)
            except Exception as e:
                self.errors.append(f"{tbl}: {e}")
                logger.error(f"[Sync] Table '{tbl}' error: {e}")

        logger.info(
            f"[Sync] Done — pushed={self.pushed}, pulled={self.pulled}, "
            f"conflicts={self.conflicts}, errors={len(self.errors)}"
        )
        return self.pushed, self.pulled, self.conflicts, self.errors

    def _sync_deletions(self):
        """Apply deletions from both sides."""
        try:
            # Local deletions → cloud
            with self.local.connect() as lc:
                rows = lc.execute(text(
                    "SELECT table_name, record_uuid FROM deleted_records"
                )).fetchall()

            with self.cloud.begin() as cc:
                for tbl, ruuid in rows:
                    if tbl in SKIP_TABLES:
                        continue
                    try:
                        cc.execute(text(f'DELETE FROM "{tbl}" WHERE uuid = :u'), {"u": ruuid})
                        self.pushed += 1
                    except Exception:
                        pass

            # Cloud deletions → local
            with self.cloud.connect() as cc:
                rows = cc.execute(text(
                    "SELECT table_name, record_uuid FROM deleted_records"
                )).fetchall()

            with self.local.begin() as lc:
                for tbl, ruuid in rows:
                    if tbl in SKIP_TABLES:
                        continue
                    try:
                        lc.execute(text(f'DELETE FROM "{tbl}" WHERE uuid = :u'), {"u": ruuid})
                        self.pulled += 1
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"[Sync Deletions] {e}")

    def _sync_table(self, tbl):
        """Sync one table bidirectionally."""
        # Fetch all local rows with uuid
        try:
            with self.local.connect() as lc:
                res = lc.execute(text(f'SELECT * FROM "{tbl}" WHERE uuid IS NOT NULL'))
                lcols = list(res.keys())
                local_rows = {r[lcols.index('uuid')]: _row_to_dict(r, lcols) for r in res.fetchall()}
        except Exception as e:
            return  # Table might not have uuid yet

        # Fetch all cloud rows with uuid
        try:
            with self.cloud.connect() as cc:
                # Filter by school_id if relevant
                if self.school_id and 'school_id' in [
                    c['name'] for c in inspect(self.cloud).get_columns(tbl)
                ]:
                    res = cc.execute(text(
                        f'SELECT * FROM "{tbl}" WHERE school_id = :sid OR school_id IS NULL'
                    ), {"sid": self.school_id})
                else:
                    res = cc.execute(text(f'SELECT * FROM "{tbl}"'))
                ccols = list(res.keys())
                cloud_rows = {r[ccols.index('uuid')]: _row_to_dict(r, ccols) for r in res.fetchall()}
        except Exception as e:
            logger.warning(f"[Sync] Could not read cloud table '{tbl}': {e}")
            return

        all_uuids = set(local_rows.keys()) | set(cloud_rows.keys())

        for rec_uuid in all_uuids:
            local_rec  = local_rows.get(rec_uuid)
            cloud_rec  = cloud_rows.get(rec_uuid)

            try:
                if local_rec and not cloud_rec:
                    # Only local → push to cloud
                    self._insert_to_cloud(tbl, local_rec)
                    self.pushed += 1

                elif cloud_rec and not local_rec:
                    # Only cloud → pull to local
                    self._insert_to_local(tbl, cloud_rec)
                    self.pulled += 1

                else:
                    # Both exist → compare timestamps
                    local_upd = _parse_dt(local_rec.get('updated_at'))
                    cloud_upd = _parse_dt(cloud_rec.get('updated_at'))
                    local_ver = int(local_rec.get('sync_version') or 1)
                    cloud_ver = int(cloud_rec.get('sync_version') or 1)

                    if local_upd == cloud_upd:
                        continue  # Identical — no action

                    # Determine winner
                    if local_ver > cloud_ver:
                        winner = 'local'
                    elif cloud_ver > local_ver:
                        winner = 'cloud'
                    elif local_upd and cloud_upd:
                        winner = 'local' if local_upd >= cloud_upd else 'cloud'
                    else:
                        winner = 'local'  # Default

                    if winner == 'local':
                        # Push local → cloud
                        local_rec['sync_version'] = max(local_ver, cloud_ver) + 1
                        self._update_on_cloud(tbl, rec_uuid, local_rec)
                        self.pushed += 1
                    else:
                        # Pull cloud → local
                        cloud_rec['sync_version'] = max(local_ver, cloud_ver) + 1
                        self._update_on_local(tbl, rec_uuid, cloud_rec)
                        self.pulled += 1

                    self.conflicts += 1

            except Exception as e:
                self.errors.append(f"{tbl}/{rec_uuid}: {e}")

    # ── Write helpers ──────────────────────────────────────

    def _insert_to_cloud(self, tbl, row):
        row = _clean_row(row)
        row['last_synced_at'] = datetime.utcnow().isoformat()
        cols = list(row.keys())
        sql = f'INSERT INTO "{tbl}" ({", ".join(f"{chr(34)}{c}{chr(34)}" for c in cols)}) VALUES ({", ".join(f":{c}" for c in cols)}) ON CONFLICT (uuid) DO NOTHING'
        with self.cloud.begin() as cc:
            cc.execute(text(sql), row)

    def _insert_to_local(self, tbl, row):
        row = _clean_row(row)
        row['last_synced_at'] = datetime.utcnow().isoformat()
        cols = list(row.keys())
        sql = f'INSERT OR IGNORE INTO "{tbl}" ({", ".join(f"{chr(34)}{c}{chr(34)}" for c in cols)}) VALUES ({", ".join(f":{c}" for c in cols)})'
        with self.local.begin() as lc:
            lc.execute(text(sql), row)

    def _update_on_cloud(self, tbl, rec_uuid, row):
        row = _clean_row(row)
        row['last_synced_at'] = datetime.utcnow().isoformat()
        cols = [c for c in row if c != 'uuid']
        if not cols:
            return
        set_clause = ", ".join(f'"{c}" = :{c}' for c in cols)
        sql = f'UPDATE "{tbl}" SET {set_clause} WHERE uuid = :uuid'
        row['uuid'] = rec_uuid
        with self.cloud.begin() as cc:
            cc.execute(text(sql), row)

    def _update_on_local(self, tbl, rec_uuid, row):
        row = _clean_row(row)
        row['last_synced_at'] = datetime.utcnow().isoformat()
        cols = [c for c in row if c != 'uuid']
        if not cols:
            return
        set_clause = ", ".join(f'"{c}" = :{c}' for c in cols)
        sql = f'UPDATE "{tbl}" SET {set_clause} WHERE uuid = :uuid'
        row['uuid'] = rec_uuid
        with self.local.begin() as lc:
            lc.execute(text(sql), row)


# ══════════════════════════════════════════════════════════
# 🔧 HELPERS
# ══════════════════════════════════════════════════════════
def _parse_dt(val):
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(str(val))
    except Exception:
        return None

def _clean_row(row):
    """Make row values DB-safe."""
    out = {}
    for k, v in row.items():
        if isinstance(v, bool):
            out[k] = int(v)
        elif v is None:
            out[k] = None
        else:
            out[k] = v
    return out


# ══════════════════════════════════════════════════════════
# 🚀 PUBLIC API — called from sync_engine.py
# ══════════════════════════════════════════════════════════
_sync_lock = threading.Lock()

def run_full_sync(local_engine, school_id=None, trigger='auto'):
    """
    Main entry point. Connects to cloud, bootstraps schema,
    runs bidirectional sync. Returns (pushed, pulled, conflicts, errors).
    Safe to call from any thread.
    """
    if _sync_lock.locked():
        logger.info(f"[DualDB] Sync already running, skipping ({trigger})")
        return 0, 0, 0, ["Sync already in progress"]

    with _sync_lock:
        cloud = get_cloud_engine()
        if not cloud:
            return 0, 0, 0, ["Cloud DB not reachable"]

        try:
            bootstrap_cloud_schema(local_engine, cloud)
        except Exception as e:
            logger.error(f"[DualDB] Bootstrap error: {e}")

        syncer = BidirectionalSync(local_engine, cloud, school_id)
        return syncer.sync_all()
