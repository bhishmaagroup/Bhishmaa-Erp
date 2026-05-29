import io
import os
import zipfile
import shutil
import tempfile
from datetime import datetime

import pandas as pd

from flask import send_file

from extensions import db


# =========================================
# AUTO DETECT ALL TABLES
# =========================================
ALL_TABLES = {
    table.name: table
    for table in db.metadata.sorted_tables
}


# =========================================
# IGNORE COLUMNS
# =========================================
IGNORE_COLUMNS = {
    "created_at",
    "updated_at"
}


# =========================================
# CLEAN VALUE
# =========================================
def clean_value(value):

    if pd.isna(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()

    return value


# =========================================
# CHECK SCHOOL RELATED TABLE
# =========================================
def is_school_related(table):

    if "school_id" in table.columns:
        return True

    fk_tables = []

    for fk in table.foreign_keys:

        try:
            fk_tables.append(
                fk.column.table.name
            )
        except:
            pass

    school_tables = [
        "students",
        "teacher",
        "schools",
        "subject",
        "routes",
        "tickets",
        "buses"
    ]

    for item in school_tables:

        if item in fk_tables:
            return True

    return False


# =========================================
# READ FILE
# =========================================
def read_file(file):

    ext = file.filename.rsplit(".", 1)[1].lower()

    if ext == "csv":
        return pd.read_csv(file)

    elif ext in ["xlsx", "xls"]:
        return pd.read_excel(file)

    raise ValueError("Only CSV/XLSX allowed")


# =========================================
# SINGLE MODULE EXPORT
# =========================================
def export_data(module, school_id):

    if module not in ALL_TABLES:
        return "Invalid module"

    table = ALL_TABLES[module]

    try:

        if "school_id" in table.columns:

            query = table.select().where(
                table.c.school_id == school_id
            )

        else:

            query = table.select()

        rows = db.session.execute(
            query
        ).mappings().all()

        data = []

        for row in rows:

            item = dict(row)

            for ignore in IGNORE_COLUMNS:
                item.pop(ignore, None)

            data.append(item)

        df = pd.DataFrame(data)

        output = io.BytesIO()

        with pd.ExcelWriter(
            output,
            engine="openpyxl"
        ) as writer:

            df.to_excel(
                writer,
                index=False,
                sheet_name=module[:31]
            )

        output.seek(0)

        return send_file(
            output,
            as_attachment=True,
            download_name=f"{module}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    except Exception as e:

        print("EXPORT ERROR:", e)

        return str(e)


# =========================================
# SINGLE MODULE IMPORT
# =========================================
def import_data(file, module, school_id):

    if module not in ALL_TABLES:

        return {
            "imported": 0,
            "skipped": 0,
            "errors": ["Invalid module"]
        }

    table = ALL_TABLES[module]

    df = read_file(file)

    success = 0
    skipped = 0
    errors = []

    valid_columns = [
        c.name for c in table.columns
    ]

    for index, row in df.iterrows():

        try:

            data = {}

            for col in df.columns:

                if col not in valid_columns:
                    continue

                data[col] = clean_value(
                    row[col]
                )

            # FORCE SCHOOL ID
            if "school_id" in valid_columns:
                data["school_id"] = school_id

            stmt = table.insert().values(
                **data
            )

            db.session.execute(stmt)

            success += 1

        except Exception as e:

            skipped += 1

            errors.append(
                f"Row {index + 2}: {str(e)}"
            )

    try:

        db.session.commit()

    except Exception as e:

        db.session.rollback()

        errors.append(str(e))

    return {
        "imported": success,
        "skipped": skipped,
        "errors": errors
    }


# =========================================
# EXPORT FULL ERP SCHOOL BACKUP
# =========================================
def export_all_data(school_id):

    with tempfile.TemporaryDirectory() as temp_dir:

        backup_folder = os.path.join(
            temp_dir,
            "backup"
        )

        os.makedirs(backup_folder)

        # =====================================
        # EXPORT ALL TABLES
        # =====================================
        for table_name, table in ALL_TABLES.items():

            try:

                print(f"EXPORTING {table_name}")

                if is_school_related(table):

                    if "school_id" in table.columns:

                        query = table.select().where(
                            table.c.school_id == school_id
                        )

                    else:

                        query = table.select()

                else:
                    continue

                rows = db.session.execute(
                    query
                ).mappings().all()

                if not rows:
                    continue

                data = []

                for row in rows:

                    item = dict(row)

                    for ignore in IGNORE_COLUMNS:
                        item.pop(ignore, None)

                    data.append(item)

                df = pd.DataFrame(data)

                excel_path = os.path.join(
                    backup_folder,
                    f"{table_name}.xlsx"
                )

                with pd.ExcelWriter(
                    excel_path,
                    engine="openpyxl"
                ) as writer:

                    df.to_excel(
                        writer,
                        index=False
                    )

                print(f"SUCCESS {table_name}")

            except Exception as e:

                print(
                    f"EXPORT FAILED {table_name}: {e}"
                )

        # =====================================
        # METADATA
        # =====================================
        meta = {
            "erp": "Bhishmaa ERP",
            "school_id": school_id,
            "created_at": str(datetime.now())
        }

        pd.DataFrame([meta]).to_json(
            os.path.join(
                backup_folder,
                "metadata.json"
            ),
            orient="records"
        )

        # =====================================
        # COPY UPLOADS
        # =====================================
        if os.path.exists("uploads"):

            shutil.copytree(
                "uploads",
                os.path.join(
                    backup_folder,
                    "uploads"
                )
            )

        # =====================================
        # CREATE ZIP
        # =====================================
        zip_path = os.path.join(
            temp_dir,
            f"school_{school_id}.zip"
        )

        with zipfile.ZipFile(
            zip_path,
            "w",
            zipfile.ZIP_DEFLATED
        ) as zf:

            for root, dirs, files in os.walk(
                backup_folder
            ):

                for file in files:

                    filepath = os.path.join(
                        root,
                        file
                    )

                    arcname = os.path.relpath(
                        filepath,
                        backup_folder
                    )

                    zf.write(
                        filepath,
                        arcname
                    )

        # =====================================
        # FIX WINDOWS FILE LOCK
        # =====================================
        with open(zip_path, "rb") as f:
            zip_data = io.BytesIO(f.read())

        zip_data.seek(0)

        return send_file(
            zip_data,
            as_attachment=True,
            download_name=f"school_{school_id}_backup.zip",
            mimetype="application/zip"
        )


# =========================================
# CLEAR SCHOOL DATA
# =========================================
def clear_school_data(school_id):

    for table_name, table in reversed(
        list(ALL_TABLES.items())
    ):

        try:

            if "school_id" in table.columns:

                print(f"CLEARING {table_name}")

                stmt = table.delete().where(
                    table.c.school_id == school_id
                )

                db.session.execute(stmt)

        except Exception as e:

            print(
                f"DELETE FAILED {table_name}: {e}"
            )


# =========================================
# FULL IMPORT
# =========================================
def import_all_data(zip_file, school_id):

    imported = 0
    skipped = 0
    errors = []

    with tempfile.TemporaryDirectory() as temp_dir:

        zip_path = os.path.join(
            temp_dir,
            "backup.zip"
        )

        zip_file.save(zip_path)

        # =====================================
        # EXTRACT ZIP
        # =====================================
        with zipfile.ZipFile(zip_path, "r") as zf:

            zf.extractall(temp_dir)

        try:

            with db.session.begin():

                # =================================
                # DELETE OLD SCHOOL DATA
                # =================================
                clear_school_data(
                    school_id
                )

                # =================================
                # IMPORT TABLES
                # =================================
                for table_name, table in ALL_TABLES.items():

                    filepath = os.path.join(
                        temp_dir,
                        f"{table_name}.xlsx"
                    )

                    if not os.path.exists(filepath):
                        continue

                    print(f"IMPORTING {table_name}")

                    df = pd.read_excel(
                        filepath
                    )

                    valid_columns = [
                        c.name
                        for c in table.columns
                    ]

                    for _, row in df.iterrows():

                        try:

                            data = {}

                            for col in df.columns:

                                if col not in valid_columns:
                                    continue

                                data[col] = clean_value(
                                    row[col]
                                )

                            # FORCE SCHOOL ID
                            if "school_id" in valid_columns:
                                data["school_id"] = school_id

                            stmt = table.insert().values(
                                **data
                            )

                            db.session.execute(stmt)

                            imported += 1

                        except Exception as e:

                            skipped += 1

                            errors.append(
                                f"{table_name}: {e}"
                            )

                # =================================
                # RESTORE UPLOADS
                # =================================
                uploads_backup = os.path.join(
                    temp_dir,
                    "uploads"
                )

                if os.path.exists(
                    uploads_backup
                ):

                    if os.path.exists(
                        "uploads"
                    ):

                        shutil.rmtree(
                            "uploads"
                        )

                    shutil.copytree(
                        uploads_backup,
                        "uploads"
                    )

            db.session.commit()

        except Exception as e:

            db.session.rollback()

            errors.append(str(e))

    return {
        "imported": imported,
        "skipped": skipped,
        "errors": errors
    }