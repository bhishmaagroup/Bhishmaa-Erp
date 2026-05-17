from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file,abort
from functools import wraps
from flask import jsonify
from werkzeug.utils import secure_filename
from flask_login import login_required, current_user, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from models.school import School
from models.user import User
from extensions import db
from datetime import datetime, timedelta
from sqlalchemy import func
import random, string, sqlite3, os
from models.super import AuditLog, Broadcast, Ticket, TicketMessage, SystemSetting, Plan, Coupon 
from utils.email import send_system_email
from flask import session
import random
import string
from models.payment import Payment
from flask import current_app
from models.super_admin import SuperAdmin
from werkzeug.security import check_password_hash
from flask import session
super_admin = Blueprint('super_admin', __name__, url_prefix='/super')




def generate_license(school_code, plan):
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BHEESHMA-{school_code}-{plan.upper()}-{rand}"

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'superadmin':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function

def log_admin_action(action_description):
    """Helper function to record super admin actions"""
    log = AuditLog(
        admin_username=current_user.username,
        action=action_description,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()

def check_plan_limit(school):
    # Count current students for this school
    current_count = User.query.filter_by(school_id=school.id, role='student').count()
    
    # Fetch the actual plan object from the database
    plan_config = Plan.query.filter_by(name=school.plan).first()
    
    if plan_config and current_count >= plan_config.student_limit:
        return False # Limit reached
    return True


def subscription_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated and current_user.role == 'admin':

            school = School.query.get(current_user.school_id)

            # ❌ NO PLAN SELECTED
            if school.status == 'approved' and not school.is_active:
                return redirect(url_for('super_admin.select_plan'))

            # 🟡 TRIAL ACTIVE
            if school.plan == 'trial' and school.expiry_date > datetime.utcnow():
                return f(*args, **kwargs)

            # 🔴 EXPIRED
            if school.expiry_date and school.expiry_date < datetime.utcnow():
                school.is_active = False
                db.session.commit()
                return redirect(url_for('super_admin.select_plan'))

        return f(*args, **kwargs)
    return decorated_function

# 🔐 Guards
def owner_only():

    if not current_user.is_authenticated:
        return False

    # 🔥 SuperAdmin check
    from models.super_admin import SuperAdmin
    if isinstance(current_user, SuperAdmin):
        return True

    # 👇 Normal user fallback
    return getattr(current_user, "role", None) == "superadmin"

def block_cross_school(target_school_id):
    # superadmin can access all; others blocked
    if current_user.role != 'superadmin' and current_user.school_id != target_school_id:
        return True
    return False

def auto_block_expired():
    schools = School.query.all()

    for s in schools:
        if s.expiry_date and s.expiry_date < datetime.utcnow():
            s.is_active = False

    db.session.commit()

# 🔐 LOGIN
@super_admin.route('/login', methods=['GET', 'POST'])
def login():

    if request.method == 'POST':

        username = request.form['username']
        password = request.form['password']

        admin = SuperAdmin.query.filter_by(username=username).first()

        if admin and check_password_hash(admin.password, password):

            # 🔥 DIRECT LOGIN (no manual flags)
            login_user(admin)

            return redirect(url_for('super_admin.dashboard'))

        flash("Invalid credentials", "danger")

    return render_template('super/login.html')
# 📊 DASHBOARD (multi-school analytics)
@super_admin.route('/dashboard')
@login_required
def dashboard():
    if not owner_only():
        return "Unauthorized", 403

    auto_block_expired()
    import json

    # 📊 CALCULATE REVENUE FROM PAYMENTS TABLE
    total_revenue = db.session.query(func.sum(Payment.amount)).scalar() or 0
    
    # 📈 GROWTH DATA (Users created over time)
    growth = db.session.query(
        func.date(User.created_at),
        func.count(User.id)
    ).group_by(func.date(User.created_at)).all()

    labels = [str(x[0]) for x in growth]
    data = [x[1] for x in growth]

    # 🏫 SCHOOLS & RECENT PAYMENTS
    schools = School.query.order_by(School.id.desc()).all()
    recent_payments = Payment.query.order_by(Payment.timestamp.desc()).limit(5).all()

    return render_template(
        'super/dashboard.html',
        total_schools=School.query.count(),
        active_schools=School.query.filter_by(is_active=True).count(),
        total_users=User.query.count(),
        total_revenue=total_revenue,
        schools=schools,
        recent_payments=recent_payments,
        user_labels=json.dumps(labels),
        user_data=json.dumps(data),
        datetime=datetime
    )

# 🏫 CREATE SCHOOL (+ admin)
@super_admin.route('/create-school', methods=['GET', 'POST'])
@login_required
def create_school():
    if not owner_only():
        return "Unauthorized", 403

    if request.method == 'POST':
        school = School(
            school_code=request.form['school_code'],
            school_name=request.form['school_name'],
            is_active=True,
            plan='free',
            expiry_date=datetime.utcnow() + timedelta(days=30)
        )
        db.session.add(school)
        db.session.commit()

        admin = User(
            school_id=school.id,
            username=request.form['admin_username'],
            password=generate_password_hash(request.form['temp_password']),
            role='admin'
        )
        db.session.add(admin)
        db.session.commit()

        flash("School created")
        return redirect(url_for('super_admin.dashboard'))

    # 👉 GET request के लिए page दिखाओ
    return render_template('super/create_school.html')


# 💰 ASSIGN PLAN + LIMITS
PLAN_LIMITS = {
    "free": {"max_students": 100},
    "pro": {"max_students": 500},
    "premium": {"max_students": 9999}
}

from werkzeug.security import generate_password_hash
from datetime import datetime, timedelta

@super_admin.route('/apply', methods=['GET', 'POST'])
def school_application():
    if request.method == 'POST':

        import random
        verification_code = str(random.randint(100000, 999999))

        new_school = School(
            school_code=request.form.get('school_code').upper(),
            school_name=request.form.get('school_name'),
            email=request.form.get('email'),

            status='pending',
            is_active=False,
            plan='trial',

            created_at=datetime.utcnow(),
            expiry_date=datetime.utcnow() + timedelta(days=7),

            verification_code=verification_code,
            otp_created_at=datetime.utcnow(),   # ✅ NEW
            otp_attempts=0                      # ✅ NEW
        )

        try:
            db.session.add(new_school)
            db.session.flush()

            hashed_pw = generate_password_hash(request.form.get('password'))

            new_admin = User(
                school_id=new_school.id,
                username=request.form.get('admin_username'),
                password=hashed_pw,
                role='admin',
                is_active=False
            )

            db.session.add(new_admin)
            db.session.commit()

            # ✅ SAVE SESSION (VERY IMPORTANT)
            session['verify_school_id'] = new_school.id

            # 📧 SEND OTP
            send_system_email(
                to_email=new_school.email,
                subject="Bhishmaa ERP - Verify Account",
                body=f"Your OTP is: {verification_code}"
            )

            flash("OTP sent to your email", "success")
            return redirect(url_for('super_admin.verify'))

        except Exception as e:
            db.session.rollback()
            print("ERROR:", e)
            flash(f"Error: {str(e)}", "danger")

    return render_template('public/register_school.html')


@super_admin.route('/verify', methods=['GET', 'POST'])
def verify():

    school_id = session.get('verify_school_id')

    if not school_id:
        flash("Session expired", "danger")
        return redirect(url_for('super_admin.school_application'))

    school = School.query.get(school_id)

    if request.method == 'POST':
        code = (request.form.get('code') or "").strip()

        if not code:
            flash("Enter OTP", "danger")
            return redirect(url_for('super_admin.verify'))

        # 🚫 BLOCK CHECK
        if school.otp_blocked_until and datetime.utcnow() < school.otp_blocked_until:
            flash("🚫 Too many attempts. Try again later.", "danger")
            return redirect(url_for('super_admin.verify'))

        # ⏰ EXPIRY (5 min)
        if datetime.utcnow() > school.otp_created_at + timedelta(minutes=5):
            flash("OTP expired. Resend.", "danger")
            return redirect(url_for('super_admin.verify'))

        # ❌ WRONG OTP
        if school.verification_code != code:
            school.otp_attempts += 1

            # 🚫 BLOCK AFTER 3 ATTEMPTS
            if school.otp_attempts >= 3:
                school.otp_blocked_until = datetime.utcnow() + timedelta(minutes=10)
                db.session.commit()

                flash("🚫 Too many attempts. Blocked for 10 minutes.", "danger")
                return redirect(url_for('super_admin.verify'))

            db.session.commit()

            left = 3 - school.otp_attempts
            flash(f"Invalid OTP. {left} attempts left.", "danger")
            return redirect(url_for('super_admin.verify'))

        # ✅ SUCCESS
        school.status = 'approved'
        school.is_active = False

        # 🔥 CLEAN OTP
        school.verification_code = None
        school.otp_attempts = 0
        school.otp_created_at = None
        school.otp_blocked_until = None

        admin = User.query.filter_by(
            school_id=school.id,
            role='admin'
        ).first()

        if admin:
            admin.is_active = True
            login_user(admin)   # 🔥 AUTO LOGIN

        db.session.commit()

        session.pop('verify_school_id', None)

        flash("✅ Verified & Logged in!", "success")
        return redirect(url_for('dashboard.home'))

    return render_template('public/verify.html')

@super_admin.route('/approve-school/<int:id>', methods=['POST'])
@login_required
@superadmin_required
def approve_school(id):
    school = School.query.get_or_404(id)
    school.status = 'approved'
    school.is_active = False  # Keep this False so dashboard shows "Awaiting Payment"
    
    # Enable the specific admin user to log in
    admin = User.query.filter_by(school_id=school.id, role='admin').first()
    if admin:
        admin.is_active = True # User can log in now
    
    db.session.commit()
    flash(f"{school.school_name} approved! They can now log in to select a plan.")
    return redirect(url_for('super_admin.dashboard'))


@super_admin.route('/assign-plan/<int:id>', methods=['POST'])
@login_required
def assign_plan(id):

    school = School.query.get_or_404(id)

    plan = request.form['plan']
    days = int(request.form.get('days', 30))  # default 30

    school.plan = plan
    school.expiry_date = datetime.utcnow() + timedelta(days=days)
    school.is_active = True

    db.session.commit()

    flash(f"{plan} plan activated for {days} days")
    return redirect(url_for('super_admin.dashboard'))


# 🔒 BLOCK / ACTIVATE SCHOOL
@super_admin.route('/toggle-school/<int:id>', methods=['POST'])
@login_required
def toggle_school(id):
    if not owner_only(): return "Unauthorized", 403
    school = School.query.get_or_404(id)
    school.is_active = not school.is_active
    db.session.commit()
    
    # 📝 LOG IT
    status = "Unblocked" if school.is_active else "Blocked"
    log_admin_action(f"{status} school: {school.school_name}")
    
    return redirect(url_for('super_admin.dashboard'))


# 🔑 RESET PASSWORD (admin of school)
def gen_pass():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=8))

