import os
import json
import shutil
import csv
import io
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, current_app
from flask_login import login_required, current_user
from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from itsdangerous import URLSafeSerializer
from extensions import db, CustomModel
from models.sync import SyncQueue, ConflictLog, DeletedRecord
from models.school import School
from utils.sync_engine import (
    EXCLUDE_TABLES, encrypt_data, decrypt_data, check_internet,
    perform_push, perform_pull, start_sync_scheduler, _sync_running,
    sync_status, _do_sync
)

sync_bp = Blueprint('sync', __name__, url_prefix='/sync')

# =========================================================
# 🔐 JWT / ITSDANGEROUS SECURITY HELPERS
# =========================================================
def verify_token(token):
    secret_key = current_app.config.get('SECRET_KEY', 'secret-key')
    s = URLSafeSerializer(secret_key)
    try:
        data = s.loads(token)
        return data.get("school_id")
    except Exception:
        return None

def sync_auth_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({"error": "Unauthorized"}), 401
        
        token = auth_header.split(" ")[1]
        school_id = verify_token(token)
        if not school_id:
            return jsonify({"error": "Invalid token"}), 401
        
        request.authenticated_school_id = school_id
        return f(*args, **kwargs)
    return decorated

# =========================================================
# 🌐 CLOUD REST API ENDPOINTS (ONLINE MODE)
# =========================================================
@sync_bp.route('/api/status', methods=['GET'])
def api_status():
    """GET /api/sync/status"""
    return jsonify({
        "status": "online",
        "time": datetime.utcnow().isoformat(),
        "mode": "cloud"
    })

@sync_bp.route('/api/push', methods=['POST'])
@sync_auth_required
def api_push():
    """POST /api/sync/push"""
    try:
        req_data = request.json
        enc_payload = req_data.get("payload")
        dec_payload = decrypt_data(enc_payload)
        data = json.loads(dec_payload)

        school_id = data.get("school_id")
        if school_id != request.authenticated_school_id:
            return jsonify({"error": "School ID mismatch"}), 403

        operations = data.get("operations", [])
        synced_ids = []
        failed_ops = []

        subclasses = db.Model.__subclasses__()
        subclass_map = {cls.__tablename__: cls for cls in subclasses if hasattr(cls, '__tablename__')}

        server_time = datetime.utcnow().isoformat()
        db.session.no_sync_logging = True  # Avoid logging sync actions themselves

        for op in operations:
            queue_id = op["queue_id"]
            tbl_name = op["table_name"]
            rec_uuid = op["record_id"]
            op_type = op["operation_type"]
            payload = json.loads(op["payload_json"]) if op["payload_json"] else None

            cls = subclass_map.get(tbl_name)
            if not cls:
                failed_ops.append({"queue_id": queue_id, "error": f"Table '{tbl_name}' not found"})
                continue

            try:
                rec = cls.query.filter_by(uuid=rec_uuid).first()
                if op_type in ('CREATE', 'UPDATE'):
                    local_updated_at = datetime.fromisoformat(payload["updated_at"])
                    if rec:
                        # Conflict Check
                        cloud_updated_at = rec.updated_at
                        if local_updated_at >= cloud_updated_at:
                            # Local is newer, update cloud
                            rec.update_from_dict(payload)
                            rec.school_id = school_id
                            rec.last_synced_at = datetime.fromisoformat(server_time)
                            rec.sync_version += 1
                            synced_ids.append(queue_id)
                        else:
                            # Cloud is newer, fail/ignore local push
                            conflict = ConflictLog(
                                school_id=school_id,
                                table_name=tbl_name,
                                record_uuid=rec_uuid,
                                local_updated_at=local_updated_at,
                                cloud_updated_at=cloud_updated_at,
                                resolution='Cloud Won (Newer)'
                            )
                            db.session.add(conflict)
                            failed_ops.append({"queue_id": queue_id, "error": "Conflict: Cloud is newer"})
                    else:
                        # CREATE (New record on cloud)
                        new_rec = cls()
                        new_rec.update_from_dict(payload)
                        new_rec.school_id = school_id
                        new_rec.last_synced_at = datetime.fromisoformat(server_time)
                        db.session.add(new_rec)
                        synced_ids.append(queue_id)
                
                elif op_type == 'DELETE':
                    if rec:
                        db.session.delete(rec)
                    synced_ids.append(queue_id)

            except Exception as e:
                failed_ops.append({"queue_id": queue_id, "error": str(e)})

        db.session.commit()
        response_payload = {"synced_ids": synced_ids, "failed_ops": failed_ops}
        enc_response = encrypt_data(json.dumps(response_payload))
        return jsonify({"payload": enc_response})

    except Exception as e:
        return jsonify({"error": str(e)}), 400
    finally:
        db.session.no_sync_logging = False

