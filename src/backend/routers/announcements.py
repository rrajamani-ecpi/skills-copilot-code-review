"""
Announcement endpoints for the High School Management System API
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementPayload(BaseModel):
    """Payload for creating or updating an announcement."""

    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=600)
    expires_at: datetime
    starts_at: Optional[datetime] = None

    @model_validator(mode="after")
    def validate_dates(self):
        if self.starts_at and self.expires_at <= self.starts_at:
            raise ValueError("Expiration date must be after start date")
        return self


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc_now_iso() -> str:
    return _utc_iso(datetime.now(timezone.utc))


def _serialize_announcement(doc: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": str(doc["_id"]),
        "title": doc["title"],
        "message": doc["message"],
        "starts_at": doc.get("starts_at"),
        "expires_at": doc["expires_at"],
        "created_at": doc.get("created_at"),
        "updated_at": doc.get("updated_at")
    }


def _require_teacher(teacher_username: Optional[str]) -> Dict[str, Any]:
    if not teacher_username:
        raise HTTPException(status_code=401, detail="Authentication required")

    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials")

    return teacher


@router.get("", response_model=List[Dict[str, Any]])
@router.get("/", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """Get currently active announcements for the public banner."""
    now_iso = _utc_now_iso()

    query = {
        "expires_at": {"$gte": now_iso},
        "$or": [
            {"starts_at": {"$exists": False}},
            {"starts_at": None},
            {"starts_at": {"$lte": now_iso}}
        ]
    }

    docs = announcements_collection.find(query).sort("expires_at", 1)
    return [_serialize_announcement(doc) for doc in docs]


@router.get("/manage", response_model=List[Dict[str, Any]])
def get_all_announcements(teacher_username: Optional[str] = Query(None)) -> List[Dict[str, Any]]:
    """Get all announcements (including expired) for authenticated management."""
    _require_teacher(teacher_username)

    docs = announcements_collection.find({}).sort("updated_at", -1)
    return [_serialize_announcement(doc) for doc in docs]


@router.post("/manage", response_model=Dict[str, Any])
def create_announcement(
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Create a new announcement. Expiration date is required."""
    _require_teacher(teacher_username)

    now_iso = _utc_now_iso()
    announcement_doc = {
        "title": payload.title.strip(),
        "message": payload.message.strip(),
        "starts_at": _utc_iso(payload.starts_at) if payload.starts_at else None,
        "expires_at": _utc_iso(payload.expires_at),
        "created_at": now_iso,
        "updated_at": now_iso
    }

    result = announcements_collection.insert_one(announcement_doc)
    created = announcements_collection.find_one({"_id": result.inserted_id})
    return _serialize_announcement(created)


@router.put("/manage/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    payload: AnnouncementPayload,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Update an existing announcement."""
    _require_teacher(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    update_doc = {
        "$set": {
            "title": payload.title.strip(),
            "message": payload.message.strip(),
            "starts_at": _utc_iso(payload.starts_at) if payload.starts_at else None,
            "expires_at": _utc_iso(payload.expires_at),
            "updated_at": _utc_now_iso()
        }
    }

    result = announcements_collection.update_one({"_id": object_id}, update_doc)
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updated = announcements_collection.find_one({"_id": object_id})
    return _serialize_announcement(updated)


@router.delete("/manage/{announcement_id}", response_model=Dict[str, Any])
def delete_announcement(
    announcement_id: str,
    teacher_username: Optional[str] = Query(None)
) -> Dict[str, Any]:
    """Delete an announcement."""
    _require_teacher(teacher_username)

    try:
        object_id = ObjectId(announcement_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid announcement id") from exc

    result = announcements_collection.delete_one({"_id": object_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted"}
