TRIGGER_MANUAL = "manual"
TRIGGER_AUTOMATIC = "automatic"


def normalize_trigger_type(value, default=TRIGGER_AUTOMATIC):
    normalized = str(value or default).strip().lower()
    if normalized == TRIGGER_MANUAL:
        return TRIGGER_MANUAL
    return TRIGGER_AUTOMATIC
