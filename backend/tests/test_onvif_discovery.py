import pytest
import asyncio
from backend.services.onvif_discovery import ONVIFDiscoveryService, ONVIFMediaClient

def test_onvif_discovery_scan_returns_valid_structure():
    res = ONVIFDiscoveryService.discover_devices(timeout=0.1)
    assert res["status"] == "success"
    assert "count" in res
    assert "is_real" in res
    assert "devices" in res
    assert len(res["devices"]) > 0

@pytest.mark.anyio
async def test_onvif_media_client_unauthenticated_fails_loudly():
    # Calling get_stream_uri without credentials must return auth_required
    res = await ONVIFMediaClient.get_stream_uri("192.168.1.100", 80, username="", password="")
    assert res["status"] == "auth_required"
    assert res["rtsp_url"] is None
