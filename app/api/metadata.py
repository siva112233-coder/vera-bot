"""GET /v1/metadata — bot identity and team information."""
from __future__ import annotations

from fastapi import APIRouter

from app.config import settings
from app.models.requests import MetadataResponse

router = APIRouter()


@router.get("/metadata", response_model=MetadataResponse)
async def metadata() -> MetadataResponse:
    return MetadataResponse(
        team_name=settings.team_name,
        team_members=settings.team_members,
        model=settings.model_descriptor,
        approach=settings.approach,
        contact_email=settings.contact_email,
        version=settings.version,
        submitted_at=settings.submitted_at,
    )
