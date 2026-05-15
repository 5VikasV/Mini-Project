# app.py — Study Habit Tracker · Flask Backend
# Endpoints:
#   POST /predict      → predict productivity for a given session
#   POST /add-entry    → save new entry, retrain the model automatically
#
# Run:  python app.py
# Deps: pip install flask scikit-learn

import json
import os

from flask import Flask, jsonify, request
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder

app = Flask(__name__)

# ── File that stores all study entries ────────────────────────────────────────
DATA_FILE = "study_data.json"

# ── In-memory model state ─────────────────────────────────────────────────────
model   = None          # trained RandomForestRegressor (or None if not ready)
encoder = LabelEncoder()  # maps subject names → integers


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def load_entries():
    """Read all entries from study_data.json.
    Returns an empty list if the file doesn't exist yet."""
    if not os.path.exists(DATA_FILE):
        return []
    with open(DATA_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def save_entries(entries):
    """Write the full entry list back to study_data.json."""
    with open(DATA_FILE, "w") as f:
        json.dump(entries, f, indent=2)


def train_model(entries):
    """Build and return a trained RandomForestRegressor from entries.

    Each entry must have:
        hours        (float)  — study hours
        mood         (int)    — 1–5
        subject      (str)    — subject name
        productivity (float)  — 1–10, the target we're predicting

    Returns (model, encoder) or (None, encoder) if there's not enough data.
    """
    global encoder

    # Need at least 5 entries for a meaningful model
    if len(entries) < 5:
        return None, encoder

    subjects     = [e["subject"]      for e in entries]
    hours_list   = [float(e["hours"]) for e in entries]
    moods        = [int(e["mood"])     for e in entries]
    productivity = [float(e["productivity"]) for e in entries]

    # Encode subject strings to numbers (fit on all known subjects)
    encoder.fit(subjects)
    subjects_encoded = encoder.transform(subjects).tolist()

    # Feature matrix: [hours, mood, subject_encoded]
    X = [[h, m, s] for h, m, s in zip(hours_list, moods, subjects_encoded)]
    y = productivity

    rf = RandomForestRegressor(
        n_estimators=50,   # small & fast — enough for personal data volumes
        max_depth=5,
        random_state=42
    )
    rf.fit(X, y)
    return rf, encoder


# ── Train on startup if data already exists ───────────────────────────────────
_startup_entries = load_entries()
if _startup_entries:
    model, encoder = train_model(_startup_entries)
    if model:
        print(f"[startup] Model trained on {len(_startup_entries)} existing entries.")
    else:
        print(f"[startup] {len(_startup_entries)} entries found — need 5+ to train.")
else:
    print("[startup] No existing data. Model will train after 5+ entries are added.")


# ═══════════════════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════════════════

@app.route("/predict", methods=["POST"])
def predict():
    """Predict productivity for a planned study session.

    Request JSON:
        { "hours": 2, "mood": 4, "subject": "Math" }

    Response JSON:
        { "predicted_productivity": 7.3 }
        or
        { "error": "..." }
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    # Validate required fields
    required = ["hours", "mood", "subject"]
    missing  = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    if model is None:
        return jsonify({"error": "Model not trained yet. Add 5+ entries first."}), 503

    try:
        hours   = float(data["hours"])
        mood    = int(data["mood"])
        subject = str(data["subject"])

        # Handle subjects the encoder hasn't seen before
        if subject not in encoder.classes_:
            # Use the average encoded value as a neutral fallback
            subject_encoded = int(len(encoder.classes_) / 2)
        else:
            subject_encoded = int(encoder.transform([subject])[0])

        features = [[hours, mood, subject_encoded]]
        prediction = model.predict(features)[0]
        # Clamp to valid 1–10 range and round to 1 decimal
        prediction = round(max(1.0, min(10.0, prediction)), 1)

        # ── Feature importance (hours=0, mood=1, subject=2) ───────────────────
        importances = model.feature_importances_  # raw weights, sum to 1.0
        total = sum(importances) or 1.0
        importance = {
            "hours":   round(importances[0] / total * 100),
            "mood":    round(importances[1] / total * 100),
            "subject": round(importances[2] / total * 100),
        }

        # ── Confidence: agreement across trees (lower std → higher confidence) ─
        # Each estimator votes a value; std of those votes measures disagreement.
        tree_preds = [t.predict(features)[0] for t in model.estimators_]
        pred_std   = (sum((p - prediction) ** 2 for p in tree_preds) / len(tree_preds)) ** 0.5
        # Map std 0→100%, std ≥3→0% (scale of 1–10 target, so 3 is very high variance)
        confidence = round(max(0, min(100, (1 - pred_std / 3) * 100)))

        return jsonify({
            "predicted_productivity": prediction,
            "confidence": confidence,
            "importance": importance,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/add-entry", methods=["POST"])
def add_entry():
    """Save a new study entry and automatically retrain the model.

    Request JSON:
        {
            "hours":        2.0,
            "mood":         4,
            "subject":      "Math",
            "productivity": 8
        }

    Response JSON (success):
        {
            "message":       "Entry saved and model retrained.",
            "total_entries": 12,
            "model_ready":   true
        }

    Response JSON (saved but not enough data to train yet):
        {
            "message":       "Entry saved. Need X more entries to train the model.",
            "total_entries": 3,
            "model_ready":   false
        }
    """
    global model, encoder

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Invalid JSON body"}), 400

    # Validate required fields and types
    required = ["hours", "mood", "subject", "productivity"]
    missing  = [k for k in required if k not in data]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    try:
        new_entry = {
            "hours":        float(data["hours"]),
            "mood":         int(data["mood"]),
            "subject":      str(data["subject"]).strip(),
            "productivity": float(data["productivity"])
        }
    except (ValueError, TypeError) as e:
        return jsonify({"error": f"Invalid field value: {e}"}), 400

    # Basic range checks
    if not (0.25 <= new_entry["hours"] <= 24):
        return jsonify({"error": "hours must be between 0.25 and 24"}), 400
    if not (1 <= new_entry["mood"] <= 5):
        return jsonify({"error": "mood must be between 1 and 5"}), 400
    if not (1 <= new_entry["productivity"] <= 10):
        return jsonify({"error": "productivity must be between 1 and 10"}), 400
    if not new_entry["subject"]:
        return jsonify({"error": "subject must not be empty"}), 400

    # ── Step 1: Load existing data ────────────────────────────────────────────
    entries = load_entries()

    # ── Step 2: Append new entry ──────────────────────────────────────────────
    entries.append(new_entry)

    # ── Step 3: Save updated dataset ─────────────────────────────────────────
    save_entries(entries)
    print(f"[add-entry] Saved entry #{len(entries)}: {new_entry}")

    # ── Step 4: Retrain the model ─────────────────────────────────────────────
    new_model, new_encoder = train_model(entries)

    if new_model is not None:
        model   = new_model     # hot-swap — /predict uses the new model immediately
        encoder = new_encoder
        needed  = 0
        print(f"[add-entry] Model retrained on {len(entries)} entries.")
        message = "Entry saved and model retrained."
    else:
        needed  = 5 - len(entries)
        message = f"Entry saved. Need {needed} more {'entry' if needed == 1 else 'entries'} to train the model."

    return jsonify({
        "message":       message,
        "total_entries": len(entries),
        "model_ready":   new_model is not None
    }), 200


# ═══════════════════════════════════════════════════════════════════════════════
# Run
# ═══════════════════════════════════════════════════════════════════════════════
from flask import send_from_directory

@app.route("/")
def index():
    return send_from_directory(".", "study-habit-tracker.html")

@app.route("/get-entries", methods=["GET"])
def get_entries():
    entries = load_entries()
    return jsonify(entries)


if __name__ == "__main__":
    # debug=True → auto-reloads on code changes; turn off in production
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
