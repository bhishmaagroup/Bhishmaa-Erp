from flask import Blueprint

idcard_bp = Blueprint(
    "idcard",
    __name__,
    url_prefix="/id-card",
    template_folder="../templates/idcard"
)

from . import routes
