from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

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


@router.get("/seeded-figures/{topic_id}/{paper_id}/{figure_id}.png")
def get_seeded_figure(topic_id: str, paper_id: str, figure_id: str):
    try:
        path = community_service.get_seeded_figure_path(topic_id, paper_id, figure_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Figure not found") from exc
    return FileResponse(str(path), media_type="image/png")


@router.get("/assets/{asset_path:path}")
def get_community_asset(asset_path: str):
    try:
        path = community_service.get_community_asset_path(asset_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Asset not found") from exc
    return FileResponse(str(path), media_type="image/png")
