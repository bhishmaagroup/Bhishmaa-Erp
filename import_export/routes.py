from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    send_file
)

from flask_login import login_required, current_user

from .services import (
    import_data,
    export_data,
    export_all_data,
    import_all_data
)

import_export = Blueprint(
    "import_export",
    __name__,
    url_prefix="/import-export"
)


# =========================================
# MAIN PAGE
# =========================================
@import_export.route("/", methods=["GET", "POST"])
@login_required
def index():

    if request.method == "POST":

        module = request.form.get("module")

        file = request.files.get("file")

        if not file:
            flash("Please select file", "danger")
            return redirect(url_for("import_export.index"))

        result = import_data(
            file,
            module,
            current_user.school_id
        )

        flash(
            f"""
            Imported: {result['imported']}
            | Skipped: {result['skipped']}
            """,
            "success"
        )

        return redirect(
            url_for("import_export.index")
        )

    return render_template(
        "import_export/index.html"
    )


# =========================================
# SINGLE MODULE EXPORT
# =========================================
@import_export.route("/export/<module>")
@login_required
def export(module):

    return export_data(
        module,
        current_user.school_id
    )


# =========================================
# FULL ERP EXPORT
# =========================================
@import_export.route("/export-all")
@login_required
def export_all():

    return export_all_data(
        current_user.school_id
    )


# =========================================
# FULL ERP IMPORT
# =========================================
@import_export.route("/import-all", methods=["POST"])
@login_required
def import_all():

    file = request.files.get("backup_zip")

    if not file:
        flash("Please select ZIP file", "danger")
        return redirect(
            url_for("import_export.index")
        )

    result = import_all_data(
        file,
        current_user.school_id
    )

    flash(
        f"""
        Backup Imported
        | Imported: {result['imported']}
        | Skipped: {result['skipped']}
        """,
        "success"
    )

    return redirect(
        url_for("import_export.index")
    )