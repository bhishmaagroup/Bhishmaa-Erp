from reportlab.lib.pagesizes import A4
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib import colors
from io import BytesIO
from datetime import datetime
import os


def generate_notice_pdf(holiday, school):
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=40,
        leftMargin=40,
        topMargin=25,
        bottomMargin=30
    )

    styles = getSampleStyleSheet()

    # ================= ERP STYLES =================
    styles.add(ParagraphStyle(
        name="ERP_SchoolInfo",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,   # ✅ CENTER FIX
        spaceAfter=6
    ))

    styles.add(ParagraphStyle(
        name="ERP_Title",
        fontSize=14,
        alignment=TA_CENTER,
        fontName="Helvetica-Bold",
        spaceAfter=20
    ))

    styles.add(ParagraphStyle(
        name="ERP_Body",
        fontSize=11,
        leading=17,
        spaceAfter=12
    ))

    styles.add(ParagraphStyle(
        name="ERP_Footer",
        fontSize=10,
        spaceAfter=6
    ))

    elements = []

    # ================= TOP COLOR STRIP =================
    elements.append(Table(
        [[""]],
        colWidths=[doc.width],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.orange),
            ("ROWHEIGHT", (0, 0), (-1, -1), 6),
        ])
    ))
    elements.append(Spacer(1, 14))

    # ================= LOGO + SCHOOL DETAILS =================
    logo_cell = ""
    if school.logo:
        logo_path = os.path.join(os.getcwd(), school.logo.replace("\\", "/"))
        if os.path.exists(logo_path):
            logo_cell = Image(logo_path, width=60, height=60)

    school_block = (
        f"<b>{school.school_name.upper()}</b><br/>"
        f"{school.address}, {school.city}, {school.state} – {school.pincode}<br/>"
        f"Phone: {school.phone} | Email: {school.email}"
    )

    header_table = Table(
        [[
            logo_cell,
            Paragraph(school_block, styles["ERP_SchoolInfo"])
        ]],
        colWidths=[80, doc.width - 80]
    )

    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (1, 0), (1, 0), 8),
    ]))

    elements.append(header_table)
    elements.append(Spacer(1, 18))

    # ================= REF NO + DATE =================
    today = datetime.now()
    ref_no = f"{school.school_code}/HOL/{today.strftime('%Y')}/{today.strftime('%m%d')}"

    ref_table = Table(
        [[
            f"Ref. No: {ref_no}",
            f"Date: {today.strftime('%d/%m/%Y')}"
        ]],
        colWidths=[doc.width / 2, doc.width / 2]
    )
    ref_table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
    ]))

    elements.append(ref_table)
    elements.append(Spacer(1, 18))

    # ================= NOTICE TITLE =================
    elements.append(Paragraph("HOLIDAY NOTICE", styles["ERP_Title"]))

    # ================= BODY =================
    holiday_date = holiday["date"].strftime("%d %B %Y")

    body = (
        "Dear Parents/Students,<br/><br/>"
        f"This is to inform you that the school will remain "
        f"<b>closed on {holiday_date}</b> on account of "
        f"<b>{holiday['reason']}</b>.<br/><br/>"
        "All academic and administrative activities of the school "
        "will remain suspended for the day.<br/><br/>"
        "Regular classes will resume from the next working day as per "
        "the normal timetable.<br/><br/>"
        "Your cooperation is highly solicited."
    )

    elements.append(Paragraph(body, styles["ERP_Body"]))
    elements.append(Spacer(1, 32))

    # ================= SIGNATURE =================
    elements.append(Paragraph("Regards,", styles["ERP_Footer"]))
    elements.append(Spacer(1, 36))
    elements.append(Paragraph("Principal", styles["ERP_Footer"]))
    elements.append(Paragraph(school.school_name, styles["ERP_Footer"]))

    doc.build(elements)
    buffer.seek(0)
    return buffer
