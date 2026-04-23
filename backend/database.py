from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
import logging

logger = logging.getLogger(__name__)

# Database path from architecture doc
# e:\Project\paperreader\code2\gui2\data\app.db
# We need to make sure the directory exists.
# We will use an absolute path for simplicity and robustness.

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "app.db")
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_PATH}"

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_and_migrate_database():
    """
    Checks database schema and performs auto-migrations for backward compatibility.
    1. Adds missing columns (template_id, model_name) to papers table.
    2. Adds missing task-level custom reading prompts and agent trace columns.
    3. Updates legacy absolute PDF paths to relative paths.
    4. Adds missing deep-research report progress columns.
    5. Drops deprecated legacy research tables that are no longer part of the app schema.
    6. Verifies critical schema integrity.
    """
    logger.info("Checking database schema...")
    inspector = inspect(engine)
    
    # 1. Check 'papers' table schema
    if inspector.has_table("papers"):
        existing_columns = {c["name"] for c in inspector.get_columns("papers")}
        
        # Expected critical columns (must exist or be auto-migratable)
        # Based on models.py Paper class
        expected_columns = {
            "id", "task_id", "title", "pdf_path", "source", "source_url", 
            "status", "failure_reason", "created_at", 
            "template_id", "model_name" # These are auto-migratable
        }
        
        missing_columns = expected_columns - existing_columns
        auto_migratable = {"template_id", "model_name"}
        
        # Check for critical missing columns that we cannot auto-fix
        critical_missing = missing_columns - auto_migratable
        if critical_missing:
            error_msg = f"Database schema mismatch: Table 'papers' is missing critical columns: {critical_missing}. Please check your database version."
            logger.error(error_msg)
            raise Exception(error_msg)
            
        # Perform auto-migration for allowable columns
        with engine.connect() as conn:
            if "template_id" in missing_columns:
                logger.info("Migrating: Adding template_id to papers table")
                conn.execute(text("ALTER TABLE papers ADD COLUMN template_id VARCHAR"))
                
            if "model_name" in missing_columns:
                logger.info("Migrating: Adding model_name to papers table")
                conn.execute(text("ALTER TABLE papers ADD COLUMN model_name VARCHAR"))
            
            # 2. Data Migration: Fix PDF paths (Absolute -> Relative)
            # Check for legacy absolute paths (containing ':' for Windows drive or starting with '/')
            # And standardize them to 'pdfs/{task_id}/{id}.pdf'
            logger.info("Checking for legacy absolute PDF paths...")
            
            # Count affected rows first
            result = conn.execute(text("""
                SELECT COUNT(*) FROM papers 
                WHERE task_id IS NOT NULL 
                AND (pdf_path LIKE '%:%' OR pdf_path LIKE '/%')
            """))
            count = result.scalar()
            
            if count > 0:
                logger.info(f"Found {count} papers with legacy paths. Migrating to relative format...")
                conn.execute(text("""
                    UPDATE papers 
                    SET pdf_path = 'pdfs/' || task_id || '/' || id || '.pdf'
                    WHERE task_id IS NOT NULL 
                    AND (pdf_path LIKE '%:%' OR pdf_path LIKE '/%')
                """))
                conn.commit()
                logger.info("PDF path migration completed.")
            else:
                logger.info("No legacy PDF paths found.")

            deprecated_tables = [
                "research_paper_candidates",
                "research_jobs",
            ]
            for table_name in deprecated_tables:
                logger.info("Migrating: Dropping deprecated table if it exists: %s", table_name)
                conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))

            conn.commit()

    if inspector.has_table("tasks"):
        with engine.connect() as conn:
            task_columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(tasks)")).fetchall()
            }
            if "custom_reading_prompts_json" not in task_columns:
                logger.info("Migrating: Adding custom_reading_prompts_json to tasks table")
                conn.execute(text("ALTER TABLE tasks ADD COLUMN custom_reading_prompts_json TEXT"))
                conn.commit()
            if "agent_trace_json" not in task_columns:
                logger.info("Migrating: Adding agent_trace_json to tasks table")
                conn.execute(text("ALTER TABLE tasks ADD COLUMN agent_trace_json TEXT"))
                conn.commit()

    if inspector.has_table("deep_research_reports"):
        with engine.connect() as conn:
            report_columns = {
                row[1]
                for row in conn.execute(text("PRAGMA table_info(deep_research_reports)")).fetchall()
            }
            if "model_name" not in report_columns:
                logger.info("Migrating: Adding model_name to deep_research_reports table")
                conn.execute(text("ALTER TABLE deep_research_reports ADD COLUMN model_name VARCHAR"))
                conn.commit()
            if "progress_stage" not in report_columns:
                logger.info("Migrating: Adding progress_stage to deep_research_reports table")
                conn.execute(text("ALTER TABLE deep_research_reports ADD COLUMN progress_stage VARCHAR"))
                conn.commit()
            if "progress_message" not in report_columns:
                logger.info("Migrating: Adding progress_message to deep_research_reports table")
                conn.execute(text("ALTER TABLE deep_research_reports ADD COLUMN progress_message TEXT"))
                conn.commit()
            if "progress_completed" not in report_columns:
                logger.info("Migrating: Adding progress_completed to deep_research_reports table")
                conn.execute(text("ALTER TABLE deep_research_reports ADD COLUMN progress_completed INTEGER NOT NULL DEFAULT 0"))
                conn.commit()
            if "progress_total" not in report_columns:
                logger.info("Migrating: Adding progress_total to deep_research_reports table")
                conn.execute(text("ALTER TABLE deep_research_reports ADD COLUMN progress_total INTEGER NOT NULL DEFAULT 0"))
                conn.commit()
            if "error" not in report_columns:
                logger.info("Migrating: Adding error to deep_research_reports table")
                conn.execute(text("ALTER TABLE deep_research_reports ADD COLUMN error TEXT"))
                conn.commit()
            
    logger.info("Database check completed.")

