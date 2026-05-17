from datetime import date
from extensions import db

# ===============================
# CLASS WISE FEE STRUCTURE
# ===============================
class FeeStructure(db.Model):
    __tablename__ = "fee_structure"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=False)

    student_class = db.Column(db.String(20), nullable=False)

    # ===== ONE TIME =====
    registration_fee = db.Column(db.Integer, default=0)
    admission_fee = db.Column(db.Integer, default=0)
    book_fee = db.Column(db.Integer, default=0)
    dress_fee = db.Column(db.Integer, default=0)

    # ===== MONTHLY =====
    tuition_fee = db.Column(db.Integer, default=0)
    transport_fee = db.Column(db.Integer, default=0)
    hostel_fee = db.Column(db.Integer, default=0)

    # ===== OCCASIONAL =====
    half_yearly_exam_fee = db.Column(db.Integer, default=0)
    annual_exam_fee = db.Column(db.Integer, default=0)
    exam_partial_allowed = db.Column(db.Boolean, default=False)
    activity_fee = db.Column(db.Integer, default=0)
    misc_fee = db.Column(db.Integer, default=0)

    # ===== FEE FINE =====
    due_day = db.Column(db.Integer, default=10)
    fine_per_day = db.Column(db.Integer, default=10)
    fine_max = db.Column(db.Integer, default=300)


# ===============================
# TRANSPORT ROUTE FEE
# ===============================
class TransportFee(db.Model):
    __tablename__ = "transport_fee"

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, nullable=False)

    route_name = db.Column(db.String(100), nullable=False)
    monthly_amount = db.Column(db.Integer, nullable=False)


# ===============================
# STUDENT FEE LEDGER
# ===============================
class StudentFeeLedger(db.Model):
    __tablename__ = "student_fee_ledger"

    id = db.Column(db.Integer, primary_key=True)

    # 🔥 FIXED (FOREIGN KEY + CASCADE)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey('students.id', ondelete='CASCADE'),
        nullable=False
    )

    school_id = db.Column(db.Integer, nullable=False)

    month = db.Column(db.String(20))
    fee_type = db.Column(db.String(50))  # admission / monthly / late

    total_amount = db.Column(db.Integer)
    paid_amount = db.Column(db.Integer)
    balance_amount = db.Column(db.Integer)
    receipt_no = db.Column(db.String(30), index=True)

    created_at = db.Column(db.Date, default=date.today)


# ===============================
# FEE DISCOUNT
# ===============================
class FeeDiscount(db.Model):
    __tablename__ = "fee_discount"

    id = db.Column(db.Integer, primary_key=True)

    # 🔥 FIXED (FOREIGN KEY + CASCADE)
    student_id = db.Column(
        db.Integer,
        db.ForeignKey('students.id', ondelete='CASCADE'),
        nullable=False
    )

    reason = db.Column(db.String(100))
    amount = db.Column(db.Integer, default=0)