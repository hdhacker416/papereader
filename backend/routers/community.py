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


@router.get("/topics", response_model=schemas.CommunityFeedResponse)
def list_topics():
    return community_service.list_topics()


@router.get("/topics/{topic_id}", response_model=schemas.CommunityTopicResponse)
def get_topic(topic_id: str):
    try:
        return community_service.get_topic(topic_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/topics/{topic_id}/generate", response_model=schemas.CommunityTopicResponse)
def generate_topic(topic_id: str, payload: schemas.CommunityAnswerRequest | None = None):
    try:
        return community_service.generate_topic(topic_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
