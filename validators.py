"""Server-side validation and input normalization for 3a2belkon."""
import re

EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
VALID_REGIONS = {"Keserwan", "Byblos", "Batroun", "Beirut", "Mount Lebanon"}
VALID_RSVP_STATUSES = {"pending", "attending", "declined"}
VALID_BUDGET_STAGES = {"Raaboun Paid", "Settled", "Planned"}
VALID_BOOKING_STATUSES = {"requested", "contacted", "confirmed", "cancelled"}
VALID_SHORTLIST_STATUSES = {"shortlisted", "visited", "top_choice", "ruled_out"}


def normalize_lebanese_phone(raw):
    """Normalize Lebanese mobile/landline input to +961XXXXXXXX format."""
    digits = re.sub(r"\D", "", str(raw or ""))
    if digits.startswith("00961"):
        digits = digits[5:]
    elif digits.startswith("961"):
        digits = digits[3:]
    if digits.startswith("0"):
        digits = digits[1:]
    if len(digits) < 7 or len(digits) > 10:
        return ""
    return "+961" + digits


def validate_signup(form):
    errors = {}
    email = str(form.get("email", "")).strip().lower()
    couple_names = str(form.get("couple_names", "")).strip()
    password = str(form.get("password", ""))
    confirm = str(form.get("confirm", ""))

    if not email:
        errors["email"] = "Email is required."
    elif len(email) > 255 or not EMAIL_RE.match(email):
        errors["email"] = "Enter a valid email address."

    if not couple_names:
        couple_names = "New Couple"
    elif len(couple_names) > 180:
        errors["couple_names"] = "Couple names must be under 180 characters."

    if not password:
        errors["password"] = "Password is required."
    elif len(password) < 8 or len(password) > 128:
        errors["password"] = "Password must be between 8 and 128 characters."

    if confirm and confirm != password:
        errors["confirm"] = "Passwords do not match."

    return errors, email, couple_names


def validate_login(form):
    errors = {}
    email = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))
    if not email:
        errors["email"] = "Email is required."
    if not password:
        errors["password"] = "Password is required."
    return errors, email


def clean_iso_date(value, fallback="2027-08-28"):
    val = str(value or "").strip()
    return val if ISO_DATE_RE.match(val) else fallback


def clean_shortlist_rating(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        r = int(value)
    except (TypeError, ValueError):
        return None
    return r if 1 <= r <= 5 else None
