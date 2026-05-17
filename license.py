import requests
import sys
import json
import os
from datetime import datetime

LICENSE_FILE = "license.json"

# 🔥 हर school के लिए change करना है
SCHOOL_CODE = "SCHOOL001"

# 🔥 deploy होने के बाद change करना
API_URL = "http://127.0.0.1:5000/api/check_license"


def check_license():
    try:
        res = requests.get(
            f"{API_URL}?school_code={SCHOOL_CODE}",
            timeout=5
        )

        data = res.json()

        if data["status"] != "active":
            print("❌ License Blocked")
            sys.exit()

        # save last check
        with open(LICENSE_FILE, "w") as f:
            json.dump({"last_check": str(datetime.now())}, f)

    except:
        print("⚠ Offline Mode")


def offline_limit():
    if not os.path.exists(LICENSE_FILE):
        return

    try:
        with open(LICENSE_FILE) as f:
            data = json.load(f)

        last = datetime.fromisoformat(data["last_check"])
        days = (datetime.now() - last).days

        if days > 3:
            print("❌ License Expired (No Internet)")
            sys.exit()

    except:
        pass


def run_license():
    check_license()
    offline_limit()