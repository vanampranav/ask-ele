"""The Ele agent definition.

`root_agent` is the name ADK looks for. `adk web` and `adk run ask_ele` both
load this module and start a chat session with it.
"""

import os

from google.adk.agents import Agent
from google.genai import types

from .prompt import ELE_INSTRUCTION
from .guardrails import before_model_guardrail, after_model_guardrail
from .profile import get_my_profile
from .fitness_tools import (
    calculate_bmi,
    calculate_bmr_tdee,
    calculate_macros,
    estimate_one_rep_max,
    daily_water_intake,
)

# Model is configurable so you can A/B test answer quality without editing code:
#   ELE_MODEL=gemini-flash-latest adk web     # higher quality, but 503s a lot now
# Default is `gemini-flash-lite-latest` — right now the regular flash models are
# heavily overloaded and 503 constantly on the free tier, while the LITE model
# responds reliably. Lite is slightly lower quality but good enough to judge
# answers; switch to gemini-flash-latest via ELE_MODEL once demand settles (or
# once billing is enabled). Newer keys can't use the gemini-2.x models.
MODEL = os.environ.get("ELE_MODEL", "gemini-flash-lite-latest")

# Gemini's built-in harm filters — a second safety layer under our own guardrails
# (guardrails.py) and the hardened prompt (prompt.py). If Gemini blocks a response,
# after_model_guardrail turns the empty result into a graceful message.
_SAFETY_SETTINGS = [
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
        threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
    types.SafetySetting(
        category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    ),
]

root_agent = Agent(
    name="ask_ele",
    model=MODEL,
    description="Ele — a fitness and nutrition coach for the Elefit app.",
    instruction=ELE_INSTRUCTION,
    generate_content_config=types.GenerateContentConfig(
        safety_settings=_SAFETY_SETTINGS,
    ),
    # Guardrails that run around every model call (see guardrails.py).
    before_model_callback=before_model_guardrail,
    after_model_callback=after_model_guardrail,
    tools=[
        get_my_profile,
        calculate_bmi,
        calculate_bmr_tdee,
        calculate_macros,
        estimate_one_rep_max,
        daily_water_intake,
    ],
)