@sync_bp.route('/api/pull', methods=['GET'])
@sync_auth_required
def api_pull():
    """GET /api/sync/pull"""
    try:
        last_sync_str = request.args.get("last_sync_time", "1970-01-01T00:00:00")
        school_id = request.args.get("school_id", type=int)

        if school_id != request.authenticated_school_id:
            return jsonify({"error": "School ID mismatch"}), 403

        last_sync_time = datetime.fromisoformat(last_sync_str)
        server_time = datetime.utcnow().isoformat()

        subclasses = db.Model.__subclasses__()
        updates = {}

        # 1. Query updates
        for cls in subclasses:
            if not hasattr(cls, '__tablename__') or cls.__tablename__ in EXCLUDE_TABLES:
                continue
            
            # Check if model has school_id
            if hasattr(cls, 'school_id'):
                records = cls.query.filter(
                    cls.school_id == school_id,
                    cls.updated_at > last_sync_time
                ).all()
            else:
                # Fallback: if no direct school_id, return all (or customize if parent filter exists)
                records = cls.query.filter(cls.updated_at > last_sync_time).all()

            if records:
                updates[cls.__tablename__] = [r.to_dict() for r in records]

        # 2. Query deletions
        deletions = DeletedRecord.query.filter(
            DeletedRecord.school_id == school_id,
            DeletedRecord.deleted_at > last_sync_time
        ).all()
        del_list = [{"table_name": d.table_name, "record_uuid": d.record_uuid} for d in deletions]

        response_payload = {
            "updates": updates,
            "deletions": del_list,
            "server_time": server_time
        }
        enc_response = encrypt_data(json.dumps(response_payload))
        return jsonify({"payload": enc_response})

    except Exception as e:
        return jsonify({"error": str(e)}), 400

@sync_bp.route('/api/ack', methods=['POST'])
@sync_auth_required
def api_ack():
    """POST /api/sync/ack"""
    return jsonify({"status": "acknowledged"})


# =========================================================
# 💻 LOCAL CLIENT DASHBOARD & ADMIN OPERATIONS (OFFLINE MODE)
# =========================================================
@sync_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    """Renders local sync dashboard page"""
    if os.environ.get("IS_ONLINE", "false").lower() == "true":
        return redirect(url_for('dashboard.admin'))

    school_id = current_user.school_id
    school = School.query.get(school_id)

    # Sync statistics
    pending_count = SyncQueue.query.filter_by(status='PENDING', school_id=school_id).count()
    failed_count = SyncQueue.query.filter_by(status='FAILED', school_id=school_id).count()
    last_sync = db.session.query(db.func.max(SyncQueue.synced_at)).filter_by(status='SYNCED', school_id=school_id).scalar()
    
    recent_queue = SyncQueue.query.filter_by(school_id=school_id).order_by(SyncQueue.created_at.desc()).limit(15).all()
    recent_conflicts = ConflictLog.query.filter_by(school_id=school_id).order_by(ConflictLog.created_at.desc()).limit(15).all()

    internet_status = "Online" if check_internet() else "Offline"
    
    # Backups list
    backups = []
    backup_dir = os.path.join("uploads", "backups")
    if os.path.exists(backup_dir):
        backups = [f for f in os.listdir(backup_dir) if f.endswith('.db')]
        backups.sort(reverse=True)

    return render_template(
        'sync/dashboard.html',
        school=school,
        pending_count=pending_count,
        failed_count=failed_count,
        last_sync=last_sync,
        recent_queue=recent_queue,
        recent_conflicts=recent_conflicts,
        internet_status=internet_status,
        backups=backups[:10],
        sync_running=_sync_running
    )

