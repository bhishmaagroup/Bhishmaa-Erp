from models.student import Student
from models.teacher import Teacher
from models.fee import StudentFeeLedger

MODEL_MAP = {
    "student": Student,
    "teacher": Teacher,
    "fee": StudentFeeLedger,
}

FIELD_MAP = {
    "student": {
        "admission_no": "admission_no",
        "first_name": "first_name",
        "last_name": "last_name",
        "student_class": "student_class",
        "section": "section",
        "session": "session"
    },
    "teacher": {
        "teacher_code": "teacher_code",
        "first_name": "first_name",
        "mobile": "mobile",
        "designation": "designation"
    },
    "fee": {
        "student_id": "student_id",
        "month": "month",
        "total_amount": "total_amount",
        "paid_amount": "paid_amount"
    }
}
