"""
helpers.py -- Shared session, CSRF, OAuth, RBAC, and SQLAlchemy serialization helpers
for 3a2belkon's modular Flask Blueprints.
"""
from datetime import date
from functools import wraps
import glob
import hmac
import json
import os
import secrets

from authlib.integrations.flask_client import OAuth
from dotenv import dotenv_values
from flask import abort, current_app, flash, jsonify, redirect, request, session, url_for
from sqlalchemy import func, or_

from models import (
    AppSetting,
    ServiceProvider,
    User,
    VenueCatalog,
    VenueProvider,
    db,
)

DAILY_AI_LIMIT = 15

oauth = OAuth()
_REPO_DIR = os.path.dirname(os.path.abspath(__file__))


def init_oauth(app):
    """Initialize Authlib Google OpenID Connect client."""
    app.config.setdefault("GOOGLE_CLIENT_ID", os.environ.get("GOOGLE_CLIENT_ID", "").strip())
    app.config.setdefault("GOOGLE_CLIENT_SECRET", os.environ.get("GOOGLE_CLIENT_SECRET", "").strip())
    oauth.init_app(app)
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )


def _discover_client_secret_json():
    """Auto-detect a Google Cloud Console client_secret*.json file if placed in the project."""
    search_dirs = [_REPO_DIR, os.path.dirname(_REPO_DIR)]
    for d in search_dirs:
        for path in sorted(glob.glob(os.path.join(d, "client_secret*.json"))):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    raw = json.load(fh)
                block = raw.get("web") or raw.get("installed") or {}
                cid = str(block.get("client_id") or "").strip()
                csec = str(block.get("client_secret") or "").strip()
                if cid and csec:
                    return cid, csec
            except Exception:
                continue
    return "", ""


def resolve_google_oauth_credentials():
    """
    Resolve Google OAuth 2.0 Client ID & Secret dynamically without requiring a server restart:
      1. Environment variables / live .env file
      2. Google Cloud Console client_secret*.json file
      3. Server-side AppSetting rows (google_client_id / google_client_secret)
    """
    env_file = os.path.join(_REPO_DIR, ".env")
    dotenv_map = dotenv_values(env_file) if os.path.exists(env_file) else {}

    cid = (
        os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        or str(dotenv_map.get("GOOGLE_CLIENT_ID") or "").strip()
        or str(current_app.config.get("GOOGLE_CLIENT_ID", "")).strip()
    )
    csec = (
        os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
        or str(dotenv_map.get("GOOGLE_CLIENT_SECRET") or "").strip()
        or str(current_app.config.get("GOOGLE_CLIENT_SECRET", "")).strip()
    )

    if not (cid and csec):
        j_cid, j_csec = _discover_client_secret_json()
        if j_cid and j_csec:
            cid, csec = j_cid, j_csec

    if not (cid and csec):
        row_id = db.session.get(AppSetting, "google_client_id")
        row_sec = db.session.get(AppSetting, "google_client_secret")
        if row_id and row_sec and row_id.value.strip() and row_sec.value.strip():
            cid = row_id.value.strip()
            csec = row_sec.value.strip()

    return cid, csec


def is_google_oauth_configured():
    """Sync resolved Google OAuth credentials into Flask/Authlib and return True when ready."""
    cid, csec = resolve_google_oauth_credentials()
    if cid and csec:
        current_app.config["GOOGLE_CLIENT_ID"] = cid
        current_app.config["GOOGLE_CLIENT_SECRET"] = csec
        client = oauth.create_client("google")
        if client is not None:
            client.client_id = cid
            client.client_secret = csec
        return True
    return False


# ---------- Session, RBAC & CSRF Helpers ------------------------------------

def get_current_user():
    uid = session.get("user_id")
    if not uid:
        return None
    return db.session.get(User, int(uid))


def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def verify_csrf():
    expected = session.get("_csrf_token", "")
    supplied = (
        request.headers.get("X-CSRFToken")
        or request.form.get("csrf_token")
        or (request.get_json(silent=True) or {}).get("csrf_token")
        or ""
    )
    if not expected or not supplied or not hmac.compare_digest(str(expected), str(supplied)):
        if request.accept_mimetypes.best == "application/json" or request.is_json:
            abort(400, description="Invalid or missing CSRF token.")
        flash("Your session expired. Please try again.")
        abort(400)


def wants_json():
    return (
        request.is_json
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or "application/json" in request.headers.get("Accept", "")
    )