@sync_bp.route('/manual', methods=['POST'])
@login_required
def manual_sync():
    """Triggers manual Push/Pull Sync"""
    school_id = current_user.school_id
    
    is_direct = bool(os.environ.get("DATABASE_URL"))
    
    if is_direct:
        from utils.sync_engine import check_internet_direct, perform_direct_db_sync
        if not check_internet_direct():
            flash("Cannot sync: Direct connection to online PostgreSQL database failed.", "danger")
            return redirect(url_for('sync.dashboard'))
    else:
        if not check_internet():
            flash("Cannot sync: Internet / Cloud Server is offline.", "danger")
            return redirect(url_for('sync.dashboard'))

    try:
        from utils.sync_engine import seed_sync_queue_from_existing_data
        seed_sync_queue_from_existing_data()

        if is_direct:
            push_count, pull_count, conflict_count, failed_ops = perform_direct_db_sync(school_id)
            if failed_ops:
                flash(f"Sync completed with errors. Pushed {push_count} ops, Pulled {pull_count}. Failed: {len(failed_ops)}.", "warning")
            else:
                flash(f"Direct DB Sync successful! Pushed {push_count} ops, Pulled {pull_count} updates. Conflicts Resolved: {conflict_count}.", "success")
        else:
            push_count, failed_ops = perform_push(school_id)
            pull_count, conflict_count = perform_pull(school_id)
            if failed_ops:
                flash(f"Sync completed with errors. Pushed {push_count} ops, Pulled {pull_count}. Failed: {len(failed_ops)}.", "warning")
            else:
                flash(f"Sync successful! Pushed {push_count} ops, Pulled {pull_count} updates. Conflicts Resolved: {conflict_count}.", "success")
    except Exception as e:
        flash(f"Sync failed: {e}", "danger")

    return redirect(url_for('sync.dashboard'))

@sync_bp.route('/backup', methods=['POST'])
@login_required
def run_backup():
    """Generates SQLite backup"""
    try:
        db_path = os.path.join("offline.db")
        if not os.path.exists(db_path):
            flash("Database file not found", "danger")
            return redirect(url_for('sync.dashboard'))

        backup_dir = os.path.join("uploads", "backups")
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"backup_{timestamp}.db"
        backup_path = os.path.join(backup_dir, backup_filename)

        # Flush db session, close connections temporarily, and copy
        db.session.remove()
        db.engine.dispose()
        shutil.copy2(db_path, backup_path)

        flash("Backup generated successfully: " + backup_filename, "success")
    except Exception as e:
        flash("Backup failed: " + str(e), "danger")
    return redirect(url_for('sync.dashboard'))

@sync_bp.route('/restore', methods=['POST'])
@login_required
def restore_backup():
    """Restores SQLite database from backup file"""
    backup_file = request.files.get('backup_file')
    if not backup_file or not backup_file.filename.endswith('.db'):
        flash("Invalid backup file. Must be a .db file", "danger")
        return redirect(url_for('sync.dashboard'))

    try:
        db_path = os.path.join("offline.db")
        
        # Discard active connections
        db.session.remove()
        db.engine.dispose()

        # Overwrite database file
        backup_file.save(db_path)
        flash("Database restored successfully!", "success")
    except Exception as e:
        flash("Restore failed: " + str(e), "danger")
    return redirect(url_for('sync.dashboard'))

@sync_bp.route('/download-backup/<filename>', methods=['GET'])
@login_required
def download_backup(filename):
    """Downloads a backup .db file"""
    backup_dir = os.path.abspath(os.path.join("uploads", "backups"))
    file_path = os.path.join(backup_dir, filename)
    if os.path.exists(file_path):
        return send_file(file_path, as_attachment=True)
    flash("File not found", "danger")
    return redirect(url_for('sync.dashboard'))

