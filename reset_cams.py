from backend.database.connection import SessionLocal
from backend.database.models import Camera
db = SessionLocal()
db.query(Camera).delete()
c1 = Camera(id='cam_01', name='Tokyo Shibuya', stream_url='https://www.youtube.com/live/yznpQlk0exE?si=4yKl8sr3PEFomGTy', status='online', width=1920, height=1080)
c2 = Camera(id='cam_02', name='NYC Times Square', stream_url='https://www.youtube.com/live/ui5S0ld_0po?si=s4slytBgrJ-8oGbf', status='online', width=1920, height=1080)
db.add(c1)
db.add(c2)
db.commit()
print('Reset cameras successfully')