@super_admin.route('/reset-password/<int:id>', methods=['POST'])
@login_required
def reset_password(id):
    if not owner_only():
        return "Unauthorized", 403

    admin = User.query.filter_by(school_id=id, role='admin').first_or_404()
    new = gen_pass()
    admin.password = generate_password_hash(new)
    db.session.commit()
    flash(f"New Password: {new}")
    return redirect(url_for('super_admin.dashboard'))


# 🏫 SCHOOL DETAIL
@super_admin.route('/school/<int:id>')
@login_required
def school_detail(id):
    if not owner_only():
        return "Unauthorized", 403

    school = School.query.get_or_404(id)
    total_users = User.query.filter_by(school_id=id).count()

    return render_template(
        'super/school_detail.html',
        school=school,
        total_users=total_users,
        limits=PLAN_LIMITS.get(school.plan, {})
    )


# 👥 USERS (search + filter)
@super_admin.route('/school/<int:id>/users')
@login_required
def view_users(id):
    if not owner_only():
        return "Unauthorized", 403

    school = School.query.get_or_404(id)

    q = request.args.get('q', '').strip()
    role = request.args.get('role', '').strip()
    page = request.args.get('page', 1, type=int) # 👉 Get page number

    query = User.query.filter_by(school_id=id)

    if q:
        query = query.filter(User.username.ilike(f"%{q}%"))
    if role:
        query = query.filter_by(role=role)

    # 👉 Use .paginate() instead of .all()
    # per_page=20 means it will only load 20 users at a time
    users_pagination = query.order_by(User.id.desc()).paginate(page=page, per_page=20)

    return render_template(
        'super/users.html',
        users=users_pagination.items,      # The list of users for the current page
        pagination=users_pagination,       # The pagination object for Next/Prev buttons
        school=school,
        q=q,
        role=role
    )


