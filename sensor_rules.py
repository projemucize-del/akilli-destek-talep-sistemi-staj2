"""Protez el sensör okumaları için doğrulama ve eşik kuralları."""

LIMITS = {
    "emg": (0.0, 100.0),
    "force": (0.0, 100.0),
    "current": (0.0, 5.0),
    "position": (0.0, 180.0),
    "battery": (0.0, 100.0),
}


def normalize_reading(data):
    errors = {}
    clean = {}
    for key, (minimum, maximum) in LIMITS.items():
        try:
            value = float(data.get(key, ""))
        except (TypeError, ValueError):
            errors[key] = "Sayısal bir değer girilmelidir."
            continue
        if not minimum <= value <= maximum:
            errors[key] = f"Değer {minimum:g}-{maximum:g} aralığında olmalıdır."
        clean[key] = round(value, 3)
    return clean, errors


def evaluate_reading(reading):
    warnings = []
    if reading["force"] >= 80:
        warnings.append("Kavrama kuvveti üst sınıra yaklaştı")
    if reading["current"] >= 2.5:
        warnings.append("Motor akımı yüksek")
    if reading["battery"] <= 20:
        warnings.append("Batarya seviyesi düşük")
    if reading["emg"] >= 90:
        warnings.append("EMG seviyesi yüksek")
    level = "Kritik" if reading["current"] >= 3.5 or reading["force"] >= 95 else "Uyarı" if warnings else "Normal"
    return {"level": level, "message": "; ".join(warnings) if warnings else "Sınırlar normal"}
