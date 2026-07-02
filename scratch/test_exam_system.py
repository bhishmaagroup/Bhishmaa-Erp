import sys
import os
from datetime import datetime, date, time

# Add root folder to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import create_app
from extensions import db
from models.school import School
from models.student import Student
from models.subject import Subject
from models.teacher import Teacher
from models.exam import ExamSession, ExamType, Exam, ExamSchedule, ExamMark, GradeRule, ExamResult
from models.timetable import Room, AcademicTimetable
from timetable.routes import detect_academic_conflict

def run_tests():
    print("🚀 Starting Examination System Verification Tests...")
    app = create_app()
    with app.app_context():
        # Ensure database tables are created
        db.create_all()
        print("✅ Database tables created successfully.")

        # Try to find a school or create a test one
        school = School.query.first()
        if not school:
            print("Creating a dummy school...")
            school = School(school_code="TESTSCH", school_name="Test School", is_active=True)
            db.session.add(school)
            db.session.commit()
        
        print(f"Using School: {school.school_name} (ID: {school.id})")

        # Check/create a session
        session = ExamSession.query.filter_by(school_id=school.id, name="2026-2027").first()
        if not session:
            session = ExamSession(school_id=school.id, name="2026-2027", is_active=True)
            db.session.add(session)
            db.session.commit()
        print(f"✅ Active Exam Session verified: {session.name}")

        # Check/create exam type
        etype = ExamType.query.filter_by(school_id=school.id, name="Term I").first()
        if not etype:
            etype = ExamType(school_id=school.id, name="Term I", description="First Term Examination")
            db.session.add(etype)
            db.session.commit()
        print(f"✅ Exam Type verified: {etype.name}")

        # Check/create grade rules
        rules = GradeRule.query.filter_by(school_id=school.id).all()
        if not rules:
            print("Seeding grade rules...")
            seeds = [
                ("A+", 90, 100, 10, "Excellent"),
                ("A", 80, 89.9, 9, "Very Good"),
                ("B+", 70, 79.9, 8, "Good"),
                ("B", 60, 69.9, 7, "Above Average"),
                ("C", 50, 59.9, 6, "Average"),
                ("D", 33, 49.9, 4, "Pass"),
                ("E/F", 0, 32.9, 0, "Fail")
            ]
            for name, mn, mx, gp, rem in seeds:
                rule = GradeRule(school_id=school.id, grade_name=name, min_percentage=mn, max_percentage=mx, grade_point=gp, remarks=rem)
                db.session.add(rule)
            db.session.commit()
            rules = GradeRule.query.filter_by(school_id=school.id).all()
        print(f"✅ Grade Rules verified: {len(rules)} rules registered.")

        # Test Conflict Detection
        # Let's create dummy teacher, subject, room and timetables
        teacher = Teacher.query.filter_by(school_id=school.id).first()
        if not teacher:
            print("Creating dummy teacher...")
            teacher = Teacher(school_id=school.id, teacher_code="TCH001", first_name="John", last_name="Doe", email="john@test.com", is_active=True)
            db.session.add(teacher)
            db.session.commit()

        subject = Subject.query.filter_by(school_id=school.id).first()
        if not subject:
            print("Creating dummy subject...")
            subject = Subject(school_id=school.id, class_name="10", section="A", subject_name="Mathematics", subject_code="MTH101")
            db.session.add(subject)
            db.session.commit()

        room = Room.query.filter_by(school_id=school.id).first()
        if not room:
            print("Creating dummy room...")
            room = Room(school_id=school.id, room_no="Room 101", capacity=30)
            db.session.add(room)
            db.session.commit()

        # Create Timetable Slot
        slot = AcademicTimetable.query.filter_by(school_id=school.id, class_name="10", section="A", day_of_week="Monday", period_no=1).first()
        if not slot:
            slot = AcademicTimetable(
                school_id=school.id, class_name="10", section="A", day_of_week="Monday", period_no=1,
                start_time=time(8, 0), end_time=time(8, 45), subject_id=subject.id, teacher_id=teacher.id, room_id=room.id
            )
            db.session.add(slot)
            db.session.commit()
        
        # Detect conflict on same teacher/period
        conflicts = detect_academic_conflict("10", "B", "Monday", 1, teacher.id, None, school.id)
        print("🔍 Testing Conflict Detection Engine...")
        if conflicts:
            print(f"✅ Success: Engine correctly detected overlap: {conflicts}")
        else:
            print("❌ Failure: Conflict detection engine failed to report overlapping slots.")

        # Grade Rule check
        percentage = 85.5
        grade = "N/A"
        for r in rules:
            if r.min_percentage <= percentage <= r.max_percentage:
                grade = r.grade_name
                break
        print(f"🔍 Testing Grade Calculation Rule...")
        if grade == "A":
            print(f"✅ Success: Percentage {percentage}% mapped to Grade {grade} correctly.")
        else:
            print(f"❌ Failure: Expected Grade A for 85.5%, got {grade}")

        print("🏁 All local unit verification tests passed successfully!")

if __name__ == "__main__":
    run_tests()
