"""
Multilingual Fixed Phrase-Template Matcher for Hindi & Gujarati (Step 3).
Narrow scope:
1. Clothing + Color + Time person search
2. Vehicle + Plate / Type search
3. Missing Person search
Zero GPU models: Uses deterministic rule/slot extraction to normalize into standard copilot query intents.
"""
import re
from typing import Dict, Any, Optional, Tuple


# Vocabulary dictionaries
HINDI_COLORS = {
    "laal": "red", "lal": "red",
    "neela": "blue", "neeli": "blue", "nila": "blue",
    "kaala": "black", "kaali": "black", "kala": "black", "kali": "black",
    "safed": "white", "chitta": "white",
    "peela": "yellow", "peeli": "yellow", "pila": "yellow",
    "hara": "green", "hari": "green",
    "bhura": "brown", "bhuri": "brown",
    "gulabi": "pink",
    "narangi": "orange",
}

GUJARATI_COLORS = {
    "lal": "red",
    "kalo": "black", "kali": "black",
    "safed": "white", "dholo": "white",
    "pilo": "yellow", "pili": "yellow",
    "leelo": "green", "lilo": "green",
    "vaadli": "blue", "vadli": "blue",
}

HINDI_CLOTHING = {
    "shirt": "shirt", "tshirt": "t-shirt", "t-shirt": "t-shirt",
    "kurta": "kurta", "kurti": "kurti", "jacket": "jacket",
    "pant": "pants", "hoodie": "hoodie", "kapde": "clothing",
}

GUJARATI_CLOTHING = {
    "shirt": "shirt", "tshirt": "t-shirt", "kurto": "kurta",
    "jacket": "jacket", "pant": "pants", "kapda": "clothing",
}

HINDI_VEHICLES = {
    "gaadi": "car", "gadi": "car", "car": "car",
    "scorpio": "scorpio", "swift": "swift", "fortuner": "fortuner",
    "bike": "motorcycle", "motorcycle": "motorcycle",
    "bus": "bus", "truck": "truck", "auto": "autorickshaw",
}

GUJARATI_VEHICLES = {
    "gaadi": "car", "gadi": "car", "car": "car",
    "bus": "bus", "truck": "truck", "bike": "motorcycle",
}


