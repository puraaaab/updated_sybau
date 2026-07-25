"""
Indian License Plate Parser with Positional Character Correction.
"""
import re

VALID_STATES = {
    'AP', 'AR', 'AS', 'BR', 'CG', 'GA', 'GJ', 'HR', 'HP', 'JH', 'KA', 'KL', 'MP',
    'MH', 'MN', 'ML', 'MZ', 'NL', 'OD', 'PB', 'RJ', 'SK', 'TN', 'TS', 'TR', 'UP',
    'UK', 'WB', 'AN', 'CH', 'DD', 'DN', 'DL', 'JK', 'LA', 'LD', 'PY'
}

_DIGIT_AS_LETTER = {
    '0': 'O', '1': 'I', '2': 'Z', '3': 'J',
    '4': 'A', '5': 'S', '6': 'G', '7': 'T', '8': 'B', '9': 'P'
}

_LETTER_AS_DIGIT = {
    'O': '0', 'Q': '0', 'D': '0',
    'I': '1', 'L': '1',
    'Z': '2',
    'J': '3',
    'A': '4',
    'S': '5',
    'G': '6',
    'T': '7',
    'B': '8',
    'P': '9',
}

def _to_letter(char: str) -> str:
    return _DIGIT_AS_LETTER.get(char, char)

def _to_digit(char: str) -> str:
    return _LETTER_AS_DIGIT.get(char, char)

def _apply_positional(text: str, pattern: str) -> str:
    out = []
    for char, pos_type in zip(text, pattern):
        if pos_type == 'L':
            out.append(_to_letter(char))
        elif pos_type == 'D':
            out.append(_to_digit(char))
        else:
            out.append(char)
    return ''.join(out)

def _edit_distance(s1: str, s2: str) -> int:
    if len(s1) != len(s2):
        return 999
    return sum(1 for a, b in zip(s1, s2) if a != b)

def _correct_state(code: str) -> tuple:
    if code in VALID_STATES:
        return code, False
    letter_code = ''.join(_to_letter(c) for c in code)
    if letter_code in VALID_STATES:
        return letter_code, True
    closest, min_dist = None, 999
    for state in VALID_STATES:
        d = _edit_distance(letter_code, state)
        if d < min_dist:
            min_dist, closest = d, state
    if min_dist <= 1:
        return closest, True
    return code, False

def _clean(raw: str) -> str:
    txt = re.sub(r'[^A-Z0-9]', '', raw.upper())
    txt = re.sub(r'^(?:1|I)(?:N|M|H)(?:D|0|O)', '', txt)
    return txt

def _parse_standard(txt: str):
    """
    Parse as standard Indian plate: [ST][##][L{0-3}][####]
    Requires strict character compliance after correction.
    """
    if not (8 <= len(txt) <= 11):
        return None, None

    for series_len in [2, 3, 1, 0]:
        total = 2 + 2 + series_len + 4
        if len(txt) != total:
            continue
            
        state_raw  = txt[0:2]
        rto_raw    = txt[2:4]
        series_raw = txt[4:4 + series_len]
        serial_raw = txt[4 + series_len:]

        state, state_fixed = _correct_state(state_raw)
        if state not in VALID_STATES:
            continue

        rto = _apply_positional(rto_raw, 'DD')
        if not re.match(r'^\d{2}$', rto):
            continue
            
        series = _apply_positional(series_raw, 'L' * series_len)
        if not re.match(r'^[A-Z]*$', series):
            continue

        serial = _apply_positional(serial_raw, 'DDDD')
        if not re.match(r'^\d{4}$', serial):
            continue
            
        parsed = f"{state}{rto}{series}{serial}"
        return parsed, "standard" if series_len > 0 else "standard_no_series"

    return None, None

def parse_plate(raw_text: str) -> dict:
    txt = _clean(raw_text)

    if len(txt) < 4:
        return {"raw_text": raw_text, "parsed": None, "reason": "too_short", "confidence": "raw"}

    # BH Series
    m = re.match(r'^(\w{2})(BH|8H|B4|B1)(\w{4})(\w{1,2})$', txt)
    if m or ('BH' in txt) or ('8H' in txt):
        bh_m = re.match(r'^(\w{2})(BH|8H|B4|B1)(\w{4})(\w{1,2})$', txt)
        if bh_m:
            yy = _apply_positional(bh_m.group(1), 'DD')
            if re.match(r'^\d{2}$', yy):
                serial = _apply_positional(bh_m.group(3), 'DDDD')
                if re.match(r'^\d{4}$', serial):
                    suffix_len = len(bh_m.group(4))
                    suffix = _apply_positional(bh_m.group(4), 'L' * suffix_len)
                    if re.match(r'^[A-Z]+$', suffix):
                        parsed = f"{yy}BH{serial}{suffix}"
                        return {"raw_text": raw_text, "parsed": parsed, "reason": "bh_series",
                                "confidence": "corrected" if parsed != txt else "exact"}

    # Delhi specific (DL1C, DL3C, DL10S etc)
    dl_m = re.match(r'^(DL|0L|D1|01)(\w{1,2})(\w{1,2})(\w{4})$', txt)
    if dl_m:
        zone = _apply_positional(dl_m.group(2), 'DD')
        if re.match(r'^\d{1,2}$', zone):
            series = _apply_positional(dl_m.group(3), 'L' * len(dl_m.group(3)))
            if re.match(r'^[A-Z]{1,2}$', series):
                serial = _apply_positional(dl_m.group(4), 'DDDD')
                if re.match(r'^\d{4}$', serial):
                    parsed = f"DL{zone}{series}{serial}"
                    return {"raw_text": raw_text, "parsed": parsed, "reason": "delhi_format",
                            "confidence": "corrected"}

    # Standard
    parsed, reason = _parse_standard(txt)
    if parsed:
        return {"raw_text": raw_text, "parsed": parsed, "reason": reason,
                "confidence": "corrected" if parsed != txt else "exact"}

    # Sliding window
    for start in range(min(3, max(0, len(txt) - 8))):
        for length in [10, 9, 11, 8]:
            sub = txt[start:start + length]
            parsed, reason = _parse_standard(sub)
            if parsed:
                return {"raw_text": raw_text, "parsed": parsed,
                        "reason": f"{reason}_extracted", "confidence": "corrected"}

    return {"raw_text": raw_text, "parsed": None, "reason": "unrecognized_format", "confidence": "raw"}
