"""
PostgreSQL & SQLite compatible SQLAlchemy models for 3a2belkon (عقبالكن).

Uses non-reserved PostgreSQL table names, explicit VARCHAR/TEXT/NUMERIC(12,2)
types, Boolean defaults, and database-level UNIQUE constraints for Render PostgreSQL.
"""
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, default="Couple")
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    google_id = db.Column(db.String(255), unique=True, nullable=True, index=True)
    password_hash = db.Column(db.Text, nullable=True)
    chat_count_today = db.Column(db.Integer, nullable=False, default=0)
    chat_quota_date = db.Column(db.Date, nullable=True)

    wedding = db.relationship(
        "Wedding",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )


class Wedding(db.Model):
    __tablename__ = "weddings"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    couple_names = db.Column(db.String(180), nullable=False, default="New Couple")
    wedding_date = db.Column(db.String(20), nullable=False, default="2027-08-28")
    city = db.Column(db.String(100), nullable=False, default="Byblos")
    budget_total_usd = db.Column(db.Numeric(12, 2), nullable=False, default=35000)
    rsvp_token = db.Column(db.String(64), unique=True, nullable=False, index=True)
    rsvp_open = db.Column(db.Boolean, nullable=False, default=True)

    user = db.relationship("User", back_populates="wedding")
    saved_venues = db.relationship(
        "SavedVenue",
        back_populates="wedding",
        cascade="all, delete-orphan",
        order_by="SavedVenue.id.asc()",
    )
    guests = db.relationship(
        "Guest",
        back_populates="wedding",
        cascade="all, delete-orphan",
        order_by="Guest.id.desc()",
    )
    budget_items = db.relationship(
        "BudgetItem",
        back_populates="wedding",
        cascade="all, delete-orphan",
        order_by="BudgetItem.id.asc()",
    )
    bookings = db.relationship(
        "ServiceBooking",
        back_populates="wedding",
        cascade="all, delete-orphan",
        order_by="ServiceBooking.id.desc()",
    )
    provider_messages = db.relationship(
        "ProviderMessage",
        back_populates="wedding",
        cascade="all, delete-orphan",
        order_by="ProviderMessage.id.asc()",
    )


