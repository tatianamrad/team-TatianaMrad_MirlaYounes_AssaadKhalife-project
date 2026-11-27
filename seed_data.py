"""
seed_data.py -- Idempotent PostgreSQL & SQLite seeder for 3a2belkon (عقبالكن).

Zero manual (lat, lon) coordinates: venues are seeded with their Lebanese
address queries only, and coordinates are gathered dynamically from Geoapify
when GEOAPIFY_KEY is configured in .env or Render Environment Variables.
"""
from datetime import date
from decimal import Decimal
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

import api_client
from models import (
    BudgetItem,
    Guest,
    ProviderMessage,
    SavedVenue,
    ServiceBooking,
    ServiceProvider,
    User,
    VenueBookedDate,
    VenueCatalog,
    VenueProvider,
    Wedding,
    db,
)

PROVIDERS_SEED = [
    ("p1", "Cat & Mouth Catering", "traiteur", "Beirut", 58, "/guest", "9613111222", "Bespoke Lebanese & Mediterranean luxury live stations and patisserie."),
    ("p2", "Fahed Catering", "traiteur", "Keserwan", 50, "/guest", "9613222333", "Generous coastal seafood displays and signature carving stations."),
    ("p3", "Nicolas Audi", "traiteur", "Beirut", 72, "/guest", "9611444555", "Haute gastronomie plated receptions and architectural dessert salons."),
    ("p4", "Manna Catering", "traiteur", "Mount Lebanon", 46, "/guest", "96170333444", "Artisanal grazing tables and contemporary Levantine menus."),
    ("p5", "Pulse Production", "photographer", "Beirut", 3200, "pkg", "9613555666", "Cinematic wedding films, aerial drone coverage, and editorial portraits."),
    ("p6", "ParAzar Productions", "photographer", "Keserwan", 3800, "pkg", "9613666777", "Timeless fine-art photography and high-energy celebration edits."),
    ("p7", "Framez by Toni", "photographer", "Byblos", 2400, "pkg", "96171777888", "Golden-hour Mediterranean coastal light and documentary storytelling."),
    ("p8", "Studio AV", "photographer", "Mount Lebanon", 2700, "pkg", "96176888999", "Natural candid photography and same-night highlight projections."),
    ("p9", "Mayyadah Zaffe", "zaffe", "Beirut", 1800, "show", "9613999000", "Choreographed Lebanese Dabke, oriental violin, and grand entrance."),
    ("p10", "Alabanza Troupe", "zaffe", "Keserwan", 2100, "show", "96170123987", "Royal fusion percussion, live brass, and custom couple entrances."),
    ("p11", "El Minieh Heritage", "zaffe", "Batroun", 1500, "show", "96171456321", "Authentic Baalbek folkloric tabl, mijwiz, and traditional swords."),
    ("p12", "Fursan Al Zaffe", "zaffe", "Byblos", 1650, "show", "9613654789", "High-energy drummers, cold sparks, and celebratory Dabke."),
]

