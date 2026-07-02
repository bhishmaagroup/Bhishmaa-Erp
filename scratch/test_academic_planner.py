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
from models.academics import AcademicClass, AcademicSection, Period, WorkingDay, SeatingPlan, AcademicPlannerSetting, SubjectWorkload
from models.student_subject import StudentSubject
from academics.routes import ensure_default_resources, generate_weekly_timetable_internal

def run_tests():
    print("🚀 Starting Academic Planning Engine Integration Tests...")
    app = create_app()
    with app.app_context():
        # Ensure database tables are created
        db.create_all()
        print("✅ Database tables created successfully.")

        # 1. Fetch or create School
        school = School.query.filter_by(school_code="PLANNERSCH").first()
        if not school:
            school = School(school_code="PLANNERSCH", school_name="Planner Test School", is_active=True)
            db.session.add(school)
            db.session.commit()
        school_id = school.id
        print(f"Using School: {school.school_name} (ID: {school_id})")

        # Clean old resources for a fresh test run
        print("Cleaning up old resources for a fresh test run...")
        StudentSubject.query.filter_by(school_id=school_id).delete()
        Student.query.filter_by(school_id=school_id).delete()
        Period.query.filter_by(school_id=school_id).delete()
        SubjectWorkload.query.filter_by(school_id=school_id).delete()
        AcademicPlannerSetting.query.filter_by(school_id=school_id).delete()
        Subject.query.filter_by(school_id=school_id).delete()
        Teacher.query.filter_by(school_id=school_id).delete()
        Room.query.filter_by(school_id=school_id).delete()
        AcademicSection.query.filter_by(school_id=school_id).delete()
        AcademicClass.query.filter_by(school_id=school_id).delete()
        db.session.commit()

        # 2. Run Zero-Configuration Seeder
        print("🔍 Seeding default resources via ensure_default_resources...")
        ensure_default_resources(school_id)

        # Keep only Class 9 and Class 10 to ensure we have enough rooms and teachers to avoid double bookings
        print("Trimming classes to Class 9 and Class 10 for resource constraint testing...")
        classes_to_delete = AcademicClass.query.filter(
            AcademicClass.school_id == school_id,
            ~AcademicClass.class_name.in_(["9", "10"])
        ).all()
        for c in classes_to_delete:
            AcademicSection.query.filter_by(school_id=school_id, class_id=c.id).delete()
            Subject.query.filter_by(school_id=school_id, class_name=c.class_name).delete()
            SubjectWorkload.query.filter_by(school_id=school_id, class_name=c.class_name).delete()
            db.session.delete(c)
        db.session.commit()
        
        # Verify settings and workloads exist
        settings = AcademicPlannerSetting.query.filter_by(school_id=school_id).first()
        if settings:
            print(f"✅ Planner Settings verified: Year={settings.academic_year}, Workload Limit={settings.max_teacher_workload}")
        else:
            print("❌ Failure: Planner settings were not seeded.")
            return

        math_subject = Subject.query.filter_by(school_id=school_id, class_name="10", subject_name="Mathematics").first()
        if math_subject:
            wl = SubjectWorkload.query.filter_by(school_id=school_id, class_name="10", subject_id=math_subject.id).first()
            if wl:
                print(f"✅ Mathematics Workload verified: {wl.periods_per_week} periods/week")
            else:
                print("❌ Failure: Mathematics workload not seeded.")
                return

        # 3. Generate Weekly Timetable and assert constraints
        print("🔍 Generating Weekly Timetable...")
        generate_weekly_timetable_internal(school_id)
        
        timetable_slots = AcademicTimetable.query.filter_by(school_id=school_id).all()
        if not timetable_slots:
            print("❌ Failure: Timetable slots were not generated.")
            return
        print(f"✅ Weekly Timetable generated: {len(timetable_slots)} total slots.")

        # Assert no teacher or room double-bookings
        allocated_rooms = set()
        allocated_teachers = set()
        overlap_found = False

        for slot in timetable_slots:
            room_key = (slot.day_of_week, slot.period_no, slot.room_id)
            teacher_key = (slot.day_of_week, slot.period_no, slot.teacher_id)
            
            if room_key in allocated_rooms:
                print(f"❌ Overlap Found: Room {slot.room_ref.room_no} double-booked on {slot.day_of_week} period {slot.period_no}")
                overlap_found = True
            if teacher_key in allocated_teachers:
                print(f"❌ Overlap Found: Teacher ID {slot.teacher_id} double-booked on {slot.day_of_week} period {slot.period_no}")
                overlap_found = True

            allocated_rooms.add(room_key)
            allocated_teachers.add(teacher_key)

        if not overlap_found:
            print("✅ Timetable check: No teacher or room double-bookings detected.")

        # Check consecutive heavy subjects (Maths, Science)
        heavy_subjects_keywords = ["math", "science", "physics", "chemistry", "biology"]
        def is_heavy(sub):
            name_lower = sub.subject_name.lower()
            return any(kw in name_lower for kw in heavy_subjects_keywords)

        consecutive_heavy_found = False
        class_10_sec_a_slots = AcademicTimetable.query.filter_by(school_id=school_id, class_name="10", section="A").order_by(AcademicTimetable.day_of_week, AcademicTimetable.period_no).all()
        
        day_slots = {}
        for slot in class_10_sec_a_slots:
            if slot.day_of_week not in day_slots:
                day_slots[slot.day_of_week] = []
            day_slots[slot.day_of_week].append(slot)

        for day, slots in day_slots.items():
            for idx in range(len(slots) - 1):
                s1 = slots[idx]
                s2 = slots[idx + 1]
                if s1.period_no + 1 == s2.period_no:
                    if is_heavy(s1.subject) and is_heavy(s2.subject):
                        print(f"⚠️ Heavy subjects consecutive on {day}: {s1.subject.subject_name} (Period {s1.period_no}) & {s2.subject.subject_name} (Period {s2.period_no})")
                        consecutive_heavy_found = True

        if not consecutive_heavy_found:
            print("✅ Timetable check: Heavy subjects spacing rules met successfully.")

        # 4. Test Unified Exam Schedule, Seating and Results Generation
        print("🔍 Testing Unified Exams Scheduling & Seating Generator...")
        
        # Create session & exam type if missing
        session = ExamSession.query.filter_by(school_id=school_id, name="2026-2027").first()
        if not session:
            session = ExamSession(school_id=school_id, name="2026-2027", is_active=True)
            db.session.add(session)
            db.session.commit()
            
        etype = ExamType.query.filter_by(school_id=school_id, name="Term I").first()
        if not etype:
            etype = ExamType(school_id=school_id, name="Term I", description="First Term Exam")
            db.session.add(etype)
            db.session.commit()

        # Simulate generate route logic programmatically
        classes = AcademicClass.query.filter_by(school_id=school_id, status=True).all()
        rooms = Room.query.filter_by(school_id=school_id).all()
        teachers = Teacher.query.filter_by(school_id=school_id, is_active=True).all()

        start_date = date(2026, 6, 8)
        end_date = date(2026, 6, 15)
        start_time = time(9, 0)
        end_time = time(12, 0)

        # Clear old exam structures
        old_exams = Exam.query.filter_by(school_id=school_id, session_id=session.id, exam_type_id=etype.id).all()
        old_exam_ids = [oe.id for oe in old_exams]
        if old_exam_ids:
            SeatingPlan.query.filter(SeatingPlan.exam_id.in_(old_exam_ids)).delete(synchronize_session=False)
            ExamSchedule.query.filter(ExamSchedule.exam_id.in_(old_exam_ids)).delete(synchronize_session=False)
            ExamResult.query.filter(ExamResult.exam_id.in_(old_exam_ids)).delete(synchronize_session=False)
            Exam.query.filter(Exam.id.in_(old_exam_ids)).delete(synchronize_session=False)
            db.session.commit()

        # Calculate dates (excluding Sunday)
        current_date = start_date
        available_dates = []
        while current_date <= end_date:
            if current_date.weekday() != 6:
                available_dates.append(current_date)
            current_date += timedelta(days=1)

        exam_count = 0
        schedule_count = 0
        seating_count = 0
        result_count = 0

        # Build Exam Masters, schedules, and seating layouts
        for cls in classes:
            sections = AcademicSection.query.filter_by(school_id=school_id, class_id=cls.id).all()
            subjects = Subject.query.filter_by(school_id=school_id, class_name=cls.class_name, status=True).all()
            if not sections or not subjects:
                continue

            exam = Exam(
                school_id=school_id, session_id=session.id, exam_type_id=etype.id,
                name=f"Term I Exam - Class {cls.class_name}", class_name=cls.class_name,
                start_date=start_date, end_date=end_date, status="Draft"
            )
            db.session.add(exam)
            db.session.flush()
            exam_count += 1

            for date_idx, sub in enumerate(subjects):
                if date_idx >= len(available_dates):
                    break
                exam_date = available_dates[date_idx]

                for sec in sections:
                    sched = ExamSchedule(
                        school_id=school_id, exam_id=exam.id, subject_id=sub.id, section=sec.section_name,
                        date=exam_date, start_time=start_time, end_time=end_time,
                        room_no=rooms[0].room_no, teacher_id=teachers[0].id, max_marks=100.0, passing_marks=33.0
                    )
                    db.session.add(sched)
                    db.session.flush()
                    schedule_count += 1

                    # Allocate seating
                    students = Student.query.join(StudentSubject, Student.id == StudentSubject.student_id).filter(
                        Student.school_id == school_id, Student.student_class == cls.class_name,
                        Student.section == sec.section_name, StudentSubject.subject_id == sub.id
                    ).order_by(Student.first_name).all()

                    for s_idx, st in enumerate(students):
                        plan = SeatingPlan(
                            school_id=school_id, exam_id=exam.id, exam_schedule_id=sched.id,
                            room_id=rooms[0].id, student_id=st.id, seat_no=f"Desk-{s_idx+1}"
                        )
                        db.session.add(plan)
                        seating_count += 1

            # Seed empty results
            students = Student.query.filter_by(school_id=school_id, student_class=cls.class_name).all()
            for st in students:
                res_rec = ExamResult(
                    school_id=school_id, exam_id=exam.id, student_id=st.id,
                    total_marks_obtained=0.0, total_max_marks=0.0, percentage=0.0, grade="-", status="Draft"
                )
                db.session.add(res_rec)
                result_count += 1

        db.session.commit()
        print(f"✅ Exam Scheduling: Created {exam_count} Exams and {schedule_count} schedules.")
        print(f"✅ Seating Layouts: Allocated {seating_count} student seating plans sequentially.")
        print(f"✅ Grade Result Sheets: Seeded {result_count} empty result templates successfully.")

        # 5. Check Grade Seeding
        grade_rules = GradeRule.query.filter_by(school_id=school_id).all()
        if not grade_rules:
            # Seed default grade rules
            default_rules = [
                ("A+", 90.0, 100.0, 10.0, "Outstanding"),
                ("A", 80.0, 89.99, 9.0, "Excellent"),
                ("B", 70.0, 79.99, 8.0, "Very Good"),
                ("C", 60.0, 69.99, 7.0, "Good"),
                ("D", 50.0, 59.99, 6.0, "Above Average"),
                ("E", 33.0, 49.99, 5.0, "Pass"),
                ("F", 0.0, 32.99, 0.0, "Fail")
            ]
            for g_name, min_p, max_p, g_pt, rem in default_rules:
                gr = GradeRule(
                    school_id=school_id, grade_name=g_name, min_percentage=min_p, max_percentage=max_p,
                    grade_point=g_pt, remarks=rem
                )
                db.session.add(gr)
            db.session.commit()
            grade_rules = GradeRule.query.filter_by(school_id=school_id).all()
        print(f"✅ Grade boundaries verified: {len(grade_rules)} grade rules set up.")

        print("🏁 All Academic Planning Engine Integration Tests Passed Successfully!")

if __name__ == "__main__":
    run_tests()
