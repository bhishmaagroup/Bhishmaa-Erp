from extensions import db
from datetime import datetime, time

class AcademicClass(db.Model):
    __tablename__ = 'academic_classes'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    class_name = db.Column(db.String(20), nullable=False)  # e.g., "10", "11"
    stream = db.Column(db.String(50))                      # e.g., "Science", "Commerce", "Arts"
    status = db.Column(db.Boolean, default=True)           # Active/Inactive

    sections = db.relationship('AcademicSection', backref='class_ref', lazy=True, cascade="all, delete-orphan")

class AcademicSection(db.Model):
    __tablename__ = 'academic_sections'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    class_id = db.Column(db.Integer, db.ForeignKey('academic_classes.id'), nullable=False)
    section_name = db.Column(db.String(10), nullable=False)  # e.g., "A", "B"
    class_teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id')) # Link to Teacher
    capacity = db.Column(db.Integer, default=40)
    academic_year = db.Column(db.String(20))                 # e.g., "2026-2027"

    class_teacher = db.relationship('Teacher', backref='assigned_sections_ref', lazy=True)

class Period(db.Model):
    __tablename__ = 'periods'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    period_name = db.Column(db.String(50), nullable=False)  # e.g., "Period 1", "Lunch Break"
    period_no = db.Column(db.Integer, nullable=False)       # 1, 2, 3
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    is_break = db.Column(db.Boolean, default=False)         # Toggles whether it is break time

class WorkingDay(db.Model):
    __tablename__ = 'working_days'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    day_name = db.Column(db.String(20), nullable=False)     # e.g., "Monday", "Tuesday"
    is_working = db.Column(db.Boolean, default=True)

class ExamGroup(db.Model):
    __tablename__ = 'exam_groups'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)        # e.g., "Unit Tests", "Term Examinations"
    description = db.Column(db.Text)

    exams = db.relationship('Exam', backref='group_ref', lazy=True)

