import pdfplumber
from datetime import date, datetime


def load_holidays(pdf_path):
    holidays = []

    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue

                # Expected format:
                # DD-MM-YYYY Holiday Name
                parts = line.split(maxsplit=1)

                if len(parts) != 2:
                    continue

                d, reason = parts

                try:
                    holiday_date = datetime.strptime(d, "%d-%m-%Y").date()
                except ValueError:
                    continue

                holidays.append({
                    "date": holiday_date,
                    "reason": reason.strip()
                })

    return holidays


def get_next_holiday(holidays):
    today = date.today()
    upcoming = [h for h in holidays if h["date"] >= today]
    return min(upcoming, key=lambda x: x["date"]) if upcoming else None
