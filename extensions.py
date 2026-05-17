from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3
from flask_mail import Mail

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
mail = Mail()  
