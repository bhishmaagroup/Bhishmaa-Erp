from flask_sqlalchemy import SQLAlchemy
from flask_sqlalchemy.model import Model
from flask_login import LoginManager
from sqlalchemy import event, Column, String, DateTime, Integer
from sqlalchemy.engine import Engine
import sqlite3
import uuid
from datetime import datetime, date
from flask_mail import Mail

class CustomModel(Model):
    uuid = Column(String(36), default=lambda: str(uuid.uuid4()), unique=True, nullable=False)
    school_id = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced_at = Column(DateTime, nullable=True)
    sync_version = Column(Integer, default=1)

    def to_dict(self):
        d = {}
        for col in self.__table__.columns:
            val = getattr(self, col.name)
            if isinstance(val, (datetime, date)):
                d[col.name] = val.isoformat()
            else:
                d[col.name] = val
        return d

    def update_from_dict(self, d):
        for col in self.__table__.columns:
            if col.name in d:
                val = d[col.name]
                if val is not None:
                    if "datetime" in str(col.type).lower():
                        try:
                            val = datetime.fromisoformat(val)
                        except Exception:
                            try:
                                val = datetime.strptime(val.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                            except Exception:
                                pass
                    elif "date" in str(col.type).lower():
                        try:
                            val = datetime.fromisoformat(val).date()
                        except Exception:
                            try:
                                val = datetime.strptime(val, "%Y-%m-%d").date()
                            except Exception:
                                pass
                setattr(self, col.name, val)

db = SQLAlchemy(model_class=CustomModel)
login_manager = LoginManager()
login_manager.login_view = 'auth.login'
mail = Mail()  
