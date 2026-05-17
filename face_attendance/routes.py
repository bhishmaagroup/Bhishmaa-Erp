import os
import uuid

from flask import Blueprint
from flask import request
from flask import jsonify

from deepface import DeepFace

from extensions import db

from models.teacher import Teacher
from models.school import School
from models.attendance import TeacherAttendance

from math import radians
from math import sin
from math import cos
from math import sqrt
from math import atan2


face_bp = Blueprint(
    "face_bp",
    __name__
)

UPLOAD_FOLDER = "uploads/attendance"

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)


def inside_school(
    school_lat,
    school_lng,
    current_lat,
    current_lng,
    radius=100
):

    R = 6371000

    dlat = radians(current_lat - school_lat)
    dlon = radians(current_lng - school_lng)

    a = (
        sin(dlat / 2) ** 2
        + cos(radians(school_lat))
        * cos(radians(current_lat))
        * sin(dlon / 2) ** 2
    )

    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c

    return distance <= radius


@face_bp.route(
    "/register-face/<int:id>",
    methods=["POST"]
)
def register_face(id):

    teacher = Teacher.query.get_or_404(id)

    image = request.files.get("image")

    if not image:

        return jsonify({
            "status": "error",
            "message": "Image required"
        })

    filename = f"{uuid.uuid4()}.jpg"

    filepath = os.path.join(
        "uploads",
        filename
    )

    image.save(filepath)

    teacher.face_image = filepath

    db.session.commit()

    return jsonify({
        "status": "success",
        "message": "Face Registered"
    })


@face_bp.route(
    "/face-checkin",
    methods=["POST"]
)
def face_checkin():

    teacher_id = request.form.get(
        "teacher_id"
    )

    latitude = float(
        request.form.get("latitude")
    )

    longitude = float(
        request.form.get("longitude")
    )

    image = request.files.get("image")

    if not image:

        return jsonify({
            "status": "error",
            "message": "Image required"
        })

    teacher = Teacher.query.get(
        teacher_id
    )

    if not teacher:

        return jsonify({
            "status": "error",
            "message": "Teacher not found"
        })

    school = School.query.get(
        teacher.school_id
    )

    allowed = inside_school(
        school.latitude,
        school.longitude,
        latitude,
        longitude,
        school.radius
    )

    if not allowed:

        return jsonify({
            "status": "error",
            "message": "Outside school campus"
        })

    filename = f"{uuid.uuid4()}.jpg"

    filepath = os.path.join(
        UPLOAD_FOLDER,
        filename
    )

    image.save(filepath)

    result = DeepFace.verify(
        img1_path=teacher.face_image,
        img2_path=filepath,
        enforce_detection=False
    )

    if not result["verified"]:

        return jsonify({
            "status": "error",
            "message": "Face not matched"
        })

    attendance = TeacherAttendance(

        school_id=teacher.school_id,

        teacher_id=teacher.id,

        attendance_date=db.func.current_date(),

        status="Present",

        latitude=latitude,

        longitude=longitude,

        photo=filename,

        method="face"
    )

    db.session.add(attendance)

    db.session.commit()

    return jsonify({
        "status": "success",
        "message": "Attendance Marked"
    })