from extensions import db
from datetime import datetime

class ExamSession(db.Model):
    __tablename__ = 'exam_sessions'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False)  # e.g., "2026-2027"
    is_active = db.Column(db.Boolean, default=True)

    exams = db.relationship('Exam', backref='session_ref', lazy=True, cascade="all, delete-orphan")

class ExamType(db.Model):
    __tablename__ = 'exam_types'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)  # e.g., "Half-Yearly", "Finals"
    description = db.Column(db.Text)

    exams = db.relationship('Exam', backref='type_ref', lazy=True, cascade="all, delete-orphan")

class Exam(db.Model):
    __tablename__ = 'exams'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('exam_sessions.id'), nullable=False)
    exam_type_id = db.Column(db.Integer, db.ForeignKey('exam_types.id'), nullable=False)
    exam_group_id = db.Column(db.Integer, db.ForeignKey('exam_groups.id', ondelete='SET NULL'), nullable=True) # Linked Group
    
    name = db.Column(db.String(100), nullable=False)  # e.g., "Class 10 Final Exams"
    class_name = db.Column(db.String(20), nullable=False)  # e.g., "10"
    section = db.Column(db.String(10))  # Optional: specific section like "A", or null for all sections
    
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_published = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(20), default="Draft") # Draft, Published, Locked
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    schedules = db.relationship('ExamSchedule', backref='exam_ref', lazy=True, cascade="all, delete-orphan")
    results = db.relationship('ExamResult', backref='exam_ref', lazy=True, cascade="all, delete-orphan")

class ExamSchedule(db.Model):
    __tablename__ = 'exam_schedules'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    section = db.Column(db.String(10))  # Section-specific schedule (invigilator and room per section)
    
    date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    room_no = db.Column(db.String(50))
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'))  # Invigilator

    # Split Marks Config
    max_marks = db.Column(db.Float, nullable=False, default=100.0) # Total Sum
    passing_marks = db.Column(db.Float, nullable=False, default=33.0)

    max_theory = db.Column(db.Float, default=100.0)
    pass_theory = db.Column(db.Float, default=33.0)

    max_practical = db.Column(db.Float, default=0.0)
    pass_practical = db.Column(db.Float, default=0.0)

    max_viva = db.Column(db.Float, default=0.0)
    pass_viva = db.Column(db.Float, default=0.0)

    max_internal = db.Column(db.Float, default=0.0)
    pass_internal = db.Column(db.Float, default=0.0)

    marks = db.relationship('ExamMark', backref='schedule_ref', lazy=True, cascade="all, delete-orphan")
    attendance_records = db.relationship('ExamAttendance', backref='schedule_ref', lazy=True, cascade="all, delete-orphan")
    subject = db.relationship('Subject', backref='exam_schedules_ref', lazy=True)

class ExamAttendance(db.Model):
    __tablename__ = 'exam_attendances'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    exam_schedule_id = db.Column(db.Integer, db.ForeignKey('exam_schedules.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    status = db.Column(db.String(10), default="P")  # P: Present, A: Absent, M: Medical, U: Unfair Means (UFM)
    remarks = db.Column(db.String(200))

    student = db.relationship('Student', backref='exam_attendance_ref', lazy=True)

class ExamMark(db.Model):
    __tablename__ = 'exam_marks'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    exam_schedule_id = db.Column(db.Integer, db.ForeignKey('exam_schedules.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    
    # Marks Split Obtained
    theory_obtained = db.Column(db.Float, default=0.0)
    practical_obtained = db.Column(db.Float, default=0.0)
    viva_obtained = db.Column(db.Float, default=0.0)
    internal_obtained = db.Column(db.Float, default=0.0)
    grace_marks = db.Column(db.Float, default=0.0)

    marks_obtained = db.Column(db.Float, default=0.0)  # Theory + Practical + Viva + Internal + Grace
    is_absent = db.Column(db.Boolean, default=False)
    remarks = db.Column(db.String(200))
    
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'))  # Evaluator
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    student = db.relationship('Student', backref='exam_marks_ref', lazy=True)
    subject = db.relationship('Subject', backref='exam_marks_ref', lazy=True)

class GradeRule(db.Model):
    __tablename__ = 'grade_rules'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    grade_name = db.Column(db.String(20), nullable=False)  # e.g., "A+", "A"
    min_percentage = db.Column(db.Float, nullable=False)  # e.g., 90.0
    max_percentage = db.Column(db.Float, nullable=False)  # e.g., 100.0
    grade_point = db.Column(db.Float, default=0.0)  # e.g., 10.0
    remarks = db.Column(db.String(200))

class ExamResult(db.Model):
    __tablename__ = 'exam_results'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    
    total_marks_obtained = db.Column(db.Float, default=0.0)
    total_max_marks = db.Column(db.Float, default=0.0)
    percentage = db.Column(db.Float, default=0.0)
    grade = db.Column(db.String(20))
    
    rank = db.Column(db.Integer)          # Class Rank
    section_rank = db.Column(db.Integer)  # Section Rank
    school_rank = db.Column(db.Integer)   # School-wide Rank
    
    gpa = db.Column(db.Float, default=0.0)
    cgpa = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default="Pass")  # Pass / Fail
    is_published = db.Column(db.Boolean, default=False)
    processed_at = db.Column(db.DateTime, default=datetime.utcnow)

    student = db.relationship('Student', backref='exam_results_ref', lazy=True)

class ExamAuditLog(db.Model):
    __tablename__ = 'exam_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='exam_audit_logs_ref', lazy=True)
