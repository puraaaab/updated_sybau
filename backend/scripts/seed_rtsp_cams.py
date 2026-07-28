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

# 1. Seed video cameras ONLY if database table is completely empty
# (prevents re-creating cameras that the user explicitly deleted from the UI)
videos_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'Videos'))

cams_def = [
    ('cam_1', 'Central Bus Depo', 'Platform Area', os.path.join(videos_dir, 'Export__Central Bus Depo-Entry Gate Platform Area_Friday July 10 2026110138  b33bb2a.avi'), 21.2035, 72.8406),
    ('cam_2', 'Chauta Bazaar A', 'Market Entrance', os.path.join(videos_dir, 'Export__Chauta Bazaar-003_Friday July 10 202655158  c62a714.avi'), 21.1959, 72.8194),
    ('cam_3', 'Chauta Bazaar B', 'Market Inside', os.path.join(videos_dir, 'Export__Chauta Bazaar-003_Friday July 10 202655158  c62a714 (1).avi'), 21.1965, 72.8210),
    ('cam_4', 'Gopi Talav', 'Gate', os.path.join(videos_dir, 'Export__Gopi Talav-Towards Gopi Talav Gate_Friday July 10 202661000  dc1f515.avi'), 21.1901, 72.8252),
    ('cam_5', 'Mahidharpura', 'Diamond Mkt', os.path.join(videos_dir, 'Export__Mahidharpura-Pipla Sheri Diamond Mkt_Friday July 10 202655441  beb5fa4.avi'), 21.2012, 72.8315),
    ('cam_6', 'Rly Station', 'Bismillah Rest', os.path.join(videos_dir, 'Export__Rly Station-Towards Bismillah Rest left_Friday July 10 202661242  09a94cc.avi'), 21.2052, 72.8412),
    ('cam_7', 'Merged View', 'Custom', os.path.join(videos_dir, 'merged.mp4'), 21.2052, 72.8412),
]

existing_count = db.query(Camera).count()
if existing_count == 0:
    for cid, cname, cloc, curl, clat, clon in cams_def:
        db.add(Camera(
            id=cid, name=cname, location=cloc, stream_url=curl,
            status='online', width=1920, height=1080, latitude=clat, longitude=clon
        ))

    db.commit()
    print('Base video camera feeds seeded successfully.')

    from backend.scripts.seed_cyber_crime_cams import seed_cyber_crime_dataset_cameras
    seed_cyber_crime_dataset_cameras()
else:
    print(f'Database already populated with {existing_count} camera(s). Preserving user camera configuration.')

db.close()

