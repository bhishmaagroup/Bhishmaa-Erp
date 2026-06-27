import os, uuid
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from extensions import db
from models import school
from models.school import School

school_bp = Blueprint('school', __name__, url_prefix='/school')

# ❌ OLD: 'uploads/schools'
# ✅ NEW:
UPLOAD_SCHOOL = 'schools'


def save_logo(file, old_logo=None):
    if not file or file.filename == '':
        return None

    ext = file.filename.rsplit('.', 1)[-1]
    filename = f"school_logo_{uuid.uuid4()}.{ext}"

    upload_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'schools')
    os.makedirs(upload_path, exist_ok=True)

    full_path = os.path.join(upload_path, filename)
    file.save(full_path)

    # ✅ OLD LOGO DELETE
    if old_logo:
        old_path = os.path.join(current_app.config['UPLOAD_FOLDER'], old_logo)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except:
                pass  # safe ignore

    return f"schools/{filename}"


@school_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def school_settings():
    # 🔐 current logged-in user's school
    school = School.query.get_or_404(current_user.school_id)

    if request.method == 'POST':
        school.school_name = request.form.get('school_name')
        school.address = request.form.get('address')
        school.city = request.form.get('city')
        school.state = request.form.get('state')
        school.pincode = request.form.get('pincode')
        school.phone = request.form.get('phone')
        school.email = request.form.get('email')
        school.affiliation_no = request.form.get('affiliation_no')
        school.website = request.form.get('website')
        school.latitude = request.form.get('latitude')

        school.longitude = request.form.get('longitude')

        school.radius = request.form.get('radius')

        logo = request.files.get('logo')
        if logo and logo.filename:
            school.logo = save_logo(logo)

        db.session.commit()
        flash("School details updated successfully", "success")
        return redirect(url_for('school.school_settings'))

    return render_template('school/settings.html', school=school)