# models.py
from datetime import date
from extensions import db
from sqlalchemy import UniqueConstraint   # optional, see below


class Student(db.Model):
    __tablename__ = "students"

    __table_args__ = (
        db.UniqueConstraint(
            "school_id",
            "admission_no",
            name="uq_school_admission_no"
        ),
    )

    id = db.Column(db.Integer, primary_key=True)

    # 🔥 MOST IMPORTANT
    school_id = db.Column(
        db.Integer,
        db.ForeignKey("schools.id"),
        nullable=False
    )

    

    # ===== ADMISSION =====
    admission_no = db.Column(db.String(50), nullable=False)

    # Basic
    first_name = db.Column(db.String(100))
    middle_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    gender = db.Column(db.String(10))
    dob = db.Column(db.Date)
    religion = db.Column(db.String(50))
    caste = db.Column(db.String(50))
    blood_group = db.Column(db.String(100))

    # Guardian (Optional)
    guardian_name = db.Column(db.String(100))
    guardian_relation = db.Column(db.String(50))
    guardian_mobile = db.Column(db.String(15))
    guardian_address = db.Column(db.Text)

    # Address
    present_address = db.Column(db.Text)
    permanent_address = db.Column(db.Text)

    # Govt
    aadhaar = db.Column(db.String(20))
    pen_no = db.Column(db.String(50))

    # Academic
    session = db.Column(db.String(20))
    student_class = db.Column(db.String(20))
    section = db.Column(db.String(10))

    # Parents
    father_name = db.Column(db.String(100))
    father_mobile = db.Column(db.String(15))
    father_aadhaar = db.Column(db.String(20))
    father_email = db.Column(db.String(120), nullable=False)
    
    mother_email = db.Column(db.String(120), nullable=False)
    mother_name = db.Column(db.String(100))
    mother_mobile = db.Column(db.String(15))
    mother_aadhaar = db.Column(db.String(20))

    # ===== TRANSPORT =====
    transport_required = db.Column(db.Boolean, default=False)
    transport_route = db.Column(db.String(100))
    pickup_point = db.Column(db.String(100))

    # ===== HOSTEL =====
    hostel_required = db.Column(db.Boolean, default=False)
    hostel_block = db.Column(db.String(50))
    hostel_room = db.Column(db.String(20))

    # Files
    student_photo = db.Column(db.String(200))
    father_photo = db.Column(db.String(200))
    mother_photo = db.Column(db.String(200))

    dob_certificate = db.Column(db.String(200))
    aadhaar_doc = db.Column(db.String(200))
    tc = db.Column(db.String(200))
    marksheet = db.Column(db.String(200))

    created_at = db.Column(db.Date, default=date.today)


    # ===============================
    # RELATIONSHIP (ADD THIS)
    # ===============================
    fees = db.relationship(
        'StudentFeeLedger',
        backref='student',
        cascade="all, delete",
        passive_deletes=True
    )

    discounts = db.relationship(
        'FeeDiscount',
        backref='student',
        cascade="all, delete",
        passive_deletes=True
    )

    subject_allocations = db.relationship(
    "StudentSubject",
    backref="student",
    lazy=True
)