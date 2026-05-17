from flask import render_template, request, send_file
from flask_login import login_required, current_user
from . import idcard_bp

from models.student import Student
from models.school import School

import io
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Table,
    Spacer,
    Image
)
from reportlab.lib.styles import ParagraphStyle


# =====================================================
# SINGLE STUDENT ID CARD (CR80 SIZE PDF)
# =====================================================
@idcard_bp.route("/student/<int:student_id>/pdf")
@login_required
def student_idcard_pdf(student_id):

    student = Student.query.get_or_404(student_id)
    school = School.query.get_or_404(current_user.school_id)

    buffer = io.BytesIO()

    # ✅ CR80 UNIVERSAL ID CARD SIZE
    ID_CARD_SIZE = (85.6 * mm, 53.98 * mm)

    doc = SimpleDocTemplate(
        buffer,
        pagesize=ID_CARD_SIZE,
        leftMargin=4 * mm,
        rightMargin=4 * mm,
        topMargin=4 * mm,
        bottomMargin=4 * mm
    )

    # ================= STYLES =================
    school_title = ParagraphStyle(
        "school_title",
        fontSize=9,
        alignment=1,
        fontName="Helvetica-Bold"
    )

    school_sub = ParagraphStyle(
        "school_sub",
        fontSize=6.5,
        alignment=1
    )

    label = ParagraphStyle(
        "label",
        fontSize=6.5,
        fontName="Helvetica-Bold"
    )

    value = ParagraphStyle(
        "value",
        fontSize=6.5
    )

    elements = []

    # ================= HEADER =================
    header = Table(
        [[
            Image(school.logo, 10 * mm, 10 * mm) if school.logo else "",
            Paragraph(
                f"""
                {school.school_name.upper()}<br/>
                <font size="6">
                {school.address}, {school.city}<br/>
                Phone: {school.phone}
                </font>
                """,
                school_title
            )
        ]],
        colWidths=[12 * mm, 60 * mm]
    )

    header.setStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.black),
    ])

    elements.append(header)
    elements.append(Spacer(1, 2 * mm))

    # ================= STUDENT DETAILS =================
    full_name = " ".join(
        filter(None, [
            student.first_name,
            student.middle_name,
            student.last_name
        ])
    )

    info = Table(
        [
            [Paragraph("Name", label), Paragraph(full_name, value)],
            [Paragraph("Class", label), Paragraph(f"{student.student_class}-{student.section}", value)],
            [Paragraph("Adm No", label), Paragraph(student.admission_no, value)],
            [Paragraph("Session", label), Paragraph(student.session, value)],
        ],
        colWidths=[18 * mm, 54 * mm]
    )

    info.setStyle([
        ("GRID", (0, 0), (-1, -1), 0.3, colors.black),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])

    elements.append(info)
    elements.append(Spacer(1, 3 * mm))

    # ================= SIGNATURE =================
    sign = Table(
        [[
            "____________________",
            "____________________"
        ],
        [
            "Class Teacher",
            "Principal"
        ]],
        colWidths=[36 * mm, 36 * mm]
    )

    sign.setStyle([
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("FONTSIZE", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
    ])

    elements.append(sign)

    # ================= BUILD =================
    doc.build(elements)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{student.admission_no}_id_card.pdf"
    )