class SeatingPlan(db.Model):
    __tablename__ = 'seating_plans'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    exam_id = db.Column(db.Integer, db.ForeignKey('exams.id'), nullable=False)
    exam_schedule_id = db.Column(db.Integer, db.ForeignKey('exam_schedules.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False)
    seat_no = db.Column(db.String(20), nullable=False)       # e.g., "Row 1, Seat 5"

    exam = db.relationship('Exam', backref='seating_plans_ref', lazy=True)
    schedule = db.relationship('ExamSchedule', backref='seating_plans_ref', lazy=True)
    room = db.relationship('Room', backref='seating_plans_ref', lazy=True)
    student = db.relationship('Student', backref='seating_plans_ref', lazy=True)

class AcademicsAuditLog(db.Model):
    __tablename__ = 'academics_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    action = db.Column(db.String(100), nullable=False)      # e.g., "Marks Updated", "Timetable Slot Created"
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='academics_audit_logs_ref', lazy=True)

class AcademicPlannerSetting(db.Model):
    __tablename__ = 'academic_planner_settings'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    academic_year = db.Column(db.String(20), nullable=False)
    working_days = db.Column(db.String(100), default="Monday,Tuesday,Wednesday,Thursday,Friday,Saturday")
    start_time = db.Column(db.Time, default=time(8, 0))
    period_duration = db.Column(db.Integer, default=45) # in minutes
    break_duration = db.Column(db.Integer, default=15) # in minutes
    lunch_break_after_period = db.Column(db.Integer, default=3) # period index
    max_teacher_workload = db.Column(db.Integer, default=5) # max periods per day
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class SubjectWorkload(db.Model):
    __tablename__ = 'subject_workloads'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    class_name = db.Column(db.String(20), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    periods_per_week = db.Column(db.Integer, default=5)

    subject = db.relationship('Subject', backref='workloads_ref', lazy=True)


class Campus(db.Model):
    __tablename__ = 'campuses'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    code = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Building(db.Model):
    __tablename__ = 'buildings'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    campus_id = db.Column(db.Integer, db.ForeignKey('campuses.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    
    campus = db.relationship('Campus', backref='buildings_ref', lazy=True)


class Laboratory(db.Model):
    __tablename__ = 'laboratories'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    building_id = db.Column(db.Integer, db.ForeignKey('buildings.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    lab_type = db.Column(db.String(50), default="General") # Computer, Physics, Chemistry, Biology
    equipment_json = db.Column(db.JSON) # JSON list/dict of equipment
    capacity = db.Column(db.Integer, default=30)
    
    building = db.relationship('Building', backref='laboratories_ref', lazy=True)


class AcademicYear(db.Model):
    __tablename__ = 'academic_years'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    name = db.Column(db.String(20), nullable=False) # e.g. "2026-2027"
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)


class AcademicTerm(db.Model):
    __tablename__ = 'academic_terms'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    academic_year_id = db.Column(db.Integer, db.ForeignKey('academic_years.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False) # e.g. "Term I", "Semester 1"
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    
    academic_year = db.relationship('AcademicYear', backref='terms_ref', lazy=True)


class Semester(db.Model):
    __tablename__ = 'semesters'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    academic_term_id = db.Column(db.Integer, db.ForeignKey('academic_terms.id'), nullable=False)
    name = db.Column(db.String(50), nullable=False) # e.g. "Semester 1"
    
    term = db.relationship('AcademicTerm', backref='semesters_ref', lazy=True)


class SubjectGroup(db.Model):
    __tablename__ = 'subject_groups'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False) # e.g. "Science Group"
    class_name = db.Column(db.String(20))
    subject_ids = db.Column(db.String(255)) # Comma-separated subject IDs


class TeacherConstraint(db.Model):
    __tablename__ = 'teacher_constraints'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    max_periods_day = db.Column(db.Integer, default=5)
    max_periods_week = db.Column(db.Integer, default=25)
    preferred_slots = db.Column(db.Text) # Comma-separated "Day:Period"
    unavailable_slots = db.Column(db.Text) # Comma-separated "Day:Period"
    
    teacher = db.relationship('Teacher', backref='constraints_ref', lazy=True)


class SubjectConstraint(db.Model):
    __tablename__ = 'subject_constraints'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    is_heavy = db.Column(db.Boolean, default=False)
    requires_lab = db.Column(db.Boolean, default=False)
    lab_type_required = db.Column(db.String(50))
    
    subject = db.relationship('Subject', backref='constraints_ref', lazy=True)


class QuestionBank(db.Model):
    __tablename__ = 'question_bank'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    chapter = db.Column(db.String(100), nullable=False)
    topic = db.Column(db.String(100))
    difficulty = db.Column(db.String(20), default="Medium") # Easy, Medium, Hard
    cognitive_level = db.Column(db.String(50), default="Remember") # Remember, Understand, Apply, Analyze
    question_text = db.Column(db.Text, nullable=False)
    options_json = db.Column(db.JSON) # List of options
    correct_answer = db.Column(db.Text)
    
    subject = db.relationship('Subject', backref='questions_ref', lazy=True)


class SubstituteAssignment(db.Model):
    __tablename__ = 'substitute_assignments'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    period_id = db.Column(db.Integer, db.ForeignKey('periods.id'), nullable=False)
    absent_teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    substitute_teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    reason = db.Column(db.String(200))
    status = db.Column(db.String(20), default="Assigned") # Assigned, Completed
    
    period = db.relationship('Period', backref='substitutes_ref', lazy=True)
    absent_teacher = db.relationship('Teacher', foreign_keys=[absent_teacher_id], backref='absent_substitutes_ref', lazy=True)
    substitute_teacher = db.relationship('Teacher', foreign_keys=[substitute_teacher_id], backref='assigned_substitutes_ref', lazy=True)


class OMRLayout(db.Model):
    __tablename__ = 'omr_layouts'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    total_questions = db.Column(db.Integer, default=50)
    answer_key_json = db.Column(db.JSON) # Dict e.g. {"1": "A", "2": "C"}
