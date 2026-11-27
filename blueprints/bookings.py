"""
blueprints/bookings.py -- Venue Date Locks, Provider Bookings, Custom Providers & Exclusive 3a2belkon Messaging.
"""
from decimal import Decimal, InvalidOperation

from flask import Blueprint, jsonify, request, session
from sqlalchemy.exc import IntegrityError

from helpers import (
    get_currency_prefs,
    get_current_user,
    login_required,
    serialize_couple_workspace,
    serialize_public_catalog,
    verify_csrf,
)
from models import ProviderMessage, ServiceBooking, ServiceProvider, VenueBookedDate, VenueCatalog, db
from validators import VALID_BOOKING_STATUSES, clean_iso_date

bookings_bp = Blueprint("bookings", __name__)


@bookings_bp.route("/bookings/venue-date", methods=["POST"])
@login_required
def book_venue_date():
    verify_csrf()
    user = get_current_user()
    w = user.wedding
    data = request.get_json(silent=True) or request.form
    venue_code = str(data.get("venue_code", "")).strip()
    iso_date = clean_iso_date(data.get("iso_date"), "")

    venue = VenueCatalog.query.filter_by(code=venue_code).first()
    if not venue or not iso_date:
        return jsonify({"ok": False, "error": "Select a valid venue and open calendar date."}), 400

    if VenueBookedDate.query.filter_by(venue_id=venue.id, iso_date=iso_date).first():
        return jsonify({"ok": False, "error": f"{iso_date} is already booked at {venue.name}."}), 409

    try:
        bk = ServiceBooking(
            wedding_id=w.id,
            provider_id=None,
            booking_kind="venue",
            venue_code=venue.code,
            request_type="Venue Date Request",
            target_name=venue.name,
            event_date=iso_date,
            budget_estimate_usd=venue.starting_price_usd,
            status="confirmed",
        )
        db.session.add(bk)
        db.session.flush()
        db.session.add(VenueBookedDate(venue_id=venue.id, iso_date=iso_date, booking_id=bk.id))
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"ok": False, "error": "That date was just booked."}), 409

    _, venues_data = serialize_public_catalog()
    return jsonify({
        "ok": True,
        "venues": venues_data,
        "couple": serialize_couple_workspace(user),
    })


@bookings_bp.route("/bookings/provider", methods=["POST"])
@login_required
def book_provider():
    verify_csrf()
    user = get_current_user()
    w = user.wedding
    data = request.get_json(silent=True) or request.form
    prov_code = str(data.get("provider_code", "")).strip()

    prov = ServiceProvider.query.filter_by(code=prov_code, is_active=True).first()
    if not prov:
        return jsonify({"ok": False, "error": "Provider not found."}), 404

    db.session.add(
        ServiceBooking(
            wedding_id=w.id,
            provider_id=prov.id,
            booking_kind="service",
            venue_code=None,
            request_type=f"{prov.category} Request",
            target_name=prov.name,
            event_date=w.wedding_date,
            budget_estimate_usd=prov.starting_price_usd,
            status="requested",
        )
    )
    db.session.commit()
    return jsonify({"ok": True, "providerName": prov.name, "couple": serialize_couple_workspace(user)})


