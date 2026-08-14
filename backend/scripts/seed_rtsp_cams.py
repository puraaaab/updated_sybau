import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env')))

from backend.database.connection import SessionLocal, engine, Base

from backend.database.models import Camera
from sqlalchemy import text

# Ensure database tables exist & migrate missing columns
Base.metadata.create_all(bind=engine)


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

# Clear old sample cameras and seed ONLY the user MOV videos from videos/ directory
videos_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'videos'))
video_files = [f for f in os.listdir(videos_dir) if f.lower().endswith(('.mov', '.mp4', '.avi', '.mkv'))] if os.path.exists(videos_dir) else []
sorted_vfiles = sorted(video_files)

# Wipe all existing camera records to ensure old sample feeds are completely removed
db.query(Camera).delete()
db.commit()

cams_locations = [
    ("Central Bus Depo", "Platform Area", 21.2035, 72.8406),
    ("Chauta Bazaar", "Market Entrance", 21.1959, 72.8194),
    ("Railway Station", "Main Terminal", 21.2052, 72.8412),
    ("Mahidharpura", "Diamond Mkt", 21.2012, 72.8315),
    ("Gopi Talav", "Main Gate", 21.1901, 72.8252),
]

for idx, vf in enumerate(sorted_vfiles, start=1):
    cid = f"cam_{idx}"
    vpath = os.path.join(videos_dir, vf)
    cname, cloc, clat, clon = cams_locations[(idx-1) % len(cams_locations)]
    cname_full = f"{cname} ({vf})"
    db.add(Camera(
        id=cid, name=cname_full, location=cloc, stream_url=vpath,
        status='online', width=1920, height=1080, latitude=clat, longitude=clon
    ))
    print(f"Seeded user video camera feed: {cid} -> {cname_full} ({vf})")

db.commit()
db.close()