# 🔒 TOGGLE USER (block/unblock)
@super_admin.route('/user/<int:id>/toggle', methods=['POST'])
@login_required
def toggle_user(id):
    if not owner_only():
        return "Unauthorized", 403

    user = User.query.get_or_404(id)
    user.is_active = not user.is_active
    db.session.commit()
    return redirect(request.referrer)


# ✏️ UPDATE USER ROLE
@super_admin.route('/user/<int:id>/update-role', methods=['POST'])
@login_required
def update_user_role(id):
    if not owner_only():
        return "Unauthorized", 403

    user = User.query.get_or_404(id)
    user.role = request.form['role']
    db.session.commit()
    return redirect(request.referrer)


# ❌ DELETE USER
@super_admin.route('/user/<int:id>/delete', methods=['POST'])
@login_required
def delete_user(id):
    if not owner_only(): return "Unauthorized", 403
    user = User.query.get_or_404(id)
    username = user.username # Save name before deleting
    db.session.delete(user)
    db.session.commit()
    
    # 📝 LOG IT
    log_admin_action(f"Deleted user: {username} from School ID {id}")
    
    return redirect(request.referrer)


# 🧾 BACKUP DATABASE (sqlite)
@super_admin.route('/backup')
@login_required
def backup_db():
    if not owner_only():
        return "Unauthorized", 403

    db_path = 'instance/app.db' if os.path.exists('instance/app.db') else 'app.db'
    backup_file = f"backup_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.sql"

    con = sqlite3.connect(db_path)
    with open(backup_file, 'w') as f:
        for line in con.iterdump():
            f.write(f"{line}\n")
    con.close()

    return send_file(backup_file, as_attachment=True)


