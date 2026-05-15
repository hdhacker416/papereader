from fastapi import APIRouter, HTTPException

import schemas
from services import community_service


router = APIRouter(
    prefix="/api/community",
    tags=["community"],
    responses={404: {"description": "Not found"}},
)


@router.post("/answers", response_model=schemas.CommunityAnswerResponse)
def generate_persona_answers(payload: schemas.CommunityAnswerRequest):
    try:
        return community_service.generate_persona_answers(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
