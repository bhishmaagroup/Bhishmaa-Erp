from app import create_app
from extensions import db
from models.school import School
from models.user import User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():

    school = School(
        school_code='ANPS001',
        school_name='A N Public School'
    )

    db.session.add(school)
    db.session.commit()

    admin = User(
        school_id=school.id,
        username='admin',
        password=generate_password_hash('anps@123'),
        role='admin',
        force_password_change=True
    )

    db.session.add(admin)
    db.session.commit()

    print("School & Admin created successfully")
