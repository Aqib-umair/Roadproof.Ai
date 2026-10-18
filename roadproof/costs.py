"""Illustrative volume calculation; these are editable teaching assumptions."""
from math import isfinite


def estimate(length_cm, width_cm, depth_cm, rate, method):
    values = (length_cm, width_cm, depth_cm, rate)
    if not all(isfinite(float(v)) and float(v) > 0 for v in values):
        raise ValueError("Enter positive, finite dimensions and a material rate.")
    if method not in {"Measured on site", "Calibrated survey"}:
        raise ValueError("A measured or calibrated survey is required for this illustration.")
    volume = length_cm * width_cm * depth_cm / 1_000_000
    return {"volume_m3": volume, "rate_per_m3": rate, "waste_factor": 1.15,
            "amount": round(volume * rate * 1.15, 2), "method": method}
