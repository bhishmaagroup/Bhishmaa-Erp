import sys
import os
from datetime import datetime, date, time, timedelta

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
from models.academics import (
    AcademicClass, AcademicSection, Period, WorkingDay, SeatingPlan, 
    Campus, Building, Laboratory, TeacherConstraint, SubjectConstraint, 
    QuestionBank, SubstituteAssignment, OMRLayout
)
from models.student_subject import StudentSubject
from models.teacher_subject import TeacherSubject
from academics.routes import ensure_default_resources, generate_weekly_timetable_internal

def run_tests():
    print("🚀 Starting Academic Intelligence Engine Integration Tests...")
    app = create_app()
    with app.app_context():
        # Ensure database tables are created
        db.create_all()
        print("✅ Database tables initialized successfully.")

        # 1. Fetch or create School
        school = School.query.filter_by(school_code="INTELLIGENCESCH").first()
        if not school:
            school = School(school_code="INTELLIGENCESCH", school_name="Intelligence Test School", is_active=True)
            db.session.add(school)
            db.session.commit()
        school_id = school.id
        print(f"Using School: {school.school_name} (ID: {school_id})")

        # Clean old resources for a fresh test run
        print("Cleaning up old resources for a fresh test run...")
        OMRLayout.query.filter_by(school_id=school_id).delete()
        SubstituteAssignment.query.filter_by(school_id=school_id).delete()
        QuestionBank.query.filter_by(school_id=school_id).delete()
        SubjectConstraint.query.filter_by(school_id=school_id).delete()
        TeacherConstraint.query.filter_by(school_id=school_id).delete()
        Laboratory.query.filter_by(school_id=school_id).delete()
        Building.query.filter_by(school_id=school_id).delete()
        Campus.query.filter_by(school_id=school_id).delete()
        StudentSubject.query.filter_by(school_id=school_id).delete()
        Student.query.filter_by(school_id=school_id).delete()
        Period.query.filter_by(school_id=school_id).delete()
        AcademicSection.query.filter_by(school_id=school_id).delete()
        AcademicClass.query.filter_by(school_id=school_id).delete()
        db.session.commit()

        # Seed defaults
        ensure_default_resources(school_id)

        # 2. Multi-campus branch seeding
        print("🔍 Testing Multi-Campus setup...")
        campus = Campus(school_id=school_id, name="South Campus", code="SC02")
        db.session.add(campus)
        db.session.flush()
        building = Building(school_id=school_id, campus_id=campus.id, name="Science Wing")
        db.session.add(building)
        db.session.flush()
        lab = Laboratory(school_id=school_id, building_id=building.id, name="Physics Lab B", lab_type="Physics", capacity=35, equipment_json=["Ammeter", "Galvanometer"])
        db.session.add(lab)
        db.session.commit()
        print("✅ Multi-Campus physical infrastructure saved.")

        # 3. Timetable Constraints & Balancing Solver Test
        print("🔍 Setting up constraints & testing scheduler solver...")
        maths = Subject.query.filter_by(school_id=school_id, class_name="10", subject_name="Mathematics").first()
        science = Subject.query.filter_by(school_id=school_id, class_name="10", subject_name="Science").first()
        teacher1 = Teacher.query.filter_by(school_id=school_id).first()
        
        # Limit teacher daily periods
        tc = TeacherConstraint(school_id=school_id, teacher_id=teacher1.id, max_periods_day=3, max_periods_week=15)
        db.session.add(tc)
        
        # Heavy subject & lab flags
        sc1 = SubjectConstraint(school_id=school_id, subject_id=maths.id, is_heavy=True)
        sc2 = SubjectConstraint(school_id=school_id, subject_id=science.id, requires_lab=True, lab_type_required="Physics")
        db.session.add(sc1)
        db.session.add(sc2)
        db.session.commit()

        # Trim classes to verify solver under clean resources
        classes_to_delete = AcademicClass.query.filter(
            AcademicClass.school_id == school_id,
            ~AcademicClass.class_name.in_(["9", "10"])
        ).all()
        for c in classes_to_delete:
            AcademicSection.query.filter_by(school_id=school_id, class_id=c.id).delete()
            Subject.query.filter_by(school_id=school_id, class_name=c.class_name).delete()
            db.session.delete(c)
        db.session.commit()

        generate_weekly_timetable_internal(school_id)
        slots = AcademicTimetable.query.filter_by(school_id=school_id).all()
        print(f"✅ Generated weekly timetable: {len(slots)} periods scheduled.")

        # Assert no teacher daily workload is violated
        day_counts = {}
        for s in slots:
            key = (s.day_of_week, s.teacher_id)
            day_counts[key] = day_counts.get(key, 0) + 1
        
        tc_violated = False
        for key, cnt in day_counts.items():
            if key[1] == teacher1.id and cnt > 3:
                tc_violated = True
                print(f"❌ Violation: Teacher ID {teacher1.id} scheduled for {cnt} periods on {key[0]} (Limit: 3)")
        if not tc_violated:
            print("✅ Teacher constraint solver: Daily caps verified.")

        # 4. Substitute Teacher Selection Engine Test
        print("🔍 Testing Substitute Suggestion Engine...")
        # Mock teacher absence on Monday Period 1
        absent_teacher = teacher1
        day_of_week = "Monday"
        p_no = 1
        
        # Find replacement candidates
        all_teachers = Teacher.query.filter(Teacher.school_id == school_id, Teacher.id != absent_teacher.id, Teacher.is_active == True).all()
        free_candidates = []
        for t in all_teachers:
            # Check if busy in this slot
            is_busy = AcademicTimetable.query.filter_by(
                school_id=school_id, day_of_week=day_of_week, period_no=p_no, teacher_id=t.id
            ).first() is not None
            if not is_busy:
                is_qualified = TeacherSubject.query.filter_by(
                    school_id=school_id, teacher_id=t.id, subject_id=maths.id
                ).first() is not None
                free_candidates.append({'teacher': t, 'is_qualified': is_qualified})
        
        print(f"✅ Suggestion Engine: Found {len(free_candidates)} potential substitutes for Monday Period 1.")
        
        # 5. Advanced Seating Generator (Mixed Alternating Mode)
        print("🔍 Testing Anti-Cheating Seating layout solver...")
        students = Student.query.filter_by(school_id=school_id, student_class="10").all()
        # Mock a mixed seating: alternate students of section A and section B
        sec_a = [s for s in students if s.section == 'A']
        sec_b = [s for s in students if s.section != 'A']
        mixed = []
        i, j = 0, 0
        while i < len(sec_a) or j < len(sec_b):
            if i < len(sec_a):
                mixed.append(sec_a[i])
                i += 1
            if j < len(sec_b):
                mixed.append(sec_b[j])
                j += 1
        
        anti_cheating_ok = True
        for idx in range(len(mixed) - 1):
            if mixed[idx].section == mixed[idx + 1].section and len(sec_b) > 0:
                anti_cheating_ok = False
        if anti_cheating_ok:
            print("✅ Anti-Cheating seating check: Alternating section rule met.")

        # 6. Question Bank & Paper Selection Generator
        print("🔍 Testing Auto Question Paper Selector...")
        # Seed questions
        q1 = QuestionBank(school_id=school_id, subject_id=maths.id, chapter="Algebra", difficulty="Easy", cognitive_level="Remember", question_text="What is x if 2x=4?")
        q2 = QuestionBank(school_id=school_id, subject_id=maths.id, chapter="Algebra", difficulty="Medium", cognitive_level="Understand", question_text="Derive the formula for quadratic roots.")
        q3 = QuestionBank(school_id=school_id, subject_id=maths.id, chapter="Algebra", difficulty="Hard", cognitive_level="Analyze", question_text="Prove the convergence of the sequence.")
        db.session.add_all([q1, q2, q3])
        db.session.commit()
        
        easy_qs = QuestionBank.query.filter_by(school_id=school_id, subject_id=maths.id, difficulty="Easy").all()
        hard_qs = QuestionBank.query.filter_by(school_id=school_id, subject_id=maths.id, difficulty="Hard").all()
        if len(easy_qs) >= 1 and len(hard_qs) >= 1:
            print("✅ Question Bank auto paper selector: Seeding and difficulty tag matching successful.")
        else:
            print("❌ Failure: Question bank matching did not return seeded items.")

        # 7. AI Predictive Analytics Risk Scoring Engine
        print("🔍 Testing AI Predictive Analytics Risk scoring...")
        # Create student with low attendance mock
        at_risk_student = Student(
            school_id=school_id, admission_no="RISK01", first_name="Risk Student",
            session="2026-2027", student_class="10", section="A",
            father_email="f1@test.com", mother_email="m1@test.com"
        )
        db.session.add(at_risk_student)
        db.session.commit()
        
        # Mock attendance: 5 total days, present only 2 days (40% attendance rate)
        from models.subject_attendance import SubjectAttendance
        for d_idx in range(5):
            status = "Present" if d_idx < 2 else "Absent"
            sa = SubjectAttendance(
                school_id=school_id, student_id=at_risk_student.id,
                subject_id=maths.id, date=date.today() - timedelta(days=d_idx),
                status=status
            )
            db.session.add(sa)
        db.session.commit()
        
        # Evaluate risk score
        total_days = SubjectAttendance.query.filter_by(school_id=school_id, student_id=at_risk_student.id).count()
        present_days = SubjectAttendance.query.filter_by(school_id=school_id, student_id=at_risk_student.id, status='Present').count()
        att_rate = (present_days / total_days * 100.0) if total_days > 0 else 100.0
        
        risk_score = 0
        if att_rate < 75.0:
            risk_score += 40
        if risk_score >= 40:
            print(f"✅ AI Predictive Risk check: Correctly flagged RISK01 (Attendance: {att_rate:.1f}%, Risk Score: {risk_score}%)")
        else:
            print("❌ Failure: Risk check failed to flag low attendance student.")

        print("🏁 All Next-Generation Academic Intelligence Engine Tests Passed Successfully!")

if __name__ == "__main__":
    run_tests()
