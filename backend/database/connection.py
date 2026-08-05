import os
import time
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# Fallback path for SQLite inside the project directory
# Fallback path for SQLite inside the project directory
LOCAL_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "vms.db"))
raw_db_url = os.getenv("DATABASE_URL", "")

is_production = os.getenv("APP_ENV") == "production"

if is_production and (not raw_db_url or "vms_password" in raw_db_url):
    raise RuntimeError(
        "FATAL: DATABASE_URL must be explicitly set with secure credentials in production mode! "
        "Default or fallback passwords are not permitted in production."
    )

DATABASE_URL = raw_db_url or "postgresql://vms_user:vms_password@127.0.0.1:5432/vms_db"

engine = None
SessionLocal = None


def _redacted_url(url: str) -> str:
    """Mask password in connection strings for safe logging."""
    if "@" in url and ":" in url:
        try:
            proto, rest = url.split("://", 1)
            user_pass, host_db = rest.split("@", 1)
            user = user_pass.split(":", 1)[0]
            return f"{proto}://{user}:****@{host_db}"
        except Exception:
            return "postgresql://***:****@***"
    return url


try:
    # Attempt to connect to PostgreSQL with retries (fast fail-out if offline to switch to SQLite)
    engine = create_engine(
        DATABASE_URL,
        connect_args={"connect_timeout": 10},
        pool_size=20,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=1800
    )
    connected = False

    for attempt in range(15):
        try:
            with engine.connect() as conn:
                print(f"Connected to PostgreSQL successfully ({_redacted_url(DATABASE_URL)}).")
                connected = True
                break
        except Exception as e:
            if is_production and attempt == 14:
                raise
            print(f"PostgreSQL not ready yet (attempt {attempt + 1}/15). Waiting 1s...")
            time.sleep(1)

    if not connected:
        raise RuntimeError("Failed to connect to PostgreSQL after 5 retries.")

except Exception as e:
    if is_production:
        print(f"FATAL database connection error in production: {e}")
        raise RuntimeError(f"Database connection failed in production: {e}") from e

    print(f"PostgreSQL unavailable ({e}). Falling back to local SQLite at {LOCAL_DB_PATH}")
    engine = create_engine(f"sqlite:///{LOCAL_DB_PATH}", connect_args={"check_same_thread": False})

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