# 🚪 LOGOUT
@super_admin.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('super_admin.login'))

# 📢 MANAGE BROADCASTS
@super_admin.route('/broadcasts', methods=['GET', 'POST'])
@login_required
def manage_broadcasts():
    if not owner_only(): return "Unauthorized", 403
    
    if request.method == 'POST':
        # Turn off all older broadcasts
        Broadcast.query.update({Broadcast.is_active: False}) 
        
        new_msg = Broadcast(
            message=request.form['message'], 
            type=request.form.get('type', 'info')
        )
        db.session.add(new_msg)
        db.session.commit()
        
        log_admin_action("Created a new global broadcast")
        flash("Broadcast sent to all schools!")
        return redirect(url_for('super_admin.manage_broadcasts'))
        
    broadcasts = Broadcast.query.order_by(Broadcast.id.desc()).limit(15).all()
    return render_template('super/broadcasts.html', broadcasts=broadcasts)


# 🎫 VIEW ALL SUPPORT TICKETS
@super_admin.route('/tickets')
@login_required
def view_tickets():
    if not owner_only(): return "Unauthorized", 403
    
    # Show Open tickets first, then sort by newest
    tickets = Ticket.query.order_by(Ticket.status.desc(), Ticket.created_at.desc()).all()
    return render_template('super/tickets.html', tickets=tickets)


# 🕵️ VIEW AUDIT LOGS
@super_admin.route('/audit-logs')
@login_required
def view_logs():
    if not owner_only(): return "Unauthorized", 403
    
    page = request.args.get('page', 1, type=int)
    logs = AuditLog.query.order_by(AuditLog.id.desc()).paginate(page=page, per_page=50)
    
    return render_template('super/logs.html', logs=logs.items, pagination=logs)



from flask import session

@super_admin.route('/impersonate/<int:school_id>')
@login_required
def impersonate(school_id):
    if not owner_only(): return "Unauthorized", 403
    
    school = School.query.get_or_404(school_id)
    admin_user = User.query.filter_by(school_id=school.id, role='admin').first()

    if not admin_user:
        flash("This school has no admin account to impersonate.", "danger")
        return redirect(url_for('super_admin.dashboard'))

    session['is_impersonating'] = True
    session['original_user_id'] = current_user.id 
    
    login_user(admin_user)
    log_admin_action(f"Impersonated Admin of {school.school_name}")
    
    flash(f"Now viewing as {school.school_name} Admin. Use the 'Exit' button to return.")
    return redirect(url_for('dashboard.home')) 

@super_admin.route('/exit-impersonation')
@login_required
def exit_impersonation():
    if not session.get('is_impersonating'):
        return redirect(url_for('super_admin.dashboard'))

    original_admin = User.query.get(session['original_user_id'])
    if original_admin:
        login_user(original_admin)
        session.pop('is_impersonating', None)
        session.pop('original_user_id', None)
        flash("Returned to Super Admin Panel.")
    
    return redirect(url_for('super_admin.dashboard'))


