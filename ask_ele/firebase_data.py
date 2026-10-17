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


# How each scoring mode earns points — so Ele can explain "how do I improve?".
_SCORING_EXPLAINER = {
    "bodyComposition":
        "Points come only from body-composition change at each approved "
        "check-in: body-fat % lost (weighted 50%), weight lost (30%), and muscle "
        "gained (20%), scaled x10. Improving beyond your personal best earns new "
        "points; a worse week adds nothing but never subtracts.",
    "bodyCompositionPlusActivity":
        "Body-composition points (body-fat 50% / weight 30% / muscle 20%, x10) "
        "PLUS daily activity: +1 each day you hit your protein goal and +1 for "
        "completing a workout.",
    "bodyCompositionPlusActivitySteps":
        "Body-composition points (body-fat 50% / weight 30% / muscle 20%, x10) "
        "PLUS daily activity: +1 for hitting your protein goal, +1 for 7,000 "
        "steps, and a weekly bonus for working out on 4 different days.",
}


def _dt(v):
    """Best-effort ISO string from a Firestore timestamp / value."""
    try:
        return v.isoformat() if hasattr(v, "isoformat") else (str(v) if v else None)
    except Exception:
        return None


def get_challenge(uid: str) -> dict:
    """The user's challenge status, enriched with the challenge details, their
    leaderboard standing, and the top of the board. Read-only; the logged-in
    user's own data + the PUBLIC (already-sanitized) leaderboard only."""
    db = _ensure_admin()
    parts = [d.to_dict() for d in
             db.collection("challengeParticipants").where("userId", "==", uid).stream()]
    if not parts:
        return {"status": "unavailable", "message": "Not in any challenge."}
    p = parts[-1]
    cid = p.get("challengeId")

    out = {
        "status": "success",
        "challenge_id": cid,
        "participant_status": p.get("status"),
        "activity_points": p.get("activityPoints"),
        "payment_status": p.get("paymentStatus"),
        "eligible_for_prizes": p.get("eligibleForPrizes"),
        "baseline_submitted": p.get("baselineSubmitted"),
    }
    if not cid:
        return out

    # 1) Challenge details (dates, status, scoring, prizes, rules).
    try:
        c = db.collection("challenges").document(cid).get()
        if c.exists:
            cd = c.to_dict()
            mode = cd.get("scoringMode", "bodyComposition")
            out["challenge"] = {
                "title": cd.get("title"),
                "status": cd.get("status"),
                "start_date": _dt(cd.get("startDate")),
                "end_date": _dt(cd.get("endDate")),
                "prize": cd.get("prizeDescription"),
                "rules_summary": cd.get("rulesSummary"),
                "scoring_mode": mode,
                "how_scoring_works": _SCORING_EXPLAINER.get(mode),
            }
    except Exception:
        pass

    # 2) The user's own standing + the top of the board (public leaderboard).
    try:
        board = sorted(
            [d.to_dict() for d in
             db.collection("challenges").document(cid).collection("leaderboard").stream()],
            key=lambda s: s.get("motivationalScore", 0) or 0, reverse=True)
        if board:
            out["total_participants"] = len(board)
            # Ranked list of names + scores (public leaderboard is already
            # sanitized for display, so this is safe to surface).
            out["top3"] = [
                {"rank": i + 1, "name": s.get("displayName"),
                 "score": round(s.get("motivationalScore", 0) or 0, 1)}
                for i, s in enumerate(board[:3])
            ]
            for i, s in enumerate(board):
                if s.get("userId") == uid:
                    rank = i + 1
                    my_score = round(s.get("motivationalScore", 0) or 0, 1)
                    gap = None
                    if rank > 1:
                        gap = round((board[i - 1].get("motivationalScore", 0) or 0)
                                    - (s.get("motivationalScore", 0) or 0), 1)
                    out["my_standing"] = {
                        "rank": rank,
                        "score": my_score,
                        "points_behind_next_rank": gap,
                        "official_score": s.get("officialScore"),
                        "body_fat_change_pct": round(s.get("bodyFatChangePercent", 0) or 0, 1),
                        "weight_loss_pct": round(s.get("weightLossPercent", 0) or 0, 1),
                        "muscle_gain_pct": round(s.get("muscleGainPercent", 0) or 0, 1),
                        "latest_checkin": s.get("latestSubmissionLabel"),
                        "last_updated": _dt(s.get("lastUpdated")),
                    }
                    break
    except Exception:
        pass

    return out


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
    """Fetch the user's full fitness-challenge picture — use this for ANY
    challenge question. Returns: their activity points, participant/payment
    status and prize eligibility; the challenge's title, start/end dates, prize,
    rules and how scoring works; their leaderboard rank, score, points behind the
    next rank, and their body-fat/weight/muscle progress; plus the top 3 of the
    board. Covers 'what's my rank/score', 'when does it end', 'what are the
    prizes/rules', 'how do I earn more points', and 'who's winning'."""
    uid = current_uid()
    if not uid:
        return {"status": "unavailable", "message": "User not signed in."}
    try:
        return get_challenge(uid)
    except Exception as e:  # noqa: BLE001
        return {"status": "unavailable", "message": f"Could not load challenge: {e}"}
