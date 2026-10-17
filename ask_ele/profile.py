"""User-profile provider for Ele — lets the agent FETCH the signed-in user's
stats (weight, height, age, sex, activity, goal) instead of asking for them.

SWAPPABLE BY DESIGN. `get_my_profile()` delegates to a ProfileProvider. Today
that's `LocalStubProvider` (fixed sample data, zero dependencies) so we can test
the flow end-to-end. In production, inject a Firebase/REST provider with the
SAME `fetch()` shape via `set_profile_provider(...)` — the tool and the prompt
don't change. This is Phase 2 of NEXT_STEPS.md ("don't make users re-type data").
"""

from typing import Protocol, runtime_checkable


@runtime_checkable
class ProfileProvider(Protocol):
    """Anything that can return the current user's profile as a dict."""

    def fetch(self) -> dict:  # pragma: no cover - interface only
        ...


class LocalStubProvider:
    """Returns a fixed sample user — stands in for the real backend during
    testing. Keep the shape identical to what the Firebase/REST provider will
    return so swapping it in later is a one-line change."""

    def fetch(self) -> dict:
        return {
            "name": "Alex",
            "weight_kg": 80.0,
            "height_cm": 178.0,
            "age": 30,
            "sex": "male",            # male | female
            "activity_level": "moderate",  # sedentary|light|moderate|active|very_active
            "goal": "lose",           # lose | maintain | gain
        }


# The active provider. In production, call set_profile_provider() at startup
# with a real backend provider (Firebase/REST) that implements .fetch().
_provider: ProfileProvider = LocalStubProvider()


def set_profile_provider(provider: ProfileProvider) -> None:
    """Swap the profile source (e.g. a real Firebase/REST provider in prod)."""
    global _provider
    _provider = provider


def get_my_profile() -> dict:
    """Fetch the current user's saved fitness profile from their account.

    Use this FIRST whenever you need the user's weight, height, age, sex,
    activity level, or goal — instead of asking them for it. Only ask the user
    for a specific value if it is missing from the returned profile.

    Returns:
        On success: status="success" plus name, weight_kg, height_cm, age,
        sex (male/female), activity_level (sedentary/light/moderate/active/
        very_active) and goal (lose/maintain/gain).
        If it can't be loaded: status="unavailable" with a message (then ask
        the user for the details you need).
    """
    try:
        p = _provider.fetch()
        if not p:
            return {
                "status": "unavailable",
                "message": "No saved profile found — ask the user for their details.",
            }
        return {"status": "success", **p}
    except Exception as e:  # noqa: BLE001 - never crash the agent on profile load
        return {"status": "unavailable", "message": f"Could not load profile: {e}"}
