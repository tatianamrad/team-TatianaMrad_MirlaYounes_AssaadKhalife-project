"""
reset_db.py -- (Re)create and seed all tables from models.py for local development.

Run locally with:
    python reset_db.py

On Render (PostgreSQL), app.py automatically runs db.create_all() and
seed_database() at startup without dropping existing production data.
"""
import os

os.environ["SKIP_STARTUP_SEED"] = "1"

from app import app
from models import db
from seed_data import seed_database

with app.app_context():
    db.drop_all()
    db.create_all()
    seed_database()
    print("Database reset: all 3a2belkon tables created and seeded from models.py.")
