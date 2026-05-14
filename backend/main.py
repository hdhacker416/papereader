from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import asyncio
import logging
from dotenv import load_dotenv
from pathlib import Path
from fastapi import HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

load_dotenv()

from database import (
    SessionLocal,
    ensure_user_database,
    get_data_dir,
    iter_user_ids,
    user_context,
)
from routers import auth, templates, tasks, papers, collections, deep_research, settings
from processor import processor_loop
from services import conference_service
from services import auth_service
from services.auto_research_task_service import auto_research_task_loop, recover_stale_auto_research_tasks
from services.pack_build_service import pack_build_loop, recover_stale_pack_build_jobs
from services.report_generation_service import report_generation_loop, recover_stale_report_jobs

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Paper Reader API", version="1.0.0")
_prepared_request_users: set[str] = set()

# CORS configuration
origins = [
    "http://localhost:5173",  # Vite default port
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=".*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    public_api = path.startswith("/api/auth") or path == "/api" or path == "/api/"
    if path.startswith("/api") and not public_api:
        user = auth_service.get_user_from_request(request)
        if user is None:
            return JSONResponse({"detail": "Authentication required"}, status_code=401)
        request.state.current_user = user
        if user.id not in _prepared_request_users:
            ensure_user_database(user.id, email=user.email, name=user.name)
            _prepared_request_users.add(user.id)
        with user_context(user.id):
            return await call_next(request)
    return await call_next(request)

# Include routers
app.include_router(auth.router)
app.include_router(templates.router)
app.include_router(tasks.router)
app.include_router(papers.router)
app.include_router(collections.router)
app.include_router(deep_research.router)
app.include_router(settings.router)


@app.get("/api/pdfs/{file_path:path}")
def serve_pdf(file_path: str, request: Request):
    auth_service.require_current_user(request)
    base_dir = (Path(get_data_dir()) / "pdfs").resolve()
    target_path = (base_dir / file_path).resolve()
    if not str(target_path).startswith(str(base_dir)) or not target_path.is_file():
        raise HTTPException(status_code=404, detail="PDF not found")
    return FileResponse(str(target_path), media_type="application/pdf", filename=target_path.name)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up...")
    auth_service.init_auth_db()
    for user_id in iter_user_ids():
        try:
            ensure_user_database(user_id)
            _prepared_request_users.add(user_id)
            with user_context(user_id):
                db = SessionLocal()
                try:
                    conference_service.ensure_seed_data(db)
                finally:
                    db.close()
        except Exception as e:
            logger.error("Error preparing user database %s: %s", user_id, e)
    recover_stale_auto_research_tasks()
    recover_stale_pack_build_jobs()
    recover_stale_report_jobs()
        
    # Start background processor
    asyncio.create_task(processor_loop())
    asyncio.create_task(auto_research_task_loop())
    asyncio.create_task(pack_build_loop())
    asyncio.create_task(report_generation_loop())

@app.get("/")
async def root():
    return {"message": "Welcome to Paper Reader API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