class SavedVenue(db.Model):
    __tablename__ = "saved_venues"

    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(
        db.Integer,
        db.ForeignKey("weddings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source = db.Column(db.String(20), nullable=False, default="directory")  # 'directory' or 'custom'
    venue_code = db.Column(db.String(50), nullable=True)  # e.g. 'v1' when source == 'directory'
    api_place_id = db.Column(db.Text, nullable=True)
    name = db.Column(db.String(200), nullable=False)
    town = db.Column(db.String(200), nullable=False, default="Mount Lebanon")
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=False, default="")
    status = db.Column(db.String(32), nullable=False, default="shortlisted")
    rating = db.Column(db.Integer, nullable=True)

    wedding = db.relationship("Wedding", back_populates="saved_venues")


class Guest(db.Model):
    __tablename__ = "guests"

    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(
        db.Integer,
        db.ForeignKey("weddings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(180), nullable=False)
    phone = db.Column(db.String(40), nullable=False, index=True)
    rsvp_status = db.Column(db.String(24), nullable=False, default="pending")
    plus_ones = db.Column(db.Integer, nullable=False, default=0)
    dietary_notes = db.Column(db.String(255), nullable=False, default="None")

    wedding = db.relationship("Wedding", back_populates="guests")


class BudgetItem(db.Model):
    __tablename__ = "budget_items"

    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(
        db.Integer,
        db.ForeignKey("weddings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(240), nullable=False)
    estimated_usd = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    actual_usd = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    payment_status = db.Column(db.String(40), nullable=False, default="Raaboun Paid")

    wedding = db.relationship("Wedding", back_populates="budget_items")


class ServiceProvider(db.Model):
    __tablename__ = "service_providers"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)  # e.g. 'p1'
    name = db.Column(db.String(180), nullable=False)
    category = db.Column(db.String(40), nullable=False, index=True)  # 'traiteur', 'photographer', 'zaffe'
    city = db.Column(db.String(100), nullable=False, default="Lebanon")
    description = db.Column(db.Text, nullable=False, default="")
    whatsapp = db.Column(db.String(40), nullable=False, default="")
    starting_price_usd = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    price_unit = db.Column(db.String(30), nullable=False, default="pkg")
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    venue_contracts = db.relationship(
        "VenueProvider",
        back_populates="provider",
        cascade="all, delete-orphan",
    )


class VenueCatalog(db.Model):
    __tablename__ = "venue_catalog"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), unique=True, nullable=False, index=True)  # e.g. 'v1'
    name = db.Column(db.String(180), nullable=False)
    region = db.Column(db.String(80), nullable=False, index=True)
    address_query = db.Column(db.String(255), nullable=False)
    setting = db.Column(db.String(100), nullable=False)
    capacity_label = db.Column(db.String(80), nullable=False)
    starting_price_usd = db.Column(db.Numeric(12, 2), nullable=False, default=8000)
    next_open_label = db.Column(db.String(60), nullable=False, default="Aug 14, 2027")
    lat = db.Column(db.Float, nullable=True)
    lon = db.Column(db.Float, nullable=True)
    api_place_id = db.Column(db.String(120), nullable=True)
    sketch_path = db.Column(db.String(255), nullable=False)

    provider_links = db.relationship(
        "VenueProvider",
        back_populates="venue",
        cascade="all, delete-orphan",
    )
    booked_dates = db.relationship(
        "VenueBookedDate",
        back_populates="venue",
        cascade="all, delete-orphan",
    )


class VenueProvider(db.Model):
    __tablename__ = "venue_providers"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(
        db.Integer,
        db.ForeignKey("venue_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id = db.Column(
        db.Integer,
        db.ForeignKey("service_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    contract_type = db.Column(db.String(32), nullable=False, default="approved")

    __table_args__ = (
        db.UniqueConstraint("venue_id", "provider_id", name="uq_venue_provider"),
    )

    venue = db.relationship("VenueCatalog", back_populates="provider_links")
    provider = db.relationship("ServiceProvider", back_populates="venue_contracts")


class ServiceBooking(db.Model):
    __tablename__ = "service_bookings"

    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(
        db.Integer,
        db.ForeignKey("weddings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id = db.Column(
        db.Integer,
        db.ForeignKey("service_providers.id", ondelete="SET NULL"),
        nullable=True,
    )
    booking_kind = db.Column(db.String(24), nullable=False, default="service")  # 'venue' or 'service'
    venue_code = db.Column(db.String(32), nullable=True)
    request_type = db.Column(db.String(100), nullable=False)
    target_name = db.Column(db.String(200), nullable=False)
    event_date = db.Column(db.String(20), nullable=False)
    budget_estimate_usd = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    status = db.Column(db.String(32), nullable=False, default="requested")
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    wedding = db.relationship("Wedding", back_populates="bookings")
    provider = db.relationship("ServiceProvider")


class VenueBookedDate(db.Model):
    __tablename__ = "venue_booked_dates"

    id = db.Column(db.Integer, primary_key=True)
    venue_id = db.Column(
        db.Integer,
        db.ForeignKey("venue_catalog.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    iso_date = db.Column(db.String(16), nullable=False)
    booking_id = db.Column(
        db.Integer,
        db.ForeignKey("service_bookings.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        db.UniqueConstraint("venue_id", "iso_date", name="uq_venue_iso_date"),
    )

    venue = db.relationship("VenueCatalog", back_populates="booked_dates")


class ProviderMessage(db.Model):
    """Exclusive in-platform messaging thread between a Couple and a ServiceProvider."""
    __tablename__ = "provider_messages"

    id = db.Column(db.Integer, primary_key=True)
    wedding_id = db.Column(
        db.Integer,
        db.ForeignKey("weddings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider_id = db.Column(
        db.Integer,
        db.ForeignKey("service_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sender_role = db.Column(db.String(20), nullable=False, default="couple")  # 'couple' or 'provider'
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    wedding = db.relationship("Wedding", back_populates="provider_messages")
    provider = db.relationship("ServiceProvider")


class AppSetting(db.Model):
    """Stores server-side configuration (e.g. optional Geoapify key) in PostgreSQL."""
    __tablename__ = "app_settings"

    key = db.Column(db.String(80), primary_key=True)
    value = db.Column(db.Text, nullable=False, default="")

