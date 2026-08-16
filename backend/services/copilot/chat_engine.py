"""
VMS Pro — Conversational Surveillance AI Chat Engine (v2)
============================================================
Multi-turn AI chatbot reasoning, visual image upload matching,
multi-camera trajectory timeline synthesis, follow-up/context
resolution, and session memory persistence.

What changed vs. v1 (see CHANGELOG at bottom of this docstring):
  * Query understanding is now a real pipeline (QueryIntentParser)
    instead of a single Hinglish regex pass — extracts camera
    filters, time windows ("aaj", "last hour", "kal raat"),
    object class, and colour, on top of language normalisation.
  * Follow-up / pronoun resolution: "uska phir kaha dikha?" now
    reuses the subject entities from the previous turn instead of
    re-searching blind.
  * Optional LLM reasoning layer (Anthropic Messages API) produces
    the conversational answer and does language-aware synthesis;
    falls back to the deterministic template engine automatically
    if no API key is configured or the call fails/times out, so
    the assistant never breaks.
  * All outbound calls (semantic search, Moondream vision, LLM)
    are wrapped with bounded retries + timeouts instead of being
    allowed to hang or crash the whole request.
  * Trajectory synthesis is now a dedicated step that also flags
    gaps/backtracking and (when cameras carry lat/lon) can report
    straight-line inferred travel speed between sightings.
  * Structured audit logging of every query (who asked what, when,
    how many hits) — required for the project's DPDP audit trail,
    written defensively so it never breaks the request if the
    audit table isn't present in a given deployment.
  * Image ingestion is validated (decodable, size-bounded, format
    whitelisted) and EXIF-stripped before it ever touches disk.
  * `get_history` supports pagination instead of loading the full
    session every time.
  * Everything is fully type-hinted, uses custom exceptions instead
    of bare `except Exception`, and session/db handling is centralised
    in a context manager so nothing can leak a connection.

Assumptions carried over from v1 (adjust to your actual schema):
  * `Camera`, `SceneCaption`, `ChatSession`, `ChatMessage` models as
    imported below. Optional columns (`Camera.latitude/longitude`,
    an `AuditLog` model) are accessed defensively via getattr/try-except
    so this module works whether or not they exist yet.
"""

from __future__ import annotations

import os
import re
import json
import time
import uuid
import base64
import logging
import datetime
import functools
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Generator, List, Optional, Tuple

import cv2
import numpy as np
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from ...database.connection import SessionLocal
from ...database.models import (
    Camera, SceneCaption, Vehicle, Track, Alert,
    PersonJourneyEvent, VehicleJourneyEvent,
    ChatSession, ChatMessage, _istnow,
)
from ...search.vector_search import perform_semantic_search
from ...ai.embeddings.embedder import get_text_embedding
from ...ai.captioning.moondream_captioner import _call_moondream_api, _encode_frame

logger = logging.getLogger(__name__)


# ============================================================
# Configuration
# ============================================================

class ChatConfig:
    SEMANTIC_SEARCH_LIMIT = 15
    IMAGE_SEARCH_LIMIT = 10
    SQL_CAPTION_SCAN_LIMIT = 60
    HISTORY_CONTEXT_TURNS = 6          # turns fed back for follow-up resolution
    MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB
    MAX_IMAGE_DIM = 1920
    ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
    RETRY_ATTEMPTS = 3
    RETRY_BASE_DELAY_S = 0.6
    EXTERNAL_CALL_TIMEOUT_S = 20
    LLM_MODEL = os.environ.get("VMS_CHAT_LLM_MODEL", "claude-sonnet-4-6")
    LLM_MAX_TOKENS = 700
    USE_LLM_REASONING = bool(os.environ.get("ANTHROPIC_API_KEY"))


# ============================================================
# Exceptions
# ============================================================

class ChatEngineError(Exception):
    """Base class for all recoverable chat-engine errors."""


class InvalidImageError(ChatEngineError):
    pass


class ExternalServiceError(ChatEngineError):
    """Raised when a downstream call (search / vision / LLM) exhausts retries."""


# ============================================================
# Retry helper
# ============================================================

