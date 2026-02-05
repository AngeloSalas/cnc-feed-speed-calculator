import math

def sfm_from_rpm(diameter_in: float, rpm: float) -> float:
    if diameter_in <= 0 or rpm <= 0:
        raise ValueError("Diameter and RPM must be > 0")
    return (math.pi * diameter_in * rpm) / 12.0

def rpm_from_sfm(diameter_in: float, sfm: float) -> float:
    if diameter_in <= 0 or sfm <= 0:
        raise ValueError("Diameter and SFM must be > 0")
    return (sfm * 12.0) / (math.pi * diameter_in)
