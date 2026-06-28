import os
import uuid
import importlib
from datetime import datetime
from sqlalchemy import inspect, text
from extensions import db

def get_all_subclasses(cls):
    subclasses = set(cls.__subclasses__())
    for s in cls.__subclasses__():
        subclasses.update(get_all_subclasses(s))
    return subclasses

def import_all_models():
    """
    Dynamically imports all modules under the models/ directory to ensure 
    they are registered with SQLAlchemy.
    """
    models_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")
    if os.path.exists(models_dir):
        for file in os.listdir(models_dir):
            if file.endswith(".py") and file != "__init__.py":
                module_name = f"models.{file[:-3]}"
                try:
                    importlib.import_module(module_name)
                except Exception as e:
                    print(f"⚠ Failed to import {module_name} during migration init: {e}")

def get_sql_type(column, dialect="sqlite") -> str:
    """
    Converts SQLAlchemy column type to proper SQL string for both PostgreSQL and SQLite.
    """
    from sqlalchemy.sql import sqltypes
    col_type = column.type
    
    if isinstance(col_type, sqltypes.String):
        length = getattr(col_type, "length", None)
        return f"VARCHAR({length})" if length else "VARCHAR(255)"
    elif isinstance(col_type, sqltypes.Integer):
        return "INTEGER"
    elif isinstance(col_type, sqltypes.Float):
        return "FLOAT"
    elif isinstance(col_type, sqltypes.Boolean):
        return "BOOLEAN"
    elif isinstance(col_type, sqltypes.DateTime):
        return "TIMESTAMP" if dialect == "postgresql" else "DATETIME"
    elif isinstance(col_type, sqltypes.Date):
        return "DATE"
    elif isinstance(col_type, sqltypes.Text):
        return "TEXT"
    elif "json" in str(col_type).lower():
        return "JSONB" if dialect == "postgresql" else "TEXT"
        
    return str(col_type).upper()

def auto_migrate(app):
    """
    Compares all registered SQLAlchemy models against actual DB schema.
    Adds any missing columns automatically.
    Works for both PostgreSQL and SQLite.
    """
    # 1. Force loading of all model classes
    import_all_models()
    
    is_online = os.environ.get("IS_ONLINE", "false").lower() == "true"
    dialect = "postgresql" if is_online else "sqlite"
    
    print(f"🔄 Starting database auto-migration on dialect: {dialect.upper()}")
    
    with app.app_context():
        try:
            engine = db.engine
            inspector = inspect(engine)
            
            # Ensure tables themselves exist
            db.create_all()
            
            # Refresh tables list
            existing_tables = inspector.get_table_names()
            all_models = get_all_subclasses(db.Model)
            
            tables_checked = 0
            columns_added = 0
            
            # Open a connection for executing alter commands
            connection = engine.connect()
            
            # Sync tracking columns list (required for Tally-like sync)
            sync_cols = [
                ("uuid", "VARCHAR(36)", "NULL"),
                ("updated_at", "TIMESTAMP" if dialect == "postgresql" else "DATETIME", "NULL"),
                ("last_synced_at", "TIMESTAMP" if dialect == "postgresql" else "DATETIME", "NULL"),
                ("sync_version", "INTEGER", "0"),
                ("retry_count", "INTEGER", "0"),
                ("priority", "INTEGER", "5"),
            ]
            
            for model in all_models:
                if not hasattr(model, "__tablename__") or not model.__tablename__:
                    continue
                
                table_name = model.__tablename__
                if table_name not in existing_tables:
                    continue
                
                tables_checked += 1
                
                # Fetch actual columns from physical DB table
                try:
                    db_cols = {col["name"].lower(): col for col in inspector.get_columns(table_name)}
                except Exception as e:
                    print(f"❌ error inspecting table '{table_name}': {e}")
                    continue
                
                # Check columns defined in SQLAlchemy model
                try:
                    model_cols = model.__table__.columns
                except AttributeError:
                    continue
                
                # A. Migrate custom model columns
                for col in model_cols:
                    col_name_lower = col.name.lower()
                    if col_name_lower not in db_cols:
                        sql_type = get_sql_type(col, dialect)
                        
                        # Handle simple default values
                        default_clause = ""
                        if col.default is not None and hasattr(col.default, 'arg') and not callable(col.default.arg):
                            arg = col.default.arg
                            if isinstance(arg, bool):
                                arg_str = "TRUE" if arg else "FALSE"
                            elif isinstance(arg, str):
                                arg_str = f"'{arg}'"
                            else:
                                arg_str = str(arg)
                            default_clause = f" DEFAULT {arg_str}"
                            
                        # Construct safe migration SQL
                        if dialect == "postgresql":
                            alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col.name}" {sql_type}{default_clause}'
                        else:
                            alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {sql_type}{default_clause}'
                            
                        try:
                            connection.execute(text(alter_sql))
                            try:
                                connection.commit()
                            except AttributeError:
                                pass
                            print(f"✅ added column '{col.name}' to table '{table_name}'")
                            columns_added += 1
                        except Exception as e:
                            print(f"❌ error adding column '{col.name}' to table '{table_name}': {e}")
                
                # B. Migrate standard sync columns
                for col_name, col_type, default_val in sync_cols:
                    if col_name.lower() not in db_cols:
                        default_clause = f" DEFAULT {default_val}" if default_val != "NULL" else ""
                        
                        if dialect == "postgresql":
                            alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}{default_clause}'
                        else:
                            alter_sql = f'ALTER TABLE "{table_name}" ADD COLUMN "{col_name}" {col_type}{default_clause}'
                            
                        try:
                            connection.execute(text(alter_sql))
                            try:
                                connection.commit()
                            except AttributeError:
                                pass
                            print(f"✅ added sync tracking column '{col_name}' to table '{table_name}'")
                            columns_added += 1
                        except Exception as e:
                            print(f"❌ error adding sync column '{col_name}' to table '{table_name}': {e}")
                
                # C. Generate unique UUIDs for rows with NULL uuid
                # Re-fetch columns to ensure 'uuid' exists
                updated_db_cols = [c["name"].lower() for c in inspector.get_columns(table_name)]
                if 'uuid' in updated_db_cols:
                    try:
                        pk_cols = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
                        if not pk_cols:
                            pk_cols = ["rowid"] if dialect == "sqlite" else []
                        
                        if pk_cols:
                            pk_name = pk_cols[0]
                            # Query all rows missing UUID
                            select_sql = f'SELECT "{pk_name}" FROM "{table_name}" WHERE "uuid" IS NULL OR "uuid" = \'\''
                            rows = connection.execute(text(select_sql)).fetchall()
                            
                            for r in rows:
                                new_uuid = str(uuid.uuid4())
                                update_sql = f'UPDATE "{table_name}" SET "uuid" = :uuid WHERE "{pk_name}" = :pk'
                                connection.execute(text(update_sql), {"uuid": new_uuid, "pk": r[0]})
                            
                            if rows:
                                try:
                                    connection.commit()
                                except AttributeError:
                                    pass
                                print(f"✅ generated unique UUIDs for {len(rows)} rows in table '{table_name}'")
                    except Exception as e:
                        print(f"⚠ skipped UUID backfilling on table '{table_name}': {e}")
            
            connection.close()
            print(f"📋 Migration completed: {tables_checked} tables checked, {columns_added} columns added.")
            
        except Exception as e:
            print(f"❌ Critical error during auto-migration: {e}")