def _safe_internal_next(raw_next, default="/dashboard"):
    val = str(raw_next or "").strip()
    if val in ("map", "/map"):
        return "/map"
    if val in ("dashboard", "/dashboard"):
        return "/dashboard"
    if val in ("profile", "/profile"):
        return "/profile"
    if val in ("home", "/"):
        return "/"
    if val.startswith("/") and not val.startswith("//") and "\\" not in val:
        return val
    return default


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        user = get_current_user()
        if not user or not user.wedding:
            session.pop("user_id", None)
            if wants_json():
                return jsonify({"ok": False, "error": "Please sign in to continue."}), 401
            return redirect(url_for("auth.auth_page", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def generate_rsvp_token():
    alphabet = "abcdefghjkmnpqrstuvwxyz23456789"
    return "".join(secrets.choice(alphabet) for _ in range(14))


def get_currency_prefs():
    curr = session.get("currency", "USD")
    if curr not in ("USD", "LBP"):
        curr = "USD"
    try:
        rate = int(session.get("lbp_rate", 89500))
        if rate < 1000:
            rate = 89500
    except (TypeError, ValueError):
        rate = 89500
    return curr, rate


def get_stored_geoapify_key():
    row = db.session.get(AppSetting, "geoapify_key")
    return row.value.strip() if (row and row.value) else ""


# ---------- Public & Couple Serializers --------------------------------------

def serialize_venue_row(v):
    prov_codes = [vp.provider.code for vp in v.provider_links if vp.provider and vp.provider.is_active]
    booked_isos = sorted({bd.iso_date for bd in v.booked_dates})
    return {
        "id": v.code,
        "dbId": v.id,
        "name": v.name,
        "region": v.region,
        "addressQuery": v.address_query,
        "setting": v.setting,
        "cap": v.capacity_label,
        "usd": float(v.starting_price_usd),
        "nextOpen": v.next_open_label,
        "lat": float(v.lat) if v.lat is not None else None,
        "lon": float(v.lon) if v.lon is not None else None,
        "apiPlaceId": v.api_place_id or "",
        "sketch": v.sketch_path,
        "providers": prov_codes,
        "booked": booked_isos,
    }


def serialize_provider_row(p):
    """Serialize public provider metadata — external phone/WhatsApp is NEVER exposed."""
    return {
        "id": p.code,
        "dbId": p.id,
        "name": p.name,
        "cat": p.category,
        "city": p.city,
        "price": float(p.starting_price_usd),
        "unit": p.price_unit,
        "bio": p.description,
    }


def serialize_public_catalog():
    providers_rows = ServiceProvider.query.filter_by(is_active=True).order_by(ServiceProvider.id.asc()).all()
    venues_rows = VenueCatalog.query.order_by(VenueCatalog.id.asc()).all()
    return (
        [serialize_provider_row(p) for p in providers_rows],
        [serialize_venue_row(v) for v in venues_rows],
    )


def parse_venue_filters_from_url():
    q = request.args.get("q", "").strip()
    region = request.args.get("region", "").strip()
    setting = request.args.get("setting", "").strip()
    traiteur_id = request.args.get("traiteur_id", "").strip()
    photographer_id = request.args.get("photographer_id", "").strip()
    zaffe_id = request.args.get("zaffe_id", "").strip()

    hero_prov = request.args.get("provider", "").strip()
    if hero_prov:
        p = ServiceProvider.query.filter_by(code=hero_prov, is_active=True).first()
        if p:
            if p.category == "traiteur" and not traiteur_id:
                traiteur_id = p.code
            elif p.category == "photographer" and not photographer_id:
                photographer_id = p.code
            elif p.category == "zaffe" and not zaffe_id:
                zaffe_id = p.code

    return {
        "q": q,
        "region": region,
        "setting": setting,
        "traiteur_id": traiteur_id,
        "photographer_id": photographer_id,
        "zaffe_id": zaffe_id,
    }


def query_filtered_venues_sql(filters):
    query = VenueCatalog.query

    if filters["q"]:
        pattern = f"%{filters['q']}%"
        query = query.filter(
            or_(VenueCatalog.name.ilike(pattern), VenueCatalog.region.ilike(pattern))
        )
    if filters["region"]:
        query = query.filter(VenueCatalog.region == filters["region"])
    if filters["setting"]:
        query = query.filter(VenueCatalog.setting == filters["setting"])

    selected_codes = [
        c for c in (filters["traiteur_id"], filters["photographer_id"], filters["zaffe_id"]) if c
    ]
    if selected_codes:
        prov_rows = ServiceProvider.query.filter(
            ServiceProvider.code.in_(selected_codes),
            ServiceProvider.is_active.is_(True),
        ).all()
        if len(prov_rows) != len(set(selected_codes)):
            return []
        prov_ids = [p.id for p in prov_rows]
        matching_venue_ids = (
            db.session.query(VenueProvider.venue_id)
            .filter(VenueProvider.provider_id.in_(prov_ids))
            .group_by(VenueProvider.venue_id)
            .having(func.count(func.distinct(VenueProvider.provider_id)) == len(prov_ids))
            .subquery()
        )
        query = query.filter(VenueCatalog.id.in_(db.session.query(matching_venue_ids.c.venue_id)))

    rows = query.order_by(VenueCatalog.id.asc()).all()
    return [serialize_venue_row(v) for v in rows]


def parse_service_filters_from_url():
    return {
        "q": request.args.get("q", "").strip(),
        "category": request.args.get("category", "").strip(),
        "city": request.args.get("city", "").strip(),
        "venue_code": request.args.get("venue_code", "").strip(),
    }


def query_filtered_providers_sql(sfilters):
    query = ServiceProvider.query.filter(ServiceProvider.is_active.is_(True))
    if sfilters["q"]:
        pattern = f"%{sfilters['q']}%"
        query = query.filter(
            or_(ServiceProvider.name.ilike(pattern), ServiceProvider.description.ilike(pattern))
        )
    if sfilters["category"]:
        query = query.filter(ServiceProvider.category == sfilters["category"])
    if sfilters["city"]:
        query = query.filter(ServiceProvider.city == sfilters["city"])
    if sfilters["venue_code"]:
        venue = VenueCatalog.query.filter_by(code=sfilters["venue_code"]).first()
        if not venue:
            return []
        query = query.join(VenueProvider, VenueProvider.provider_id == ServiceProvider.id).filter(
            VenueProvider.venue_id == venue.id
        )
    rows = query.order_by(ServiceProvider.id.asc()).all()
    return [serialize_provider_row(p) for p in rows]


def serialize_couple_workspace(user):
    """Serialize ONLY the authenticated couple's private workspace records."""
    if not user or not user.wedding:
        return None
    today = date.today()
    if user.chat_quota_date != today:
        user.chat_count_today = 0
        user.chat_quota_date = today
        db.session.commit()

    w = user.wedding
    saved_dir_codes = [
        sv.venue_code for sv in w.saved_venues if sv.source == "directory" and sv.venue_code
    ]
    saved_venue_details = [
        {
            "id": sv.id,
            "source": sv.source,
            "venueCode": sv.venue_code or "",
            "name": sv.name,
            "town": sv.town,
            "notes": sv.notes,
            "status": sv.status,
            "rating": sv.rating,
        }
        for sv in w.saved_venues
    ]
    custom_venues = [
        {
            "id": f"cv_{sv.id}",
            "dbId": sv.id,
            "name": sv.name,
            "town": sv.town,
            "lat": float(sv.lat) if sv.lat is not None else None,
            "lon": float(sv.lon) if sv.lon is not None else None,
            "notes": sv.notes,
            "status": sv.status,
            "rating": sv.rating,
        }
        for sv in w.saved_venues
        if sv.source == "custom"
    ]
    guests = [
        {
            "id": g.id,
            "name": g.name,
            "phone": g.phone,
            "status": g.rsvp_status,
            "plus": g.plus_ones,
            "diet": g.dietary_notes,
        }
        for g in w.guests
    ]
    budget = [
        {
            "id": b.id,
            "cat": b.category,
            "item": b.title,
            "est": float(b.estimated_usd),
            "act": float(b.actual_usd),
            "stage": b.payment_status,
        }
        for b in w.budget_items
    ]
    bookings = [
        {
            "id": bk.id,
            "kind": bk.booking_kind,
            "venueId": bk.venue_code,
            "providerCode": (
                bk.provider.code
                if bk.provider
                else (bk.venue_code or "")
            ),
            "isCustomProvider": bool(
                bk.booking_kind == "service" and bk.provider_id is None and not bk.venue_code
            ),
            "type": bk.request_type,
            "name": bk.target_name,
            "date": bk.event_date,
            "usd": float(bk.budget_estimate_usd),
            "status": bk.status,
        }
        for bk in w.bookings
    ]
    provider_messages = [
        {
            "id": pm.id,
            "providerCode": pm.provider.code if pm.provider else "",
            "providerName": pm.provider.name if pm.provider else "Provider",
            "category": pm.provider.category if pm.provider else "provider",
            "sender": pm.sender_role,
            "body": pm.body,
            "sentAt": pm.created_at.strftime("%Y-%m-%d %H:%M") if pm.created_at else "",
        }
        for pm in w.provider_messages
    ]
    return {
        "name": user.name,
        "email": user.email,
        "googleLinked": bool(user.google_id),
        "hasPassword": bool(user.password_hash),
        "couple": w.couple_names,
        "date": w.wedding_date,
        "city": w.city,
        "budgetUsd": float(w.budget_total_usd),
        "rsvpToken": w.rsvp_token,
        "rsvpOpen": bool(w.rsvp_open),
        "chatCountToday": int(user.chat_count_today),
        "dailyAiLimit": DAILY_AI_LIMIT,
        "savedVenues": saved_dir_codes,
        "savedVenueDetails": saved_venue_details,
        "customVenues": custom_venues,
        "guests": guests,
        "budget": budget,
        "bookings": bookings,
        "providerMessages": provider_messages,
    }
