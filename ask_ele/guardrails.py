"""Safety guardrails for Ele — defense that lives OUTSIDE the system prompt.

Two layers wrap every model call:
  • before_model_guardrail — screens the USER message for prompt-injection /
    jailbreak attempts and clearly dangerous requests, and short-circuits with a
    safe, in-character reply BEFORE the model is ever called.
  • after_model_guardrail  — a safety net on Ele's REPLY: catches a leaked system
    prompt or an empty/safety-blocked response and returns something graceful.

These are fast, free, deterministic heuristic (regex) checks — a FIRST line of
defense layered on top of the hardened prompt (prompt.py) and Gemini's built-in
safety settings (agent.py). A stronger setup would add an LLM-based injection
classifier here too (see NEXT_STEPS.md, Phase 1 step 5).
"""

from __future__ import annotations

from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from google.genai import types

from .guardrail_rules import classify, is_prompt_leak

# ── Refusal messages (kept in Ele's warm, in-character voice) ─────────────────
_REFUSE_INJECTION = (
    "I can't change my instructions or step outside my role as your fitness "
    "coach 💪 — but I'm here for anything training, nutrition, or body-composition "
    "related. What would you like to work on?"
)
_REFUSE_DANGER = (
    "I really want to keep you safe, so I'm not able to help with that — what "
    "you're describing can be genuinely harmful. Please reach out to a doctor, a "
    "registered dietitian, or a mental-health professional, and if you're in "
    "crisis please contact your local emergency services or a helpline right "
    "away. I'm glad to help with safe, healthy training and nutrition whenever "
    "you're ready. 🤍"
)
_FALLBACK_BLOCKED = (
    "I wasn't able to answer that one safely. Could you rephrase it, or ask me "
    "something about training, nutrition, or your goals? Happy to help. 💪"
)


def _latest_user_text(llm_request: LlmRequest) -> str:
    """The most recent user message text in the request (best-effort)."""
    try:
        for content in reversed(llm_request.contents or []):
            if content.role == "user" and content.parts:
                return " ".join(p.text or "" for p in content.parts if p.text)
    except Exception:
        pass
    return ""


def _reply(text: str) -> LlmResponse:
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=text)])
    )


def before_model_guardrail(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """Input guardrail. Returns a canned reply to short-circuit the model, or
    None to let the request proceed normally."""
    verdict = classify(_latest_user_text(llm_request))
    if verdict == "danger":
        return _reply(_REFUSE_DANGER)
    if verdict == "injection":
        return _reply(_REFUSE_INJECTION)
    return None


def after_model_guardrail(
    callback_context: CallbackContext, llm_response: LlmResponse
) -> Optional[LlmResponse]:
    """Output guardrail. Catches a leaked system prompt or an empty/blocked reply.
    Returns a replacement LlmResponse, or None to keep the model's response."""
    # Don't act on streaming partials — only the final/full response.
    if getattr(llm_response, "partial", False):
        return None
    try:
        parts = (llm_response.content.parts
                 if llm_response and llm_response.content and
                 llm_response.content.parts else [])
    except Exception:
        parts = []

    # A TOOL-CALL turn carries a function_call and no text — that's a normal
    # intermediate step (e.g. fetching the profile), NOT a blocked answer. Leave
    # it alone, otherwise we'd kill every tool use.
    if any(getattr(p, "function_call", None) for p in parts):
        return None

    text = "".join(p.text or "" for p in parts if getattr(p, "text", None))
    if not text.strip():
        # Genuinely empty — e.g. Gemini's safety filter blocked the output.
        return _reply(_FALLBACK_BLOCKED)
    if is_prompt_leak(text):
        return _reply(_REFUSE_INJECTION)
    return None