# 💬 TICKET VIEW & REPLY INTERFACE
# routes.py
@super_admin.route('/ticket/<int:id>', methods=['GET', 'POST'])
@login_required
def ticket_detail(id):
    if not owner_only(): abort(403)
    ticket = Ticket.query.get_or_404(id)

    if request.method == 'POST':
        reply_text = request.form.get('message')
        
        if reply_text:
            msg = TicketMessage(ticket_id=ticket.id, sender='SuperAdmin', message=reply_text)
            db.session.add(msg)
            
            # TRIGGER EMAIL: Notify the School Admin
            # We assume the school has an admin user as created in create_school
            school_admin = User.query.filter_by(school_id=ticket.school_id, role='admin').first()
            if school_admin and school_admin.email:
                send_system_email(
                    school_admin.email, 
                    f"Update on Ticket #{ticket.id}", 
                    f"The Support Team has replied: {reply_text[:50]}..."
                )

        db.session.commit()
        flash("Reply sent and admin notified.", "success")
        return redirect(url_for('super_admin.ticket_detail', id=ticket.id))

    return render_template('super/ticket_detail.html', ticket=ticket)


# ⚙️ GLOBAL SYSTEM SETTINGS UI
@super_admin.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    if not owner_only(): return "Unauthorized", 403

    if request.method == 'POST':
        # Process dynamically generated form fields
        for key, value in request.form.items():
            setting = SystemSetting.query.filter_by(key=key).first()
            if setting:
                setting.value = value
            else:
                db.session.add(SystemSetting(key=key, value=value))
        
        db.session.commit()
        log_admin_action("Updated global system environment variables")
        flash("Settings saved successfully.", "success")
        return redirect(url_for('super_admin.settings'))

    all_settings = SystemSetting.query.all()
    # Convert list of objects to a simple dictionary for easy template rendering
    settings_dict = {s.key: s.value for s in all_settings}
    
    return render_template('super/settings.html', settings=settings_dict)

@super_admin.route('/health')
@superadmin_required
def system_health():
    # 1. Count users who logged in within the last 15 minutes
    timestamp_limit = datetime.utcnow() - timedelta(minutes=15)
    active_sessions = User.query.filter(User.last_login >= timestamp_limit).count()
    
    # 2. Calculate Database Size
    db_path = 'instance/app.db' if os.path.exists('instance/app.db') else 'app.db'
    db_size_mb = 0
    if os.path.exists(db_path):
        db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 2)

    return render_template(
        'super/health.html', 
        total_active_sessions=active_sessions, 
        db_size_mb=db_size_mb
    )


# Add these to your existing super_admin blueprint in routes.py

@super_admin.route('/plans', methods=['GET'])
@login_required
def manage_plans():
    if not owner_only(): abort(403)
    plans = Plan.query.all()
    return render_template('super/plans.html', plans=plans)

@super_admin.route('/plans/update/<int:id>', methods=['POST'])
@login_required
def update_plan_config(id):
    if not owner_only(): abort(403)
    plan = Plan.query.get_or_404(id)
    plan.price = request.form.get('price')
    plan.student_limit = request.form.get('limit')
    db.session.commit()
    flash(f"Plan {plan.name} updated successfully!")
    return redirect(url_for('super_admin.manage_plans'))

@super_admin.route('/revenue/export')
@login_required
def export_revenue():
    """Generates a CSV of all payments for accounting"""
    import csv
    from io import StringIO
    from flask import make_response

    si = StringIO()
    cw = csv.writer(si)
    payments = Payment.query.all()
    cw.writerow(['ID', 'School', 'Amount', 'Date', 'Transaction ID'])
    for p in payments:
        cw.writerow([p.id, p.school.school_name, p.amount, p.timestamp, p.transaction_id])
    
    output = make_response(si.getvalue())
    output.headers["Content-Disposition"] = "attachment; filename=revenue_report.csv"
    output.headers["Content-type"] = "text/csv"
    return output

@super_admin.route('/maintenance')
@login_required
def maintenance_panel():
    if not owner_only(): abort(403)
    log_count = AuditLog.query.count()
    return render_template('super/maintenance.html', log_count=log_count)

