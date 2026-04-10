from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import asyncio
import logging
import json
from dotenv import load_dotenv

load_dotenv()

from fastapi.staticfiles import StaticFiles
from database import engine, Base, SessionLocal, DATA_DIR, check_and_migrate_database
import models
from routers import templates, tasks, papers, collections, research, deep_research
from processor import processor_loop
from services import conference_service

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create tables
models.Base.metadata.create_all(bind=engine)

# Perform backward compatibility migrations
try:
    check_and_migrate_database()
except Exception as e:
    logger.error(f"Database migration failed: {e}")
    # We might want to stop startup if DB is critical mismatch
    # but for now we log it. In production, we should probably exit.
    pass

app = FastAPI(title="Paper Reader API", version="1.0.0")

# CORS configuration
origins = [
    "http://localhost:5173",  # Vite default port
    "http://127.0.0.1:5173",
    "*", # Allow extensions and other origins
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for local tool convenience
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount PDF storage
# Ensure pdf directory exists
os.makedirs(os.path.join(DATA_DIR, "pdfs"), exist_ok=True)
app.mount("/api/pdfs", StaticFiles(directory=os.path.join(DATA_DIR, "pdfs")), name="pdfs")

# Include routers
app.include_router(templates.router)
app.include_router(tasks.router)
app.include_router(papers.router)
app.include_router(collections.router)
app.include_router(research.router)
app.include_router(deep_research.router)

@app.on_event("startup")
async def startup_event():
    logger.info("Starting up...")
    
    # Create default user if not exists
    db = SessionLocal()
    try:
        from routers.tasks import DEFAULT_USER_ID
        user = db.query(models.User).filter(models.User.id == DEFAULT_USER_ID).first()
        if not user:
            logger.info("Creating default user")
            user = models.User(id=DEFAULT_USER_ID, email="user@example.com", name="Default User")
            db.add(user)
            db.commit()

        default_template = db.query(models.Template).filter(
            models.Template.user_id == DEFAULT_USER_ID,
            models.Template.is_default == True,
        ).first()
        if not default_template:
            logger.info("Creating default template")
            template = models.Template(
                user_id=DEFAULT_USER_ID,
                name="Default Paper Summary",
                content=json.dumps([
                    "Summarize the paper's main contribution, technical method, experimental evidence, limitations, and the most important safety implications."
                ]),
                is_default=True,
            )
            db.add(template)
            db.commit()

        conference_service.ensure_seed_data(db)
    except Exception as e:
        logger.error(f"Error creating default user: {e}")
    finally:
        db.close()
        
    # Start background processor
    asyncio.create_task(processor_loop())

@app.get("/")
async def root():
    return {"message": "Welcome to Paper Reader API"}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
