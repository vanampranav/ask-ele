"""Real Elefit data for Ele — read the signed-in user's profile, body
measurements and challenge status from Firebase (server-side, Admin SDK).

Phase 4, Step 1. Flow:
  1. The user logs in with their real Elefit email/password (verify_login →
     Firebase REST sign-in → uid).
  2. We set that uid as the current user (set_current_uid).
  3. Ele's tools (get_my_profile via the provider, get_my_measurements,
     get_my_challenge) read ONLY that uid's data via the Firebase Admin SDK.

SECRETS (set in the host env / Streamlit secrets — NEVER in the repo):
  • FIREBASE_SERVICE_ACCOUNT  — the service-account JSON (as a string), used by
    the Admin SDK to read Firestore.
  • FIREBASE_API_KEY          — the Firebase Web API key, used only to verify the
    user's password at login (REST sign-in).

NOTE (multi-user): the "current uid" is process-global, which is fine for
single-user testing. A real multi-user backend must scope the uid per request;
in the Streamlit console we re-set it on every turn before calling the agent.
"""

import json
import os
from typing import Optional

import requests

# ── Firebase Admin (lazy init) ───────────────────────────────────────────────
_db = None


def _ensure_admin():
    """Initialise the Admin SDK once, from FIREBASE_SERVICE_ACCOUNT."""
    global _db
    if _db is not None:
        return _db
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        sa = os.environ.get("FIREBASE_SERVICE_ACCOUNT")
        if sa:
            firebase_admin.initialize_app(credentials.Certificate(json.loads(sa)))
        else:
            firebase_admin.initialize_app()  # Application Default Credentials
    _db = firestore.client()
    return _db


# ── Current user (set at login) ──────────────────────────────────────────────
_current_uid: Optional[str] = None


def set_current_uid(uid: Optional[str]) -> None:
    global _current_uid
    _current_uid = uid


def current_uid() -> Optional[str]:
    return _current_uid


# ── Login: verify the user's real Elefit credentials ─────────────────────────
def verify_login(email: str, password: str) -> dict:
    """Verify email/password against Firebase Auth (REST). Returns
    {status, uid, email} on success, or {status:'error', message}."""
    key = os.environ.get("FIREBASE_API_KEY")
    if not key:
        return {"status": "error", "message": "FIREBASE_API_KEY not configured."}
    try:
        r = requests.post(
            "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword",
            params={"key": key},
            json={"email": email, "password": password, "returnSecureToken": True},
            timeout=15,
        )
        if r.status_code == 200:
            d = r.json()
            return {"status": "success", "uid": d["localId"], "email": d.get("email", email)}
        msg = r.json().get("error", {}).get("message", "Login failed")
        return {"status": "error", "message": msg}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "message": f"Login error: {e}"}


# ── Data reads (scoped to a uid) ─────────────────────────────────────────────
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def get_profile(uid: str) -> dict:
    """Read the user's profile from users/{uid} (+ profiles/{uid}) and map it to
    Ele's profile shape. Field names are mapped defensively."""
    db = _ensure_admin()
    data = {}
    for coll in ("users", "profiles"):
        snap = db.collection(coll).document(uid).get()
        if snap.exists:
            data = {**snap.to_dict(), **data}  # users wins over profiles
    if not data:
        return {}

    sex = str(data.get("gender") or data.get("sex") or "").lower()
    sex = "female" if sex.startswith("f") else ("male" if sex.startswith("m") else "male")

    goal_raw = str(data.get("goal") or "").lower()
    if "gain" in goal_raw or "muscle" in goal_raw or "bulk" in goal_raw:
        goal = "gain"
    elif "maintain" in goal_raw:
        goal = "maintain"
    else:
        goal = "lose"

    age = data.get("age")
    if age is None and data.get("birthYear"):
        # best-effort; a precise age needs the current date (not critical here)
        age = 2026 - int(data["birthYear"])

    return {
        "name": data.get("firstName") or data.get("name") or "there",
        "weight_kg": _num(data.get("weightKg") or data.get("weight")),
        "height_cm": _num(data.get("heightCm") or data.get("height")),
        "age": int(age) if age else None,
        "sex": sex,
        "activity_level": str(data.get("activityLevel") or "moderate").lower(),
        "goal": goal,
    }


def get_measurements(uid: str, limit: int = 8) -> dict:
    """Recent body-composition measurements from users/{uid}/bodyMeasurements."""
    db = _ensure_admin()
    docs = [d.to_dict() for d in
            db.collection("users").document(uid).collection("bodyMeasurements").stream()]
    if not docs:
        return {"status": "unavailable", "message": "No saved measurements."}

    def _ts(d):
        return d.get("date") or d.get("createdAt") or d.get("timestamp") or 0

    docs.sort(key=lambda d: str(_ts(d)))
    recent = docs[-limit:]
    rows = [{
        "weight_kg": _num(m.get("weightKg") or m.get("weight")),
        "body_fat_pct": _num(m.get("bodyFat")),
        "muscle_mass_kg": _num(m.get("muscleMass")),
    } for m in recent]
    return {"status": "success", "count": len(docs), "latest": rows[-1], "recent": rows}


def get_challenge(uid: str) -> dict:
    """The user's challenge participation (points, status, eligibility)."""
    db = _ensure_admin()
    parts = [d.to_dict() for d in
             db.collection("challengeParticipants").where("userId", "==", uid).stream()]
    if not parts:
        return {"status": "unavailable", "message": "Not in any challenge."}
    p = parts[-1]  # most relevant / latest
    return {
        "status": "success",
        "challenge_id": p.get("challengeId"),
        "participant_status": p.get("status"),
        "activity_points": p.get("activityPoints"),
        "payment_status": p.get("paymentStatus"),
        "eligible_for_prizes": p.get("eligibleForPrizes"),
        "baseline_submitted": p.get("baselineSubmitted"),
    }


# ── Tools (bound to the current logged-in user) ──────────────────────────────
def get_my_measurements() -> dict:
    """Fetch the user's recent weight and body-composition measurements
    (weight, body-fat %, muscle mass) from their account. Use this for progress,
    trends, or body-composition questions instead of asking."""
    uid = current_uid()
    if not uid:
        return {"status": "unavailable", "message": "User not signed in."}
    try:
        return get_measurements(uid)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "message": f"Could not load measurements: {e}"}


def get_my_challenge() -> dict:
    """Fetch the user's current fitness-challenge status: their activity points,
    participation status, payment status, and prize eligibility. Use this for any
    question about their challenge, points, or ranking."""
    uid = current_uid()
    if not uid:
        return {"status": "unavailable", "message": "User not signed in."}
    try:
        return get_challenge(uid)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "message": f"Could not load challenge: {e}"}
