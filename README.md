# Ask Ele — ADK test sandbox

A **standalone** Google ADK (Agent Development Kit) project for testing an
"Ask Ele" fitness coach agent. It is **not integrated** with the Elefit app,
Firebase, FatSecret, or the AI-coach backend — on purpose. The goal of this
first phase is only to judge **answer quality** on real fitness questions
before deciding how (or whether) to build it into the app.

It lives in its own folder and touches nothing in the Flutter project.

```
ask_ele_adk/
├── ask_ele/                 # the agent package (ADK loads this)
│   ├── __init__.py
│   ├── agent.py             # root_agent = the Ele coach
│   ├── prompt.py            # Ele's system instruction  <-- tune answers here
│   ├── fitness_tools.py     # local BMI / calorie / macro / 1RM / water tools
│   ├── .env.example         # copy to .env and add your key
│   └── .env                 # (you create this — gitignored)
├── test_questions.py        # batch-run ~19 fitness Qs and save the answers
├── requirements.txt
└── results/                 # saved transcripts (gitignored)
```

---

## Setup (one time, ~5 minutes)

1. **Python 3.10+** required. From inside this folder:

   ```bash
   cd ask_ele_adk
   python3 -m venv .venv
   source .venv/bin/activate          # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Get a free Gemini API key** at <https://aistudio.google.com/apikey>.

3. **Add the key:**

   ```bash
   cp ask_ele/.env.example ask_ele/.env
   ```

   Open `ask_ele/.env` and paste your key into `GOOGLE_API_KEY=`.

---

## Two ways to test

### A) Interactive chat UI (best for exploring)

```bash
# from the ask_ele_adk/ folder, with the venv active
adk web
```

Open the printed URL (usually <http://localhost:8000>), pick **ask_ele** from
the dropdown, and chat. You can see when Ele calls a tool (BMI, calories, etc.)
and follow up naturally. Great for poking at edge cases. If a request hits a
`503` (model busy), the UI just shows an error and keeps running — resend it.

Prefer the terminal? Use **`python chat.py`** (NOT `adk run`). `chat.py` keeps
one conversation AND auto-retries on 503/429. `adk run` has no retry and crashes
the whole process on a single busy-model error.

### B) Batch question run (best for judging quality)

```bash
python test_questions.py
```

This runs a curated set of ~19 fitness questions — nutrition, training,
plateaus, supplements, the calculator tools, and **three safety cases**
(knee pain, diabetes, crash dieting) where the right answer is a careful
deferral to a professional. Each answer prints to the terminal **and** is saved
to `results/run_<timestamp>.md` so you can read through them calmly.

Ask a single one-off question:

```bash
python test_questions.py "Is fasted cardio better for fat loss?"
```

---

## Tuning while you test

- **Change Ele's behavior/voice/rules:** edit `ask_ele/prompt.py`. This is where
  most of the tuning happens. Re-run and compare.
- **Switch models:** set `ELE_MODEL` before running. Default is
  `gemini-flash-lite-latest` — chosen because the regular flash models are
  heavily overloaded right now and 503 constantly on the free tier, while lite
  responds reliably.
  ```bash
  ELE_MODEL=gemini-flash-latest python test_questions.py   # higher quality (503s more now)
  ```
  Verified working on your key: `gemini-flash-lite-latest` (default, reliable),
  `gemini-flash-latest` and `gemini-3.8-flash` (higher quality, but 503-prone).
  Newer API keys no longer have access to the older `gemini-2.x` models.
- **Add/adjust calculators:** edit `ask_ele/fitness_tools.py`. Any plain Python
  function with type hints + a docstring becomes a tool automatically.

---

## What to look for when judging

- Are the numbers right (does it actually *use* the tools vs. guessing)?
- Does it ask for missing info before giving a personalized plan?
- Are the safety cases handled responsibly (defer to a doctor/physio, discourage
  crash diets) — not just confidently answered?
- Is the tone right for your users, and are veg/Indian options offered where
  relevant?
- Where does it go wrong, get vague, or make things up? Note these — they drive
  the next decision (better prompt, better model, or real tools/RAG).

---

## Next step (when you're happy with answers)

This classic `google-adk` sandbox is intentionally lightweight. When you decide
to move toward something deployable, the next step is Google's
**`google-agents-cli`** scaffold (FastAPI service + Docker + an eval dataset
framework) — see the notes your developer has, or
<https://adk.dev/get-started/agents-cli/>. At that point we'd also wire in real
tools (FatSecret food lookup, the user's own weight/workout data) instead of the
local calculators here.
