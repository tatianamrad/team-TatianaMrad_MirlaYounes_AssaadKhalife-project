"""
blueprints/auth.py -- Couple Sign In, Registration, Google OAuth 2.0 (Authlib), Account Profile & Currency Preferences.
"""
from datetime import date
from decimal import Decimal, InvalidOperation
import os

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import (
    _REPO_DIR,
    _safe_internal_next,
    generate_rsvp_token,
    get_csrf_token,
    get_currency_prefs,
    get_current_user,
    is_google_oauth_configured,
    login_required,
    oauth,
    serialize_couple_workspace,
    verify_csrf,
    wants_json,
)
from models import AppSetting, User, Wedding, db
from validators import VALID_REGIONS, clean_iso_date, validate_login, validate_signup

auth_bp = Blueprint("auth", __name__)


def _upsert_env_keys(updates):
    """Persist local OAuth keys into git/.env when running locally so restarts keep them."""
    env_path = os.path.join(_REPO_DIR, ".env")
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    remaining = dict(updates)
    out = []
    for line in lines:
        replaced = False
        for k, v in list(remaining.items()):
            if line.strip().startswith(f"{k}="):
                out.append(f"{k}={v}")
                remaining.pop(k, None)
                replaced = True
                break
        if not replaced:
            out.append(line)
    for k, v in remaining.items():
        out.append(f"{k}={v}")
    with open(env_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")


@auth_bp.route("/auth")
def auth_page():
    """Sign In / Create Account Page."""
    user = get_current_user()
    curr, rate = get_currency_prefs()
    couple_data = serialize_couple_workspace(user)
    mode = "register" if request.args.get("mode", "login") == "register" else "login"
    next_url = _safe_internal_next(request.args.get("next", ""), default="/dashboard")
    setup_google = request.args.get("setup_google") == "1"

    bootstrap = {
        "signedIn": bool(couple_data),
        "authMode": mode,
        "nextUrl": next_url,
        "googleConfigured": is_google_oauth_configured(),
        "setupGoogle": setup_google and not is_google_oauth_configured(),
        "googleCallbackUri": url_for("auth.google_callback", _external=True),
        "currency": curr,
        "lbpRate": rate,
        "csrfToken": get_csrf_token(),
        "couple": (
            {
                "couple": couple_data["couple"],
                "email": couple_data["email"],
                "date": couple_data["date"],
                "city": couple_data["city"],
                "budgetUsd": couple_data["budgetUsd"],
                "googleLinked": couple_data["googleLinked"],
            }
            if couple_data
            else None
        ),
    }
    return render_template("auth.html", page_bootstrap=bootstrap)


@auth_bp.route("/register")
def register_page():
    return redirect(url_for("auth.auth_page", mode="register", next=request.args.get("next", "")))


@auth_bp.route("/profile")
@login_required
def profile_page():
    """Authenticated Couple Profile & Account Settings Page."""
    user = get_current_user()
    curr, rate = get_currency_prefs()
    couple_data = serialize_couple_workspace(user)

    bootstrap = {
        "signedIn": True,
        "googleConfigured": is_google_oauth_configured(),
        "currency": curr,
        "lbpRate": rate,
        "csrfToken": get_csrf_token(),
        "couple": couple_data,
    }
    return render_template("profile.html", page_bootstrap=bootstrap)


@auth_bp.route("/profile/password", methods=["POST"])
@login_required
def update_password():
    """Set or update the couple's account password."""
    verify_csrf()
    user = get_current_user()
    data = request.get_json(silent=True) or request.form
    current_pw = str(data.get("current_password", ""))
    new_pw = str(data.get("new_password", ""))

    if user.password_hash:
        if not current_pw or not check_password_hash(user.password_hash, current_pw):
            return jsonify({"ok": False, "error": "Current password is incorrect."}), 400

    if len(new_pw) < 8 or len(new_pw) > 128:
        return jsonify({"ok": False, "error": "New password must be between 8 and 128 characters."}), 400

    user.password_hash = generate_password_hash(new_pw)
    db.session.commit()
    return jsonify({"ok": True, "couple": serialize_couple_workspace(user)})


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return redirect(url_for("auth.auth_page", mode="register", next=request.args.get("next", "")))

    verify_csrf()
    payload = request.get_json(silent=True) if request.is_json else request.form
    errors, email, couple_names = validate_signup(payload)
    if User.query.filter_by(email=email).first():
        errors["email"] = "An account with this email already exists. Please sign in."

    if errors:
        msg = next(iter(errors.values()))
        if wants_json():
            return jsonify({"ok": False, "error": msg, "errors": errors}), 400
        flash(msg)
        return redirect(url_for("auth.auth_page", mode="register"))

    city = str(payload.get("city", "Byblos")).strip()
    if city not in VALID_REGIONS:
        city = "Byblos"
    w_date = clean_iso_date(payload.get("wedding_date"), "2027-08-28")
    curr_choice = str(payload.get("currency", "USD")).strip()
    _, rate = get_currency_prefs()
    try:
        raw_budget = Decimal(str(payload.get("budget_total", "35000")))
    except (InvalidOperation, ValueError):
        raw_budget = Decimal("35000")
    budget_usd = (raw_budget / Decimal(str(rate))) if curr_choice == "LBP" else raw_budget
    budget_usd = max(Decimal("500.00"), budget_usd.quantize(Decimal("0.01")))

    user = User(
        name=couple_names,
        email=email,
        password_hash=generate_password_hash(str(payload.get("password", ""))),
        chat_count_today=0,
        chat_quota_date=date.today(),
    )
    db.session.add(user)
    db.session.flush()

    wedding = Wedding(
        user_id=user.id,
        couple_names=couple_names,
        wedding_date=w_date,
        city=city,
        budget_total_usd=budget_usd,
        rsvp_token=generate_rsvp_token(),
        rsvp_open=True,
    )
    db.session.add(wedding)
    db.session.commit()

    session["user_id"] = user.id
    if curr_choice in ("USD", "LBP"):
        session["currency"] = curr_choice

    dest = _safe_internal_next(payload.get("next", ""), default="/dashboard")
    if wants_json():
        return jsonify({"ok": True, "redirectUrl": dest, "couple": serialize_couple_workspace(user)})
    return redirect(dest)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return redirect(url_for("auth.auth_page", mode="login", next=request.args.get("next", "")))

    verify_csrf()
    payload = request.get_json(silent=True) if request.is_json else request.form
    errors, email = validate_login(payload)
    if errors:
        msg = next(iter(errors.values()))
        if wants_json():
            return jsonify({"ok": False, "error": msg}), 400
        flash(msg)
        return redirect(url_for("auth.auth_page", mode="login"))

    user = User.query.filter_by(email=email).first()
    password = str(payload.get("password", ""))
    if user and not user.password_hash:
        msg = "This account uses Google Sign-In. Please continue with Google."
        if wants_json():
            return jsonify({"ok": False, "error": msg}), 401
        flash(msg)
        return redirect(url_for("auth.auth_page", mode="login"))

    if not user or not check_password_hash(user.password_hash, password):
        msg = "Invalid email or password."
        if wants_json():
            return jsonify({"ok": False, "error": msg}), 401
        flash(msg)
        return redirect(url_for("auth.auth_page", mode="login"))

    session["user_id"] = user.id
    dest = _safe_internal_next(payload.get("next", ""), default="/dashboard")
    if wants_json():
        return jsonify({"ok": True, "redirectUrl": dest, "couple": serialize_couple_workspace(user)})
    return redirect(dest)


@auth_bp.route("/auth/google/configure", methods=["POST"])
def configure_google_oauth():
    """Save Google OAuth 2.0 Client ID & Secret from local setup UI and activate Google Sign-In immediately."""
    verify_csrf()
    if request.remote_addr not in ("127.0.0.1", "::1") and os.environ.get("RENDER"):
        return jsonify({"ok": False, "error": "Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in environment variables."}), 403

    data = request.get_json(silent=True) or request.form
    cid = str(data.get("client_id", "")).strip()
    csec = str(data.get("client_secret", "")).strip()
    next_dest = _safe_internal_next(data.get("next", ""), default="/dashboard")

    if not cid or not csec:
        return jsonify({"ok": False, "error": "Both Google Client ID and Client Secret are required."}), 400

    for key, val in (("google_client_id", cid), ("google_client_secret", csec)):
        row = db.session.get(AppSetting, key)
        if row:
            row.value = val
        else:
            db.session.add(AppSetting(key=key, value=val))
    db.session.commit()

    os.environ["GOOGLE_CLIENT_ID"] = cid
    os.environ["GOOGLE_CLIENT_SECRET"] = csec
    if not os.environ.get("RENDER"):
        try:
            _upsert_env_keys({"GOOGLE_CLIENT_ID": cid, "GOOGLE_CLIENT_SECRET": csec})
        except OSError:
            pass

    is_google_oauth_configured()
    return jsonify({
        "ok": True,
        "authorizeUrl": url_for("auth.google_login", next=next_dest),
    })


@auth_bp.route("/auth/google")
def google_login():
    """Initiate Google OAuth 2.0 / OpenID Connect sign-in via Authlib."""
    next_dest = _safe_internal_next(request.args.get("next", ""), default="/dashboard")
    session["oauth_next"] = next_dest

    if not is_google_oauth_configured():
        flash("Google Sign-In is temporarily unavailable until GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are set in .env.")
        return redirect(url_for("auth.auth_page", next=next_dest))

    redirect_uri = url_for("auth.google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route("/auth/google/callback")
def google_callback():
    """Verify Google OIDC callback, link or provision Couple + Wedding, and establish session."""
    next_dest = _safe_internal_next(session.pop("oauth_next", ""), default="/dashboard")

    if not is_google_oauth_configured():
        return redirect(url_for("auth.auth_page", setup_google="1", next=next_dest))

    try:
        token = oauth.google.authorize_access_token()
        userinfo = token.get("userinfo")
        if not userinfo:
            userinfo = oauth.google.userinfo()

        sub = str((userinfo or {}).get("sub") or "").strip()
        email = str((userinfo or {}).get("email") or "").strip().lower()
        email_verified = (userinfo or {}).get("email_verified", True)
        raw_name = str((userinfo or {}).get("name") or "").strip()

        if not sub or not email or not email_verified:
            flash("Google Sign-In did not return a verified email address.")
            return redirect(url_for("auth.auth_page", next=next_dest))

        couple_names = (raw_name[:180] if raw_name else email.split("@")[0].title()) or "New Couple"

        # If a user is already signed in and linking their Google account from /profile:
        active_user = get_current_user()
        if active_user:
            conflict = User.query.filter(User.google_id == sub, User.id != active_user.id).first()
            if conflict:
                flash("That Google account is already linked to another 3a2belkon profile.")
                return redirect(url_for("auth.profile_page"))
            active_user.google_id = sub
            db.session.commit()
            return redirect(next_dest)

        user = User.query.filter_by(google_id=sub).first()
        if not user:
            user = User.query.filter_by(email=email).first()
            if user:
                user.google_id = sub

        if not user:
            user = User(
                name=couple_names,
                email=email,
                google_id=sub,
                password_hash=None,
                chat_count_today=0,
                chat_quota_date=date.today(),
            )
            db.session.add(user)
            db.session.flush()

        if not user.wedding:
            db.session.add(
                Wedding(
                    user_id=user.id,
                    couple_names=couple_names,
                    wedding_date="2027-08-28",
                    city="Byblos",
                    budget_total_usd=Decimal("35000.00"),
                    rsvp_token=generate_rsvp_token(),
                    rsvp_open=True,
                )
            )

        db.session.commit()
        session["user_id"] = user.id
        return redirect(next_dest)
    except Exception:
        db.session.rollback()
        flash("Google Sign-In could not be completed. Verify your Google OAuth Client ID, Secret, and Authorized Redirect URI.")
        return redirect(url_for("auth.auth_page", next=next_dest))


@auth_bp.route("/logout", methods=["POST"])
def logout():
    verify_csrf()
    curr, rate = get_currency_prefs()
    payload = request.get_json(silent=True) if request.is_json else request.form
    dest = _safe_internal_next((payload or {}).get("next", ""), default="/")
    session.clear()
    session["currency"] = curr
    session["lbp_rate"] = rate
    if wants_json():
        return jsonify({"ok": True, "redirectUrl": dest, "csrfToken": get_csrf_token()})
    return redirect(dest)


@auth_bp.route("/preferences/currency", methods=["POST"])
def update_currency():
    verify_csrf()
    data = request.get_json(silent=True) or request.form
    curr = str(data.get("currency", session.get("currency", "USD"))).strip().upper()
    if curr in ("USD", "LBP"):
        session["currency"] = curr
    if "lbp_rate" in data:
        try:
            rate = int(float(data.get("lbp_rate", 89500)))
            if rate >= 1000:
                session["lbp_rate"] = rate
        except (TypeError, ValueError):
            pass
    c_out, r_out = get_currency_prefs()
    return jsonify({"ok": True, "currency": c_out, "lbpRate": r_out})
