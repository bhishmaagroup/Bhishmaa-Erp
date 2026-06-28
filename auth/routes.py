from flask import Blueprint, render_template, request, redirect, url_for, flash, session, current_app
from flask_login import login_user, logout_user, login_required, current_user
from extensions import db, login_manager
from models import user
from models.user import User
from models.school import School
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import random
from extensions import mail 
from flask_mail import Message

auth = Blueprint('auth', __name__)

@login_manager.user_loader
def load_user(user_id):

    # 🔥 SUPER ADMIN HANDLE
    if str(user_id).startswith("superadmin-"):
        admin_id = int(user_id.split("-")[1])
        from models.super_admin import SuperAdmin
        return SuperAdmin.query.get(admin_id)

    # 👇 NORMAL USER
    return User.query.get(int(user_id))

@auth.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('auth.login'))

@auth.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        school_code = request.form['school_code']
        username = request.form['username']
        password = request.form['password']

        # 🏫 SCHOOL CHECK: Allow 'active' schools OR 'approved' schools (for payment)
        school = School.query.filter_by(school_code=school_code).first()

        if not school:
            flash('Invalid School Code', 'danger')
            return redirect(url_for('auth.login'))

        # 🚨 STATUS CHECK: Block 'pending' or 'suspended' (non-approved)
        if school.status == 'pending':
            flash('Your school application is still pending approval.', 'warning')
            return redirect(url_for('auth.login'))
        
        if school.status == 'suspended':
            flash('This school account has been suspended.', 'danger')
            return redirect(url_for('auth.login'))

        # ⏳ SUBSCRIPTION EXPIRY CHECK
        if school.status == 'active' and school.expiry_date and school.expiry_date < datetime.utcnow():
            flash("Subscription expired. Contact Super Admin for renewal.", "warning")
            # We don't block login here so they can still see payment options
        
        # 👤 USER CHECK
        user = User.query.filter_by(
            school_id=school.id,
            username=username
        ).first()

        if user and check_password_hash(user.password, password):
            # Check if User account itself is active
            if not user.is_active:
                flash('Your user account is disabled.', 'danger')
                return redirect(url_for('auth.login'))

            login_user(user)

            # 🔄 SYNC ON LOGIN — background thread (never blocks login)
            try:
                from utils.sync_engine import sync_on_login
                import threading
                _st = threading.Thread(
                    target=sync_on_login,
                    args=(school.id, current_app._get_current_object()),
                    name=f"LoginSync-{school.id}",
                    daemon=True
                )
                _st.start()
            except Exception as _se:
                pass  # Sync failure must never block login

            allowed_roles = [
                "teacher",
                "employee",
                "staff",
                "director",
                "accountant"
                ]

            if user.role.lower() in allowed_roles:
                session["gps_attendance_pending"] = True

            # 🕒 TRACK LAST LOGIN123    
            user.last_login = datetime.utcnow()
            db.session.commit()

            # 🔄 FORCE PASSWORD CHANGE CHECK
            if user.force_password_change:
                return redirect(url_for('auth.change_password'))

            # ✅ SUCCESSFUL LOGIN
            # The subscription_required decorator on the dashboard will handle
            # redirecting approved-but-not-active schools to the plan page.
            return redirect(url_for('dashboard.home'))

        flash('Invalid Username or Password', 'danger')

    return render_template('auth/login.html')

@auth.route('/change-password', methods=['GET', 'POST'])
@login_required
def change_password():
    if request.method == 'POST':
        new_password = request.form['password']
        current_user.password = generate_password_hash(new_password)
        current_user.force_password_change = False
        db.session.commit()
        flash('Password updated successfully!', 'success')
        return redirect(url_for('dashboard.home'))

    return render_template('auth/change_password.html')

@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        school_code = request.form['school_code']
        username = request.form['username']

        school = School.query.filter_by(school_code=school_code).first()

        if not school:
            flash('Invalid School Code', 'danger')
            return redirect(url_for('auth.forgot_password'))

        user = User.query.filter_by(
            school_id=school.id,
            username=username
        ).first()

        if not user:
            flash('User not found', 'danger')
            return redirect(url_for('auth.forgot_password'))

        # ❗ school email check
        if not school.email:
            flash('School email not set', 'danger')
            return redirect(url_for('auth.forgot_password'))

        # 🔥 OTP generate
        otp = str(random.randint(100000, 999999))

        user.otp = otp
        user.otp_expiry = datetime.utcnow() + timedelta(minutes=5)
        user.otp_attempts = 0
        db.session.commit()

        # 📧 SEND MAIL TO SCHOOL EMAIL
        try:
            msg = Message(
                'OTP Verification - Bhishmaa ERP',
                sender='your_email@gmail.com',
                recipients=[school.email]   # 🔥 IMPORTANT
            )

            msg.body = f"""
Hello {school.school_name},

OTP for user ({username}) is: {otp}

Valid for 5 minutes.
"""

            mail.send(msg)

            print("OTP:", otp)  # debug backup

        except Exception as e:
            print("MAIL ERROR:", e)
            flash('OTP send failed', 'danger')
            return redirect(url_for('auth.forgot_password'))

        flash('OTP sent to school email', 'success')
        return redirect(url_for('auth.verify_otp', user_id=user.id))

    return render_template('auth/forgot_password.html')


@auth.route('/verify-otp/<int:user_id>', methods=['GET', 'POST'])
def verify_otp(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        entered_otp = request.form['otp']

        if not user.otp or datetime.utcnow() > user.otp_expiry:
            flash('OTP expired', 'danger')
            return redirect(url_for('auth.forgot_password'))

        if user.otp_attempts >= 3:
            flash('Too many attempts', 'danger')
            return redirect(url_for('auth.forgot_password'))

        if entered_otp != user.otp:
            user.otp_attempts += 1
            db.session.commit()
            flash('Invalid OTP', 'danger')
            return redirect(request.url)

        # ✅ success
        user.otp = None
        user.otp_expiry = None
        user.otp_attempts = 0
        db.session.commit()

        return redirect(url_for('auth.reset_password', user_id=user.id))

    return render_template('auth/verify_otp.html')



@auth.route('/reset-password/<int:user_id>', methods=['GET', 'POST'])
def reset_password(user_id):
    user = User.query.get_or_404(user_id)

    if request.method == 'POST':
        new_password = request.form['password']

        user.password = generate_password_hash(new_password)
        db.session.commit()

        flash('Password reset successful', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html')