# =========================================================
# 📄 SYNC REPORT EXPORT (CSV, EXCEL, PDF)
# =========================================================
@sync_bp.route('/export/<format>', methods=['GET'])
@login_required
def export_sync_logs(format):
    """Export SyncQueue history in requested format"""
    school_id = current_user.school_id
    logs = SyncQueue.query.filter_by(school_id=school_id).order_by(SyncQueue.created_at.desc()).all()

    if format == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["ID", "Table Name", "Operation Type", "Record ID", "Status", "Created At", "Synced At"])
        for l in logs:
            writer.writerow([l.id, l.table_name, l.operation_type, l.record_id, l.status, l.created_at, l.synced_at])
        
        mem_file = io.BytesIO()
        mem_file.write(output.getvalue().encode('utf-8'))
        mem_file.seek(0)
        return send_file(
            mem_file,
            mimetype='text/csv',
            as_attachment=True,
            download_name='sync_history.csv'
        )

    elif format == 'excel':
        wb = Workbook()
        ws = wb.active
        ws.title = "Sync Logs"
        ws.append(["ID", "Table Name", "Operation Type", "Record ID", "Status", "Created At", "Synced At"])
        for l in logs:
            ws.append([l.id, l.table_name, l.operation_type, l.record_id, l.status, l.created_at.isoformat() if l.created_at else "", l.synced_at.isoformat() if l.synced_at else ""])
        
        mem_file = io.BytesIO()
        wb.save(mem_file)
        mem_file.seek(0)
        return send_file(
            mem_file,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name='sync_history.xlsx'
        )

    elif format == 'pdf':
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        styles = getSampleStyleSheet()
        elements = []

        title_style = ParagraphStyle(
            name='TitleStyle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=16,
            textColor=colors.HexColor('#2c3e50'),
            spaceAfter=15
        )
        elements.append(Paragraph("Bhishmaa ERP - Sync Logs Report", title_style))
        elements.append(Spacer(1, 10))

        # Build Table
        table_data = [["ID", "Table", "Operation", "Record UUID", "Status", "Created At"]]
        for l in logs[:100]:  # Limit to first 100 for PDF layout
            table_data.append([
                str(l.id),
                l.table_name,
                l.operation_type,
                l.record_id[:8] + "...",
                l.status,
                l.created_at.strftime('%Y-%m-%d %H:%M') if l.created_at else ""
            ])

        t = Table(table_data, colWidths=[30, 90, 70, 100, 70, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2c3e50')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 6),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTSIZE', (0, 1), (-1, -1), 8),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        elements.append(t)
        
        doc.build(elements)
        buffer.seek(0)
        return send_file(
            buffer,
            mimetype='application/pdf',
            as_attachment=True,
            download_name='sync_history.pdf'
        )

    flash("Invalid format requested", "danger")
    return redirect(url_for('sync.dashboard'))


# =========================================================
# 🆕 OFFLINE-FIRST SYNC SYSTEM — NEW ENDPOINTS
# =========================================================



# =========================================================
# NEW OFFLINE-FIRST ENDPOINTS
# =========================================================

@sync_bp.route('/status')
@login_required
def status_page():
    from datetime import timedelta
    school_id = current_user.school_id
    now = datetime.utcnow()

    pending_count = SyncQueue.query.filter_by(status='PENDING', school_id=school_id).count()
    failed_count  = SyncQueue.query.filter(
        SyncQueue.status.in_(['FAILED', 'PERMANENTLY_FAILED']),
        SyncQueue.school_id == school_id
    ).count()
    synced_count  = SyncQueue.query.filter(
        SyncQueue.status == 'SYNCED',
        SyncQueue.school_id == school_id,
        SyncQueue.synced_at >= now - timedelta(hours=24)
    ).count()
    conflict_count = ConflictLog.query.filter(
        ConflictLog.school_id == school_id,
        ConflictLog.created_at >= now - timedelta(days=7),
        ConflictLog.resolved == False
    ).count()

    from models.sync import SyncSession
    recent_sessions = SyncSession.query.filter_by(school_id=school_id).order_by(
        SyncSession.started_at.desc()
    ).limit(10).all()

    pending_items = SyncQueue.query.filter_by(
        status='PENDING', school_id=school_id
    ).order_by(SyncQueue.priority, SyncQueue.created_at.desc()).limit(20).all()

    school_sync = sync_status.get(school_id, {"status": "never", "message": "Never synced"})
    is_internet = check_internet()

    return render_template('sync/dashboard.html',
        pending_count=pending_count,
        failed_count=failed_count,
        synced_count=synced_count,
        conflict_count=conflict_count,
        recent_sessions=recent_sessions,
        pending_items=pending_items,
        sync_status_dict=school_sync,
        is_internet=is_internet
    )


@sync_bp.route('/api/live-status', methods=['GET'])
def live_status_api():
    try:
        school_id = current_user.school_id if current_user.is_authenticated else None
    except Exception:
        school_id = None

    if not school_id:
        return jsonify({"status": "unknown", "pending": 0, "failed": 0,
                        "last_sync": None, "is_internet": False, "message": "Not logged in"})

    school_sync = sync_status.get(school_id, {})
    pending  = SyncQueue.query.filter_by(status='PENDING', school_id=school_id).count()
    failed   = SyncQueue.query.filter(
        SyncQueue.status.in_(['FAILED', 'PERMANENTLY_FAILED']),
        SyncQueue.school_id == school_id
    ).count()
    is_net   = check_internet()
    last_sync = school_sync.get("last_sync")

    msg = school_sync.get("message", "")
    if last_sync and not msg:
        try:
            diff = (datetime.utcnow() - datetime.fromisoformat(last_sync)).total_seconds()
            msg = "Abhi synced" if diff < 60 else (
                f"{int(diff//60)} min pehle" if diff < 3600 else f"{int(diff//3600)} ghante pehle"
            )
        except Exception:
            pass

    return jsonify({
        "status":    school_sync.get("status", "never"),
        "pending":   pending,
        "failed":    failed,
        "last_sync": last_sync,
        "is_internet": is_net,
        "message":   msg,
        "pushed":    school_sync.get("pushed", 0),
        "pulled":    school_sync.get("pulled", 0),
        "conflicts": school_sync.get("conflicts", 0),
    })


@sync_bp.route('/trigger-manual', methods=['POST'])
@login_required
def trigger_manual_sync():
    """Manual sync trigger (different URL to avoid conflict with existing /manual)."""
    school_id = current_user.school_id
    app = current_app._get_current_object()

    import threading
    def _run():
        with app.app_context():
            _do_sync(school_id, trigger='manual')

    threading.Thread(target=_run, name=f"ManualSync-{school_id}", daemon=True).start()
    flash("🔄 Sync shuru ho gaya background mein. 30 seconds mein refresh karein.", "info")
    return redirect(url_for('sync.status_page'))


@sync_bp.route('/conflicts')
@login_required
def conflict_list():
    school_id = current_user.school_id
    page = request.args.get('page', 1, type=int)
    conflicts = ConflictLog.query.filter_by(
        school_id=school_id, resolved=False
    ).order_by(ConflictLog.created_at.desc()).paginate(page=page, per_page=20)
    return render_template('sync/conflicts.html', conflicts=conflicts)


@sync_bp.route('/resolve-conflict/<int:conflict_id>', methods=['POST'])
@login_required
def resolve_conflict(conflict_id):
    action    = request.args.get('action', 'keep_cloud')
    school_id = current_user.school_id
    conflict  = ConflictLog.query.filter_by(id=conflict_id, school_id=school_id).first_or_404()

    from utils.auto_migrate import import_all_models, get_all_subclasses
    import_all_models()
    subclass_map = {c.__tablename__: c for c in get_all_subclasses(db.Model) if hasattr(c, '__tablename__')}
    cls = subclass_map.get(conflict.table_name)

    try:
        if action == 'keep_cloud' and conflict.cloud_payload and cls:
            cloud_data = json.loads(conflict.cloud_payload)
            rec = cls.query.filter_by(uuid=conflict.record_uuid).first()
            if rec and hasattr(rec, 'update_from_dict'):
                db.session.no_sync_logging = True
                rec.update_from_dict(cloud_data)
                db.session.no_sync_logging = False
        elif action == 'keep_local' and conflict.local_payload:
            db.session.add(SyncQueue(
                school_id=school_id,
                table_name=conflict.table_name,
                record_id=conflict.record_uuid,
                operation_type='UPDATE',
                payload_json=conflict.local_payload,
                status='PENDING', priority=3
            ))
        conflict.resolved = True
        db.session.commit()
        flash(f"✅ Conflict resolve ho gaya ({action.replace('_', ' ')})", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Resolve failed: {e}", "danger")

    return redirect(url_for('sync.conflict_list'))


@sync_bp.route('/full-initial-sync', methods=['POST'])
@login_required
def full_initial_sync():
    from utils.sync_engine import perform_full_initial_sync
    result = perform_full_initial_sync(current_user.school_id)
    flash(f"✅ Initial sync complete: {result['total_pulled']} records pulled.", "success")
    return redirect(url_for('sync.status_page'))
