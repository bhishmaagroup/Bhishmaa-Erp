import os
import shutil
from datetime import datetime

def perform_cloud_backup():
    source_db = 'instance/app.db'
    backup_dir = 'backups/cloud_vault'
    
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(backup_dir, f"founder_vault_{timestamp}.db")
    
    try:
        shutil.copy2(source_db, backup_path)
        # Here you would typically use boto3 to upload to AWS S3
        return True, backup_path
    except Exception as e:
        return False, str(e)