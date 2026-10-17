"""Local test console for Ele — a simple web UI (Streamlit).

Set the user profile in the sidebar, chat with Ele in the main panel, and see
which tools it called (so you can confirm it fetched the profile and used the
calculators). Use it to judge answer quality.

Run:
    pip install streamlit          # one-time
    streamlit run web_test.py      # opens http://localhost:8501

Uses the same Gemini key in ask_ele/.env that chat.py / adk web use.
"""

import asyncio
import os
import warnings

warnings.filterwarnings("ignore")
os.environ.setdefault("GRPC_VERBOSITY", "NONE")

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "ask_ele", ".env"))

import streamlit as st  # noqa: E402

# When deployed (Streamlit Community Cloud / Hugging Face Spaces) there's no .env
# file — the Gemini key comes from the host's SECRETS. Copy them into the
# environment BEFORE the agent is imported (which configures the model).
try:
    for _k in ("GOOGLE_API_KEY", "GEMINI_API_KEY", "ELE_MODEL",
               "GOOGLE_GENAI_USE_VERTEXAI",
               "FIREBASE_API_KEY", "FIREBASE_SERVICE_ACCOUNT"):
        if not os.environ.get(_k) and _k in st.secrets:
            os.environ[_k] = str(st.secrets[_k])
except Exception:
    pass  # no secrets configured (e.g. local run) → rely on .env / env vars

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from ask_ele.agent import root_agent  # noqa: E402
from ask_ele.profile import set_profile_provider, FirebaseProfileProvider  # noqa: E402
from ask_ele.firebase_data import verify_login, set_current_uid  # noqa: E402

APP_NAME, USER_ID, SESSION_ID = "ask_ele", "tester", "web"


# ── Profile provider driven by the sidebar form ──────────────────────────────
class _DictProvider:
    def __init__(self, data):
        self.data = data

    def fetch(self):
        return self.data


# ── Agent call (collects the final text + which tools were called) ───────────
def _retryable(e):
    s = str(e)
    return any(c in s for c in
               ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL"))


async def _ensure_session(svc):
    try:
        await svc.create_session(app_name=APP_NAME, user_id=USER_ID,
                                 session_id=SESSION_ID)
    except Exception:
        pass  # already exists


async def _send(runner, svc, text):
    await _ensure_session(svc)
    content = types.Content(role="user", parts=[types.Part(text=text)])
    out, tools = "", []
    async for ev in runner.run_async(user_id=USER_ID, session_id=SESSION_ID,
                                     new_message=content):
        if ev.content and ev.content.parts:
            for p in ev.content.parts:
                fc = getattr(p, "function_call", None)
                if fc and getattr(fc, "name", None):
                    tools.append(fc.name)
        if ev.is_final_response() and ev.content and ev.content.parts:
            out = "".join(p.text or "" for p in ev.content.parts)
    return out.strip(), tools


async def _send_with_retry(runner, svc, text, max_retries=5):
    last = None
    for attempt in range(max_retries):
        try:
            return await _send(runner, svc, text)
        except Exception as e:  # noqa: BLE001
            last = e
            if _retryable(e) and attempt < max_retries - 1:
                await asyncio.sleep(min(2 ** attempt, 20))
                continue
            raise
    raise last


# ── Streamlit app ────────────────────────────────────────────────────────────
st.set_page_config(page_title="Ask Ele — Test", page_icon="💪", layout="centered")

if "svc" not in st.session_state:
    st.session_state.svc = InMemorySessionService()
    st.session_state.runner = Runner(
        agent=root_agent, app_name=APP_NAME, session_service=st.session_state.svc)
    st.session_state.history = []  # list of dicts: {role, text, tools}


def _reset_chat():
    st.session_state.svc = InMemorySessionService()
    st.session_state.runner = Runner(
        agent=root_agent, app_name=APP_NAME, session_service=st.session_state.svc)
    st.session_state.history = []


with st.sidebar:
    st.header("🔐 Account")
    if st.session_state.get("uid"):
        st.success(f"Logged in: {st.session_state.get('email')}")
        st.caption("Ele is using your REAL Elefit data (profile, measurements, "
                   "challenge).")
        if st.button("Log out", use_container_width=True):
            st.session_state.pop("uid", None)
            st.session_state.pop("email", None)
            _reset_chat()
            st.rerun()
    else:
        st.caption("Log in with your Elefit account to use your real data — "
                   "or use the manual profile below.")
        with st.form("login"):
            li_email = st.text_input("Email")
            li_pw = st.text_input("Password", type="password")
            if st.form_submit_button("Log in", use_container_width=True):
                res = verify_login(li_email.strip(), li_pw)
                if res.get("status") == "success":
                    st.session_state.uid = res["uid"]
                    st.session_state.email = res.get("email", li_email)
                    _reset_chat()
                    st.rerun()
                else:
                    st.error(res.get("message", "Login failed"))

    st.divider()
    st.header("👤 Manual profile")
    st.caption("Used only when you're NOT logged in.")
    name = st.text_input("Name", "Alex")
    weight = st.number_input("Weight (kg)", 30.0, 300.0, 80.0, 0.5)
    height = st.number_input("Height (cm)", 100.0, 250.0, 178.0, 0.5)
    age = st.number_input("Age", 10, 100, 30, 1)
    sex = st.selectbox("Sex", ["male", "female"])
    activity = st.selectbox(
        "Activity level",
        ["sedentary", "light", "moderate", "active", "very_active"], index=2)
    goal = st.selectbox("Goal", ["lose", "maintain", "gain"])
    st.divider()
    st.button("🔄 Reset chat", on_click=_reset_chat, use_container_width=True)
    st.caption(f"Model: {os.environ.get('ELE_MODEL', 'gemini-flash-lite-latest')}")

# Pick the data source for THIS run: real Firebase data when logged in, else the
# manual stub profile. (Re-set every run so the agent's tools use the right user.)
if st.session_state.get("uid"):
    set_current_uid(st.session_state["uid"])
    set_profile_provider(FirebaseProfileProvider(st.session_state["uid"]))
else:
    set_current_uid(None)
    set_profile_provider(_DictProvider({
        "name": name, "weight_kg": weight, "height_cm": height, "age": int(age),
        "sex": sex, "activity_level": activity, "goal": goal,
    }))

st.title("💪 Ask Ele — test console")
st.caption("Set the profile on the left, then ask away. Tool calls show under "
           "each answer so you can confirm it used the profile + calculators.")

# Replay history.
for msg in st.session_state.history:
    with st.chat_message(msg["role"]):
        st.markdown(msg["text"])
        if msg.get("tools"):
            st.caption("🔧 tools: " + ", ".join(msg["tools"]))

# New message.
prompt = st.chat_input("Ask about training, nutrition, macros, BMI…")
if prompt:
    st.session_state.history.append({"role": "user", "text": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner("Ele is thinking…"):
            try:
                reply, tools = asyncio.run(
                    _send_with_retry(st.session_state.runner,
                                     st.session_state.svc, prompt))
            except Exception as e:  # noqa: BLE001
                reply, tools = f"⚠️ Error: {e}", []
        st.markdown(reply or "[no response]")
        if tools:
            st.caption("🔧 tools: " + ", ".join(tools))
    st.session_state.history.append(
        {"role": "assistant", "text": reply, "tools": tools})
