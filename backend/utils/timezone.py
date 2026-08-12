import datetime

# Indian Standard Time (IST) timezone (+05:30)
IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime.datetime:
    """Returns current datetime object in Indian Standard Time (IST / Asia/Kolkata)."""
    return datetime.datetime.now(IST_TZ)

def get_ist_now_iso() -> str:
    """Returns ISO 8601 string of current datetime in IST."""
    return datetime.datetime.now(IST_TZ).isoformat()

def format_ist_str(dt: datetime.datetime | None) -> str:
    """Formats any datetime into YYYY-MM-DD HH:MM:SS in Indian Standard Time."""
    if not dt:
        return get_ist_now().strftime("%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST_TZ)
    return dt.astimezone(IST_TZ).strftime("%Y-%m-%d %H:%M:%S")
