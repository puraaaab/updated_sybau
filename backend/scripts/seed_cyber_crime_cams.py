import os
import sys
import xml.etree.ElementTree as ET

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from backend.database.connection import SessionLocal, engine, Base
from backend.database.models import Camera

# Ensure tables exist
Base.metadata.create_all(bind=engine)

base_dir = r"d:\sybau_granth\Cyber Crime-TATA Black Colour Car  27-7-2028"

def seed_cyber_crime_dataset_cameras():
    db = SessionLocal()
    try:
        xml_files = [
            os.path.join(base_dir, "Black car-Kharvarnagar BRTS Junction", "ExportedMedia", "Export__Rokadiya Hanuman-Towards Bhatena C-Turn_Monday July 27 2026123156  cf6384e.xml"),
            os.path.join(base_dir, "Black car-Kharvarnagar BRTS Junction", "ExportedMedia", "Export__Rokadiya Hanuman-Towards Bhatena_Monday July 27 2026123151  e6f4a55.xml"),
            os.path.join(base_dir, "Black car-Kharvarnagar BRTS Junction", "ExportedMedia", "Export__Rokadiya Hanuman-Towards JoganiMata Mandir_Monday July 27 2026123201  7356363.xml"),
            os.path.join(base_dir, "Gauravpath", "ExportedMedia", "Export__GauravPath - Towards Kargil Chowk_Monday July 27 2026122148  aa50cd0.xml"),
            os.path.join(base_dir, "Kargil Chowk", "ExportedMedia", "Export__Kargil Chowk-From Lake view_Monday July 27 2026122056  0ace428.xml"),
            os.path.join(base_dir, "Kargil Chowk", "ExportedMedia", "Export__Kargil Chowk-Towards LakeView General_Monday July 27 2026122054  23f0c44.xml"),
            os.path.join(base_dir, "Parle Point", "ExportedMedia", "Export__Parle Point-Traffic come in SVNIT_Monday July 27 2026121700  0d30db2.xml"),
            os.path.join(base_dir, "SVNIT", "ExportedMedia", "Export__Svnit-Towards Parle Point_Monday July 27 2026121926  7608450.xml")
        ]

        coords_map = {
            "Black car-Kharvarnagar BRTS Junction": (21.1782, 72.8451),
            "Gauravpath": (21.1685, 72.7852),
            "Kargil Chowk": (21.1624, 72.7821),
            "Parle Point": (21.1731, 72.7964),
            "SVNIT": (21.1654, 72.7835)
        }

        seeded_count = 0
        for idx, xml_path in enumerate(xml_files, start=1):
            if not os.path.exists(xml_path):
                print(f"Skipping missing XML file: {xml_path}")
                continue

            tree = ET.parse(xml_path)
            root = tree.getroot()
            cam_elem = root.find("Camera")
            clip_elem = root.find(".//MediaClip")

            rel_dir = os.path.dirname(os.path.relpath(xml_path, base_dir))
            loc_folder = rel_dir.split(os.sep)[0]
            
            cam_name = cam_elem.attrib.get("name", f"Dataset Cam {idx}") if cam_elem is not None else f"Dataset Cam {idx}"
            cam_name = cam_name.strip(" .")
            avi_filename = clip_elem.attrib["file"] if clip_elem is not None else ""
            avi_full_path = os.path.abspath(os.path.join(os.path.dirname(xml_path), avi_filename))

            cam_id = f"cyber_cam_{idx}"
            lat, lon = coords_map.get(loc_folder, (21.1702, 72.8311))

            existing = db.query(Camera).filter(Camera.id == cam_id).first()
            if existing:
                existing.name = cam_name
                existing.location = loc_folder
                existing.stream_url = avi_full_path
                existing.status = "online"
                existing.latitude = lat
                existing.longitude = lon
                print(f"Updated existing camera {cam_id}: {cam_name}")
            else:
                new_cam = Camera(
                    id=cam_id,
                    name=cam_name,
                    location=loc_folder,
                    stream_url=avi_full_path,
                    status="online",
                    width=1920,
                    height=1080,
                    latitude=lat,
                    longitude=lon
                )
                db.add(new_cam)
                print(f"Added new camera {cam_id}: {cam_name} -> {avi_full_path}")
            
            seeded_count += 1

        db.commit()
        print(f"\nSuccessfully registered {seeded_count} dataset cameras into the database.")
    except Exception as e:
        db.rollback()
        print(f"Error seeding dataset cameras: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    seed_cyber_crime_dataset_cameras()
