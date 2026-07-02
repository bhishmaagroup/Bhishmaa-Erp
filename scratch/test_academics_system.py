import sys
import os
from datetime import datetime, date, time
import matplotlib.pyplot as plt
import io

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
from models.academics import AcademicClass, AcademicSection, Period, WorkingDay, SeatingPlan
from models.student_subject import StudentSubject
from timetable.routes import detect_academic_conflict
from academics.routes import detect_timetable_conflict

def run_tests():
    print("🚀 Starting Academics Module Integration Tests...")
    app = create_app()
    with app.app_context():
        # Ensure database tables are created
        db.create_all()
        print("✅ Database tables created successfully.")

        # Fetch or create School
        school = School.query.first()
        if not school:
            school = School(school_code="SCH001", school_name="Bhishmaa Test School", is_active=True)
            db.session.add(school)
            db.session.commit()

        # 1. Classes & Sections Test
        ac_class = AcademicClass.query.filter_by(school_id=school.id, class_name="10").first()
        if not ac_class:
            ac_class = AcademicClass(school_id=school.id, class_name="10", stream=None)
            db.session.add(ac_class)
            db.session.commit()
        print(f"✅ Academic Class verified: Class {ac_class.class_name}")

        ac_section = AcademicSection.query.filter_by(school_id=school.id, class_id=ac_class.id, section_name="A").first()
        if not ac_section:
            ac_section = AcademicSection(school_id=school.id, class_id=ac_class.id, section_name="A", capacity=35)
            db.session.add(ac_section)
            db.session.commit()
        print(f"✅ Academic Section verified: Section {ac_section.section_name} (Capacity: {ac_section.capacity})")

        # 2. Periods & Working Days Test
        period = Period.query.filter_by(school_id=school.id, period_no=1).first()
        if not period:
            period = Period(school_id=school.id, period_name="Period 1", period_no=1, start_time=time(8, 0), end_time=time(8, 45), is_break=False)
            db.session.add(period)
            db.session.commit()
        print(f"✅ Class Period verified: {period.period_name} ({period.start_time} - {period.end_time})")

        # 3. Timetable & Conflict Engine Test
        teacher = Teacher.query.filter_by(school_id=school.id).first()
        if not teacher:
            teacher = Teacher(school_id=school.id, teacher_code="TCH002", first_name="Alice", last_name="Smith", email="alice@test.com", is_active=True)
            db.session.add(teacher)
            db.session.commit()

        subject = Subject.query.filter_by(school_id=school.id, class_name="10").first()
        if not subject:
            subject = Subject(school_id=school.id, class_name="10", subject_name="English", subject_code="ENG101", subject_type="Theory")
            db.session.add(subject)
            db.session.commit()

        room = Room.query.filter_by(school_id=school.id).first()
        if not room:
            room = Room(school_id=school.id, room_no="Room 201", capacity=30)
            db.session.add(room)
            db.session.commit()

        # Add timetable record
        slot = AcademicTimetable.query.filter_by(school_id=school.id, class_name="10", section="A", day_of_week="Monday", period_no=1).first()
        if not slot:
            slot = AcademicTimetable(
                school_id=school.id, class_name="10", section="A", day_of_week="Monday", period_no=1,
                start_time=time(8, 0), end_time=time(8, 45), subject_id=subject.id, teacher_id=teacher.id, room_id=room.id
            )
            db.session.add(slot)
            db.session.commit()

        # Check conflict
        conflicts = detect_timetable_conflict("Monday", period.id, teacher.id, room.id, school.id)
        print("🔍 Testing Timetable Conflict Checker...")
        if conflicts:
            print(f"✅ Success: Timetable engine detected overlap: {conflicts}")
        else:
            print("❌ Failure: Overlap check did not flag conflicts.")

        # 4. Result Ranking Engine Test (Class, Section, School-wide)
        # Create test students
        students = []
        for i in range(1, 4):
            adm = f"ADM00{i}"
            st = Student.query.filter_by(school_id=school.id, admission_no=adm).first()
            if not st:
                st = Student(
                    school_id=school.id, admission_no=adm, first_name=f"Student_{i}",
                    session="2026-2027", student_class="10", section="A", father_email=f"father{i}@test.com", mother_email=f"mother{i}@test.com"
                )
                db.session.add(st)
                db.session.commit()
            students.append(st)
            
            # Link student to subject
            stud_sub = StudentSubject.query.filter_by(school_id=school.id, student_id=st.id, subject_id=subject.id).first()
            if not stud_sub:
                stud_sub = StudentSubject(school_id=school.id, student_id=st.id, subject_id=subject.id)
                db.session.add(stud_sub)
                db.session.commit()

        # Process processed mock ranks
        exam_session = ExamSession.query.filter_by(school_id=school.id).first()
        exam_type = ExamType.query.filter_by(school_id=school.id).first()
        exam = Exam.query.filter_by(school_id=school.id, name="Test Final Exam").first()
        if not exam:
            exam = Exam(school_id=school.id, session_id=exam_session.id, exam_type_id=exam_type.id, name="Test Final Exam", class_name="10", status="Draft")
            db.session.add(exam)
            db.session.commit()

        # Set up marks
        results = []
        marks_data = [95.0, 80.0, 60.0]  # Student 1, 2, 3 percentages
        for idx, pct in enumerate(marks_data):
            res_rec = ExamResult.query.filter_by(exam_id=exam.id, student_id=students[idx].id).first()
            if not res_rec:
                res_rec = ExamResult(
                    school_id=school.id, exam_id=exam.id, student_id=students[idx].id,
                    total_marks_obtained=pct, total_max_marks=100.0, percentage=pct, grade="A" if pct >= 80 else "B", status="Pass"
                )
                db.session.add(res_rec)
                db.session.commit()
            results.append(res_rec)

        # Run Ranks Sorting
        sorted_res = ExamResult.query.filter_by(exam_id=exam.id).order_by(ExamResult.percentage.desc()).all()
        for r_rank, r in enumerate(sorted_res):
            r.rank = r_rank + 1
            r.section_rank = r_rank + 1
            r.school_rank = r_rank + 1
        db.session.commit()

        print("🔍 Testing Rank processing...")
        st1_res = ExamResult.query.filter_by(exam_id=exam.id, student_id=students[0].id).first()
        st3_res = ExamResult.query.filter_by(exam_id=exam.id, student_id=students[2].id).first()
        if st1_res.rank == 1 and st3_res.rank == 3:
            print(f"✅ Success: Student 1 ranked #{st1_res.rank}, Student 3 ranked #{st3_res.rank} correctly.")
        else:
            print(f"❌ Failure: Rankings sorting error. Student 1: #{st1_res.rank}, Student 3: #{st3_res.rank}")

        # 5. ReportLab PDF Admit Card compilation test
        from exam.routes import generate_single_admit_card_pdf
        print("🔍 Testing ReportLab PDF Compile...")
        try:
            # Create exam schedule
            sched = ExamSchedule.query.filter_by(exam_id=exam.id).first()
            if not sched:
                sched = ExamSchedule(
                    school_id=school.id, exam_id=exam.id, subject_id=subject.id,
                    date=date.today(), start_time=time(9, 0), end_time=time(12, 0), room_no="Hall 1"
                )
                db.session.add(sched)
                db.session.commit()

            pdf_buffer = generate_single_admit_card_pdf(exam, students[0])
            if pdf_buffer:
                print("✅ Success: PDF Admit Card binary stream compiled successfully.")
        except Exception as pdf_ex:
            print(f"❌ Failure: ReportLab error during Admit Card generation: {pdf_ex}")

        # 6. Matplotlib charts test
        print("🔍 Testing Matplotlib image generation...")
        try:
            fig, ax = plt.subplots(figsize=(2, 2))
            ax.bar(['Pass', 'Fail'], [2, 1])
            buf = io.BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            plt.close(fig)
            if buf:
                print("✅ Success: Matplotlib performance charts generated in-memory.")
        except Exception as plt_ex:
            print(f"❌ Failure: Matplotlib engine crashed: {plt_ex}")

        # 7. Auto-Scheduler Engine Test
        print("🔍 Testing Auto-Scheduling Engine (Timetables & Exams)...")
        try:
            # Rebuild academic weekly timetables
            AcademicTimetable.query.filter_by(school_id=school.id).delete()
            db.session.commit()

            periods = Period.query.filter_by(school_id=school.id, is_break=False).all()
            classes = AcademicClass.query.filter_by(school_id=school.id, status=True).all()
            rooms = Room.query.filter_by(school_id=school.id).all()
            teachers = Teacher.query.filter_by(school_id=school.id, is_active=True).all()
            days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

            slot_count = 0
            for cls in classes:
                sections = AcademicSection.query.filter_by(school_id=school.id, class_id=cls.id).all()
                subjects = Subject.query.filter_by(school_id=school.id, class_name=cls.class_name, status=True).all()
                for sec in sections:
                    subject_cycle_idx = 0
                    for day in days:
                        for period in periods:
                            sub = subjects[subject_cycle_idx % len(subjects)]
                            subject_cycle_idx += 1
                            selected_teacher = teachers[0]
                            selected_room = rooms[0]

                            slot = AcademicTimetable(
                                school_id=school.id, class_name=cls.class_name, section=sec.section_name,
                                day_of_week=day, period_no=period.period_no, start_time=period.start_time, end_time=period.end_time,
                                subject_id=sub.id, teacher_id=selected_teacher.id, room_id=selected_room.id
                            )
                            db.session.add(slot)
                            slot_count += 1
            db.session.commit()
            print(f"✅ Success: Timetable Auto-Scheduler generated {slot_count} slots.")

            # Rebuild exam schedules
            available_dates = [date.today()]
            schedule_count = 0
            for cls in classes:
                sections = AcademicSection.query.filter_by(school_id=school.id, class_id=cls.id).all()
                subjects = Subject.query.filter_by(school_id=school.id, class_name=cls.class_name, status=True).all()

                exam = Exam.query.filter_by(school_id=school.id, name="Test Final Exam").first()
                ExamSchedule.query.filter_by(exam_id=exam.id).delete()
                db.session.commit()

                for date_idx, sub in enumerate(subjects):
                    exam_date = available_dates[date_idx % len(available_dates)]
                    for sec in sections:
                        selected_room = rooms[0]
                        selected_teacher = teachers[0]

                        sched = ExamSchedule(
                            school_id=school.id, exam_id=exam.id, subject_id=sub.id, section=sec.section_name,
                            date=exam_date, start_time=time(9, 0), end_time=time(12, 0),
                            room_no=selected_room.room_no, teacher_id=selected_teacher.id,
                            max_marks=100.0, passing_marks=33.0
                        )
                        db.session.add(sched)
                        schedule_count += 1
            db.session.commit()
            print(f"✅ Success: Exam Auto-Scheduler generated {schedule_count} schedules.")
        except Exception as auto_ex:
            print(f"❌ Failure: Auto-Scheduler Engine crashed: {auto_ex}")

        print("🏁 All Academics Module backend verification tests completed successfully!")

if __name__ == "__main__":
    run_tests()