@super_admin.route('/cleanup-logs', methods=['POST'])
@superadmin_required # Use the new decorator
def cleanup_logs():
    days = int(request.form.get('days', 30))
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    # Delete logs older than the cutoff
    deleted_count = AuditLog.query.filter(AuditLog.timestamp < cutoff).delete()
    db.session.commit()
    
    log_admin_action(f"Purged {deleted_count} audit logs older than {days} days")
    flash(f"Successfully cleaned up {deleted_count} logs.", "success")
    return redirect(url_for('super_admin.maintenance_panel'))

@super_admin.route('/optimize-db')
@login_required
def optimize_db():
    if not owner_only(): abort(403)
    # This executes raw SQL to optimize SQLite
    db.session.execute('VACUUM')
    log_admin_action("Performed database optimization (VACUUM)")
    flash("Database optimized successfully.", "success")
    return redirect(url_for('super_admin.maintenance_panel'))



@super_admin.route('/checkout/<int:plan_id>')
@login_required
def checkout(plan_id):
    plan = Plan.query.get_or_404(plan_id)
    # Here you would normally integrate Stripe/Razorpay
    # For now, let's create a "Mock Payment" success route
    return render_template('public/checkout.html', plan=plan)

@super_admin.route('/process-payment/<int:plan_id>', methods=['POST'])
@login_required
def process_payment(plan_id):
    plan = Plan.query.get_or_404(plan_id)
    school = School.query.get(current_user.school_id)

    school.plan = plan.name
    school.expiry_date = datetime.utcnow() + timedelta(days=30)
    school.is_active = True
    school.status = 'active'

    new_payment = Payment(
        school_id=school.id,
        amount=plan.price,
        plan_name=plan.name,
        transaction_id=f"TXN-WEB-{random.randint(10000, 99999)}",
        timestamp=datetime.utcnow()
    )
    
    db.session.add(new_payment)
    db.session.commit()

    flash(f"Payment Successful! {plan.name.upper()} plan activated.", "success")
    return redirect(url_for('dashboard.home'))

@super_admin.route('/request-license/<int:plan_id>', methods=['POST'])
@login_required
def request_license(plan_id):

    plan = Plan.query.get_or_404(plan_id)
    school = School.query.get(current_user.school_id)

    from models.license_request import LicenseRequest

    req = LicenseRequest(
        school_id=school.id,
        plan=plan.name
    )

    db.session.add(req)
    db.session.commit()

    flash("Request sent! Call admin for license.", "info")

    return redirect(url_for('super_admin.enter_license'))

@super_admin.route('/apply-coupon')
def apply_coupon():
    code = request.args.get('code')
    coupon = Coupon.query.filter_by(code=code, active=True).first()

    if coupon:
        return {"valid": True, "discount": coupon.discount_percent}
    return {"valid": False}

@super_admin.route('/plans/create', methods=['POST'])
@login_required
def create_plan():
    if not owner_only(): abort(403)

    new_plan = Plan(
        name=request.form['name'].lower(),
        price=int(request.form['price']),
        student_limit=int(request.form['limit'])
    )

    db.session.add(new_plan)
    db.session.commit()

    flash("Plan created!", "success")
    return redirect(url_for('super_admin.manage_plans'))

@super_admin.route('/plans/delete/<int:id>', methods=['POST'])
@login_required
def delete_plan(id):
    if not owner_only(): abort(403)

    plan = Plan.query.get_or_404(id)
    db.session.delete(plan)
    db.session.commit()

    flash("Plan deleted!", "success")
    return redirect(url_for('super_admin.manage_plans'))

@super_admin.route('/coupon/create', methods=['POST'])
@login_required
def create_coupon():
    code = request.form['code']
    discount = int(request.form['discount'])

    new_coupon = Coupon(
        code=code,
        discount_percent=discount,
        active=True
    )

    db.session.add(new_coupon)
    db.session.commit()

    flash("Coupon created!", "success")
    return redirect(url_for('super_admin.manage_plans'))

@super_admin.route('/select-plan')
@login_required
def select_plan():
    if current_user.role != 'admin': abort(403)

    ensure_default_plans()   # 🔥 AUTO FIX

    plans = Plan.query.all()
    return render_template('public/select_plan.html', plans=plans)

def ensure_default_plans():
    if Plan.query.count() == 0:
        default_plans = [
            Plan(name='free', price=0, student_limit=100),
            Plan(name='pro', price=499, student_limit=500),
            Plan(name='premium', price=999, student_limit=2000),
        ]
        db.session.add_all(default_plans)
        db.session.commit()




