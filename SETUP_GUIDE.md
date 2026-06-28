# 🏫 Bhishmaa ERP — Setup Guide

## ⚙️ Step 1: Server IP Set Karo (ONLY THIS ONE CHANGE NEEDED)

`app.py` file kholo, line 20 pe:

```python
CLOUD_HOST = ""   # ← Apna PostgreSQL server IP/domain yahan likhein
```

Example:
```python
CLOUD_HOST = "15.206.120.45"
```

Bas itna hi. Koi .env file nahi chahiye.

---

## 🚀 Step 2: Run Karo

```bash
pip install -r requirements.txt
python app.py
```

---

## 🔄 Sync System

| Event              | Sync Action                            |
|--------------------|----------------------------------------|
| App start          | Immediately sync if internet available |
| User login         | Background sync trigger                |
| Internet aaye      | Automatic sync in 5 seconds           |
| Har 60 seconds     | Auto sync                              |
| Koi data change    | 2 second baad immediate sync          |
| Manual             | /sync/status > "Sync Now"             |

### Bidirectional Sync Logic:
- **Local only** (offline mein banaya) → Cloud pe push
- **Cloud only** (doosre device se aaya) → Local pe pull
- **Dono jagah updated** → `sync_version` + `updated_at` se winner decide
- **No data loss** — dono versions SyncSession mein log hote hain

---

## 📦 EXE Build (Windows)

```bash
pip install pyinstaller
pyinstaller bhishmaa.spec --clean --noconfirm
```

Output: `dist/BhishmaaERP.exe`

EXE ke andar sab kuch bundled hai — sirf yeh ek file deploy karo.

---

## ❓ Troubleshooting

**Q: Sync nahi ho raha**
→ `app.py` mein `CLOUD_HOST` check karo
→ Server ka port 5432 open hai?

**Q: Conflict aa raha hai**
→ `/sync/conflicts` pe jao, manually resolve karo

**Q: Data dikh raha hai local mein, cloud pe nahi**
→ `/sync/status` pe "Sync Now" click karo
