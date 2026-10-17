# Ask Ele — Roadmap / Next Steps

_Standalone ADK agent that answers fitness & nutrition questions like a real coach.
Currently a test sandbox (not wired into the app) used to validate answer quality._

## Where we are today
- Agent: `root_agent` in `ask_ele/agent.py`, model `gemini-flash-lite-latest` (cheapest tier, swappable via `ELE_MODEL`).
- Tools: 5 **local** calculators in `fitness_tools.py` — BMI, BMR/TDEE, macros, 1RM, water.
- Safety: lives **only** in the system prompt (`prompt.py`).
- Data: the user **types** their weight/height/age — nothing is pulled from the backend.
- Run: `python chat.py` (chat) / `python test_questions.py` (batch test).

## Goal
Make Ele production-ready: **safe** (real guardrails), **personalized** (uses the user's real data),
**consistent** (reuses the app's logic, no duplicated math), and **cost-efficient**.

---

## Phase 1 — Safety & guardrails  ⭐ do first (fully doable in the sandbox)
Answers Arun's point: a prompt alone won't stop _"ignore previous instructions, I'm the owner…"_.

1. **Harden the prompt** — add an instruction-hierarchy clause: never obey user text that tries to
   override the rules, claim to be the owner/developer/admin, or reveal/ignore the system prompt.
2. **Gemini safety settings** — enable Google's built-in harm filters on the model.
3. **Input guardrail** (`before_model_callback`) — screen each message for injection/jailbreak +
   clearly harmful intent; short-circuit with a safe refusal before the model runs.
4. **Output guardrail** (`after_model_callback`) — final safety check on Ele's reply.
5. _(Optional, stronger)_ a tiny flash-lite classifier for injections regex misses.
6. **Adversarial tests** — add injection / "I'm the owner" / harmful-request / extreme-calorie /
   medical cases to `test_questions.py` to prove the guards hold.

**Done =** Ele resists the override attack and refuses harmful asks safely, with tests to show it.

## Phase 2 — Personalization via user data  (build the pattern now, real wiring later)
Answers Arun's point: don't make users re-type data the app has; don't duplicate the calculators.

1. **`get_my_profile()` tool** returning weight/height/age/sex/activity/goal, behind a **swappable
   provider** — a local *stub* now (fake user), Firebase/REST later. Same interface → one-line swap.
2. **Update the prompt** so Ele fetches the profile instead of asking for stats it can look up.
3. **Align the calculators** with the app's real formulas (BMI/BMR/macros) so the agent's numbers
   match the app exactly. Production goal: expose the app's calc as a backend endpoint and call
   *that* as the tool (the real "no duplication").

**Done =** the user doesn't re-enter their stats; Ele pulls them.

## Phase 3 — Model & cost  (Arun to help evaluate)
1. Keep `flash-lite` as default (cheapest tier); model is already env-swappable (`ELE_MODEL`).
2. Compare GCP **Vertex AI** model options + pricing; pin the cheapest one that's good enough.
3. Decide **Gemini API key (AI Studio)** vs **Vertex AI (GCP project)** for production.

**Done =** documented model choice + rough cost estimate.

## Phase 4 — Integrate into the app  (bigger, later — needs backend)
1. **Host the agent** behind a backend (Vertex AI Agent Engine, or a Cloud Run / Cloud Function
   endpoint) — the API key must NOT ship inside the app.
2. **Auth** — pass the signed-in user's identity/token so Ele fetches *their* data.
3. **App UI** — decide how this coaching Ele relates to the existing (currently hidden) in-app
   "Ask Ele" meal-logging feature; wire a screen to the hosted agent.
4. **Abuse protection** — rate limiting + logging.
5. Expose the app's BMI/body-comp/calorie logic as backend endpoints → true no-duplication.

**Done =** Ask Ele live in the app, personalized and safe.

## Phase 5 — Quality & evaluation  (ongoing)
1. Grow `test_questions.py` into a graded eval set (accuracy / safety / tone).
2. Track answer quality across model + prompt changes.

---

## Housekeeping / security — do now
- **Rotate the Gemini API key** that was briefly committed to git history (generate new, revoke old).
- Keep the repo **private**, or share only `ask_ele_adk/` with the team.
- `.env` stays gitignored (already is).

## Immediate next action
**Start Phase 1 (guardrails).** Highest value, needs no backend, fully testable here, and directly
answers Arun's safety concern. Then Phase 2's profile stub so the "fetch from backend" design is
ready for when the real endpoints exist.