@super_admin.route('/resend-otp', methods=['POST'])
def resend_otp():

    school_id = session.get('verify_school_id')

    if not school_id:
        flash("Session expired", "danger")
        return redirect(url_for('super_admin.school_application'))

    school = School.query.get(school_id)

    import random
    new_otp = str(random.randint(100000, 999999))

    school.verification_code = new_otp
    school.otp_created_at = datetime.utcnow()
    school.otp_attempts = 0

    db.session.commit()

    send_system_email(
        to_email=school.email,
        subject="Resend OTP",
        body=f"New OTP: {new_otp}"
    )

    flash("New OTP sent!", "success")
    return redirect(url_for('super_admin.verify'))

@super_admin.route('/delete-school/<int:id>', methods=['POST'])
@login_required
def delete_school(id):
    if not owner_only():
        return "Unauthorized", 403

    school = School.query.get_or_404(id)

    from models.license_request import LicenseRequest

    # 🔥 DELETE ALL RELATED DATA
    User.query.filter_by(school_id=id).delete()
    Payment.query.filter_by(school_id=id).delete()
    Ticket.query.filter_by(school_id=id).delete()
    LicenseRequest.query.filter_by(school_id=id).delete()   # ✅ IMPORTANT

    db.session.delete(school)
    db.session.commit()

    flash("School deleted permanently", "success")
    return redirect(url_for('super_admin.dashboard'))

# ============================
# 🔑 ENTER LICENSE (FIXED)
# ============================
@super_admin.route('/enter-license', methods=['GET', 'POST'])
@login_required
def enter_license():

    # ❗ super admin login से crash ना हो
    if not hasattr(current_user, "school_id"):
        return redirect(url_for('super_admin.dashboard'))

    school = School.query.get(current_user.school_id)

    if request.method == 'POST':
        key = (request.form.get('license_key') or "").strip()

        print("ENTERED:", key)
        print("DB:", school.license_key)

        # ❌ INVALID LICENSE
        if not school.license_key or key != school.license_key.strip():
            flash("❌ Invalid License", "danger")
            return redirect(url_for('super_admin.enter_license'))

        from models.license_request import LicenseRequest

        # 🔥 FIX: pending ना ढूंढो → latest request लो
        req = LicenseRequest.query.filter_by(
            school_id=school.id
        ).order_by(LicenseRequest.id.desc()).first()

        # ✅ APPLY PLAN
        if req:
            school.plan = req.plan
            req.status = "approved"
        else:
            # fallback अगर request नहीं है
            school.plan = school.plan or "pro"

        # 🔥 PLAN DAYS
        if school.plan == "free":
            days = 7
        elif school.plan == "pro":
            days = 30
        else:
            days = 365

        school.expiry_date = datetime.utcnow() + timedelta(days=days)
        school.is_active = True

        db.session.commit()

        flash("✅ License Activated!", "success")
        return redirect(url_for('dashboard.home'))

    return render_template('public/license.html')

@super_admin.route('/license-requests')
@login_required
def license_requests():

    if not owner_only():
        abort(403)

    from models.license_request import LicenseRequest

    requests = LicenseRequest.query.order_by(
        LicenseRequest.id.desc()
    ).all()

    return render_template('super/license_requests.html', requests=requests)


@super_admin.route('/generate-license/<int:school_id>')
@login_required
def generate_license_admin(school_id):

    if not owner_only():
        abort(403)

    import random, string

    school = School.query.get_or_404(school_id)

    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

    school.license_key = f"BHEESHMA-{school.school_code}-{rand}"

    db.session.commit()

    flash("License Generated!", "success")
    return redirect(url_for('super_admin.license_requests'))

