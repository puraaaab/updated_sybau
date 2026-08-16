import os
import sys
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '.env')))

from backend.database.connection import SessionLocal, engine, Base
from backend.database.models import Camera, User
from backend.auth.helpers import get_password_hash

# Ensure database tables exist
Base.metadata.create_all(bind=engine)

db = SessionLocal()
force_seed = "--force" in sys.argv

marker_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'storage'))
marker_file = os.path.join(marker_dir, '.cameras_seeded')
os.makedirs(marker_dir, exist_ok=True)

try:
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

    is_already_seeded = os.path.exists(marker_file)
    existing_count = db.query(Camera).count()

    if is_already_seeded and not force_seed and existing_count > 0:
        print(f"[seed_rtsp_cams] Preserving camera configuration ({existing_count} active cameras in DB). Deleted cameras stay deleted.")
        sys.exit(0)

    print("[seed_rtsp_cams] Re-seeding all 20 surveillance, cyber crime, and Re-ID camera feeds...")
    db.query(Camera).delete()
    db.commit()

    ALL_CAMERA_DEFINITIONS = [
        # 1. Cyber Crime City Feeds
        {
            "id": "cyber_cam_1",
            "name": "Rokadiya Hanuman-Towards Bhatena C-Turn",
            "location": "Kharvarnagar BRTS",
            "lat": 21.1738, "lon": 72.8423,
            "stream_url": r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028\Black car-Kharvarnagar BRTS Junction\ExportedMedia\Export__Rokadiya Hanuman-Towards Bhatena C-Turn_Monday July 27 2026123156  cf6384e.avi"
        },
        {
            "id": "cyber_cam_2",
            "name": "Rokadiya Hanuman-Towards Bhatena",
            "location": "Kharvarnagar BRTS",
            "lat": 21.1742, "lon": 72.8418,
            "stream_url": r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028\Black car-Kharvarnagar BRTS Junction\ExportedMedia\Export__Rokadiya Hanuman-Towards Bhatena_Monday July 27 2026123151  e6f4a55.avi"
        },
        {
            "id": "cyber_cam_3",
            "name": "Rokadiya Hanuman-Towards JoganiMata Mandir",
            "location": "Kharvarnagar BRTS",
            "lat": 21.1745, "lon": 72.8410,
            "stream_url": r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028\Black car-Kharvarnagar BRTS Junction\ExportedMedia\Export__Rokadiya Hanuman-Towards JoganiMata Mandir_Monday July 27 2026123201  7356363.avi"
        },
        {
            "id": "cyber_cam_4",
            "name": "GauravPath - Towards Kargil Chowk",
            "location": "Gauravpath Piplod",
            "lat": 21.1560, "lon": 72.7750,
            "stream_url": r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028\Gauravpath\ExportedMedia\Export__GauravPath - Towards Kargil Chowk_Monday July 27 2026122148  aa50cd0.avi"
        },
        {
            "id": "cyber_cam_5",
            "name": "Kargil Chowk-From Lake view",
            "location": "Kargil Chowk Piplod",
            "lat": 21.1548, "lon": 72.7715,
            "stream_url": r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028\Kargil Chowk\ExportedMedia\Export__Kargil Chowk-From Lake view_Monday July 27 2026122056  0ace428.avi"
        },
        {
            "id": "cyber_cam_6",
            "name": "Kargil Chowk-Towards LakeView General",
            "location": "Kargil Chowk Piplod",
            "lat": 21.1552, "lon": 72.7720,
            "stream_url": r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028\Kargil Chowk\ExportedMedia\Export__Kargil Chowk-Towards LakeView General_Monday July 27 2026122054  23f0c44.avi"
        },
        {
            "id": "cyber_cam_7",
            "name": "Parle Point-Traffic come in SVNIT",
            "location": "Parle Point Flyover",
            "lat": 21.1712, "lon": 72.7954,
            "stream_url": r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028\Parle Point\ExportedMedia\Export__Parle Point-Traffic come in SVNIT_Monday July 27 2026121700  0d30db2.avi"
        },
        {
            "id": "cyber_cam_8",
            "name": "Svnit-Towards Parle Point",
            "location": "SVNIT Circle",
            "lat": 21.1645, "lon": 72.7845,
            "stream_url": r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028\SVNIT\ExportedMedia\Export__Svnit-Towards Parle Point_Monday July 27 2026121926  7608450.avi"
        },
        # 2. City Surveillance Feeds
        {
            "id": "cam_1",
            "name": "Central Bus Depo (Platform Area)",
            "location": "Platform Area",
            "lat": 21.2035, "lon": 72.8406,
            "stream_url": r"D:\sybau_granth\Videos\Export__Central Bus Depo-Entry Gate Platform Area_Friday July 10 2026110138  b33bb2a.avi"
        },
        {
            "id": "cam_2",
            "name": "Chauta Bazaar (Export 1)",
            "location": "Market Entrance 1",
            "lat": 21.1959, "lon": 72.8194,
            "stream_url": r"D:\sybau_granth\Videos\Export__Chauta Bazaar-003_Friday July 10 202655158  c62a714 (1).avi"
        },
        {
            "id": "cam_3",
            "name": "Chauta Bazaar (Export Main)",
            "location": "Market Entrance Main",
            "lat": 21.1965, "lon": 72.8198,
            "stream_url": r"D:\sybau_granth\Videos\Export__Chauta Bazaar-003_Friday July 10 202655158  c62a714.avi"
        },
        {
            "id": "cam_4",
            "name": "Gopi Talav (Gate Entry)",
            "location": "Main Gate",
            "lat": 21.1901, "lon": 72.8252,
            "stream_url": r"D:\sybau_granth\Videos\Export__Gopi Talav-Towards Gopi Talav Gate_Friday July 10 202661000  dc1f515.avi"
        },
        {
            "id": "cam_5",
            "name": "Mahidharpura Diamond Market",
            "location": "Pipla Sheri",
            "lat": 21.2012, "lon": 72.8315,
            "stream_url": r"D:\sybau_granth\Videos\Export__Mahidharpura-Pipla Sheri Diamond Mkt_Friday July 10 202655441  beb5fa4.avi"
        },
        {
            "id": "cam_6",
            "name": "Railway Station (Ring Road Junction)",
            "location": "Towards Bismillah Rest",
            "lat": 21.1980, "lon": 72.8300,
            "stream_url": r"D:\sybau_granth\Videos\Export__Rly Station-Towards Bismillah Rest left_Friday July 10 202661242  09a94cc.avi"
        },
        {
            "id": "cam_7",
            "name": "Athwa Gate (Merged Traffic)",
            "location": "Athwa Gate Junction",
            "lat": 21.1850, "lon": 72.8150,
            "stream_url": r"D:\sybau_granth\Videos\merged.mp4"
        },
        # 3. Re-ID Checkpoint Feeds
        {
            "id": "cam_8",
            "name": "Re-ID Checkpoint 8 (IMG_0111.MOV)",
            "location": "Re-ID Node #8",
            "lat": 21.2160, "lon": 72.8360,
            "stream_url": r"D:\sybau_granth\Videos\Re-id check\IMG_0111.MOV"
        },
        {
            "id": "cam_9",
            "name": "Re-ID Checkpoint 9 (IMG_0112.MOV)",
            "location": "Re-ID Node #9",
            "lat": 21.2180, "lon": 72.8380,
            "stream_url": r"D:\sybau_granth\Videos\Re-id check\IMG_0112.MOV"
        },
        {
            "id": "cam_10",
            "name": "Re-ID Checkpoint 10 (IMG_0113.MOV)",
            "location": "Re-ID Node #10",
            "lat": 21.2200, "lon": 72.8400,
            "stream_url": r"D:\sybau_granth\Videos\Re-id check\IMG_0113.MOV"
        },
        {
            "id": "cam_11",
            "name": "Re-ID Checkpoint 11 (IMG_0114.MOV)",
            "location": "Re-ID Node #11",
            "lat": 21.2220, "lon": 72.8420,
            "stream_url": r"D:\sybau_granth\Videos\Re-id check\IMG_0114.MOV"
        },
        {
            "id": "cam_12",
            "name": "Re-ID Checkpoint 12 (IMG_0115.MOV)",
            "location": "Re-ID Node #12",
            "lat": 21.2240, "lon": 72.8440,
            "stream_url": r"D:\sybau_granth\Videos\Re-id check\IMG_0115.MOV"
        },
    ]

    for item in ALL_CAMERA_DEFINITIONS:
        db.add(Camera(
            id=item["id"],
            name=item["name"],
            location=item["location"],
            stream_url=item["stream_url"],
            status="online",
            width=1920,
            height=1080,
            latitude=item["lat"],
            longitude=item["lon"]
        ))
        print(f"  [+] Seeded Camera: {item['id']} -> {item['name']}")

    db.commit()
    with open(marker_file, "w") as f:
        f.write("seeded\n")
    print(f"[seed_rtsp_cams] Successfully seeded all {len(ALL_CAMERA_DEFINITIONS)} camera feeds.")

finally:
    db.close()
