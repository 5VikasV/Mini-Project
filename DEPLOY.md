# Deploying Study Habit Tracker to Render

## Files needed

Make sure your project folder contains all five of these:

```
study-tracker/
├── app.py                    ← Flask backend
├── study-habit-tracker.html  ← Frontend (served by Flask)
├── study_data.json           ← Starts as [] — grows as entries are added
├── requirements.txt          ← Python dependencies
└── Procfile                  ← Tells Render how to start the app
```

---

## Step 1 — Push to GitHub

Render deploys from a Git repository.

```bash
# From inside your project folder:
git init
git add .
git commit -m "Initial deploy"
```

Then go to https://github.com/new, create a new repo, and follow the
instructions to push your local code there.

---

## Step 2 — Create a Web Service on Render

1. Go to https://render.com and sign in (free account works).
2. Click **New → Web Service**.
3. Connect your GitHub account and select your repository.
4. Fill in the settings:

| Field            | Value                        |
|------------------|------------------------------|
| **Name**         | study-habit-tracker (or any) |
| **Branch**       | main                         |
| **Runtime**      | Python 3                     |
| **Build Command**| `pip install -r requirements.txt` |
| **Start Command**| `gunicorn app:app`           |

5. Click **Create Web Service**.

Render will build and deploy automatically. Takes about 1–2 minutes.

---

## Step 3 — Open your app

Render gives you a URL like:

```
https://study-habit-tracker.onrender.com
```

Open that URL — your app is live. The frontend and backend are served
from the same origin, so all `/predict`, `/add-entry`, and `/get-entries`
calls work without any URL changes.

---

## Important: study_data.json persistence

Render's free tier uses an **ephemeral filesystem** — `study_data.json`
resets to `[]` every time the server restarts or redeploys.

**This is fine for testing.** For permanent storage, the easiest upgrade
is to replace `study_data.json` with a free PostgreSQL database on Render
(Render → New → PostgreSQL) and swap `load_entries` / `save_entries` to
use `psycopg2`. That's a separate step when you're ready.

---

## Local development (unchanged)

```bash
pip install -r requirements.txt
python app.py
# Open http://localhost:5000
```

---

## What changed for production

| File              | What changed                                      |
|-------------------|---------------------------------------------------|
| `app.py`          | `app.run` now reads `PORT` from environment,      |
|                   | binds to `0.0.0.0`, and sets `debug=False`        |
| `requirements.txt`| New — lists Flask, scikit-learn, gunicorn         |
| `Procfile`        | New — tells Render: `gunicorn app:app`            |
| HTML frontend     | No changes needed — all fetch calls already use  |
|                   | relative paths like `/predict` (not localhost)    |