@super_admin.route('/upload-payment', methods=['POST'])
@login_required
def upload_payment():

    file = request.files.get('screenshot')

    if not file:
        flash("No file selected", "danger")
        return redirect(request.referrer)

    filename = file.filename

    path = os.path.join(
        current_app.config['UPLOAD_FOLDER'],
        filename
    )

    # 🔥 LOCAL SAVE
    file.save(path)

    # 🔥 CURRENT SCHOOL
    school = School.query.get(current_user.school_id)

    # 🔥 LOCAL PAYMENT SAVE
    new_payment = Payment(
        school_id=school.id,
        amount=0,
        method="manual",
        screenshot=filename,
        status="pending"
    )

    db.session.add(new_payment)
    db.session.commit()

    # ==========================================
    # 🌐 SEND PAYMENT TO ONLINE SERVER
    # ==========================================

    import requests

    try:

        url = "https://bheeshma-erp.onrender.com/super/api/offline-payment"

        files = {
            "screenshot": open(path, "rb")
        }

        data = {
            "school_name": school.school_name,
            "school_code": school.school_code,
            "email": school.email,
            "plan": school.plan or "premium"
        }

        response = requests.post(
            url,
            files=files,
            data=data,
            timeout=30
        )

        print("SERVER RESPONSE:", response.text)

    except Exception as e:

        print("SERVER ERROR:", e)

    flash("Payment screenshot uploaded!", "success")

    return redirect(url_for('super_admin.enter_license'))
    
@super_admin.route('/approve-payment/<int:payment_id>')
@login_required
def approve_payment(payment_id):

    if not owner_only():
        abort(403)

    payment = Payment.query.get_or_404(payment_id)
    school = School.query.get(payment.school_id)

    payment.status = "approved"

    from models.license_request import LicenseRequest

    # 🔥 latest request
    req = LicenseRequest.query.filter_by(
        school_id=school.id
    ).order_by(LicenseRequest.id.desc()).first()

    # 🔥 GENERATE LICENSE
    import random
    import string

    rand = ''.join(
        random.choices(
            string.ascii_uppercase + string.digits,
            k=6
        )
    )

    if req:

        license_key = (
            f"BHEESHMA-{school.school_code}-"
            f"{req.plan.upper()}-{rand}"
        )

        school.plan = req.plan
        req.status = "approved"

    else:

        license_key = (
            f"BHEESHMA-{school.school_code}-"
            f"PRO-{rand}"
        )

        school.plan = "pro"

    school.license_key = license_key

    # 🔥 PLAN DAYS
    if school.plan == "free":
        days = 7

    elif school.plan == "pro":
        days = 30

    else:
        days = 365

    school.expiry_date = datetime.utcnow() + timedelta(days=days)

    school.is_active = True

    # 🔥 SAVE DB FIRST
    db.session.commit()

    # =========================================
    # 📧 SEND LICENSE EMAIL
    # =========================================

    try:

        print("SENDING EMAIL TO:", school.email)

        send_system_email(
            to_email=school.email,
            subject="Bheeshma ERP License Approved",
            body=f"""
Hello {school.school_name},

✅ Your payment has been approved.

🔑 License Key:
{license_key}

Enter this license inside your ERP software
to activate your system.

Thanks,
Bheeshma ERP
"""
        )

        print("✅ LICENSE EMAIL SENT")

    except Exception as e:

        print("❌ MAIL ERROR:", e)

    flash("✅ Payment Approved + License Generated!", "success")

    return redirect(url_for('super_admin.dashboard'))

# =========================================
# 🌐 OFFLINE EXE PAYMENT API
# =========================================

@super_admin.route('/api/offline-payment', methods=['POST'])
def offline_payment():

    try:

        school_name = request.form.get('school_name')
        school_code = request.form.get('school_code')
        email = request.form.get('email')
        plan = request.form.get('plan', 'premium')

        screenshot = request.files.get('screenshot')

        if not school_code:
            return jsonify({
                "status": "error",
                "message": "school_code missing"
            })

        # 🔥 SCHOOL CHECK
        school = School.query.filter_by(
            school_code=school_code
        ).first()

        # 🔥 CREATE SCHOOL
        if not school:

            school = School(
                school_name=school_name,
                school_code=school_code,
                email=email,
                status='approved',
                is_active=False,
                plan=plan,
                created_at=datetime.utcnow()
            )

            db.session.add(school)
            db.session.commit()

        # 🔥 SAVE SCREENSHOT
        filename = None

        if screenshot:

            filename = secure_filename(screenshot.filename)

            upload_path = os.path.join(
                current_app.config['UPLOAD_FOLDER'],
                filename
            )

            screenshot.save(upload_path)

        # 🔥 CREATE PAYMENT
        payment = Payment(
            school_id=school.id,
            amount=0,
            method="offline",
            screenshot=filename,
            status="pending"
        )

        db.session.add(payment)
        db.session.commit()

        return jsonify({
            "status": "success"
        })

    except Exception as e:

        return jsonify({
            "status": "error",
            "message": str(e)
        })
