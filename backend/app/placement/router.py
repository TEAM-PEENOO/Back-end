from fastapi import APIRouter, HTTPException

from app.placement.schemas import (
    PlacementAnswerRequest,
    PlacementCompletedResponse,
    PlacementInProgressResponse,
    PlacementStartResponse,
)

router = APIRouter(prefix="/placement", tags=["Placement"])


@router.post("/start", response_model=PlacementStartResponse)
async def placement_start():
    raise HTTPException(status_code=410, detail="Placement is removed in v2 subject-scoped flow")


@router.post("/answer", response_model=PlacementInProgressResponse | PlacementCompletedResponse)
async def placement_answer(payload: PlacementAnswerRequest):
    _ = payload
    raise HTTPException(status_code=410, detail="Placement is removed in v2 subject-scoped flow")