@bookings_bp.route("/bookings/custom-provider", methods=["POST"])
@login_required
def add_custom_provider_booking():
    """
    Records a custom off-platform provider inputted by the couple themselves.
    Custom user-inputted providers are the ONLY providers without 3a2belkon messaging.
    """
    verify_csrf()
    user = get_current_user()
    w = user.wedding
    data = request.get_json(silent=True) or request.form

    name = str(data.get("name", "")).strip()[:180]
    category = str(data.get("category", "Custom Vendor")).strip()[:80] or "Custom Vendor"
    if not name:
        return jsonify({"ok": False, "error": "Please enter the custom provider's name."}), 400

    entry_curr = str(data.get("currency", session.get("currency", "USD"))).strip().upper()
    _, rate = get_currency_prefs()
    try:
        raw_est = max(Decimal("0"), Decimal(str(data.get("estimated_amount", "0") or "0")))
    except (InvalidOperation, ValueError):
        raw_est = Decimal("0")
    est_usd = (raw_est / Decimal(str(rate))) if entry_curr == "LBP" else raw_est
    est_usd = est_usd.quantize(Decimal("0.01"))

    db.session.add(
        ServiceBooking(
            wedding_id=w.id,
            provider_id=None,
            booking_kind="service",
            venue_code=None,
            request_type=f"Custom {category}",
            target_name=name,
            event_date=w.wedding_date,
            budget_estimate_usd=est_usd,
            status="confirmed",
        )
    )
    db.session.commit()
    return jsonify({"ok": True, "providerName": name, "couple": serialize_couple_workspace(user)})


@bookings_bp.route("/bookings/<int:booking_id>/delete", methods=["POST"])
@login_required
def delete_booking_row(booking_id):
    verify_csrf()
    user = get_current_user()
    bk = ServiceBooking.query.filter_by(id=booking_id, wedding_id=user.wedding.id).first()
    if not bk:
        return jsonify({"ok": False, "error": "Booking not found."}), 404
    if bk.booking_kind == "venue" and bk.venue_code:
        venue = VenueCatalog.query.filter_by(code=bk.venue_code).first()
        if venue:
            VenueBookedDate.query.filter_by(venue_id=venue.id, booking_id=bk.id).delete()
    db.session.delete(bk)
    db.session.commit()
    _, venues_data = serialize_public_catalog()
    return jsonify({"ok": True, "venues": venues_data, "couple": serialize_couple_workspace(user)})


@bookings_bp.route("/bookings/<int:booking_id>/status", methods=["POST"])
@login_required
def booking_update_status(booking_id):
    verify_csrf()
    user = get_current_user()
    bk = ServiceBooking.query.filter_by(id=booking_id, wedding_id=user.wedding.id).first()
    if not bk:
        return jsonify({"ok": False, "error": "Booking not found."}), 404

    data = request.get_json(silent=True) or request.form
    new_status = str(data.get("status", "")).strip()
    if new_status not in VALID_BOOKING_STATUSES:
        return jsonify({"ok": False, "error": "Invalid booking status."}), 400

    if bk.booking_kind == "venue" and bk.venue_code:
        venue = VenueCatalog.query.filter_by(code=bk.venue_code).first()
        if venue:
            existing_lock = VenueBookedDate.query.filter_by(
                venue_id=venue.id, iso_date=bk.event_date
            ).first()
            if new_status == "confirmed" and bk.status != "confirmed":
                if existing_lock and existing_lock.booking_id != bk.id:
                    return jsonify({
                        "ok": False,
                        "error": f"Cannot confirm: {bk.event_date} is already booked at {venue.name}.",
                    }), 409
                if not existing_lock:
                    db.session.add(
                        VenueBookedDate(venue_id=venue.id, iso_date=bk.event_date, booking_id=bk.id)
                    )
            elif bk.status == "confirmed" and new_status != "confirmed":
                if existing_lock and (existing_lock.booking_id == bk.id or existing_lock.booking_id is None):
                    db.session.delete(existing_lock)

    bk.status = new_status
    db.session.commit()
    _, venues_data = serialize_public_catalog()
    return jsonify({
        "ok": True,
        "venues": venues_data,
        "couple": serialize_couple_workspace(user),
    })


