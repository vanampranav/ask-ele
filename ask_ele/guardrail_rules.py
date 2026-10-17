"""Pure guardrail detection logic — NO ADK / network dependencies.

Kept separate from guardrails.py (which wires these into ADK callbacks) so the
rules can be unit-tested offline with `python test_guardrails.py` — no Gemini key
and no API calls needed. guardrails.py imports `classify` and `is_prompt_leak`
from here.
"""

import re
from typing import Optional

# Prompt-injection / role-override / instruction-extraction attempts.
_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|prompts?|rules)",
    r"disregard\s+(all\s+|the\s+)?(previous|prior|above)?\s*(instructions|rules|prompts?)",
    r"forget\s+(all\s+|everything\s+)?(your\s+|the\s+)?(previous\s+|prior\s+)?(instructions|rules)",
    r"override\s+(all\s+|the\s+|your\s+)?(previous\s+)?(instructions|rules|settings)",
    r"(reveal|show|print|repeat|tell\s+me|give\s+me)\s+(me\s+)?(your\s+)?(system\s+)?(prompt|instructions)",
    r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions)",
    r"you\s+are\s+now\s+",
    r"from\s+now\s+on,?\s+you\s+(are|will|must|should)",
    r"pretend\s+(that\s+)?you\s+(are|have\s+no|can)",
    r"developer\s+mode",
    r"\bjailbreak\b",
    r"\bDAN\b",
    r"no\s+(restrictions|rules|limits|filter|guardrails)",
    r"without\s+(any\s+)?(restrictions|rules|limits|filter|guardrails)",
    r"\bbypass\b.{0,30}(rules|safety|filter|instructions|guardrails)",
    r"new\s+instructions?\s*:",
    r"i\s+am\s+(the\s+)?(owner|developer|admin|administrator|creator)\b.{0,60}(ignore|override|tell|give|now|so|reveal)",
    r"as\s+(the\s+)?(owner|developer|admin)\b.{0,40}(ignore|override|tell|give|reveal)",
]

# Clearly dangerous requests → steer to professional help, don't engage.
_DANGER_PATTERNS = [
    r"\banorexi",
    r"\bbulimi",
    r"\bpurg(e|ing)\b",
    r"\blaxative",
    r"starve\s+(myself|me)\b",
    r"stop\s+eating\s+(completely|entirely|altogether)",
    r"(kill|hurt|harm)\s+(myself|me)\b",
    r"\bsuicid(e|al)\b",
    r"steroid\s+(cycle|dose|dosage|stack)",
    r"how\s+much\s+(insulin|steroids?|clenbuterol|anavar|testosterone|dnp)\b",
    r"\binject(ing|ion)?\b.{0,30}(steroid|insulin|hormone|testosterone)",
]

_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)
_DANGER_RE = re.compile("|".join(_DANGER_PATTERNS), re.IGNORECASE)

# System-prompt fingerprint — if Ele's REPLY contains this, it leaked its prompt.
_PROMPT_LEAK_RE = re.compile(
    r"you are \*\*ele\*\*|# safety \(important\)|ELE_INSTRUCTION|# staying in role",
    re.IGNORECASE,
)


def classify(text: str) -> Optional[str]:
    """Classify a user message. Returns 'danger', 'injection', or None (allow).
    Danger is checked first so a dangerous request is never treated as mere
    injection."""
    if not text:
        return None
    if _DANGER_RE.search(text):
        return "danger"
    if _INJECTION_RE.search(text):
        return "injection"
    return None


def is_prompt_leak(text: str) -> bool:
    """True if a model reply appears to leak the system prompt."""
    return bool(text and _PROMPT_LEAK_RE.search(text))
