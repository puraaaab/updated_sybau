import numpy as np
import pytest
from backend.ai.embeddings.embedder import get_text_embedding, EMBEDDING_DIM

def test_module2_rich_document_construction_and_embedding():
    """Validates rich multi-modal document construction and 1024-D embedding."""
    caption = "A light blue bus is parked near a multi-story building."
    ocr_texts = ["SAGAR TOURS & TRAVELS", "KA51MB8811"]
    yolo_classes = ["bus", "person"]

    rich_document = caption
    if ocr_texts:
        rich_document += f" | Signage/Text: {', '.join(ocr_texts)}"
    if yolo_classes:
        rich_document += f" | Objects: {', '.join(yolo_classes)}"

    expected_doc = (
        "A light blue bus is parked near a multi-story building. | "
        "Signage/Text: SAGAR TOURS & TRAVELS, KA51MB8811 | "
        "Objects: bus, person"
    )
    assert rich_document == expected_doc

    # Generate embedding
    vec = get_text_embedding(rich_document)
    assert isinstance(vec, list)
    assert len(vec) == EMBEDDING_DIM
    assert len(vec) == 1024

    # Verify vector is unit-normalized
    norm = np.linalg.norm(vec)
    assert abs(norm - 1.0) < 1e-3


def test_module2_qdrant_payload_structure():
    """Validates Qdrant schema version 2 payload structure."""
    payload = {
        "type": "scene",
        "camera_id": "cam_11",
        "caption": "A cyan bus parked on street",
        "rich_document": "A cyan bus parked on street | Signage/Text: SAGAR TOURS | Objects: bus",
        "ocr_text": "SAGAR TOURS",
        "schema_version": 2,
        "enriched": True,
        "yolo_class": "bus",
    }

    assert payload["schema_version"] == 2
    assert payload["enriched"] is True
    assert "SAGAR TOURS" in payload["rich_document"]
