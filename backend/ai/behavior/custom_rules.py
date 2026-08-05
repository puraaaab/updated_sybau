import logging
import re
import numpy as np
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Cache rule embeddings in memory so we don't re-encode prompt text on every frame
_rule_embedding_cache = {}

def get_prompt_embedding(prompt: str):
    """Computes and caches SentenceTransformer vector embedding for custom rule prompt."""
    if not prompt:
        return None
    clean_p = prompt.strip().lower()
    if clean_p in _rule_embedding_cache:
        return _rule_embedding_cache[clean_p]

    try:
        from ..embeddings.embedder import get_text_embedding
        vec = get_text_embedding(prompt)
        if vec is not None and len(vec) > 0:
            _rule_embedding_cache[clean_p] = vec
            return vec
    except Exception as e:
        logger.warning(f"[CustomRules] Failed to embed rule prompt '{prompt}': {e}")

    return None


def clear_rule_cache():
    """Clears cached embeddings when user deletes or updates a rule."""
    global _rule_embedding_cache
    _rule_embedding_cache.clear()


class CustomRuleEvaluator:
    """
    Evaluates dynamic, user-defined AI alert rules against frame results in real time (< 1-2s latency).
    Supports:
      1. License Plate Matching (e.g. "MH87LH0898", "MH87*")
      2. Threat & Object Class Matching (e.g. "weapon", "knife", "fire", "crowd")
      3. Semantic & Natural Language Visual Scene Matching (e.g. "someone near the blue car", "girl with black tshirt")
    """

    def evaluate_custom_rules(
        self,
        frame_results: Dict[str, Any],
        custom_rules: List[Dict[str, Any]],
        camera_id: str
    ) -> List[Dict[str, Any]]:
        """
        Evaluates active custom rules for this frame.
        """
        if not custom_rules:
            return []

        triggered_alerts = []
        caption = frame_results.get("caption", "")
        frame_embedding = frame_results.get("embedding")
        tracks = frame_results.get("tracks", [])
        vehicles = frame_results.get("vehicles", [])

        # Extract plates present in current frame
        detected_plates = [v.get("license_plate").strip().upper() for v in vehicles if v.get("license_plate")]

        # Extract object labels present in current frame
        detected_classes = set(t.get("class_name", "").lower() for t in tracks if t.get("class_name"))

        for rule in custom_rules:
            # Skip if rule is disabled or scoped to a different camera
            if not rule.get("is_active", True):
                continue

            rule_cam = rule.get("camera_id", "ALL")
            if rule_cam != "ALL" and rule_cam != camera_id:
                continue

            prompt = (rule.get("prompt") or "").strip()
            if not prompt:
                continue

            rule_id = rule.get("id")
            rule_name = rule.get("name") or prompt
            severity = rule.get("severity", "high")
            threshold = float(rule.get("confidence_threshold", 0.65))

            clean_prompt = prompt.upper().replace(" ", "")

            # ── 1. License Plate Match ────────────────────────────────────────
            plate_matched = False
            for p in detected_plates:
                if clean_prompt in p or p in clean_prompt:
                    plate_matched = True
                    triggered_alerts.append({
                        "type": f"CUSTOM_ALERT // PLATE MATCH ({rule_name})",
                        "message": f"🎯 Custom Rule Triggered: Detected Target Plate '{p}' matching prompt '{prompt}'",
                        "severity": severity,
                        "confidence": 0.99
                    })
                    break

            if plate_matched:
                continue

            # ── 2. Object Class & Attribute Match (YOLO + Vehicle/Person analytics) ─
            prompt_lower = prompt.lower()
            prompt_words = set(re.findall(r'\b\w+\b', prompt_lower))

            # Check exact or word match against detected YOLO classes
            if prompt_lower in detected_classes or any(w in detected_classes for w in prompt_words if len(w) > 2):
                triggered_alerts.append({
                    "type": f"CUSTOM_ALERT // OBJECT MATCH ({rule_name})",
                    "message": f"⚠️ Custom Rule Triggered: Detected target object matching '{prompt}' on camera {camera_id}",
                    "severity": severity,
                    "confidence": 0.92
                })
                continue

            # Check vehicle attributes (color, type)
            veh_matched = False
            for v in vehicles:
                v_color = (v.get("vehicle_color") or "").lower()
                v_type = (v.get("vehicle_type") or "").lower()
                if (v_color and v_color in prompt_words) or (v_type and v_type in prompt_words):
                    veh_matched = True
                    triggered_alerts.append({
                        "type": f"CUSTOM_ALERT // VEHICLE ATTR MATCH ({rule_name})",
                        "message": f"🚙 Custom Rule Triggered: Detected {v_color} {v_type} matching prompt '{prompt}'",
                        "severity": severity,
                        "confidence": 0.90
                    })
                    break
            if veh_matched:
                continue

            # ── 3. Semantic Natural Language Match (Florence-2 + MiniLM) ──────
            if frame_embedding is not None and len(frame_embedding) > 0:
                prompt_vec = get_prompt_embedding(prompt)
                if prompt_vec is not None and len(prompt_vec) == len(frame_embedding):
                    try:
                        # Cosine similarity
                        dot = np.dot(frame_embedding, prompt_vec)
                        norm_f = np.linalg.norm(frame_embedding)
                        norm_p = np.linalg.norm(prompt_vec)
                        if norm_f > 1e-6 and norm_p > 1e-6:
                            similarity = float(dot / (norm_f * norm_p))
                        else:
                            similarity = 0.0

                        # Check if prompt keywords exist in text or similarity >= threshold (default 0.65)
                        prompt_words = [w for w in prompt_lower.split() if len(w) > 2]
                        words_in_caption = all(w in caption.lower() for w in prompt_words) if prompt_words else False

                        if (words_in_caption and similarity >= 0.45) or similarity >= max(threshold, 0.68):
                            conf_pct = round(similarity * 100, 1)
                            triggered_alerts.append({
                                "type": f"CUSTOM_ALERT // AI MATCH ({rule_name})",
                                "message": f"🚨 Custom AI Rule Matched ({conf_pct}% confidence): '{prompt}' in scene: {caption}",
                                "severity": severity,
                                "confidence": round(similarity, 2)
                            })
                            continue
                    except Exception as err:
                        logger.warning(f"[CustomRules] Similarity calculation error: {err}")

            # Fallback substring search on scene caption if embedding not ready
            if prompt_lower in caption.lower():
                triggered_alerts.append({
                    "type": f"CUSTOM_ALERT // SCENE MATCH ({rule_name})",
                    "message": f"🚨 Custom Rule Matched caption: '{prompt}' on camera {camera_id}",
                    "severity": severity,
                    "confidence": 0.85
                })

        return triggered_alerts


custom_rule_evaluator = CustomRuleEvaluator()
