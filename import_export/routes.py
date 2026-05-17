from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from .services import import_data, export_data

import_export = Blueprint(
    "import_export",
    __name__,
    url_prefix="/import-export"
)

@import_export.route("/", methods=["GET", "POST"])
@login_required
def index():
    if request.method == "POST":
        module = request.form.get("module")
        file = request.files.get("file")

        if not file:
            flash("File select karo", "danger")
            return redirect(url_for("import_export.index"))

        import_data(file, module, current_user.school_id)
        flash("Import complete", "success")
        return redirect(url_for("import_export.index"))

    # 👇 IMPORTANT CHANGE
    return render_template("import_export/index.html")


@import_export.route("/export/<module>")
@login_required
def export(module):
    return export_data(module, current_user.school_id)
