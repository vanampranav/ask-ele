"""Interactive terminal chat with Ele — a resilient replacement for `adk run`.

Unlike `adk run`, this keeps ONE conversation (Ele remembers the thread) AND
retries automatically on the transient 503 / 429 errors that `adk run` crashes
on. Use this for back-and-forth testing on the free tier.

Usage:
    python chat.py          # start chatting; type 'exit' or Ctrl-C to quit

Prereqs:
    pip install -r requirements.txt
    key in ask_ele/.env  (see ask_ele/.env.example)
"""

import asyncio
import os
import re
import sys
import warnings

# Silence ADK's harmless [EXPERIMENTAL] UserWarnings so they don't look like errors.
warnings.filterwarnings("ignore")
os.environ.setdefault("GRPC_VERBOSITY", "NONE")

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "ask_ele", ".env"))

from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from ask_ele.agent import root_agent  # noqa: E402

APP_NAME = "ask_ele"
USER_ID = "tester"
SESSION_ID = "chat"
MAX_RETRIES = int(os.environ.get("ELE_RETRIES", "5"))


def _is_retryable(err: Exception) -> bool:
    s = str(err)
    return any(c in s for c in ("429", "RESOURCE_EXHAUSTED", "503", "UNAVAILABLE", "500", "INTERNAL"))


def _retry_seconds(err: Exception, default: float) -> float:
    m = re.search(r"retry in ([\d.]+)s", str(err)) or re.search(r"retryDelay['\"]?:?\s*['\"]?([\d.]+)s", str(err))
    return float(m.group(1)) + 2 if m else default


async def _send(runner, question):
    content = types.Content(role="user", parts=[types.Part(text=question)])
    out = ""
    async for event in runner.run_async(user_id=USER_ID, session_id=SESSION_ID, new_message=content):
        if event.is_final_response() and event.content and event.content.parts:
            out = "".join(p.text or "" for p in event.content.parts)
    return out.strip()


async def _send_with_retry(runner, question):
    for attempt in range(MAX_RETRIES):
        try:
            return await _send(runner, question)
        except Exception as e:
            if _is_retryable(e) and attempt < MAX_RETRIES - 1:
                is_rate = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                wait = _retry_seconds(e, default=35 if is_rate else 8 * (attempt + 1))
                reason = "rate-limited (5/min)" if is_rate else "model busy (503)"
                print(f"  …{reason}; retrying in {wait:.0f}s ({attempt + 2}/{MAX_RETRIES})…")
                await asyncio.sleep(wait)
                continue
            return f"[ERROR: {e}]"


async def main():
    session_service = InMemorySessionService()
    runner = Runner(agent=root_agent, app_name=APP_NAME, session_service=session_service)
    await session_service.create_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)

    print(f"Chatting with Ele (model: {os.environ.get('ELE_MODEL', 'gemini-flash-latest')}).")
    print("Type your message. 'exit' or Ctrl-C to quit.\n")

    while True:
        try:
            q = input("you › ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye 👋")
            return
        if not q:
            continue
        if q.lower() in ("exit", "quit"):
            print("bye 👋")
            return

        # Show a live "thinking" ticker so a slow 503-retry doesn't look frozen.
        async def _ticker():
            n = 0
            while True:
                await asyncio.sleep(1)
                n += 1
                print(f"\r  …Ele is thinking ({n}s)   ", end="", flush=True)

        tick = asyncio.create_task(_ticker())
        try:
            answer = await _send_with_retry(runner, q)
        finally:
            tick.cancel()
            print("\r" + " " * 40 + "\r", end="")  # clear the ticker line
        print(f"\nEle › {answer}\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nbye 👋")
        sys.exit(0)
