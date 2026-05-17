from extensions import db
from datetime import datetime

# 🕵️ SUPER ADMIN AUDIT LOGS
class AuditLog(db.Model):
    __tablename__ = 'audit_logs'
    id = db.Column(db.Integer, primary_key=True)
    admin_username = db.Column(db.String(100), nullable=False) # Store username directly for safety
    action = db.Column(db.String(255), nullable=False) 
    ip_address = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# 📢 GLOBAL BROADCASTS
class Broadcast(db.Model):
    __tablename__ = 'broadcasts'
    id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.Text, nullable=False)
    type = db.Column(db.String(50), default="info") # 'info', 'warning', 'danger'
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

# 🎫 SUPPORT TICKETS (Helpdesk)
class Ticket(db.Model):
    __tablename__ = 'tickets'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    subject = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(50), default='Open') # Open, In Progress, Closed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    messages = db.relationship('TicketMessage', backref='ticket', lazy=True, cascade="all, delete-orphan")

class TicketMessage(db.Model):
    __tablename__ = 'ticket_messages'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('tickets.id'), nullable=False)
    sender = db.Column(db.String(50)) 
    message = db.Column(db.Text, nullable=True) # Changed to True if only sending a file
    attachment = db.Column(db.String(255), nullable=True) # New Field for file path
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

# ⚙️ GLOBAL SYSTEM SETTINGS
class SystemSetting(db.Model):
    __tablename__ = 'system_settings'
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False) # e.g., 'SMTP_PASSWORD'
    value = db.Column(db.String(255), nullable=False)

class Payment(db.Model):
    __tablename__ = 'payments'
    id = db.Column(db.Integer, primary_key=True)
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    plan_name = db.Column(db.String(50)) # e.g., 'pro', 'premium'
    transaction_id = db.Column(db.String(100), unique=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    # Relationship to get school name easily
    school = db.relationship('School', backref='payments')

# 📊 SUBSCRIPTION PLANS (Optional: if you want to store limits in DB)
class Plan(db.Model):
    __tablename__ = 'plans'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False) # 'free', 'pro', 'premium'
    student_limit = db.Column(db.Integer, default=100)
    price = db.Column(db.Float, default=0.0)
    features = db.Column(db.Text) # JSON string of enabled features

class Invoice(db.Model):
    __tablename__ = 'invoices'
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.Integer, db.ForeignKey('payments.id'))
    school_id = db.Column(db.Integer, db.ForeignKey('schools.id'))
    invoice_number = db.Column(db.String(50), unique=True)
    file_path = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Coupon(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True)
    discount_percent = db.Column(db.Integer)
    active = db.Column(db.Boolean, default=True)