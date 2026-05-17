from extensions import db
from datetime import datetime

class Teacher(db.Model):
    __tablename__ = 'teacher'

    id = db.Column(db.Integer, primary_key=True)

    

    subject_assignments = db.relationship(
    "TeacherSubject",
    backref="teacher",
    lazy=True
)
    # 🔐 MULTI SCHOOL SAFETY
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)



    # BASIC
    teacher_code = db.Column(db.String(30), nullable=False)
    first_name = db.Column(db.String(100), nullable=False)
    middle_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))

    gender = db.Column(db.String(10))
    dob = db.Column(db.Date)

    mobile = db.Column(db.String(15))
    email = db.Column(db.String(120))

    address = db.Column(db.Text)
    permanent_address =db.Column(db.Text)

    # PROFESSIONAL
    qualification = db.Column(db.String(200))
    experience = db.Column(db.String(50))
    specialization = db.Column(db.String(200))
    employment_type = db.Column(db.String(50))  # Permanent / Contract
    joining_date = db.Column(db.Date)
    salary = db.Column(db.Integer)
    designation = db.Column(db.String(50))
    # GOV DOCS
    aadhaar = db.Column(db.String(20))
    pan = db.Column(db.String(20))
    #TEACHER PHOTO
    photo = db.Column(db.String(200))

        # FACE ATTENDANCE
    face_encoding = db.Column(db.JSON)
    device_id = db.Column(db.String(255))
    face_image = db.Column(db.String(255))

    # FILES
    pass_doc = db.Column(db.String(300))
    resume = db.Column(db.String(300))
    aadhaar_doc = db.Column(db.String(300))
    qualification_doc = db.Column(db.String(300))

    # STATUS
    is_active = db.Column(db.Boolean, default=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Teacher {self.teacher_code} - {self.first_name}>"



# ================= SALARY STRUCTURE =================
class SalaryStructure(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(db.Integer, nullable=False)

    # 🔥 NULL = default structure
    staff_id = db.Column(db.Integer, nullable=True)

    is_default = db.Column(db.Boolean, default=False)

    # ===== EARNINGS =====
    basic = db.Column(db.Float, default=0)
    grade_pay = db.Column(db.Float, default=0)
    hra = db.Column(db.Float, default=0)
    da = db.Column(db.Float, default=0)
    ta = db.Column(db.Float, default=0)
    medical = db.Column(db.Float, default=0)
    academic = db.Column(db.Float, default=0)
    other_allowance = db.Column(db.Float, default=0)

    # ===== AUTO CALC =====
    per_day_salary = db.Column(db.Float, default=0)

    # ===== ATTENDANCE RULES =====
    absent_cut_percent = db.Column(db.Float, default=100)
    late_cut_percent = db.Column(db.Float, default=25)
    half_day_cut_percent = db.Column(db.Float, default=50)
    grace_minutes = db.Column(db.Integer, default=10)
    # HEADER INFO
    effective_from = db.Column(db.Date)

    # ATTENDANCE EXTRA
    grace_minutes = db.Column(db.Integer, default=10)

    # ===== DEDUCTIONS =====
    pf = db.Column(db.Float, default=0)
    esi = db.Column(db.Float, default=0)
    pt = db.Column(db.Float, default=0)
    tds = db.Column(db.Float, default=0)
    loan = db.Column(db.Float, default=0)
    advance = db.Column(db.Float, default=0)

    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ================= SALARY RECORD =================
class SalaryRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(db.Integer, nullable=False)
    staff_id = db.Column(db.Integer, nullable=False)

    month = db.Column(db.String(7), nullable=False)  # 2026-04

    # ===== ATTENDANCE =====
    total_days = db.Column(db.Integer, default=0)
    present = db.Column(db.Integer, default=0)
    absent = db.Column(db.Integer, default=0)
    late = db.Column(db.Integer, default=0)
    half_day = db.Column(db.Integer, default=0)

    basic = db.Column(db.Float, default=0)
    hra = db.Column(db.Float, default=0)
    da = db.Column(db.Float, default=0)
    ta = db.Column(db.Float, default=0)
    medical = db.Column(db.Float, default=0)
    special = db.Column(db.Float, default=0)

    pf = db.Column(db.Float, default=0)
    pt = db.Column(db.Float, default=0)
    tds = db.Column(db.Float, default=0)
    esi = db.Column(db.Float, default=0)
    loan = db.Column(db.Float, default=0)

    # ===== SALARY BREAKDOWN =====
    gross_salary = db.Column(db.Float, default=0)

    attendance_deduction = db.Column(db.Float, default=0)

    other_deduction = db.Column(db.Float, default=0)

    total_deduction = db.Column(db.Float, default=0)

    net_salary = db.Column(db.Float, default=0)

    # ===== ADVANCE TRACK =====
    prev_advance = db.Column(db.Float, default=0)
    adjusted_salary = db.Column(db.Float, default=0)

    # ===== STATUS =====
    status = db.Column(db.String(20), default="Pending")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)


# ================= PAYMENT =================
class SalaryPayment(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    salary_id = db.Column(db.Integer, nullable=False)

    paid_amount = db.Column(db.Float, default=0)

    payment_mode = db.Column(db.String(20))  # Cash / UPI / Bank
    transaction_id = db.Column(db.String(100))

    note = db.Column(db.String(200))  # 🔥 extra field

    payment_date = db.Column(db.DateTime, default=datetime.utcnow)


# ================= BONUS =================
class SalaryBonus(db.Model):
    id = db.Column(db.Integer, primary_key=True)

    school_id = db.Column(db.Integer, nullable=False)
    staff_id = db.Column(db.Integer, nullable=False)

    month = db.Column(db.String(7), nullable=False)

    bonus_type = db.Column(db.String(50))  # Festival / Overtime / Incentive
    amount = db.Column(db.Float, default=0)

    note = db.Column(db.String(200))

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

