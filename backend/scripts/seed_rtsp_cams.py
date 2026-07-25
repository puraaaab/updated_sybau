import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.database.connection import SessionLocal, engine, Base
from backend.database.models import Camera
from sqlalchemy import text

# Ensure database tables exist & migrate missing columns
# Base.metadata.create_all(bind=engine)
# with engine.connect() as conn:
#     conn.execute(text("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS latitude FLOAT DEFAULT 21.1702;"))
#     conn.execute(text("ALTER TABLE cameras ADD COLUMN IF NOT EXISTS longitude FLOAT DEFAULT 72.8311;"))
#     conn.commit()


from backend.database.models import Camera, User
from backend.auth.helpers import get_password_hash
from sqlalchemy import text

db = SessionLocal()

# 0. Ensure default user accounts exist in DB
users_to_seed = [
    ("admin", "Admin@123456", "admin"),
    ("operator", "Operator@123456", "operator"),
    ("viewer", "Viewer@123456", "viewer"),
]
for uname, pwd, role in users_to_seed:
    user = db.query(User).filter(User.username == uname).first()
    if not user:
        db.add(User(username=uname, password_hash=get_password_hash(pwd), role=role))
db.commit()

# 1. Seed RTSP cameras ONLY if table is completely empty
existing_cams_count = db.query(Camera).count()
if existing_cams_count == 0:
    print("Database has no cameras. Seeding initial RTSP camera feeds...")
    cams_to_seed = [
        Camera(id='cam_1', name='Central Bus Depo', location='Platform Area', stream_url='rtsp://127.0.0.1:8554/cam_1', status='online', width=1920, height=1080, latitude=21.2035, longitude=72.8406),
        Camera(id='cam_2', name='Chauta Bazaar A', location='Market Entrance', stream_url='rtsp://127.0.0.1:8554/cam_2', status='online', width=1920, height=1080, latitude=21.1959, longitude=72.8194),
        Camera(id='cam_3', name='Chauta Bazaar B', location='Market Inside', stream_url='rtsp://127.0.0.1:8554/cam_3', status='online', width=1920, height=1080, latitude=21.1965, longitude=72.8210),
        Camera(id='cam_4', name='Gopi Talav', location='Gate', stream_url='rtsp://127.0.0.1:8554/cam_4', status='online', width=1920, height=1080, latitude=21.1901, longitude=72.8252),
        Camera(id='cam_5', name='Mahidharpura', location='Diamond Mkt', stream_url='rtsp://127.0.0.1:8554/cam_5', status='online', width=1920, height=1080, latitude=21.2012, longitude=72.8315),
        Camera(id='cam_6', name='Rly Station', location='Bismillah Rest', stream_url='rtsp://127.0.0.1:8554/cam_6', status='online', width=1920, height=1080, latitude=21.2052, longitude=72.8412),
        Camera(id='cam_7', name='Merged View', location='Custom', stream_url='rtsp://127.0.0.1:8554/cam_7', status='online', width=1920, height=1080, latitude=21.2052, longitude=72.8412)
    ]
    for cam in cams_to_seed:
        db.add(cam)
    db.commit()
    print('Initial camera feeds seeded successfully.')
else:
    print(f'Preserving existing {existing_cams_count} camera(s) in PostgreSQL database.')