def _resolve_or_provision_platform_desk(prov_code, target_name="", target_city="Lebanon"):
    """
    Resolve a 3a2belkon messaging desk for any platform provider (p1..p12),
    catalog venue (v1..v6), or live-discovered venue (gp_*) on our map.
    Never provisions messaging for user-inputted custom providers/venues (cv_* / custom_*).
    """
    code = str(prov_code or "").strip()[:32]
    if not code or code.startswith("cv_") or code.startswith("custom"):
        return None

    prov = ServiceProvider.query.filter_by(code=code).first()
    if prov:
        return prov

    venue = VenueCatalog.query.filter_by(code=code).first()
    if venue:
        desk = ServiceProvider(
            code=venue.code,
            name=venue.name,
            category="venue",
            city=venue.region,
            description=f"{venue.setting} · {venue.capacity_label}",
            whatsapp="",
            starting_price_usd=venue.starting_price_usd,
            price_unit="estate",
            is_active=False,
        )
        db.session.add(desk)
        db.session.flush()
        return desk

    if code.startswith("gp_") and target_name:
        desk = ServiceProvider(
            code=code,
            name=str(target_name).strip()[:180],
            category="venue",
            city=str(target_city or "Lebanon").strip()[:100] or "Lebanon",
            description="3a2belkon Live Discovered Venue Desk",
            whatsapp="",
            starting_price_usd=Decimal("0.00"),
            price_unit="estate",
            is_active=False,
        )
        db.session.add(desk)
        db.session.flush()
        return desk

    return None


@bookings_bp.route("/messages/provider", methods=["POST"])
@login_required
def send_provider_message():
    """
    Exclusive in-platform provider & venue messaging (logged-in couples only).
    Every platform provider and venue communicates exclusively inside 3a2belkon;
    only custom user-inputted entries have no platform contact.
    """
    verify_csrf()
    user = get_current_user()
    w = user.wedding
    data = request.get_json(silent=True) or request.form
    prov_code = str(data.get("provider_code", "")).strip()
    target_name = str(data.get("target_name", "")).strip()
    target_city = str(data.get("target_city", "Lebanon")).strip()
    body = str(data.get("message", "")).strip()[:600]

    if not body:
        return jsonify({"ok": False, "error": "Please enter a message for the provider."}), 400

    if prov_code.startswith("cv_") or prov_code.startswith("custom"):
        return jsonify({
            "ok": False,
            "error": "Custom providers added by you do not have 3a2belkon platform messaging.",
        }), 400

    prov = _resolve_or_provision_platform_desk(prov_code, target_name=target_name, target_city=target_city)
    if not prov:
        return jsonify({"ok": False, "error": "Provider not found."}), 404

    db.session.add(
        ProviderMessage(
            wedding_id=w.id,
            provider_id=prov.id,
            sender_role="couple",
            body=body,
        )
    )
    price_clause = (
        f"({prov.category}, starting ${int(prov.starting_price_usd):,} {prov.price_unit})"
        if float(prov.starting_price_usd or 0) > 0
        else f"({prov.city} venue desk)"
    )
    db.session.add(
        ProviderMessage(
            wedding_id=w.id,
            provider_id=prov.id,
            sender_role="provider",
            body=(
                f"Received via 3a2belkon Exclusive Desk for {prov.name} {price_clause}. "
                f"Our team is reviewing {w.couple_names}'s {w.wedding_date} inquiry and will send "
                f"your official quote & Raaboun terms right here inside 3a2belkon."
            ),
        )
    )

    if prov.is_active:
        existing_bk = ServiceBooking.query.filter_by(
            wedding_id=w.id, provider_id=prov.id, booking_kind="service"
        ).first()
        if not existing_bk:
            db.session.add(
                ServiceBooking(
                    wedding_id=w.id,
                    provider_id=prov.id,
                    booking_kind="service",
                    venue_code=None,
                    request_type=f"{prov.category} Inquiry",
                    target_name=prov.name,
                    event_date=w.wedding_date,
                    budget_estimate_usd=prov.starting_price_usd,
                    status="contacted",
                )
            )

    db.session.commit()
    return jsonify({
        "ok": True,
        "providerCode": prov.code,
        "providerName": prov.name,
        "couple": serialize_couple_workspace(user),
    })
