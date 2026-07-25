import os
import time
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# Fallback path for SQLite inside the project directory
LOCAL_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vms.db"))
DATABASE_URL = os.getenv("DATABASE_URL", f"postgresql://vms_user:vms_password@127.0.0.1:5432/vms_db")

engine = None
SessionLocal = None

is_production = os.getenv("APP_ENV") == "production"

try:
    # Attempt to connect to PostgreSQL with retries (fast fail-out if offline to switch to SQLite)
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"connect_timeout": 3},
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True
    )
    connected = False
    
    for attempt in range(5):
        try:
            # Force connection check
            with engine.connect() as conn:
                print("Connected to PostgreSQL successfully.")
                connected = True
                break
        except Exception as e:
            if is_production and attempt == 4:
                raise
            print(f"PostgreSQL not ready yet (attempt {attempt + 1}/5). Waiting 2s...")
            time.sleep(2)
            
    if not connected:
        raise RuntimeError("Failed to connect to PostgreSQL after multiple attempts.")
        
except Exception as e:
    if is_production:
        print(f"FATAL database connection error in production: {e}")
        raise RuntimeError(f"Database connection failed in production: {e}") from e
    print(f"{e} Falling back to local SQLite at {LOCAL_DB_PATH}")
    engine = create_engine(f"sqlite:///{LOCAL_DB_PATH}", connect_args={"check_same_thread": False})
    
    # Enable WAL mode and synchronous=NORMAL on SQLite for non-blocking concurrent reads/writes
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