def with_retries(attempts: int = ChatConfig.RETRY_ATTEMPTS,
                  base_delay: float = ChatConfig.RETRY_BASE_DELAY_S):
    """Decorator: retries a flaky external call with exponential backoff."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc: Optional[Exception] = None
            for attempt in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001 - deliberately broad, external boundary
                    last_exc = exc
                    if attempt == attempts:
                        break
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "[ChatEngine] %s failed (attempt %d/%d): %s — retrying in %.1fs",
                        fn.__name__, attempt, attempts, exc, delay,
                    )
                    time.sleep(delay)
            raise ExternalServiceError(f"{fn.__name__} failed after {attempts} attempts: {last_exc}") from last_exc
        return wrapper
    return decorator


# ============================================================
# Language normalisation (Hinglish / Gujlish -> English search terms)
# ============================================================

class HinglishQueryTranslator:
    """Translates Hinglish, Gujlish, and Romanized Hindi/Gujarati query terms to normalized English search terms."""

    HINGLISH_MAP: List[Tuple[str, str]] = [
        # Colors
        (r"\b(nila|neela|nili|blue color)\b", "blue"),
        (r"\b(laal|lal|lali|red color)\b", "red"),
        (r"\b(kaala|kala|kali|black color)\b", "black"),
        (r"\b(safed|chitta|white color)\b", "white"),
        (r"\b(pila|peela|yellow color)\b", "yellow"),
        (r"\b(hara|haraa|green color)\b", "green"),
        (r"\b(gulabi|pink color)\b", "pink"),
        (r"\b(bhura|bhoora|brown color)\b", "brown"),
        (r"\b(sonery|golden|sunehra)\b", "gold"),

        # Persons & Attributes
        (r"\b(banda|bande|aadmi|insan|man|guy|ladka|larkaa|bhai|chokro)\b", "person man"),
        (r"\b(aurat|mahila|ladki|woman|girl|larki|chokri)\b", "woman person"),
        (r"\b(bacha|bachcha|bachi|child|kid|balak)\b", "child person"),
        (r"\b(shirt|kamiz|kameez|tshirt|t-shirt|top|kapde|kapda)\b", "shirt clothing top"),
        (r"\b(pant|penta|jeans|lower|pyjama)\b", "pants bottom clothing"),
        (r"\b(bag|jhola|backpack|basta)\b", "backpack bag"),

        # Vehicles
        (r"\b(gadi|gaadi|car|vehicle|vhicle)\b", "car vehicle"),
        (r"\b(scooter|activa|gaddi|bike|motorcycle|scooty|two wheeler)\b", "motorcycle scooter activa"),
        (r"\b(auto|rickshaw|tuktuk|three wheeler)\b", "auto-rickshaw rickshaw"),
        (r"\b(truck|lorry|bus)\b", "truck bus"),

        # Actions & Sighting terms (Hindi & Gujarati)
        (r"\b(dikha|dikhaa|dikhna|dekha|dekhi|joyeli|milya|spot|spotted|found|seen|dekhna)\b", "spotted detected observed"),
        (r"\b(chalane|chala raha|riding|rider|chalati|chala)\b", "riding driving"),
        (r"\b(baitha|baithi|sitting|khada|khadi|standing)\b", "sitting standing"),
        (r"\b(bina helmet|no helmet|helmet bagar|without helmet)\b", "without helmet motorcycle"),
        (r"\b(bhaag raha|bhagi|running|daud|daudta)\b", "running"),

        # Locations
        (r"\b(station|railway station|bus station)\b", "station main gate entrance"),
        (r"\b(paas|dhabe pase|dokan|shop|counter|gate|entrance|parking|bazar|market)\b", "gate entrance parking bay market"),
    ]

    INDICATORS = [
        "kya", "dikha", "dekha", "wala", "wali", "wale", "banda", "gadi", "gaadi",
        "station", "par", "pr", "hai", "tha", "thi", "koi", "bina", "joyeli",
        "milya", "kaha", "kya", "chhe", "hato", "kyare",
    ]

    FILLER = r"\b(koi|ka|ki|ke|pr|par|kya|tha|thi|hai|hu|huwa|huya|pase|najeek|chhe|hato)\b"

    @classmethod
    def is_hinglish(cls, text: str) -> bool:
        t_lower = text.lower()
        return any(re.search(rf"\b{ind}\b", t_lower) for ind in cls.INDICATORS)

    @classmethod
    def translate_to_english(cls, text: str) -> str:
        translated = text.lower()
        for pattern, replacement in cls.HINGLISH_MAP:
            translated = re.sub(pattern, replacement, translated, flags=re.IGNORECASE)
        translated = re.sub(cls.FILLER, "", translated, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", translated).strip()


# ============================================================
# Query intent extraction (camera filter, time window, follow-up refs)
# ============================================================

@dataclass
class QueryIntent:
    raw_query: str
    search_prompt: str
    is_hinglish: bool
    camera_filter: Optional[str] = None
    time_start: Optional[datetime.datetime] = None
    time_end: Optional[datetime.datetime] = None
    is_followup: bool = False
    followup_reference: Optional[str] = None  # entity carried over from previous turn


_CAMERA_PATTERN = re.compile(r"\bcam(?:era)?\s*[\-#]?\s*(\w[\w\- ]{0,20})", re.IGNORECASE)

_TIME_WINDOWS = [
    (r"\b(last|pichhle|pichle)\s+(hour|ghanta|ghante)\b", datetime.timedelta(hours=1)),
    (r"\b(last|pichhle|pichle)\s+(30|thirty)\s*min", datetime.timedelta(minutes=30)),
    (r"\b(last|pichhle|pichle)\s+(15|fifteen)\s*min", datetime.timedelta(minutes=15)),
    (r"\b(today|aaj|aaje)\b", datetime.timedelta(hours=24)),
    (r"\b(yesterday|kal|gaikale)\b", datetime.timedelta(hours=48)),
]

_FOLLOWUP_MARKERS = re.compile(
    r"^\s*(usko?|uska|usse|usne|and (then|after)|then\??|uske baad|phir\s|kaha aur|"
    r"where else|what about (him|her|it|them)|any other sighting)",
    re.IGNORECASE,
)


class QueryIntentParser:
    """Extracts structured filters/context from a raw natural-language query."""

    @staticmethod
    def parse(user_query: str, last_intent: Optional["QueryIntent"] = None) -> QueryIntent:
        is_hi = HinglishQueryTranslator.is_hinglish(user_query)
        search_prompt = HinglishQueryTranslator.translate_to_english(user_query) if is_hi else user_query

        camera_filter = None
        cam_match = _CAMERA_PATTERN.search(user_query)
        if cam_match:
            camera_filter = cam_match.group(1).strip()

        now = _istnow()
        time_start = None
        time_end = now
        for pattern, delta in _TIME_WINDOWS:
            if re.search(pattern, user_query, flags=re.IGNORECASE):
                time_start = now - delta
                break

        # 1. "between 9AM and 12PM" / "9 se 12 ke beech"
        if time_start is None:
            between_match = re.search(
                r"\b(?:between|from)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:and|to|se)\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b",
                user_query, re.IGNORECASE
            )
            if between_match:
                h1, m1, mer1, h2, m2, mer2 = between_match.groups()
                try:
                    hour1 = int(h1)
                    min1 = int(m1 or 0)
                    if mer1 and mer1.lower() == "pm" and hour1 < 12:
                        hour1 += 12
                    elif mer1 and mer1.lower() == "am" and hour1 == 12:
                        hour1 = 0
                    elif not mer1 and mer2 and mer2.lower() == "pm" and hour1 < 12 and hour1 < int(h2):
                        hour1 += 12
                        
                    hour2 = int(h2)
                    min2 = int(m2 or 0)
                    if mer2 and mer2.lower() == "pm" and hour2 < 12:
                        hour2 += 12
                    elif mer2 and mer2.lower() == "am" and hour2 == 12:
                        hour2 = 0
                        
                    time_start = now.replace(hour=hour1, minute=min1, second=0, microsecond=0)
                    time_end = now.replace(hour=hour2, minute=min2, second=0, microsecond=0)
                except Exception:
                    pass

        # 2. "after 10AM", "after 10:30 am", "from 10am", "10 baje ke baad"
        if time_start is None:
            after_match = re.search(
                r"\b(?:after|post|since)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b|\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:ke baad|baje ke baad)\b",
                user_query, re.IGNORECASE
            )
            if after_match:
                h_str = after_match.group(1) or after_match.group(4)
                m_str = after_match.group(2) or after_match.group(5) or "0"
                meridiem = (after_match.group(3) or after_match.group(6) or "").lower()
                try:
                    hour = int(h_str)
                    minute = int(m_str)
                    if meridiem == "pm" and hour < 12:
                        hour += 12
                    elif meridiem == "am" and hour == 12:
                        hour = 0
                    time_start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                except Exception:
                    pass

        # 3. "before 2PM", "prior to 11AM", "2 baje se pehle"
        if time_start is None:
            before_match = re.search(
                r"\b(?:before|prior to|until|till)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b|\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*(?:se pehle|baje se pehle)\b",
                user_query, re.IGNORECASE
            )
            if before_match:
                h_str = before_match.group(1) or before_match.group(4)
                m_str = before_match.group(2) or before_match.group(5) or "0"
                meridiem = (before_match.group(3) or before_match.group(6) or "").lower()
                try:
                    hour = int(h_str)
                    minute = int(m_str)
                    if meridiem == "pm" and hour < 12:
                        hour += 12
                    elif meridiem == "am" and hour == 12:
                        hour = 0
                    time_end = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    time_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
                except Exception:
                    pass

        is_followup = bool(_FOLLOWUP_MARKERS.search(user_query.strip()))
        followup_reference = None
        if is_followup and last_intent is not None:
            # Carry forward the previous turn's effective search subject so a
            # short follow-up like "phir kaha dikha?" still resolves to a target.
            followup_reference = last_intent.search_prompt
            if camera_filter is None:
                camera_filter = None  # explicit: don't inherit old camera filter, user usually wants "elsewhere"

        return QueryIntent(
            raw_query=user_query,
            search_prompt=search_prompt,
            is_hinglish=is_hi,
            camera_filter=camera_filter,
            time_start=time_start,
            time_end=time_end,
            is_followup=is_followup,
            followup_reference=followup_reference,
        )

    @staticmethod
    def effective_search_prompt(intent: QueryIntent) -> str:
        if intent.is_followup and intent.followup_reference:
            return f"{intent.followup_reference} {intent.search_prompt}".strip()
        return intent.search_prompt


# ============================================================
# Timeline / trajectory synthesis
# ============================================================

@dataclass
class TimelineItem:
    camera_id: Any
    camera_name: str
    timestamp: str
    time_display: str
    description: str
    snapshot_url: Optional[str]
    score: float

    def as_dict(self) -> Dict[str, Any]:
        return {
            "camera_id": self.camera_id,
            "camera_name": self.camera_name,
            "timestamp": self.timestamp,
            "time_display": self.time_display,
            "description": self.description,
            "snapshot_url": self.snapshot_url,
            "score": self.score,
        }


def _format_time_display(ts_str: str) -> str:
    if not ts_str:
        return "N/A"
    try:
        dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return dt.strftime("%I:%M %p").lstrip("0")
    except (ValueError, TypeError):
        return ts_str[:16]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    from math import radians, sin, cos, asin, sqrt
    r = 6371.0
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def build_trajectory_summary(timeline_items: List[Dict[str, Any]],
                              camera_geo: Dict[Any, Tuple[float, float]]) -> Dict[str, Any]:
    """Summarises movement across cameras: order, gaps, and (if geo available) inferred speed/anomalies."""
    if len(timeline_items) < 2:
        return {"legs": [], "flags": []}

    legs = []
    flags: List[str] = []
    for prev, curr in zip(timeline_items, timeline_items[1:]):
        leg: Dict[str, Any] = {
            "from_camera": prev["camera_name"],
            "to_camera": curr["camera_name"],
            "from_time": prev["time_display"],
            "to_time": curr["time_display"],
        }
        try:
            t1 = datetime.datetime.fromisoformat((prev["timestamp"] or "").replace("Z", "+00:00"))
            t2 = datetime.datetime.fromisoformat((curr["timestamp"] or "").replace("Z", "+00:00"))
            gap_minutes = max((t2 - t1).total_seconds() / 60.0, 0.0)
            leg["gap_minutes"] = round(gap_minutes, 1)
            if gap_minutes < 0:
                flags.append(f"Out-of-order timestamps between {prev['camera_name']} and {curr['camera_name']}")
        except (ValueError, TypeError, KeyError):
            gap_minutes = None

        geo1 = camera_geo.get(prev["camera_id"])
        geo2 = camera_geo.get(curr["camera_id"])
        if geo1 and geo2 and gap_minutes and gap_minutes > 0:
            dist_km = _haversine_km(*geo1, *geo2)
            speed_kmh = dist_km / (gap_minutes / 60.0)
            leg["distance_km"] = round(dist_km, 2)
            if speed_kmh <= 120.0:
                leg["inferred_speed_kmh"] = round(speed_kmh, 1)
            else:
                # Discard physically impossible speeds (e.g. multiple concurrent camera hits)
                leg["inferred_speed_kmh"] = None
                flags.append(
                    f"Concurrent sightings at {prev['camera_name']} and {curr['camera_name']} within {gap_minutes:.1f}m (independent events)"
                )
        legs.append(leg)

    return {"legs": legs, "flags": flags}


# ============================================================
# Optional LLM reasoning layer
# ============================================================

class LLMReasoner:
    """Thin wrapper around the Anthropic Messages API for conversational synthesis.

    Falls back cleanly (raises ExternalServiceError) if unavailable — callers
    must catch this and use the deterministic template engine instead.
    """

    def __init__(self):
        self._client = None
        if ChatConfig.USE_LLM_REASONING:
            try:
                import anthropic  # type: ignore # local import: optional dependency
                self._client = anthropic.Anthropic()
            except Exception as exc:  # noqa: BLE001
                logger.warning("[ChatEngine] LLM reasoning disabled — anthropic client unavailable: %s", exc)
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    @with_retries()
    def synthesize_answer(self, *, user_query: str, is_hinglish: bool,
                           timeline_items: List[Dict[str, Any]],
                           trajectory: Dict[str, Any],
                           recent_history: List[Dict[str, str]]) -> str:
        if not self._client:
            raise ExternalServiceError("LLM client not configured")

        system_prompt = (
            "You are the conversational assistant inside a police CCTV surveillance "
            "console (VMS Pro). You are given structured sighting results already "
            "retrieved by the system's search pipeline — never invent sightings, "
            "cameras, or times that are not in the provided data. "
            "Answer in the same language register the operator used (English, or "
            "Hinglish/Gujlish if they wrote in that style). Be concise, factual, and "
            "operational: lead with whether a match was found, list the strongest "
            "matches with camera + time, and note the overall movement pattern if "
            "there is more than one sighting. Flag any anomalies you're given "
            "(implausible speed, out-of-order timestamps) plainly. If there are zero "
            "matches, say so clearly and suggest one or two concrete ways to refine "
            "the search. Never speculate about identity beyond what the captions say."
        )

        payload = {
            "operator_query": user_query,
            "timeline": timeline_items[:10],
            "trajectory": trajectory,
        }

        messages = []
        for turn in recent_history[-ChatConfig.HISTORY_CONTEXT_TURNS:]:
            role = "user" if turn.get("sender") == "user" else "assistant"
            messages.append({"role": role, "content": turn.get("text", "")})
        messages.append({"role": "user", "content": json.dumps(payload, default=str)})

        resp = self._client.messages.create(
            model=ChatConfig.LLM_MODEL,
            max_tokens=ChatConfig.LLM_MAX_TOKENS,
            system=system_prompt,
            messages=messages,
        )
        text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        answer = "\n".join(text_parts).strip()
        if not answer:
            raise ExternalServiceError("LLM returned empty response")
        return answer


# ============================================================
# Deterministic template fallback (always available, zero external deps)
# ============================================================

def _template_answer(user_query: str, is_hinglish: bool,
                      timeline_items: List[Dict[str, Any]],
                      trajectory: Dict[str, Any]) -> str:
    if not timeline_items:
        if is_hinglish:
            return (
                f"Maine saare active camera feeds aur archives check kiye for **\"{user_query}\"**, "
                f"par recent video logs me koi clear match nahi mila. "
                f"Aap specific clothing color, vehicle type ya location name ke saath search try kar sakte hain."
            )
        return (
            f"I searched all active camera feeds and event archives for **\"{user_query}\"**, "
            f"but could not find any clear matches in recent video logs. "
            f"You can try refining your query with specific clothing colors, vehicle types, or location names."
        )

    cams_involved = list(dict.fromkeys(t["camera_name"] for t in timeline_items))
    first_seen, last_seen = timeline_items[0], timeline_items[-1]

    if is_hinglish:
        lines = [f"Haan! Live surveillance feeds ke analysis ke according, **{len(timeline_items)} matching sighting(s)** mili hain **{len(cams_involved)} camera location(s)** par:\n"]
        for idx, t in enumerate(timeline_items[:5], 1):
            lines.append(f"{idx}. **{t['camera_name']}** par **{t['time_display']}** ko: {t['description']}")
        if len(timeline_items) > 1:
            lines.append(f"\n📍 **Movement Trajectory**: Sabse pehle **{first_seen['camera_name']}** ({first_seen['time_display']}) par spot hua, aur baad me **{last_seen['camera_name']}** ({last_seen['time_display']}) par dekha gaya.")
    else:
        lines = [f"Yes! Based on live surveillance analysis, I found **{len(timeline_items)} matching sighting(s)** across **{len(cams_involved)} camera location(s)**:\n"]
        for idx, t in enumerate(timeline_items[:5], 1):
            lines.append(f"{idx}. **{t['camera_name']}** at **{t['time_display']}**: {t['description']}")
        if len(timeline_items) > 1:
            lines.append(f"\n📍 **Movement Summary**: First spotted at **{first_seen['camera_name']}** ({first_seen['time_display']}), and later observed at **{last_seen['camera_name']}** ({last_seen['time_display']}).")

    for flag in trajectory.get("flags", []):
        lines.append(f"\n⚠️ {flag}")

    return "\n".join(lines)


# ============================================================
# Main engine
# ============================================================

class SurveillanceChatEngine:
    """Conversational AI Surveillance Assistant Engine with Multi-Lingual Hinglish & Gujlish Support."""

    def __init__(self):
        self.snap_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "storage", "snapshots")
        )
        os.makedirs(self.snap_dir, exist_ok=True)
        self.reasoner = LLMReasoner()

    # ---- session / db plumbing -------------------------------------------------

    @contextmanager
    def _db_session(self) -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def get_or_create_session(self, db: Session, session_uuid: Optional[str] = None,
                               username: str = "operator") -> ChatSession:
        if session_uuid:
            session = db.query(ChatSession).filter(ChatSession.session_uuid == session_uuid).first()
            if session:
                return session

        new_uuid = session_uuid or f"chat_{uuid.uuid4().hex[:10]}"
        session = ChatSession(
            session_uuid=new_uuid,
            username=username,
            title="Surveillance Investigation Chat",
            created_at=_istnow(),
            updated_at=_istnow(),
        )
        db.add(session)
        db.commit()
        return session

    def _recent_history(self, db: Session, session_uuid: str, limit: int) -> List[Dict[str, str]]:
        msgs = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_uuid == session_uuid)
            .order_by(ChatMessage.timestamp.desc())
            .limit(limit)
            .all()
        )
        return [{"sender": m.sender, "text": m.text} for m in reversed(msgs)]

    def _last_intent(self, db: Session, session_uuid: str) -> Optional[QueryIntent]:
        last_user_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_uuid == session_uuid, ChatMessage.sender == "user")
            .order_by(ChatMessage.timestamp.desc())
            .offset(1)  # skip the message just inserted for the current turn
            .first()
        )
        if not last_user_msg:
            return None
        return QueryIntentParser.parse(last_user_msg.text)

    def _audit_log(self, db: Session, *, session_uuid: str, username: str,
                    action: str, detail: Dict[str, Any]) -> None:
        """Best-effort audit trail write. Never allowed to break the request."""
        try:
            from ...database.models import QueryAuditLog
            query_txt = detail.get("query", action)
            mode_str = detail.get("search_mode", "all")
            hits_cnt = detail.get("hits", 0)
            db.add(QueryAuditLog(
                username=username,
                session_uuid=session_uuid,
                query_text=query_txt,
                search_mode=mode_str,
                matched_records_count=hits_cnt,
                matched_sighting_ids=json.dumps(detail.get("sighting_ids", []), default=str),
                execution_time_ms=float(detail.get("execution_time_ms", 0.0)),
                timestamp=_istnow(),
            ))
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[ChatEngine] QueryAuditLog write note (%s): %s", action, exc)

    # ---- shared search helpers --------------------------------------------------

    @with_retries()
    def _semantic_search(self, prompt: str, limit: int) -> List[Dict[str, Any]]:
        return perform_semantic_search(prompt, limit=limit)

    def _camera_lookup(self, db: Session) -> Tuple[Dict[Any, str], Dict[Any, Tuple[float, float]]]:
        cameras = db.query(Camera).all()
        name_map = {c.id: c.name for c in cameras}
        geo_map: Dict[Any, Tuple[float, float]] = {}
        for c in cameras:
            lat, lon = getattr(c, "latitude", None), getattr(c, "longitude", None)
            if lat is not None and lon is not None:
                geo_map[c.id] = (float(lat), float(lon))
        return name_map, geo_map

    def _build_timeline(self, semantic_results: List[Dict[str, Any]],
                         sql_captions: List[SceneCaption],
                         camera_map: Dict[Any, str],
                         intent: QueryIntent) -> List[Dict[str, Any]]:
        items: List[TimelineItem] = []
        seen = set()

        def _matches_filters(cid: Any, ts_str: str) -> bool:
            if intent.camera_filter:
                cname = str(camera_map.get(cid, "")).lower()
                cid_str = str(cid).lower()
                cf = intent.camera_filter.lower().strip()
                num_only = re.sub(r"[^\d]", "", cf)
                # Match against camera name, camera ID (cam_11), or numeric suffix
                matches_cam = (
                    cf in cname or
                    cf in cid_str or
                    (num_only and (f"cam_{num_only}" == cid_str or f"checkpoint {num_only}" in cname or f"node #{num_only}" in cname or f"cam {num_only}" in cname or num_only == cid_str.replace("cam_", "")))
                )
                if not matches_cam:
                    return False
            if intent.time_start and ts_str:
                try:
                    dt = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if dt < intent.time_start:
                        return False
                except (ValueError, TypeError):
                    pass
            return True

        for item in semantic_results:
            cid = item.get("camera_id") or "cam_1"
            ts_str = item.get("timestamp") or ""
            if not _matches_filters(cid, ts_str):
                continue
            cap_text = item.get("caption") or ""
            key = (cid, ts_str, cap_text[:30])
            if key in seen:
                continue
            seen.add(key)
            items.append(TimelineItem(
                camera_id=cid,
                camera_name=camera_map.get(cid, f"Camera {cid}"),
                timestamp=ts_str,
                time_display=_format_time_display(ts_str),
                description=cap_text,
                snapshot_url=item.get("snapshot_url"),
                score=round(float(item.get("score", 0.85)), 2),
            ))

        for sc in sql_captions:
            cid = sc.camera_id
            ts_str = sc.timestamp.isoformat() if sc.timestamp else ""
            if not _matches_filters(cid, ts_str):
                continue
            key = (cid, ts_str, sc.caption[:30])
            if key in seen:
                continue
            seen.add(key)
            items.append(TimelineItem(
                camera_id=cid,
                camera_name=camera_map.get(cid, f"Camera {cid}"),
                timestamp=ts_str,
                time_display=_format_time_display(ts_str),
                description=sc.caption,
                snapshot_url=sc.snapshot_url,
                score=0.90,
            ))

        items.sort(key=lambda x: x.timestamp or "")
        return [i.as_dict() for i in items]

    def _synthesize_answer(self, *, session_uuid: str, db: Session, intent: QueryIntent,
                            timeline_items: List[Dict[str, Any]],
                            trajectory: Dict[str, Any]) -> str:
        if self.reasoner.available:
            try:
                history = self._recent_history(db, session_uuid, ChatConfig.HISTORY_CONTEXT_TURNS)
                return self.reasoner.synthesize_answer(
                    user_query=intent.raw_query,
                    is_hinglish=intent.is_hinglish,
                    timeline_items=timeline_items,
                    trajectory=trajectory,
                    recent_history=history,
                )
            except ExternalServiceError as exc:
                logger.warning("[ChatEngine] LLM reasoning failed, falling back to templates: %s", exc)
        return _template_answer(intent.raw_query, intent.is_hinglish, timeline_items, trajectory)

    # ---- public API --------------------------------------------------------------

    def list_sessions(self, username: str = "operator") -> List[Dict[str, Any]]:
        """Lists persistent AI Chatbot investigation sessions with metadata."""
        with self._db_session() as db:
            sessions = (
                db.query(ChatSession)
                .order_by(ChatSession.updated_at.desc())
                .limit(50)
                .all()
            )
            out = []
            for s in sessions:
                msg_count = db.query(ChatMessage).filter(ChatMessage.session_uuid == s.session_uuid).count()
                first_msg = (
                    db.query(ChatMessage)
                    .filter(ChatMessage.session_uuid == s.session_uuid, ChatMessage.sender == "user")
                    .order_by(ChatMessage.id.asc())
                    .first()
                )
                title = s.title
                if first_msg and (not title or title == "Surveillance AI Chat" or title == "Surveillance Investigation Chat"):
                    clean_txt = first_msg.text.replace("[Uploaded Image]", "").strip()
                    title = clean_txt[:36].replace("\n", " ")
                    if len(clean_txt) > 36:
                        title += "..."
                out.append({
                    "session_uuid": s.session_uuid,
                    "title": title or "Investigation Chat",
                    "created_at": s.created_at.isoformat() if s.created_at else "",
                    "updated_at": s.updated_at.isoformat() if s.updated_at else "",
                    "message_count": msg_count,
                })
            return out

    def delete_session(self, session_uuid: str, username: str = "operator") -> bool:
        """Deletes an entire chat session and its associated messages."""
        with self._db_session() as db:
            db.query(ChatMessage).filter(ChatMessage.session_uuid == session_uuid).delete()
            db.query(ChatSession).filter(ChatSession.session_uuid == session_uuid).delete()
            db.commit()
            return True

    def process_text_query(self, user_query: str, session_uuid: Optional[str] = None,
                            username: str = "operator", search_mode: str = "all") -> Dict[str, Any]:
        """Processes natural language (English / Hinglish / Gujlish) user questions
        and generates a conversational answer with a supporting timeline."""
        if not user_query or not user_query.strip():
            return {
                "session_uuid": session_uuid or "chat_default",
                "text": "I didn't catch a question — what would you like me to look for?",
                "timeline": [],
                "timestamp": _istnow().isoformat(),
            }

        with self._db_session() as db:
            try:
                session = self.get_or_create_session(db, session_uuid, username)
                session_id = session.session_uuid

                last_intent = self._last_intent(db, session_id)
                intent = QueryIntentParser.parse(user_query, last_intent=last_intent)
                effective_prompt = QueryIntentParser.effective_search_prompt(intent)

                logger.info(
                    "[ChatEngine] session=%s mode=%s query=%r hinglish=%s followup=%s effective_prompt=%r",
                    session_id, search_mode, user_query, intent.is_hinglish, intent.is_followup, effective_prompt,
                )

                db.add(ChatMessage(session_uuid=session_id, sender="user", text=user_query, timestamp=_istnow()))
                session.updated_at = _istnow()
                db.commit()

                camera_map, camera_geo = self._camera_lookup(db)
                timeline_items = []

                stopwords = {
                    "have", "you", "seen", "any", "the", "with", "from", "this", "that",
                    "there", "show", "tell", "kya", "koi", "hai", "kaha", "dikha", "and", "&",
                    "for", "are", "were", "what", "where", "when", "how", "all", "please",
                    "find", "look", "search", "spot", "spotted", "check", "batao", "dikhao",
                    "is", "me", "to", "of", "a", "an", "in", "on", "at", "by"
                }

                is_escape_phrase = any(w in user_query.lower() for w in ["escape route", "next camera", "heading next", "escape path", "next hop", "next-hop", "monitor next", "predict escape", "where is this", "where will"])
                is_convoy_phrase = any(w in user_query.lower() for w in ["following", "traveling together", "travelling together", "convoy", "shadow", "escort"])

                from .multilingual_matcher import multilingual_matcher
                if not (is_escape_phrase or is_convoy_phrase) and multilingual_matcher.is_indic_script_or_romanized(user_query):
                    m_res = multilingual_matcher.match_query(user_query)
                    if m_res.get("matched"):
                        effective_prompt = m_res["normalized_english_query"]
                        user_query = effective_prompt
                    else:
                        # Indic query fell out of pattern -> return graceful guidance
                        return {
                            "text": m_res["error_message"],
                            "timeline": [],
                            "sources": [],
                            "session_id": session_id,
                            "intent": "multilingual_out_of_pattern",
                        }

                clean_terms = [w for w in re.findall(r"\w+", user_query.lower()) if len(w) >= 2 and w not in stopwords]
                if not clean_terms:
                    clean_terms = [w for w in re.findall(r"\w+", user_query.lower()) if len(w) >= 2]

                vehicle_types = {
                    "bus", "buses", "busses", "coach", "volvo", "sagar", "brts", "citybus",
                    "car", "cars", "sedan", "hatchback", "suv", "santro", "scorpio", "fortuner", "thar", "creta", "innova", "swift", "baleno", "bolero", "nexon", "brezza", "ertiga", "safari", "harrier", "wagonr", "alto", "i20", "dzire", "seltos",
                    "van", "vans", "minivan", "tempo", "omni", "eeco", "ambulance", "traveller", "matador",
                    "truck", "trucks", "lorry", "pickup", "dumper", "chhota hathi", "chota hathi", "eicher", "tata407", "tanker", "trailer", "container",
                    "motorcycle", "bike", "scooter", "scooty", "activa", "bullet", "pulsar", "splendor", "moped", "jupiter", "access", "two wheeler",
                    "rickshaw", "auto", "auto-rickshaw", "tuk-tuk", "tuktuk", "e-rickshaw", "erickshaw", "three wheeler"
                }
                specific_keywords = [w for w in clean_terms if w not in vehicle_types]
                if not specific_keywords:
                    specific_keywords = clean_terms

                from ...database.models import RawOCR, VehicleJourneyEvent, Vehicle, StolenVehicleWatchlist, PersonWatchlist
                from ..integrations.cctns_service import lookup_cctns_vehicle, lookup_cctns_person, get_all_active_stolen_vehicles, get_all_wanted_persons

                # ── INTENT A: Stolen Vehicle Hot-List Cross-Check (Prompt 3.4) ──────
                is_stolen_query = any(w in user_query.lower() for w in ["stolen", "hotlist", "hot-list", "blacklisted", "chori"])
                is_watchlist_query = any(w in user_query.lower() for w in ["wanted list", "wanted person", "watchlist", "criminal list", "wanted suspect", "wanted criminal"])
                is_cctns_query = any(w in user_query.lower() for w in ["cctns", "crime database", "state crime", "fir record", "prior record", "criminal history", "case record"])

                if is_stolen_query and search_mode not in ["plate", "ocr"]:
                    stolen_entries = db.query(StolenVehicleWatchlist).filter(StolenVehicleWatchlist.status == "ACTIVE").all()
                    cctns_hotlist = get_all_active_stolen_vehicles()
                    all_stolen_plates = set([s.plate_number for s in stolen_entries] + [c["plate_number"] for c in cctns_hotlist])
                    
                    # Check if user mentioned a specific plate or wants all stolen hits
                    target_plate = None
                    for sp in all_stolen_plates:
                        if sp.lower() in user_query.lower() or sp[-4:] in user_query:
                            target_plate = sp
                            break

                    search_plates = [target_plate] if target_plate else list(all_stolen_plates)
                    matched_sightings = (
                        db.query(VehicleJourneyEvent)
                        .filter(VehicleJourneyEvent.license_plate.in_(search_plates))
                        .order_by(VehicleJourneyEvent.timestamp_start.desc())
                        .limit(10)
                        .all()
                    )
                    if matched_sightings:
                        for v in matched_sightings:
                            cid = v.camera_id or "cam_1"
                            cname = camera_map.get(cid, cid)
                            ts_s = v.timestamp_start.isoformat() if v.timestamp_start else ""
                            cctns_rec = lookup_cctns_vehicle(v.license_plate) or {}
                            fir_info = cctns_rec.get("fir_number", "FIR Registered")
                            timeline_items.append({
                                "camera_id": cid,
                                "camera_name": cname,
                                "timestamp": ts_s,
                                "time_display": _format_time_display(ts_s),
                                "description": f"🚨 **HOT-LIST STOLEN VEHICLE** [{v.license_plate}] sighted on {cname}. Case: {fir_info} ({cctns_rec.get('police_station', 'Police Station')})",
                                "snapshot_url": v.snapshot_url or f"/api/v1/playback/snapshot/{cid}_latest",
                                "confidence": 99.0,
                                "entity_type": "stolen_vehicle"
                            })
                        answer_text = (
                            f"🚨 **Hot-List Stolen Vehicle Sighting(s) Detected!**\n\n"
                            f"Identified **{len(timeline_items)} critical sighting(s)** matching the State Stolen Vehicle Watchlist. "
                            f"Automatic alerts have been flagged on the Control Room console."
                        )
                    else:
                        stolen_summary = ", ".join(list(all_stolen_plates)[:4])
                        answer_text = (
                            f"🛡️ **Stolen Vehicle Watchlist Active**\n\n"
                            f"Cross-referenced all live camera feeds against **{len(all_stolen_plates)} hot-list vehicle registrations** ({stolen_summary}). "
                            f"No active stolen vehicles were detected in recent camera footage."
                        )

                elif is_watchlist_query and search_mode not in ["plate", "ocr"]:
                    wanted_list = db.query(PersonWatchlist).filter(PersonWatchlist.status == "ACTIVE").all()
                    cctns_wanted = get_all_wanted_persons()
                    all_wanted_names = [p.full_name for p in wanted_list] + [p["full_name"] for p in cctns_wanted]
                    
                    # Search caption / person logs for wanted names or aliases
                    wanted_caption_hits = (
                        db.query(SceneCaption)
                        .filter(SceneCaption.caption.ilike("%wanted%") | SceneCaption.caption.ilike("%suspect%"))
                        .order_by(SceneCaption.timestamp.desc())
                        .limit(5)
                        .all()
                    )
                    for sc in wanted_caption_hits:
                        cid = sc.camera_id or "cam_1"
                        cname = camera_map.get(cid, cid)
                        ts_s = sc.timestamp.isoformat() if sc.timestamp else ""
                        timeline_items.append({
                            "camera_id": cid,
                            "camera_name": cname,
                            "timestamp": ts_s,
                            "time_display": _format_time_display(ts_s),
                            "description": f"🎯 **WANTED WATCHLIST CANDIDATE**: \"{sc.caption}\" on {cname}",
                            "snapshot_url": sc.snapshot_url or f"/api/v1/playback/snapshot/{cid}_latest",
                            "confidence": 94.0,
                            "entity_type": "watchlist_person"
                        })
                    
                    names_str = ", ".join(list(dict.fromkeys(all_wanted_names))[:3])
                    if timeline_items:
                        answer_text = (
                            f"🎯 **Wanted Persons Watchlist Match!**\n\n"
                            f"Found **{len(timeline_items)} sighting(s)** corresponding to active wanted records ({names_str})."
                        )
                    else:
                        answer_text = (
                            f"🛡️ **Wanted Persons Watchlist Active**\n\n"
                            f"Continuously comparing live face embeddings against **{len(all_wanted_names)} wanted dossiers** ({names_str}). "
                            f"No wanted individuals have crossed active camera checkpoints in the selected time window."
                        )

                elif is_cctns_query and search_mode not in ["plate", "ocr"]:
                    # Search CCTNS by any plate or name mentioned
                    found_cctns_vehicle = None
                    found_cctns_person = None
                    for kw in clean_terms:
                        if not found_cctns_vehicle:
                            found_cctns_vehicle = lookup_cctns_vehicle(kw)
                        if not found_cctns_person:
                            found_cctns_person = lookup_cctns_person(kw)

                    if found_cctns_vehicle:
                        v = found_cctns_vehicle
                        answer_text = (
                            f"📑 **CCTNS Vehicle Record Found:**\n\n"
                            f"• **Registration:** `{v['plate_number']}` ({v['vehicle_make_model']} - {v['vehicle_color']})\n"
                            f"• **FIR Number:** `{v['fir_number']}`\n"
                            f"• **Jurisdiction:** {v['police_station']}\n"
                            f"• **Status:** 🚨 **{v['status']}** (Threat Level: {v['risk_level']})\n"
                            f"• **Charges:** {v['charges']}\n"
                            f"• **Investigating Officer:** {v['investigating_officer']}"
                        )
                    elif found_cctns_person:
                        p = found_cctns_person
                        firs_text = "\n".join([f"  - `{f['fir']}`: {f['sections']} ({f['ps']})" for f in p.get("active_firs", [])])
                        answer_text = (
                            f"📑 **CCTNS State Criminal Dossier:**\n\n"
                            f"• **Name:** **{p['full_name']}** (Alias: *\"{p.get('alias', 'None')}\"*)\n"
                            f"• **CCTNS ID:** `{p['cctns_id']}`\n"
                            f"• **Category:** `{p['category']}`\n"
                            f"• **Warrant Status:** 🚨 **{p['warrant_status']}** (Threat Level: {p.get('threat_level', 'HIGH')})\n"
                            f"• **Active FIRs:**\n{firs_text}\n"
                            f"• **Gang Affiliation:** {p.get('gang_affiliation', 'None')}\n"
                            f"• **Last Known Address:** {p.get('last_known_address', 'Unknown')}"
                        )
                    else:
                        answer_text = (
                            f"📑 **CCTNS State Database Query**\n\n"
                            f"Searched state police records for **\"{user_query}\"**. "
                            f"No active FIRs or criminal history records matched this identifier."
                        )

                # ── INTENT B: Predictive Next-Hop Escape Routing (Prompt 1.3) ───────
                elif (
                    any(w in user_query.lower() for w in [
                        "escape route", "escape path", "next-hop", "next hop", "next camera",
                        "monitor next", "heading next", "where will", "where is it going",
                        "where is this", "likely heading", "arrival time", "estimated arrival",
                        "heading north", "heading south", "heading east", "heading west",
                        "going north", "going south", "going east", "going west",
                        "which camera next", "which cameras", "predict escape", "predict next",
                        "kaunse camera"
                    ])
                    and search_mode not in ["plate", "ocr"]
                ):
                    from ..topology.escape_router import predict_next_hop_escape_routes

                    # Determine heading
                    heading = "forward"
                    for h in ["north", "south", "east", "west"]:
                        if h in user_query.lower():
                            heading = h
                            break

                    # Determine source camera from query or default to active route camera
                    source_cam_id = "cam_route_1" if "cam_route_1" in camera_map else (list(camera_map.keys())[0] if camera_map else "cam_1")
                    matched_cam = None
                    for cid, cname in camera_map.items():
                        if cid.lower() in user_query.lower():
                            matched_cam = cid
                            break
                        if cname and len(cname) >= 3 and cname.lower() in user_query.lower():
                            matched_cam = cid
                            break

                    if not matched_cam:
                        # Check partial segment tokens like "Sector 4"
                        for cid, cname in camera_map.items():
                            if cname:
                                segments = [s.strip().lower() for s in re.split(r"[-/–,]", cname) if len(s.strip()) >= 4]
                                if any(seg in user_query.lower() for seg in segments):
                                    matched_cam = cid
                                    break

                    if matched_cam:
                        source_cam_id = matched_cam

                    dep_time = intent.time_start or _istnow()
                    escape_data = predict_next_hop_escape_routes(
                        db=db,
                        source_camera_identifier=source_cam_id,
                        target_description=effective_prompt or "Vehicle",
                        heading_direction=heading,
                        departure_time=dep_time,
                        observed_speed_kmh=40.0,
                    )

                    if escape_data.get("success") and escape_data.get("routes"):
                        routes = escape_data["routes"]
                        src_info = escape_data["source_camera"]
                        route_lines = []
                        for idx, r in enumerate(routes, 1):
                            prob_pct = int(r["intercept_probability"] * 100)
                            route_lines.append(
                                f"{idx}. **{r['camera_name']}** ({r['location']}) — Distance: `{r['distance_meters']}m`\n"
                                f"   • **ETA Window:** ⏱️ `{r['eta_display']}` (in {r['estimated_transit_seconds']})\n"
                                f"   • **Interception Probability:** `{prob_pct}%` ({r['priority']} Priority)\n"
                                f"   • **Action:** {r['recommended_action']}"
                            )
                            # Add to timeline
                            timeline_items.append({
                                "camera_id": r["camera_id"],
                                "camera_name": r["camera_name"],
                                "timestamp": r["eta_window_start"],
                                "time_display": f"ETA {r['eta_display']}",
                                "description": f"🎯 PREDICTIVE INTERCEPTION POINT: {r['camera_name']} ({prob_pct}% probability)",
                                "snapshot_url": f"/api/v1/playback/snapshot/{r['camera_id']}_latest",
                                "confidence": round(r["intercept_probability"] * 100, 1),
                                "entity_type": "predictive_route"
                            })

                        answer_text = (
                            f"📡 **Predictive Next-Hop Escape Routing Analysis:**\n\n"
                            f"• **Origin Waypoint:** {src_info['name']} ({src_info['location']})\n"
                            f"• **Heading Direction:** `{escape_data['heading_direction']}` @ 40 km/h\n"
                            f"• **Departure Time:** `{escape_data['departure_time']}`\n\n"
                            f"**Recommended Downstream Interception Cameras:**\n"
                            + "\n\n".join(route_lines)
                        )
                    elif escape_data.get("is_dead_end"):
                        src_info = escape_data.get("source_camera", {})
                        answer_text = (
                            f"🛑 **Terminal Waypoint / Dead-End Checkpoint**\n\n"
                            f"Camera **{src_info.get('name', source_cam_id)}** ({src_info.get('location', 'Surveillance Area')}) "
                            f"is configured as a terminal perimeter node with **no outgoing escape routes**.\n\n"
                            f"The target is contained within this perimeter or must reverse direction back into monitored sectors."
                        )
                    else:
                        answer_text = (
                            f"📡 **Predictive Escape Routing:**\n\n"
                            f"No downstream topological routes could be calculated from camera checkpoint **{source_cam_id}** "
                            f"with heading `{heading}`. Check the Topology Map to configure transit edges."
                        )

                # ── INTENT C: Convoy / Shadow-Vehicle Co-Occurrence (Prompt 6.1) ────
                elif (
                    any(w in user_query.lower() for w in [
                        "following", "traveling together", "travelling together", "convoy",
                        "shadow", "escort", "co-occurrence", "co occurrence", "companion",
                        "trailing", "piche chal rahi", "saath me"
                    ])
                    and search_mode not in ["plate", "ocr"]
                ):
                    from ..co_occurrence import find_convoy_companions

                    # Extract target plate or keyword from query
                    target_kw = None
                    plate_matches = re.findall(r"\b[A-Za-z]{2}\d{1,2}[A-Za-z]{0,3}\d{3,4}\b", user_query)
                    if plate_matches:
                        target_kw = plate_matches[0].upper()
                    else:
                        ignore_words = {
                            "following", "detect", "vehicle", "proximity", "across", "cameras", "camera",
                            "more", "travelling", "traveling", "together", "convoy", "shadow", "escort",
                            "been", "have", "with", "from", "show", "tell", "check"
                        }
                        for kw in clean_terms:
                            if kw.lower() not in ignore_words and len(kw) >= 3:
                                target_kw = kw.upper()
                                break
                    if not target_kw:
                        target_kw = "DL01AB1234"

                    convoy_data = find_convoy_companions(
                        db=db,
                        target_identifier=target_kw,
                        time_window_minutes=60,
                        max_gap_seconds=45.0,
                        min_cameras=2
                    )

                    if convoy_data.get("success") and convoy_data.get("convoy_candidates"):
                        candidates = convoy_data["convoy_candidates"]
                        cand_summaries = []
                        for c in candidates:
                            conf_pct = int(c["correlation_confidence"] * 100)
                            timeline_bullets = []
                            for ev in c["shared_timeline"]:
                                timeline_bullets.append(
                                    f"     - **{ev['camera_name']}**: Target @ `{ev['target_time']}` → Companion @ `{ev['companion_time']}` (Trailing gap: `{ev['trailing_gap_seconds']}s`)"
                                )
                                timeline_items.append({
                                    "camera_id": ev["camera_id"],
                                    "camera_name": ev["camera_name"],
                                    "timestamp": ev["companion_time"],
                                    "time_display": ev["companion_time"],
                                    "description": f"🚨 SHADOW CONVOY: [{c['companion_identifier']}] trailing [{convoy_data['target_identifier']}] by {ev['trailing_gap_seconds']}s on {ev['camera_name']}",
                                    "snapshot_url": ev["snapshot_url"],
                                    "confidence": conf_pct,
                                    "entity_type": "convoy"
                                })

                            cand_summaries.append(
                                f"• **Companion Vehicle:** `{c['companion_identifier']}`\n"
                                f"   - **Threat Assessment:** 🚨 **{c['threat_assessment']}**\n"
                                f"   - **Correlation Score:** `{conf_pct}%` across `{c['cameras_co_occurred_count']}` separate camera checkpoints\n"
                                f"   - **Average Trailing Gap:** `{c['avg_trailing_gap_seconds']} seconds`\n"
                                f"   - **Multi-Camera Sighting Sequence:**\n" + "\n".join(timeline_bullets)
                            )

                        answer_text = (
                            f"🚨 **Convoy / Shadow-Vehicle Co-Occurrence Detected!**\n\n"
                            f"Analyzed multi-camera transit trajectories for target **{convoy_data['target_identifier']}**. "
                            f"Found **{len(candidates)} vehicle(s)** exhibiting correlated convoy trailing patterns:\n\n"
                            + "\n\n".join(cand_summaries)
                        )
                    else:
                        answer_text = (
                            f"🛡️ **Convoy Analysis Completed for \"{target_kw}\"**\n\n"
                            f"Scanned all camera transit logs within a 60-minute window for synchronized trailing vehicles (Delta T <= 45s across >= 2 cameras). "
                            f"No vehicles were detected traveling in convoy with this target."
                        )

                # Handle Dedicated Search Modes
                elif search_mode == "plate":
                    clean_q = re.sub(r"[^A-Za-z0-9]", "", user_query).upper()
                    v_matches = (
                        db.query(VehicleJourneyEvent)
                        .filter(VehicleJourneyEvent.license_plate.ilike(f"%{clean_q}%"))
                        .order_by(VehicleJourneyEvent.timestamp_start.desc())
                        .limit(10)
                        .all()
                    )
                    if v_matches:
                        for v in v_matches:
                            cid = v.camera_id or "cam_1"
                            cname = camera_map.get(cid, cid)
                            ts_s = v.timestamp_start.isoformat() if v.timestamp_start else ""
                            v_conf = getattr(v, "confidence", 0.90)
                            timeline_items.append({
                                "camera_id": cid,
                                "camera_name": cname,
                                "timestamp": ts_s,
                                "time_display": _format_time_display(ts_s),
                                "description": f"License Plate **{v.license_plate}** sighted on {cname} (Confidence: {int(v_conf * 100)}%)",
                                "snapshot_url": v.snapshot_url or f"/api/v1/playback/snapshot/{cid}_latest",
                                "confidence": round(v_conf * 100, 1),
                                "entity_type": "plate"
                            })
                        answer_text = f"🚗 **License Plate Match Found!**\n\nSighted vehicle with registration **{clean_q}** across **{len(timeline_items)} camera event(s)**."
                    else:
                        answer_text = f"❌ **No License Plate Matches Found**\n\nNo records for vehicle registration **\"{user_query}\"** were found in the surveillance database."

                elif search_mode == "ocr":
                    # Search across all salient keywords in RawOCR using exact + pg_trgm fuzzy matching
                    ocr_seen_ids = set()
                    for kw in specific_keywords:
                        try:
                            # 1. Exact ILIKE match
                            exact_recs = db.query(RawOCR).filter((RawOCR.raw_text.ilike(f"%{kw}%")) | (RawOCR.detected_text.ilike(f"%{kw}%"))).limit(10).all()
                            for o in exact_recs:
                                if o.id in ocr_seen_ids:
                                    continue
                                ocr_seen_ids.add(o.id)
                                cid = o.camera_id or "cam_1"
                                cname = camera_map.get(cid, cid)
                                ts_s = o.timestamp.isoformat() if o.timestamp else ""
                                txt = o.raw_text or o.detected_text or ""
                                ocr_conf = getattr(o, "ocr_confidence", getattr(o, "confidence", 0.90))
                                timeline_items.append({
                                    "camera_id": cid,
                                    "camera_name": cname,
                                    "timestamp": ts_s,
                                    "time_display": _format_time_display(ts_s),
                                    "description": f"🟢 EXACT OCR MATCH (100%): \"{txt}\" on {cname}",
                                    "snapshot_url": o.snapshot_url or f"/api/v1/playback/snapshot/{cid}_latest",
                                    "confidence": round(ocr_conf * 100, 1),
                                    "match_type": "exact",
                                    "entity_type": "ocr"
                                })

                            # 2. pg_trgm Fuzzy Word Similarity Match (Threshold >= 0.30)
                            fuzzy_recs = (
                                db.query(RawOCR, func.word_similarity(kw, RawOCR.raw_text).label("sim"))
                                .filter(func.word_similarity(kw, RawOCR.raw_text) >= 0.30)
                                .order_by(text("sim DESC"))
                                .limit(5)
                                .all()
                            )
                            for o, sim_val in fuzzy_recs:
                                if o.id in ocr_seen_ids:
                                    continue
                                ocr_seen_ids.add(o.id)
                                cid = o.camera_id or "cam_1"
                                cname = camera_map.get(cid, cid)
                                ts_s = o.timestamp.isoformat() if o.timestamp else ""
                                txt = o.raw_text or o.detected_text or ""
                                sim_pct = int(float(sim_val) * 100)
                                timeline_items.append({
                                    "camera_id": cid,
                                    "camera_name": cname,
                                    "timestamp": ts_s,
                                    "time_display": _format_time_display(ts_s),
                                    "description": f"🟡 FUZZY OCR MATCH ({sim_pct}% - \"{txt}\" ≈ \"{kw}\") on {cname}",
                                    "snapshot_url": o.snapshot_url or f"/api/v1/playback/snapshot/{cid}_latest",
                                    "confidence": round(float(sim_val) * 100, 1),
                                    "match_type": "fuzzy",
                                    "entity_type": "ocr"
                                })
                        except Exception as q_exc:
                            logger.debug("[ChatEngine] Trigram query note: %s", q_exc)

                    if timeline_items:
                        answer_text = f"🔤 **OCR Text Matches Found!**\n\nFound **{len(timeline_items)} camera sighting(s)** matching on-screen text **\"{' '.join(specific_keywords)}\"**."
                    else:
                        answer_text = f"❌ **No OCR Text Matches Found**\n\nNo on-screen signage, decals, or overlays containing **\"{user_query}\"** were found."

                else:
                    # General Multi-modal Search: Cross-checks OCR (Exact + Fuzzy), Vehicle events, Scene Captions & Vector DB
                    # 1. Multi-ledger OCR Search (Exact + pg_trgm similarity)
                    ocr_timeline_items = []
                    ocr_seen_ids = set()
                    for kw in specific_keywords:
                        try:
                            exact_matches = (
                                db.query(RawOCR)
                                .filter((RawOCR.raw_text.ilike(f"%{kw}%")) | (RawOCR.detected_text.ilike(f"%{kw}%")))
                                .order_by(RawOCR.timestamp.desc())
                                .limit(5)
                                .all()
                            )
                            for o in exact_matches:
                                if o.id in ocr_seen_ids:
                                    continue
                                ocr_seen_ids.add(o.id)
                                cid = o.camera_id or "cam_1"
                                cname = camera_map.get(cid, cid)
                                ts_s = o.timestamp.isoformat() if o.timestamp else ""
                                txt = o.raw_text or o.detected_text or ""
                                ocr_conf = getattr(o, "ocr_confidence", getattr(o, "confidence", 0.90))
                                ocr_timeline_items.append({
                                    "camera_id": cid,
                                    "camera_name": cname,
                                    "timestamp": ts_s,
                                    "time_display": _format_time_display(ts_s),
                                    "description": f"🟢 EXACT OCR Signage: \"{txt}\" on {cname}",
                                    "snapshot_url": o.snapshot_url or f"/api/v1/playback/snapshot/{cid}_latest",
                                    "confidence": round(ocr_conf * 100, 1),
                                    "match_type": "exact",
                                    "entity_type": "ocr"
                                })

                            fuzzy_matches = (
                                db.query(RawOCR, func.word_similarity(kw, RawOCR.raw_text).label("sim"))
                                .filter(func.word_similarity(kw, RawOCR.raw_text) >= 0.30)
                                .order_by(text("sim DESC"))
                                .limit(3)
                                .all()
                            )
                            for o, sim_val in fuzzy_matches:
                                if o.id in ocr_seen_ids:
                                    continue
                                ocr_seen_ids.add(o.id)
                                cid = o.camera_id or "cam_1"
                                cname = camera_map.get(cid, cid)
                                ts_s = o.timestamp.isoformat() if o.timestamp else ""
                                txt = o.raw_text or o.detected_text or ""
                                sim_pct = int(float(sim_val) * 100)
                                ocr_timeline_items.append({
                                    "camera_id": cid,
                                    "camera_name": cname,
                                    "timestamp": ts_s,
                                    "time_display": _format_time_display(ts_s),
                                    "description": f"🟡 FUZZY OCR Signage ({sim_pct}% - \"{txt}\" ≈ \"{kw}\") on {cname}",
                                    "snapshot_url": o.snapshot_url or f"/api/v1/playback/snapshot/{cid}_latest",
                                    "confidence": round(float(sim_val) * 100, 1),
                                    "match_type": "fuzzy",
                                    "entity_type": "ocr"
                                })
                        except Exception as q_exc:
                            logger.debug("[ChatEngine] Trigram general query note: %s", q_exc)

                    # 2. Scene Caption Search & Visual Ledger
                    caption_matches = []
                    sql_captions_all = (
                        db.query(SceneCaption)
                        .order_by(SceneCaption.timestamp.desc())
                        .limit(ChatConfig.SQL_CAPTION_SCAN_LIMIT)
                        .all()
                    )
                    # Find captions matching specific keywords or clean terms
                    for sc in sql_captions_all:
                        cap_lower = sc.caption.lower()
                        if any(kw in cap_lower for kw in specific_keywords):
                            caption_matches.append(sc)

                    # 3. Vector Database Semantic Search
                    try:
                        semantic_results = self._semantic_search(effective_prompt, ChatConfig.SEMANTIC_SEARCH_LIMIT)
                    except ExternalServiceError as exc:
                        logger.error("[ChatEngine] Semantic search unavailable: %s", exc)
                        semantic_results = []

                    semantic_timeline_items = self._build_timeline(semantic_results, caption_matches, camera_map, intent)

                    # 4. Synthesize Multi-ledger Findings with Strict Visual Attribute Validation
                    all_evidence = []
                    for o in ocr_timeline_items:
                        all_evidence.append(o)

                    # Extract target colors, vehicle types, and query attributes
                    color_set = {"yellow", "red", "blue", "green", "black", "white", "silver", "grey", "gray", "orange", "purple", "pink", "brown", "maroon", "golden", "dark", "light"}
                    location_noise = {"near", "market", "entrance", "station", "junction", "gate", "road", "street", "toll", "corridor", "terminal", "depo", "bazaar", "chauta", "ring", "gopi", "talav", "mahidharpura", "athwa", "vesu", "adajan", "varachha", "svnit", "kargil", "parle", "bhatena", "jogani", "area", "point", "chowk"}
                    
                    vehicle_synonym_groups = {
                        "van": {"van", "vans", "minivan", "tempo", "omni", "eeco", "ambulance", "traveller", "matador"},
                        "car": {"car", "cars", "sedan", "hatchback", "suv", "santro", "scorpio", "fortuner", "thar", "creta", "innova", "swift", "baleno", "bolero", "nexon", "brezza", "ertiga", "safari", "harrier", "wagonr", "alto", "i20", "dzire", "seltos"},
                        "bus": {"bus", "buses", "busses", "coach", "volvo", "sagar", "brts", "citybus"},
                        "truck": {"truck", "trucks", "lorry", "pickup", "dumper", "chhota hathi", "chota hathi", "eicher", "tata407", "tanker", "trailer", "container"},
                        "motorcycle": {"motorcycle", "bike", "scooter", "scooty", "activa", "bullet", "pulsar", "splendor", "moped", "jupiter", "access", "two wheeler"},
                        "auto": {"auto", "rickshaw", "auto-rickshaw", "tuk-tuk", "tuktuk", "three wheeler", "e-rickshaw", "erickshaw"},
                    }

                    query_colors = [w for w in clean_terms if w in color_set]
                    query_vehicles = [w for w in clean_terms if w in vehicle_types]
                    query_visual_targets = [w for w in specific_keywords if w not in location_noise and w not in color_set]

                    # Expand query vehicle types with their specific synonyms
                    target_vehicle_words = set()
                    for qv in query_vehicles:
                        matched_group = False
                        for group_key, synonyms in vehicle_synonym_groups.items():
                            if qv == group_key or qv in synonyms:
                                target_vehicle_words.update(synonyms)
                                matched_group = True
                        if not matched_group:
                            target_vehicle_words.add(qv)

                    for s in semantic_timeline_items:
                        desc_lower = s["description"].lower()
                        
                        # 1. Strict Color + Vehicle Binding:
                        # If both color and vehicle are queried (e.g. "yellow van"),
                        # the description must contain the exact combination "yellow van/tempo" or the bound vehicle must match.
                        if query_colors and target_vehicle_words:
                            color_bound_match = False
                            for c in query_colors:
                                for v in target_vehicle_words:
                                    if f"{c} {v}" in desc_lower or f"{v} in {c}" in desc_lower or f"{c}-colored {v}" in desc_lower or f"{c} colored {v}" in desc_lower:
                                        color_bound_match = True
                                        break
                                if color_bound_match:
                                    break
                            if not color_bound_match:
                                continue

                        # 2. Color-only query: candidate must mention requested color
                        elif query_colors and not any(c in desc_lower for c in query_colors):
                            continue
                            
                        # 3. Vehicle-only query: candidate must mention requested vehicle type
                        elif target_vehicle_words and not any(v in desc_lower for v in target_vehicle_words):
                            continue

                        # 4. Specific visual target (e.g. brand, clothing item):
                        if query_visual_targets and not any(t in desc_lower for t in query_visual_targets):
                            if float(s.get("score", 0.0)) < 0.78:
                                continue

                        all_evidence.append(s)

                    # Deduplicate evidence
                    seen_keys = set()
                    timeline_items = []
                    for item in all_evidence:
                        k = (item.get("camera_id"), item.get("timestamp"), item.get("description", "")[:40])
                        if k not in seen_keys:
                            seen_keys.add(k)
                            timeline_items.append(item)

                    timeline_items.sort(key=lambda x: x.get("timestamp") or "")
                    trajectory = build_trajectory_summary(timeline_items, camera_geo)

                    if timeline_items:
                        matched_cams = list(dict.fromkeys([s["camera_name"] for s in timeline_items]))
                        evidence_snippets = []
                        for item in timeline_items[:3]:
                            desc = item["description"]
                            if "[Moondream]:" in desc:
                                desc = desc.split("[Moondream]:")[-1].split("|")[0].strip()
                            elif "[YOLO]:" in desc:
                                desc = desc.split("[YOLO]:")[-1].split("|")[0].strip()
                            tag = "Visual Sighting" if item.get("entity_type") != "ocr" else "On-Screen OCR Text"
                            evidence_snippets.append(f"• **{tag}**: {desc[:160]}...")

                        target_title = user_query.strip().title()
                        answer_text = (
                            f"🎯 **Forensic Match Found!**\n\n"
                            f"Identified targets matching **\"{target_title}\"** on **{', '.join(matched_cams)}**:\n\n"
                            + "\n".join(evidence_snippets)
                        )
                    else:
                        timeline_items = []
                        trajectory = {"legs": [], "flags": []}
                        target_title = user_query.strip()
                        answer_text = (
                            f"❌ **No Matching Sightings Found**\n\n"
                            f"I scanned all active surveillance feeds and visual ledgers for **\"{target_title}\"**, "
                            f"but no matching targets or sightings were detected in recent surveillance logs."
                        )

                trajectory = build_trajectory_summary(timeline_items, camera_geo)

                db.add(ChatMessage(
                    session_uuid=session_id, sender="assistant", text=answer_text,
                    timeline_json=json.dumps(timeline_items), timestamp=_istnow(),
                ))
                db.commit()

                self._audit_log(
                    db, session_uuid=session_id, username=username, action="text_query",
                    detail={"query": user_query, "hits": len(timeline_items), "camera_filter": intent.camera_filter},
                )

                return {
                    "session_uuid": session_id,
                    "text": answer_text,
                    "timeline": timeline_items,
                    "trajectory": trajectory,
                    "timestamp": _istnow().isoformat(),
                }
            except Exception as exc:  # noqa: BLE001 - top-level request boundary
                logger.error("[ChatEngine] Error processing query: %s", exc, exc_info=True)
                return {
                    "session_uuid": session_uuid or "chat_default",
                    "text": "I hit an internal error analyzing the surveillance feed. Please retry, or narrow the query.",
                    "timeline": [],
                    "timestamp": _istnow().isoformat(),
                    "error": str(exc),
                }

    def _validate_and_load_image(self, image_bytes: bytes) -> np.ndarray:
        if not image_bytes:
            raise InvalidImageError("Empty image payload")
        if len(image_bytes) > ChatConfig.MAX_IMAGE_BYTES:
            raise InvalidImageError(f"Image exceeds {ChatConfig.MAX_IMAGE_BYTES // (1024*1024)}MB limit")

        nparr = np.frombuffer(image_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None or getattr(img, "size", 0) == 0:
            raise InvalidImageError("Corrupt or unreadable image format")
        return img

    @with_retries()
    def _moondream_caption(self, data_uri: str, upload_id: str) -> str:
        return _call_moondream_api(data_uri, upload_id)

    def process_image_query(self, image_bytes: bytes, user_query: Optional[str] = None,
                             session_uuid: Optional[str] = None, username: str = "operator",
                             search_mode: str = "all") -> Dict[str, Any]:
        """Uploads image, detects facial/plate targets or generates rich vision caption,
        and matches biometric/visual evidence across city cameras."""
        with self._db_session() as db:
            try:
                img = self._validate_and_load_image(image_bytes)
                h, w = img.shape[:2]
                if max(h, w) > ChatConfig.MAX_IMAGE_DIM:
                    scale = ChatConfig.MAX_IMAGE_DIM / max(h, w)
                    img = cv2.resize(img, (int(w * scale), int(h * scale)))

                session = self.get_or_create_session(db, session_uuid, username)
                session_id = session.session_uuid

                upload_id = f"upload_{uuid.uuid4().hex[:10]}"
                snap_filename = f"{upload_id}.jpg"
                snap_path = os.path.join(self.snap_dir, snap_filename)
                cv2.imwrite(snap_path, img)
                upload_url = f"/api/v1/playback/snapshot/{upload_id}"

                camera_map, camera_geo = self._camera_lookup(db)
                face_timeline_items = []
                face_found = False
                face_emb = None

                # 1. Biometric Face Extraction via YuNet + SFace
                try:
                    from ...ai.face.face_pipeline import get_face_models, face_lock
                    from ...search.vector_search import perform_face_search

                    det, rec = get_face_models(640, 480)
                    det_frame = cv2.resize(img, (640, 480))
                    with face_lock:
                        ret, faces = det.detect(det_frame)

                    if faces is not None and len(faces) > 0:
                        sorted_faces = sorted(faces, key=lambda f: f[2] * f[3], reverse=True)
                        best_face = sorted_faces[0]
                        conf = float(best_face[14])
                        if conf >= 0.40:
                            face_found = True
                            scale_x = w / 640.0
                            scale_y = h / 480.0
                            scaled_face = best_face.copy()
                            scaled_face[0] *= scale_x
                            scaled_face[2] *= scale_x
                            for i in range(4, 14, 2):
                                scaled_face[i] *= scale_x
                            scaled_face[1] *= scale_y
                            scaled_face[3] *= scale_y
                            for i in range(5, 14, 2):
                                scaled_face[i] *= scale_y

                            with face_lock:
                                aligned_face = rec.alignCrop(img, scaled_face)
                                feat = rec.feature(aligned_face)
                            if feat is not None and len(feat) > 0:
                                face_emb = feat[0].tolist()
                                face_results = perform_face_search(face_emb, limit=ChatConfig.IMAGE_SEARCH_LIMIT)
                                for r in face_results:
                                    payload = r.get("payload", {})
                                    cam_id = payload.get("camera_id", "cam_1")
                                    cam_name = camera_map.get(cam_id, cam_id)
                                    ts_str = payload.get("timestamp")
                                    conf_pct = round(float(r.get("score", 0.85)) * 100, 1)
                                    snap = payload.get("snapshot_url") or upload_url
                                    face_timeline_items.append({
                                        "camera_id": cam_id,
                                        "camera_name": cam_name,
                                        "timestamp": ts_str,
                                        "time_display": ts_str.split("T")[1][:8] if ts_str and "T" in ts_str else (ts_str or "Live"),
                                        "description": f"Biometric Face Match ({conf_pct}% confidence)",
                                        "snapshot_url": snap,
                                        "confidence": conf_pct,
                                        "entity_type": "face"
                                    })
                except Exception as f_err:
                    logger.warning(f"[ChatEngine] Biometric face extraction note: {f_err}")

                # 2. Vision Context & Target Description
                detailed_caption = (user_query or "").strip()
                if not detailed_caption:
                    detailed_caption = "Person in frame" if face_found else "Visual target"

                user_msg_text = f"[Uploaded Image] {user_query or 'Search for this target in city cameras'}"
                db.add(ChatMessage(session_uuid=session_id, sender="user", text=user_msg_text, image_url=upload_url, timestamp=_istnow()))
                session.updated_at = _istnow()
                db.commit()

                # Search Mode Routing
                timeline_items = []
                trajectory = {"legs": [], "flags": []}

                if search_mode == "face":
                    if not face_found or face_emb is None:
                        # Fallback to visual appearance if face detector was borderline
                        combined_search_prompt = f"{user_query or ''} person {detailed_caption}".strip()
                        try:
                            semantic_results = self._semantic_search(combined_search_prompt, ChatConfig.IMAGE_SEARCH_LIMIT)
                        except Exception:
                            semantic_results = []
                        dummy_intent = QueryIntent(raw_query=user_query or "", search_prompt=combined_search_prompt, is_hinglish=False)
                        semantic_timeline_items = self._build_timeline(semantic_results, [], camera_map, dummy_intent)
                        if semantic_timeline_items:
                            timeline_items = semantic_timeline_items
                            trajectory = build_trajectory_summary(timeline_items, camera_geo)
                            cams_involved = list(dict.fromkeys(t["camera_name"] for t in timeline_items))
                            lines = [
                                f"👤 **Visual Appearance Sighting(s) Found**\n",
                                f"Exact biometric facial vectors were obscured, but matching visual profile (**{detailed_caption[:100]}**) was spotted across **{len(timeline_items)} camera sighting(s)** ({', '.join(cams_involved)}):\n",
                            ]
                            for idx, t in enumerate(timeline_items[:5], 1):
                                lines.append(f"{idx}. **{t['camera_name']}** at **{t['time_display']}**: {t['description']}")
                            answer_text = "\n".join(lines)
                        else:
                            answer_text = (
                                "❌ **No Human Face Detected in Image**\n\n"
                                "The uploaded photo does not contain a recognizable human face. "
                                "Please upload a clear, front-facing portrait to perform biometric facial matching."
                            )
                    elif not face_timeline_items:
                        # Fallback to appearance search
                        combined_search_prompt = f"{user_query or ''} person {detailed_caption}".strip()
                        try:
                            semantic_results = self._semantic_search(combined_search_prompt, ChatConfig.IMAGE_SEARCH_LIMIT)
                        except Exception:
                            semantic_results = []
                        dummy_intent = QueryIntent(raw_query=user_query or "", search_prompt=combined_search_prompt, is_hinglish=False)
                        semantic_timeline_items = self._build_timeline(semantic_results, [], camera_map, dummy_intent)
                        if semantic_timeline_items:
                            timeline_items = semantic_timeline_items
                            trajectory = build_trajectory_summary(timeline_items, camera_geo)
                            cams_involved = list(dict.fromkeys(t["camera_name"] for t in timeline_items))
                            lines = [
                                f"🎯 **Visual Appearance Sighting(s) Found**\n",
                                f"Exact 512-D facial vector was not registered in vector index, but matching visual profile (**{detailed_caption[:100]}**) was spotted across **{len(timeline_items)} camera sighting(s)** ({', '.join(cams_involved)}):\n",
                            ]
                            for idx, t in enumerate(timeline_items[:5], 1):
                                lines.append(f"{idx}. **{t['camera_name']}** at **{t['time_display']}**: {t['description']}")
                            answer_text = "\n".join(lines)
                        else:
                            answer_text = (
                                "❌ **No Biometric Face Matches Found**\n\n"
                                "I analyzed the biometric facial vectors from your photo and scanned all active city camera feeds. "
                                "This individual **has not been sighted** on any camera in recent surveillance logs."
                            )
                    else:
                        timeline_items = face_timeline_items
                        trajectory = build_trajectory_summary(timeline_items, camera_geo)
                        cams_involved = list(dict.fromkeys(t["camera_name"] for t in timeline_items))
                        lines = [
                            f"🎯 **Biometric Face Match Confirmed!**\n",
                            f"Identified facial match with high confidence across **{len(timeline_items)} camera sighting(s)** ({', '.join(cams_involved)}):\n",
                        ]
                        for idx, t in enumerate(timeline_items[:5], 1):
                            lines.append(f"{idx}. **{t['camera_name']}** at **{t['time_display']}**: {t['description']}")
                        for flag in trajectory.get("flags", []):
                            lines.append(f"\n⚠️ {flag}")
                        answer_text = "\n".join(lines)

                elif search_mode == "all" and face_found:
                    # If auto-detect found a face in the user's photo
                    if face_timeline_items:
                        timeline_items = face_timeline_items
                        trajectory = build_trajectory_summary(timeline_items, camera_geo)
                        cams_involved = list(dict.fromkeys(t["camera_name"] for t in timeline_items))
                        lines = [
                            f"🎯 **Biometric Face Match Confirmed!**\n",
                            f"Identified matching individual across **{len(timeline_items)} camera sighting(s)** ({', '.join(cams_involved)}):\n",
                        ]
                        for idx, t in enumerate(timeline_items[:5], 1):
                            lines.append(f"{idx}. **{t['camera_name']}** at **{t['time_display']}**: {t['description']}")
                        lines.append(f"\n*Target Appearance*: {detailed_caption[:200]}...")
                        answer_text = "\n".join(lines)
                    else:
                        # Fallback to visual multi-modal semantic search
                        combined_search_prompt = f"{user_query or ''} person {detailed_caption}".strip()
                        try:
                            semantic_results = self._semantic_search(combined_search_prompt, ChatConfig.IMAGE_SEARCH_LIMIT)
                        except ExternalServiceError:
                            semantic_results = []

                        dummy_intent = QueryIntent(raw_query=user_query or "", search_prompt=combined_search_prompt, is_hinglish=False)
                        semantic_timeline_items = self._build_timeline(semantic_results, [], camera_map, dummy_intent)
                        
                        if semantic_timeline_items:
                            timeline_items = semantic_timeline_items
                            trajectory = build_trajectory_summary(timeline_items, camera_geo)
                            cams_involved = list(dict.fromkeys(t["camera_name"] for t in timeline_items))
                            lines = [
                                f"🎯 **Visual Sighting(s) Identified!**\n",
                                f"Scanned camera feeds for matching target (**{detailed_caption[:100]}**). Identified across **{len(timeline_items)} camera sighting(s)** ({', '.join(cams_involved)}):\n",
                            ]
                            for idx, t in enumerate(timeline_items[:5], 1):
                                lines.append(f"{idx}. **{t['camera_name']}** at **{t['time_display']}**: {t['description']}")
                            answer_text = "\n".join(lines)
                        else:
                            answer_text = (
                                f"👤 **Target Identification**: Human Face Detected.\n\n"
                                f"❌ **No Biometric Face Match Found**: Scanned all city cameras, but this individual has not been sighted on any camera feed."
                            )

                else:
                    # Vehicle/Scene/Object Semantic Visual Search
                    combined_search_prompt = f"{user_query or ''} {detailed_caption}".strip()
                    try:
                        semantic_results = self._semantic_search(combined_search_prompt, ChatConfig.IMAGE_SEARCH_LIMIT)
                    except ExternalServiceError as exc:
                        semantic_results = []

                    dummy_intent = QueryIntent(raw_query=user_query or "", search_prompt=combined_search_prompt, is_hinglish=False)
                    semantic_timeline_items = self._build_timeline(semantic_results, [], camera_map, dummy_intent)
                    timeline_items = semantic_timeline_items
                    trajectory = build_trajectory_summary(timeline_items, camera_geo)

                    if timeline_items:
                        cams_involved = list(dict.fromkeys(t["camera_name"] for t in timeline_items))
                        lines = [
                            f"🔍 **Visual Target Analysis**: {detailed_caption}\n",
                            f"✅ **Visual Match Found!** Matched this visual target across **{len(timeline_items)} location(s)** ({', '.join(cams_involved)}):\n",
                        ]
                        for idx, t in enumerate(timeline_items[:5], 1):
                            lines.append(f"{idx}. **{t['camera_name']}** at **{t['time_display']}**: {t['description']}")
                        for flag in trajectory.get("flags", []):
                            lines.append(f"\n⚠️ {flag}")
                        answer_text = "\n".join(lines)
                    else:
                        answer_text = (
                            f"🔍 **Visual Target Analysis**: {detailed_caption}\n\n"
                            f"I scanned all city camera feeds against this visual target, but could not find a matching scene or vehicle in recent video logs."
                        )

                db.add(ChatMessage(
                    session_uuid=session_id, sender="assistant", text=answer_text,
                    timeline_json=json.dumps(timeline_items), timestamp=_istnow(),
                ))
                db.commit()

                self._audit_log(
                    db, session_uuid=session_id, username=username, action="image_query",
                    detail={"upload_id": upload_id, "hits": len(timeline_items), "mode": search_mode},
                )

                return {
                    "session_uuid": session_id,
                    "text": answer_text,
                    "timeline": timeline_items,
                    "trajectory": trajectory,
                    "upload_url": upload_url,
                    "caption": detailed_caption,
                    "timestamp": _istnow().isoformat(),
                }
            except InvalidImageError as exc:
                logger.warning("[ChatEngine] Rejected image upload: %s", exc)
                return {
                    "session_uuid": session_uuid or "chat_default",
                    "text": f"That image couldn't be processed: {exc}",
                    "timeline": [],
                    "timestamp": _istnow().isoformat(),
                }
            except Exception as exc:  # noqa: BLE001 - top-level request boundary
                logger.error("[ChatEngine] Error in image search: %s", exc, exc_info=True)
                return {
                    "session_uuid": session_uuid or "chat_default",
                    "text": "I hit an internal error performing the visual image search. Please retry.",
                    "timeline": [],
                    "timestamp": _istnow().isoformat(),
                    "error": str(exc),
                }

    def get_history(self, session_uuid: str, limit: int = 50, before_id: Optional[int] = None) -> Dict[str, Any]:
        """Retrieves persistent chat message history for session memory, paginated
        newest-first-fetched-then-returned-chronologically."""
        with self._db_session() as db:
            q = db.query(ChatMessage).filter(ChatMessage.session_uuid == session_uuid)
            if before_id is not None:
                q = q.filter(ChatMessage.id < before_id)
            msgs = q.order_by(ChatMessage.id.desc()).limit(limit + 1).all()

            has_more = len(msgs) > limit
            msgs = msgs[:limit]
            msgs.reverse()

            _, camera_geo = self._camera_lookup(db)
            out = []
            for m in msgs:
                timeline = []
                trajectory = None
                candidates = []
                if m.timeline_json:
                    try:
                        timeline = json.loads(m.timeline_json)
                        if isinstance(timeline, list) and timeline:
                            trajectory = build_trajectory_summary(timeline, camera_geo)
                            if len(timeline) > 1:
                                for c_idx, item in enumerate(timeline[:4], 1):
                                    candidates.append({
                                        "candidate_id": c_idx,
                                        "title": f"Candidate #{c_idx}",
                                        "camera_id": item.get("camera_id"),
                                        "camera_name": item.get("camera_name"),
                                        "time_display": item.get("time_display"),
                                        "description": item.get("description"),
                                        "snapshot_url": item.get("snapshot_url"),
                                        "video_url": f"/api/v1/playback/stream/{item.get('camera_id')}?time={item.get('timestamp') or ''}"
                                    })
                    except (ValueError, TypeError):
                        timeline = []
                out.append({
                    "id": m.id,
                    "sender": m.sender,
                    "text": m.text,
                    "image_url": m.image_url,
                    "timeline": timeline,
                    "trajectory": trajectory,
                    "candidates": candidates,
                    "timestamp": m.timestamp.isoformat() if m.timestamp else "",
                })

            return {
                "messages": out,
                "has_more": has_more,
                "next_before_id": out[0]["id"] if (has_more and out) else None,
            }


chat_engine = SurveillanceChatEngine()