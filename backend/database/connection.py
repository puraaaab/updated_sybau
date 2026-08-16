import os
import time
from dotenv import load_dotenv
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base

# Load .env configuration
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".env")))

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
    # Attempt to connect to PostgreSQL with fast fail-out if offline to switch to SQLite
    max_attempts = 15 if is_production else 1
    timeout_secs = 10 if is_production else 1

    # In local/dev mode, pre-probe socket to avoid hanging on unreachable PostgreSQL
    if not is_production:
        try:
            from urllib.parse import urlparse
            import socket
            parsed_db = urlparse(DATABASE_URL)
            db_host = parsed_db.hostname or "127.0.0.1"
            db_port = parsed_db.port or 5432
            probe_sock = socket.create_connection((db_host, db_port), timeout=0.8)
            probe_sock.close()
        except Exception as probe_err:
            raise RuntimeError(f"PostgreSQL port unreachable ({probe_err})")

    engine = create_engine(
        DATABASE_URL,
        connect_args={"connect_timeout": 10},
        pool_size=50,
        max_overflow=50,
        pool_timeout=30,
        pool_pre_ping=True,
        pool_recycle=1800
    )
    connected = False

    for attempt in range(max_attempts):
        try:
            with engine.connect() as conn:
                print(f"Connected to PostgreSQL successfully ({_redacted_url(DATABASE_URL)}).")
                connected = True
                break
        except Exception as e:
            if is_production and attempt == max_attempts - 1:
                raise
            if not is_production and attempt == max_attempts - 1:
                raise RuntimeError(f"PostgreSQL unreachable: {e}")
            print(f"PostgreSQL not ready yet (attempt {attempt + 1}/{max_attempts}). Waiting 1s...")
            time.sleep(1)

    if not connected:
        raise RuntimeError("Failed to connect to PostgreSQL.")

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
        try:
            cursor.execute("PRAGMA table_info(cameras);")
            cols = [row[1] for row in cursor.fetchall()]
            if cols and "proximity_scale" not in cols:
                cursor.execute("ALTER TABLE cameras ADD COLUMN proximity_scale FLOAT DEFAULT 1.25;")
        except Exception:
            pass
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