VENUES_SEED = [
    {
        "code": "v1",
        "name": "Château Rweiss",
        "region": "Keserwan",
        "address_query": "Chnaniir, Keserwan, Lebanon",
        "setting": "Stone Château & Gardens",
        "capacity_label": "250 – 750 guests",
        "usd": 9500,
        "next_open": "Aug 14, 2027",
        "sketch_path": "/static/assets/hero_lebanese_estate.jpg",
        "providers": ["p1", "p2", "p5", "p6", "p9", "p10"],
        "booked": ["2027-07-10", "2027-07-17", "2027-07-24", "2027-08-07", "2027-08-21", "2027-09-04", "2027-09-11"],
    },
    {
        "code": "v2",
        "name": "Orizon Byblos",
        "region": "Byblos",
        "address_query": "Halat, Jbeil, Lebanon",
        "setting": "Coastal Cliff Terrace",
        "capacity_label": "200 – 600 guests",
        "usd": 8800,
        "next_open": "Aug 21, 2027",
        "sketch_path": "/static/assets/byblos_coastal_terrace.jpg",
        "providers": ["p1", "p3", "p5", "p7", "p9", "p12"],
        "booked": ["2027-07-03", "2027-07-17", "2027-08-14", "2027-08-28", "2027-09-11", "2027-09-25"],
    },
    {
        "code": "v3",
        "name": "Blanc de Chêne",
        "region": "Batroun",
        "address_query": "Smar Jbeil, Batroun, Lebanon",
        "setting": "Cedar Mountain Estate",
        "capacity_label": "180 – 500 guests",
        "usd": 7900,
        "next_open": "Jul 31, 2027",
        "sketch_path": "/static/assets/mount_lebanon_cedars.jpg",
        "providers": ["p2", "p4", "p7", "p8", "p11", "p12"],
        "booked": ["2027-07-10", "2027-07-24", "2027-08-07", "2027-08-14", "2027-09-18"],
    },
    {
        "code": "v4",
        "name": "Palais Sursock Gardens",
        "region": "Beirut",
        "address_query": "Sursock, Beirut, Lebanon",
        "setting": "Heritage Palace",
        "capacity_label": "150 – 420 guests",
        "usd": 12000,
        "next_open": "Sep 04, 2027",
        "sketch_path": "/static/assets/beirut_heritage_palace.jpg",
        "providers": ["p1", "p3", "p6", "p9", "p10"],
        "booked": ["2027-07-17", "2027-07-31", "2027-08-07", "2027-08-21", "2027-08-28", "2027-09-18"],
    },
    {
        "code": "v5",
        "name": "Domaine Haut-Metn",
        "region": "Mount Lebanon",
        "address_query": "Beit Mery, Metn, Lebanon",
        "setting": "Cedar Mountain Estate",
        "capacity_label": "220 – 650 guests",
        "usd": 8200,
        "next_open": "Aug 07, 2027",
        "sketch_path": "/static/assets/mount_lebanon_cedars.jpg",
        "providers": ["p1", "p4", "p5", "p8", "p10", "p12"],
        "booked": ["2027-07-10", "2027-08-14", "2027-09-04"],
    },
    {
        "code": "v6",
        "name": "Bahsa Sea Arch",
        "region": "Batroun",
        "address_query": "Bahsa, Batroun, Lebanon",
        "setting": "Coastal Cliff Terrace",
        "capacity_label": "140 – 360 guests",
        "usd": 7400,
        "next_open": "Jul 24, 2027",
        "sketch_path": "/static/assets/byblos_coastal_terrace.jpg",
        "providers": ["p3", "p4", "p6", "p7", "p9", "p11"],
        "booked": ["2027-07-17", "2027-08-07", "2027-08-21", "2027-09-11"],
    },
]


def hydrate_missing_coordinates_via_geoapify(custom_api_key=""):
    """
    Geocode any VenueCatalog or SavedVenue rows whose (lat, lon) are still NULL
    by calling the live geocoding API (Geoapify when configured, or live
    OpenStreetMap Nominatim out of the box—zero hardcoded coordinates).
    """
    updated = 0
    for venue in VenueCatalog.query.filter(VenueCatalog.lat.is_(None)).all():
        geo = api_client.geocode_lebanon(venue.address_query, custom_api_key=custom_api_key)
        if geo:
            venue.lat = geo["lat"]
            venue.lon = geo["lon"]
            venue.api_place_id = geo["place_id"]
            updated += 1

    for sv in SavedVenue.query.filter(SavedVenue.lat.is_(None)).all():
        geo = api_client.geocode_lebanon(f"{sv.town}, Lebanon", custom_api_key=custom_api_key)
        if not geo and "," in str(sv.town):
            first_part = str(sv.town).split(",")[0].strip()
            geo = api_client.geocode_lebanon(f"{first_part}, Lebanon", custom_api_key=custom_api_key)
        if geo:
            sv.lat = geo["lat"]
            sv.lon = geo["lon"]
            sv.api_place_id = geo["place_id"]
            updated += 1

    if updated:
        db.session.commit()
    return updated


