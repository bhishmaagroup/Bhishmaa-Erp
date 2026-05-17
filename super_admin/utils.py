import os
from datetime import datetime
from extensions import db
from models.school import School
from flask import current_app

def check_and_block_expired_schools():
    """Run this via a Cron job or at Admin login"""
    expired_schools = School.query.filter(
        School.expiry_date < datetime.utcnow(),
        School.is_active == True
    ).all()
    
    for school in expired_schools:
        school.is_active = False
        # Log the auto-block action
    db.session.commit()
    return len(expired_schools)

def generate_invoice_pdf(payment):
    """Placeholder for PDF generation logic (e.g., using FPDF or WeasyPrint)"""
    invoice_num = f"INV-{payment.id}-{datetime.utcnow().strftime('%Y%m%d')}"
    # Logic to save a PDF file to /static/invoices/
    return invoice_num