class MultilingualTemplateMatcher:
    """
    Matches Hindi and Gujarati structured surveillance queries and converts them
    to standard English intent payloads.
    """

    def is_indic_script_or_romanized(self, text: str) -> bool:
        # Check Devanagari (\u0900-\u097F) or Gujarati (\u0A80-\u0AFF)
        has_indic_script = bool(re.search(r"[\u0900-\u097F\u0A80-\u0AFF]", text))
        if has_indic_script:
            return True

        # Distinctive non-English romanized Indic particles (word boundaries)
        romanized_indic_tokens = [
            r"\bwala\b", r"\bwali\b", r"\bpehne\b", r"\bkapde\b", r"\bkhojo\b", r"\bdhoondo\b",
            r"\bgaadi\b", r"\bgadi\b", r"\bbaje\b", r"\bke baad\b", r"\bgumshuda\b", r"\blaapata\b",
            r"\baadmi\b", r"\baurat\b", r"\bbachha\b", r"\bvalo\b", r"\bvali\b", r"\bpehrel\b",
            r"\bkapda\b", r"\bshodho\b", r"\bbatavo\b", r"\bvagya\b", r"\bpachhi\b",
            r"\bgum thayel\b", r"\blapata\b", r"\bmanas\b", r"\bchokro\b", r"\bchokri\b",
            r"\bbatao\b", r"\bdikhao\b", r"\bkya\b", r"\byaha\b", r"\bbhai\b", r"\bche\b", r"\bshu\b"
        ]
        q_lower = text.lower()
        return any(re.search(pat, q_lower) for pat in romanized_indic_tokens)

    def match_query(self, query: str) -> Dict[str, Any]:
        """
        Attempts to match the query against the supported 3 categories in Hindi and Gujarati.
        If matched, returns a normalized English query and extracted entities.
        If out of pattern, returns success=False with clear actionable guidance.
        """
        q = query.strip().lower()

        # ── 1. MISSING PERSON SEARCH ─────────────────────────────────────────
        # Hindi: गुमशुदा व्यक्ति / gumshuda aadmi / laapata bachha
        # Gujarati: ગુમ થયેલ વ્યક્તિ / gum thayel manas / lapata chokro
        missing_patterns = [
            r"(?:gumshuda|laapata|lapata|gum thayel|ગુમ થયેલ|લાપતા|गुमशुदा|लापता)\s+(?:bachha|bachhi|ladka|ladki|aadmi|mahila|person|manas|chokro|chokri|vyakti|व्यक्ति|માણસ)?\s*(?:naam|name)?\s*([a-zA-Z\u0900-\u097F\u0A80-\u0AFF]+)?",
            r"(?:khojo|dhoondo|shodho|શોધો|ढूंढो)\s+(?:gumshuda|laapata|gum thayel)\s+([a-zA-Z\u0900-\u097F\u0A80-\u0AFF]+)?",
        ]
        for pat in missing_patterns:
            m = re.search(pat, q)
            if m:
                target_name = m.group(1).strip() if (m.lastindex and m.group(1)) else ""
                clean_name = target_name if target_name not in ["khojo", "dhoondo", "shodho", "batavo"] else ""
                eng_query = f"find missing person {clean_name}".strip()
                return {
                    "matched": True,
                    "language": "indic_multilingual",
                    "category": "missing_person",
                    "normalized_english_query": eng_query,
                    "entities": {"person_name": clean_name},
                    "source_query": query,
                }

        # ── 2. VEHICLE + PLATE SEARCH ────────────────────────────────────────
        # Hindi: गाड़ी नंबर DL01AB1234 / 10 baje ke baad bus / laal car khojo
        # Gujarati: ગાડી નંબર DL01AB1234 / 10 vagya pachhi bus / lal gadi shodho
        plate_m = re.search(r"(?:number plate|gaadi number|gadi number|plate|નંબર|नंबर)\s*([A-Za-z0-9]{4,12})", q)
        if plate_m:
            plate = plate_m.group(1).upper()
            return {
                "matched": True,
                "language": "indic_multilingual",
                "category": "vehicle_plate",
                "normalized_english_query": f"find vehicle with plate {plate}",
                "entities": {"license_plate": plate},
                "source_query": query,
            }

        # Vehicle type + color / time
        time_m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(?:baje|vagya|am|pm|बजे|વાગ્યા)\s*(?:ke baad|pachhi|baad|પછી|बाद)?", q)
        time_str = f"{time_m.group(1)}:00" if time_m else ""

        found_color = None
        for k, v in {**HINDI_COLORS, **GUJARATI_COLORS}.items():
            if re.search(r"\b" + k + r"\b", q):
                found_color = v
                break

        found_vehicle = None
        for k, v in {**HINDI_VEHICLES, **GUJARATI_VEHICLES}.items():
            if re.search(r"\b" + k + r"\b", q):
                found_vehicle = v
                break

        if found_vehicle or (found_color and ("gaadi" in q or "gadi" in q or "car" in q)):
            v_type = found_vehicle or "car"
            eng_parts = ["find", found_color, v_type]
            if time_str:
                eng_parts.extend(["after", time_str])
            eng_query = " ".join([p for p in eng_parts if p])
            return {
                "matched": True,
                "language": "indic_multilingual",
                "category": "vehicle_search",
                "normalized_english_query": eng_query,
                "entities": {"vehicle_type": v_type, "color": found_color, "time": time_str},
                "source_query": query,
            }

        # ── 3. CLOTHING + COLOR + TIME PERSON SEARCH ─────────────────────────
        # Hindi: laal shirt wala aadmi 10 baje ke baad
        # Gujarati: lal shirt valo manas 10 vagya pachhi
        found_clothing = None
        for k, v in {**HINDI_CLOTHING, **GUJARATI_CLOTHING}.items():
            if re.search(r"\b" + k + r"\b", q):
                found_clothing = v
                break

        if found_color and (found_clothing or any(tok in q for tok in ["wala", "wali", "valo", "vali", "pehne", "pehrel", "manas", "aadmi", "person"])):
            c_type = found_clothing or "clothing"
            eng_parts = ["find person wearing", found_color, c_type]
            if time_str:
                eng_parts.extend(["after", time_str])
            eng_query = " ".join([p for p in eng_parts if p])
            return {
                "matched": True,
                "language": "indic_multilingual",
                "category": "person_clothing_search",
                "normalized_english_query": eng_query,
                "entities": {"color": found_color, "clothing": c_type, "time": time_str},
                "source_query": query,
            }

        # ── OUT OF PATTERN HANDLING ──────────────────────────────────────────
        return {
            "matched": False,
            "language": "indic_multilingual",
            "error_message": (
                "⚠️ **भाषा पैटर्न समर्थित नहीं है / ભાષા પેટર્ન સમર્થિત નથી**\n\n"
                "कृपया समर्थित 3 श्रेणियों में से किसी एक प्रारूप में पूछें:\n"
                "1. **कपड़े और रंग (Clothing + Color):** *'लाल शर्ट वाला आदमी 10 बजे के बाद'* / *'લાલ શર્ટ વાળો માણસ'*\n"
                "2. **वाहन और नंबर प्लेट (Vehicle + Plate):** *'गाड़ी नंबर DL01AB1234'* / *'ગાડી નંબર DL01AB1234'*\n"
                "3. **गुमशुदा व्यक्ति (Missing Person):** *'गुमशुदा व्यक्ति विक्रम खोजो'* / *'ગુમ થયેલ વ્યક્તિ શોધો'*"
            ),
            "source_query": query,
        }


multilingual_matcher = MultilingualTemplateMatcher()
