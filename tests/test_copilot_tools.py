"""
Test Suite: AI Investigation Copilot 18 Controlled Tools & Report Generation
"""

import pytest
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.database.connection import Base
from backend.database.models import (
    Camera, CanonicalEvent, PersonJourneyEvent, VehicleJourneyEvent, _istnow
)
from backend.services.copilot.copilot_agent import copilot_agent, CopilotToolRouter
from backend.services.copilot.report_generator import report_generator


@pytest.fixture
def in_memory_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def test_copilot_allowed_tools_list():
    """Verifies that all tools are listed and unauthorized tools are rejected."""
    assert len(CopilotToolRouter.ALLOWED_TOOLS) >= 18
    res = CopilotToolRouter.execute_tool("invalid_shell_execution", {})
    assert "error" in res


def test_copilot_investigation_query(monkeypatch, in_memory_db):
    """Tests AIInvestigationCopilot investigation execution and session persistence."""
    import backend.services.copilot.copilot_agent as copilot_module
    import backend.services.copilot.report_generator as report_module
    monkeypatch_db = lambda: in_memory_db
    monkeypatch.setattr(copilot_module, "SessionLocal", monkeypatch_db)
    monkeypatch.setattr(report_module, "SessionLocal", monkeypatch_db)

    # Insert test camera & journey event
    now_dt = _istnow()
    cam = Camera(id="cam_07", name="Warehouse Entrance", stream_url="rtsp://localhost/cam07")
    p_journey = PersonJourneyEvent(
        global_person_id="GLOBAL_PERSON_0042",
        camera_id="cam_07",
        track_id="TRK_701",
        timestamp_start=now_dt,
        timestamp_end=now_dt,
        confidence=0.94
    )
    in_memory_db.add(cam)
    in_memory_db.add(p_journey)
    in_memory_db.commit()

    # Run Copilot investigation
    res = copilot_agent.run_investigation("What happened at warehouse entrance?", username="operator")
    assert res is not None
    assert "investigation_id" in res
    assert "answer" in res
    assert res["tool_calls_executed"] >= 1

    inv_id = res["investigation_id"]

    # Generate Report
    rep = report_generator.build_report(inv_id, investigator_username="operator")
    assert rep is not None
    assert "report_markdown" in rep
    assert "SYBAU AI Forensic Investigation Report" in rep["report_markdown"]
