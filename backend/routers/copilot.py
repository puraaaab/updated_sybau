"""
VMS Pro — AI Investigation Copilot API Router
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from ..database.connection import get_db
from ..auth.helpers import verify_operator, verify_viewer
from ..services.copilot.copilot_agent import copilot_agent, CopilotToolRouter
from ..services.copilot.report_generator import report_generator

router = APIRouter(prefix="/copilot", tags=["AICopilot"])


@router.post("/query")
def run_copilot_investigation_query(
    question: str = Query(..., min_length=2),
    user=Depends(verify_viewer)
):
    """Executes a natural language investigation query via controlled tool calling."""
    try:
        res = copilot_agent.run_investigation(question=question, username=user.username)
        return res
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Copilot investigation error: {str(exc)}")


@router.get("/report/{investigation_id}")
def generate_investigation_report(
    investigation_id: str,
    user=Depends(verify_operator)
):
    """Generates a formal forensic evidence report for an investigation session."""
    try:
        rep = report_generator.build_report(investigation_id, username=user.username)
        return rep
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Report generation error: {str(exc)}")


@router.get("/tools")
def list_available_copilot_tools(user=Depends(verify_viewer)):
    """Lists all 18 controlled tool interfaces available to Copilot."""
    return {"tools": CopilotToolRouter.ALLOWED_TOOLS}
