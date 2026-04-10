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
    2. Updates legacy absolute PDF paths to relative paths.
    3. Verifies critical schema integrity.
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
                
            conn.commit()
            
    logger.info("Database check completed.")

