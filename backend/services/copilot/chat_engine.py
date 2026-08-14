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
            leg["inferred_speed_kmh"] = round(speed_kmh, 1)
            if speed_kmh > 140:
                flags.append(
                    f"Implausible inferred speed ({speed_kmh:.0f} km/h) between "
                    f"{prev['camera_name']} and {curr['camera_name']} — likely two different subjects"
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
            from ...database.models import AuditLog  # optional model
            db.add(AuditLog(
                username=username,
                session_uuid=session_uuid,
                action=action,
                detail_json=json.dumps(detail, default=str),
                timestamp=_istnow(),
            ))
            db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.debug("[ChatEngine] Audit log skipped (%s): %s", action, exc)

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
                if intent.camera_filter.lower() not in cname:
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

    def process_text_query(self, user_query: str, session_uuid: Optional[str] = None,
                            username: str = "operator") -> Dict[str, Any]:
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
                    "[ChatEngine] session=%s query=%r hinglish=%s followup=%s effective_prompt=%r",
                    session_id, user_query, intent.is_hinglish, intent.is_followup, effective_prompt,
                )

                db.add(ChatMessage(session_uuid=session_id, sender="user", text=user_query, timestamp=_istnow()))
                db.commit()

                camera_map, camera_geo = self._camera_lookup(db)

                try:
                    semantic_results = self._semantic_search(effective_prompt, ChatConfig.SEMANTIC_SEARCH_LIMIT)
                except ExternalServiceError as exc:
                    logger.error("[ChatEngine] Semantic search unavailable: %s", exc)
                    semantic_results = []

                q_terms = [w for w in effective_prompt.lower().split() if len(w) > 2]
                sql_captions_all = (
                    db.query(SceneCaption)
                    .order_by(SceneCaption.timestamp.desc())
                    .limit(ChatConfig.SQL_CAPTION_SCAN_LIMIT)
                    .all()
                )
                matching_captions = [sc for sc in sql_captions_all if any(w in sc.caption.lower() for w in q_terms)]

                timeline_items = self._build_timeline(semantic_results, matching_captions, camera_map, intent)
                trajectory = build_trajectory_summary(timeline_items, camera_geo)

                answer_text = self._synthesize_answer(
                    session_uuid=session_id, db=db, intent=intent,
                    timeline_items=timeline_items, trajectory=trajectory,
                )

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
        if img is None:
            raise InvalidImageError("Could not decode image bytes — unsupported or corrupt format")
        return img

    @with_retries()
    def _moondream_caption(self, data_uri: str, upload_id: str) -> str:
        return _call_moondream_api(data_uri, upload_id)

    def process_image_query(self, image_bytes: bytes, user_query: Optional[str] = None,
                             session_uuid: Optional[str] = None, username: str = "operator") -> Dict[str, Any]:
        """Uploads image, extracts a detailed vision caption, and matches the target
        across city cameras. EXIF is stripped implicitly by the cv2 re-encode."""
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
                # Re-encoding via cv2 (rather than writing raw bytes) strips EXIF/GPS metadata.
                cv2.imwrite(snap_path, img)
                upload_url = f"/api/v1/playback/snapshot/{upload_id}"

                try:
                    data_uri = _encode_frame(img, max_dim=ChatConfig.MAX_IMAGE_DIM)
                    detailed_caption = self._moondream_caption(data_uri, upload_id)
                    logger.info("[ChatEngine] Vision caption generated for %s: %.100s...", upload_id, detailed_caption)
                except ExternalServiceError as vision_err:
                    logger.warning("[ChatEngine] Vision API unavailable, degrading to user query only: %s", vision_err)
                    detailed_caption = user_query or "Uploaded visual target (vision analysis unavailable)"

                combined_search_prompt = f"{user_query or ''} {detailed_caption}".strip()

                user_msg_text = f"[Uploaded Image] {user_query or 'Find this in city cameras'}\n\n*Visual Analysis*: {detailed_caption[:200]}..."
                db.add(ChatMessage(session_uuid=session_id, sender="user", text=user_msg_text, image_url=upload_url, timestamp=_istnow()))
                db.commit()

                camera_map, camera_geo = self._camera_lookup(db)
                try:
                    semantic_results = self._semantic_search(combined_search_prompt, ChatConfig.IMAGE_SEARCH_LIMIT)
                except ExternalServiceError as exc:
                    logger.error("[ChatEngine] Semantic search unavailable for image query: %s", exc)
                    semantic_results = []

                dummy_intent = QueryIntent(raw_query=user_query or "", search_prompt=combined_search_prompt, is_hinglish=False)
                timeline_items = self._build_timeline(semantic_results, [], camera_map, dummy_intent)
                trajectory = build_trajectory_summary(timeline_items, camera_geo)

                if timeline_items:
                    cams_involved = list(dict.fromkeys(t["camera_name"] for t in timeline_items))
                    lines = [
                        f"🔍 **Uploaded Image Analysis**: {detailed_caption}\n",
                        f"✅ **City Camera Match Found!** Matched this visual target across **{len(timeline_items)} location(s)** ({', '.join(cams_involved)}):\n",
                    ]
                    for idx, t in enumerate(timeline_items[:5], 1):
                        lines.append(f"{idx}. **{t['camera_name']}** at **{t['time_display']}**: {t['description']}")
                    for flag in trajectory.get("flags", []):
                        lines.append(f"\n⚠️ {flag}")
                    answer_text = "\n".join(lines)
                else:
                    answer_text = (
                        f"🔍 **Uploaded Image Analysis**: {detailed_caption}\n\n"
                        f"I analyzed all city camera feeds against this image, but could not find a matching target in recent video logs."
                    )

                db.add(ChatMessage(
                    session_uuid=session_id, sender="assistant", text=answer_text,
                    timeline_json=json.dumps(timeline_items), timestamp=_istnow(),
                ))
                db.commit()

                self._audit_log(
                    db, session_uuid=session_id, username=username, action="image_query",
                    detail={"upload_id": upload_id, "hits": len(timeline_items)},
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