from extensions import db
from datetime import datetime

class Room(db.Model):
    __tablename__ = 'rooms'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    room_no = db.Column(db.String(50), nullable=False)  # e.g., "Room 101"
    building = db.Column(db.String(100))  # e.g., "Main Block"
    capacity = db.Column(db.Integer, default=40)

    # Relationship to academic timetables
    timetables = db.relationship('AcademicTimetable', backref='room_ref', lazy=True, cascade="all, delete-orphan")

class AcademicTimetable(db.Model):
    __tablename__ = 'academic_timetables'

    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    class_name = db.Column(db.String(20), nullable=False)  # e.g., "10"
    section = db.Column(db.String(10), nullable=False)  # e.g., "A"
    
    day_of_week = db.Column(db.String(20), nullable=False)  # e.g., "Monday", "Tuesday"
    period_no = db.Column(db.Integer, nullable=False)  # e.g., 1, 2, 3
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    
    subject_id = db.Column(db.Integer, db.ForeignKey('subject.id'), nullable=False)
    teacher_id = db.Column(db.Integer, db.ForeignKey('teacher.id'), nullable=False)
    room_id = db.Column(db.Integer, db.ForeignKey('rooms.id'))  # Optional room allocation

    subject = db.relationship('Subject', backref='academic_timetables_ref', lazy=True)
    teacher = db.relationship('Teacher', backref='academic_timetables_ref', lazy=True)