def seed_database():
    """Populate curated providers, estates (by address only), and demo couple if empty."""
    try:
        provider_by_code = {p.code: p for p in ServiceProvider.query.all()}
        for code, name, cat, city, price, unit, wa, bio in PROVIDERS_SEED:
            if code not in provider_by_code:
                prov = ServiceProvider(
                    code=code,
                    name=name,
                    category=cat,
                    city=city,
                    starting_price_usd=Decimal(str(price)),
                    price_unit=unit,
                    whatsapp=wa,
                    description=bio,
                    is_active=True,
                )
                db.session.add(prov)
                db.session.flush()
                provider_by_code[code] = prov

        existing_venues = {v.code: v for v in VenueCatalog.query.all()}
        for vdata in VENUES_SEED:
            if vdata["code"] not in existing_venues:
                venue = VenueCatalog(
                    code=vdata["code"],
                    name=vdata["name"],
                    region=vdata["region"],
                    address_query=vdata["address_query"],
                    setting=vdata["setting"],
                    capacity_label=vdata["capacity_label"],
                    starting_price_usd=Decimal(str(vdata["usd"])),
                    next_open_label=vdata["next_open"],
                    lat=None,
                    lon=None,
                    api_place_id=None,
                    sketch_path=vdata["sketch_path"],
                )
                db.session.add(venue)
                db.session.flush()

                for pcode in vdata["providers"]:
                    prov = provider_by_code.get(pcode)
                    if prov:
                        db.session.add(
                            VenueProvider(venue_id=venue.id, provider_id=prov.id, contract_type="approved")
                        )

                for iso in vdata["booked"]:
                    db.session.add(VenueBookedDate(venue_id=venue.id, iso_date=iso))

        demo_email = "maya.rami@example.com"
        if not User.query.filter_by(email=demo_email).first():
            demo_user = User(
                name="Maya & Rami",
                email=demo_email,
                password_hash=generate_password_hash("maya-rami-2027"),
                chat_count_today=2,
                chat_quota_date=date.today(),
            )
            db.session.add(demo_user)
            db.session.flush()

            demo_wedding = Wedding(
                user_id=demo_user.id,
                couple_names="Maya & Rami",
                wedding_date="2027-09-18",
                city="Byblos",
                budget_total_usd=Decimal("32000.00"),
                rsvp_token="m9r27-9f8a4c21b0",
                rsvp_open=True,
            )
            db.session.add(demo_wedding)
            db.session.flush()

            db.session.add_all([
                SavedVenue(
                    wedding_id=demo_wedding.id,
                    source="directory",
                    venue_code="v1",
                    api_place_id=None,
                    name="Château Rweiss",
                    town="Keserwan",
                    lat=None,
                    lon=None,
                    notes="Shortlisted directory estate",
                    status="top_choice",
                    rating=5,
                ),
                SavedVenue(
                    wedding_id=demo_wedding.id,
                    source="directory",
                    venue_code="v2",
                    api_place_id=None,
                    name="Orizon Byblos",
                    town="Byblos",
                    lat=None,
                    lon=None,
                    notes="Shortlisted coastal terrace",
                    status="shortlisted",
                    rating=4,
                ),
                SavedVenue(
                    wedding_id=demo_wedding.id,
                    source="custom",
                    venue_code=None,
                    api_place_id=None,
                    name="Beit El Qamar Courtyard",
                    town="Deir El Qamar, Chouf",
                    lat=None,
                    lon=None,
                    notes="230 guests outdoors · stone terrace",
                    status="visited",
                    rating=5,
                ),
            ])

            db.session.add_all([
                Guest(wedding_id=demo_wedding.id, name="Nadine Khoury", phone="+9613712490", rsvp_status="attending", plus_ones=1, dietary_notes="Pescatarian"),
                Guest(wedding_id=demo_wedding.id, name="Tarek Haddad", phone="+96170884210", rsvp_status="attending", plus_ones=2, dietary_notes="None"),
                Guest(wedding_id=demo_wedding.id, name="Yara Karam", phone="+96171449012", rsvp_status="pending", plus_ones=0, dietary_notes="Gluten-free"),
                Guest(wedding_id=demo_wedding.id, name="Ziad Mouawad", phone="+9613990145", rsvp_status="declined", plus_ones=0, dietary_notes="—"),
            ])

            db.session.add_all([
                BudgetItem(wedding_id=demo_wedding.id, category="Venue", title="Château Rweiss Estate Rental", estimated_usd=Decimal("9500"), actual_usd=Decimal("9500"), payment_status="Raaboun Paid"),
                BudgetItem(wedding_id=demo_wedding.id, category="Traiteur / Catering", title="Cat & Mouth Live Stations (240 guests)", estimated_usd=Decimal("13200"), actual_usd=Decimal("12800"), payment_status="Raaboun Paid"),
                BudgetItem(wedding_id=demo_wedding.id, category="Photography & Film", title="Pulse Production Full-Day & Drone", estimated_usd=Decimal("3400"), actual_usd=Decimal("3400"), payment_status="Planned"),
                BudgetItem(wedding_id=demo_wedding.id, category="Zaffe & Entertainment", title="Mayyadah Zaffe Grand Entrance", estimated_usd=Decimal("1800"), actual_usd=Decimal("1800"), payment_status="Settled"),
            ])

            p1 = provider_by_code.get("p1")
            p9 = provider_by_code.get("p9")
            db.session.add_all([
                ServiceBooking(
                    wedding_id=demo_wedding.id,
                    provider_id=None,
                    booking_kind="venue",
                    venue_code="v2",
                    request_type="Venue Date Request",
                    target_name="Orizon Byblos",
                    event_date="2027-09-18",
                    budget_estimate_usd=Decimal("8800"),
                    status="requested",
                ),
                ServiceBooking(
                    wedding_id=demo_wedding.id,
                    provider_id=p1.id if p1 else None,
                    booking_kind="service",
                    venue_code=None,
                    request_type="traiteur Request",
                    target_name="Cat & Mouth Catering",
                    event_date="2027-09-18",
                    budget_estimate_usd=Decimal("12800"),
                    status="contacted",
                ),
                ServiceBooking(
                    wedding_id=demo_wedding.id,
                    provider_id=p9.id if p9 else None,
                    booking_kind="service",
                    venue_code=None,
                    request_type="zaffe Request",
                    target_name="Mayyadah Zaffe",
                    event_date="2027-09-18",
                    budget_estimate_usd=Decimal("1800"),
                    status="confirmed",
                ),
            ])

            if p1:
                db.session.add_all([
                    ProviderMessage(
                        wedding_id=demo_wedding.id,
                        provider_id=p1.id,
                        sender_role="couple",
                        body="Bonjour Cat & Mouth team! Could you share your 240-guest live Mediterranean station menu and Raaboun schedule for Sep 18, 2027 at Orizon Byblos?",
                    ),
                    ProviderMessage(
                        wedding_id=demo_wedding.id,
                        provider_id=p1.id,
                        sender_role="provider",
                        body="Mabrouk Maya & Rami! Through your exclusive 3a2belkon thread: Sep 18, 2027 is open for Orizon Byblos ($58/guest + patisserie salon, 35% Raaboun to lock the date).",
                    ),
                ])

        db.session.commit()
        hydrate_missing_coordinates_via_geoapify()
    except IntegrityError:
        db.session.rollback()
