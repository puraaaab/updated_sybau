"""
Test Suite: SHA-256 Evidence Integrity, Digital Manifests, and Tamper Verification
"""

import os
import pytest
import tempfile
import hashlib
from backend.services.event_export import compute_sha256


def test_sha256_computation_and_tamper_detection():
    """Tests SHA-256 computation and verifies that modifying 1 byte fails integrity check."""
    with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
        tmp.write(b"ORIGINAL UNALTERED SURVEILLANCE EVIDENCE DATA 2026")
        tmp_path = tmp.name

    try:
        original_hash = compute_sha256(tmp_path)
        assert len(original_hash) == 64

        # Re-verify clean file -> MUST MATCH
        verify_hash = compute_sha256(tmp_path)
        assert verify_hash == original_hash

        # Tamper 1 byte of the evidence file
        with open(tmp_path, "r+b") as f:
            f.seek(0)
            f.write(b"X")

        tampered_hash = compute_sha256(tmp_path)
        assert tampered_hash != original_hash, "FAILURE: Tampered evidence produced identical hash!"
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
