"""
Watchlist REST API Endpoints for Stolen Vehicles and Wanted Persons.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
import datetime

from ...database.connection import get_db
from ...database.models import StolenVehicleWatchlist, PersonWatchlist
from ..integrations.cctns_service import get_all_active_stolen_vehicles, get_all_wanted_persons

router = APIRouter(tags=["Watchlist"])


@router.get("/stolen-vehicles")
def get_stolen_vehicles(
    status: str = "ACTIVE",
    db: Session = Depends(get_db),
):
    """Lists stolen vehicle hot-list registrations from DB and state repository."""
    db_items = db.query(StolenVehicleWatchlist).filter(StolenVehicleWatchlist.status == status).all()
    cctns_items = get_all_active_stolen_vehicles()
    return {
        "success": True,
        "database_records_count": len(db_items),
        "cctns_records_count": len(cctns_items),
        "total_active_stolen": len(db_items) + len(cctns_items),
        "watchlist": [
            {
                "plate_number": s.plate_number,
                "make_model": s.vehicle_make_model,
                "fir_number": s.fir_number,
                "police_station": s.police_station,
                "owner": s.owner_name,
                "priority": s.priority,
                "source": "INTERNAL_WATCHLIST",
            }
            for s in db_items
        ] + [
            {
                "plate_number": c["plate_number"],
                "make_model": c["make_model"],
                "fir_number": c["fir_number"],
                "police_station": c["police_station"],
                "owner": c["owner"],
                "priority": c["priority"],
                "source": "CCTNS_NATIONAL_REPOSITORY",
            }
            for c in cctns_items
        ]
    }


@router.get("/wanted-persons")
def get_wanted_persons(
    status: str = "ACTIVE",
    db: Session = Depends(get_db),
):
    """Lists active wanted person dossiers from DB and CCTNS state registry."""
    db_items = db.query(PersonWatchlist).filter(PersonWatchlist.status == status).all()
    cctns_items = get_all_wanted_persons()
    return {
        "success": True,
        "database_records_count": len(db_items),
        "cctns_records_count": len(cctns_items),
        "total_active_wanted": len(db_items) + len(cctns_items),
        "wanted_dossiers": [
            {
                "person_uuid": p.person_uuid,
                "full_name": p.full_name,
                "alias": p.alias,
                "category": p.category,
                "case_reference": p.case_reference,
                "priority": p.priority,
                "source": "INTERNAL_WATCHLIST",
            }
            for p in db_items
        ] + [
            {
                "person_uuid": c["person_uuid"],
                "full_name": c["full_name"],
                "alias": c["alias"],
                "category": c["category"],
                "case_reference": c["case_reference"],
                "priority": c["priority"],
                "source": "CCTNS_NATIONAL_REPOSITORY",
            }
            for c in cctns_items
        ]
    }
