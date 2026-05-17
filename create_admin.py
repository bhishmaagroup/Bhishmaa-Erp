from app import create_app
from extensions import db
from models.user import User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    admin = User(
        username='admin',
        password=generate_password_hash('admin@123'),
        role='admin'
    )
    db.session.add(admin)
    db.session.commit()
    print("Admin created successfully")
