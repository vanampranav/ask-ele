"""Local, self-contained fitness calculators exposed to Ele as tools.

These are plain Python functions. ADK reads each function's signature and
docstring to build the tool declaration the model sees, so the docstrings
below are part of the "prompt" — keep them clear.

Nothing here calls an external API or the Elefit backend. This is deliberate:
during this first testing phase Ele is fully isolated so you can judge answer
quality without any integration.

Every function returns a plain dict. By convention we include a "status" key
so the model can tell success from a validation error.
"""

from typing import Literal


def calculate_bmi(weight_kg: float, height_cm: float) -> dict:
    """Calculate Body Mass Index (BMI) and its health category.

    Args:
        weight_kg: Body weight in kilograms.
        height_cm: Height in centimetres.

    Returns:
        A dict with the BMI value (rounded to 1 decimal) and its WHO category
        (Underweight / Normal / Overweight / Obese).
    """
    if weight_kg <= 0 or height_cm <= 0:
        return {"status": "error", "message": "Weight and height must be positive."}

    height_m = height_cm / 100.0
    bmi = weight_kg / (height_m * height_m)

    if bmi < 18.5:
        category = "Underweight"
    elif bmi < 25:
        category = "Normal"
    elif bmi < 30:
        category = "Overweight"
    else:
        category = "Obese"

    return {"status": "success", "bmi": round(bmi, 1), "category": category}


def calculate_bmr_tdee(
    weight_kg: float,
    height_cm: float,
    age: int,
    sex: Literal["male", "female"],
    activity_level: Literal[
        "sedentary", "light", "moderate", "active", "very_active"
    ],
) -> dict:
    """Estimate daily calorie needs using the Mifflin-St Jeor equation.

    BMR is the calories burned at rest; TDEE is BMR multiplied by an activity
    factor and is the estimate of maintenance calories.

    Args:
        weight_kg: Body weight in kilograms.
        height_cm: Height in centimetres.
        age: Age in years.
        sex: "male" or "female".
        activity_level: One of sedentary (little/no exercise), light (1-3
            days/week), moderate (3-5 days/week), active (6-7 days/week),
            very_active (hard training / physical job).

    Returns:
        A dict with BMR and TDEE (maintenance calories), both rounded to whole
        numbers.
    """
    if weight_kg <= 0 or height_cm <= 0 or age <= 0:
        return {"status": "error", "message": "Weight, height and age must be positive."}

    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age
    bmr += 5 if sex == "male" else -161

    factors = {
        "sedentary": 1.2,
        "light": 1.375,
        "moderate": 1.55,
        "active": 1.725,
        "very_active": 1.9,
    }
    factor = factors.get(activity_level)
    if factor is None:
        return {"status": "error", "message": f"Unknown activity_level: {activity_level}"}

    tdee = bmr * factor
    return {
        "status": "success",
        "bmr": round(bmr),
        "tdee": round(tdee),
        "maintenance_calories": round(tdee),
    }


def calculate_macros(
    daily_calories: float,
    goal: Literal["lose", "maintain", "gain"],
    weight_kg: float,
) -> dict:
    """Split a daily calorie target into protein, carbs and fat grams.

    Uses a protein anchor by goal (higher protein when cutting to protect
    muscle), sets fat at ~25% of calories, and fills the rest with carbs.

    Args:
        daily_calories: Target calories for the day.
        goal: "lose" (fat loss), "maintain", or "gain" (muscle gain).
        weight_kg: Body weight in kilograms (protein is scaled to body weight).

    Returns:
        A dict with grams of protein, carbs and fat, and the protein-per-kg used.
    """
    if daily_calories <= 0 or weight_kg <= 0:
        return {"status": "error", "message": "Calories and weight must be positive."}

    protein_per_kg = {"lose": 2.0, "maintain": 1.6, "gain": 1.8}[goal]
    protein_g = protein_per_kg * weight_kg
    protein_cal = protein_g * 4

    fat_cal = daily_calories * 0.25
    fat_g = fat_cal / 9

    carbs_cal = daily_calories - protein_cal - fat_cal
    carbs_g = max(carbs_cal, 0) / 4

    return {
        "status": "success",
        "protein_g": round(protein_g),
        "carbs_g": round(carbs_g),
        "fat_g": round(fat_g),
        "protein_per_kg": protein_per_kg,
    }


def estimate_one_rep_max(weight_lifted: float, reps: int) -> dict:
    """Estimate a one-rep max (1RM) from a set using the Epley formula.

    Args:
        weight_lifted: The weight used for the set (kg or lb — unit is passed
            through unchanged).
        reps: Number of reps completed (best accuracy for 1-10 reps).

    Returns:
        A dict with the estimated 1RM (same unit as weight_lifted) and a note
        if the rep count is outside the reliable range.
    """
    if weight_lifted <= 0 or reps <= 0:
        return {"status": "error", "message": "Weight and reps must be positive."}

    one_rm = weight_lifted * (1 + reps / 30.0)
    result = {"status": "success", "one_rep_max": round(one_rm, 1)}
    if reps > 10:
        result["note"] = "Estimate is less reliable above ~10 reps."
    return result


def daily_water_intake(weight_kg: float) -> dict:
    """Estimate a daily water intake target from body weight (~35 ml/kg).

    Args:
        weight_kg: Body weight in kilograms.

    Returns:
        A dict with the recommended intake in litres, plus a reminder that
        needs rise with heat and exercise.
    """
    if weight_kg <= 0:
        return {"status": "error", "message": "Weight must be positive."}

    litres = weight_kg * 0.035
    return {
        "status": "success",
        "recommended_litres": round(litres, 1),
        "note": "Add more on hot days and around intense workouts.",
    }
