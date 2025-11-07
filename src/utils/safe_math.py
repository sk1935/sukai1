def to_float(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def safe_mul(a, b, default=0.0):
    if a is None or b is None:
        return default
    try:
        return float(a) * float(b)
    except Exception:
        return default


def safe_add(a, b, default=0.0):
    try:
        return float(a or 0.0) + float(b or 0.0)
    except Exception:
        return default
