from sqlalchemy import (
    Column,
    String,
    Integer,
    DateTime,
    Boolean,
    ForeignKey,
    Text,
    Float,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid
from database import Base


def generate_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=generate_uuid)
    email = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tasks = relationship("Task", back_populates="user")
    templates = relationship("Template", back_populates="user")
    collections = relationship("Collection", back_populates="user")


class Template(Base):
    __tablename__ = "templates"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="templates")
    tasks = relationship("Task", back_populates="template")


class Task(Base):
    __tablename__ = "tasks"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String)
    template_id = Column(String, ForeignKey("templates.id"), nullable=True)
    custom_reading_prompts_json = Column(Text, nullable=True)
    agent_trace_json = Column(Text, nullable=True)
    model_name = Column(String, default="gemini-3-flash-preview")
    status = Column(
        String, default="created"
    )  # created, running, paused, completed, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user = relationship("User", back_populates="tasks")
    template = relationship("Template", back_populates="tasks")
    papers = relationship("Paper", back_populates="task")
    deep_research_report = relationship(
        "DeepResearchReport", back_populates="task", uselist=False
    )


class Paper(Base):
    __tablename__ = "papers"

    id = Column(String, primary_key=True, default=generate_uuid)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False)
    title = Column(String, nullable=False)
    pdf_path = Column(String)
    source = Column(String)  # arxiv, openreview
    source_url = Column(String)
    status = Column(
        String, default="queued"
    )  # queued, processing, done, failed, skipped
    failure_reason = Column(Text)
    # Overrides for re-read functionality
    template_id = Column(String, ForeignKey("templates.id"), nullable=True)
    model_name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    task = relationship("Task", back_populates="papers")
    interpretation = relationship(
        "Interpretation", back_populates="paper", uselist=False
    )
    chat_messages = relationship("ChatMessage", back_populates="paper")
    notes = relationship("Note", back_populates="paper")
    collections = relationship("PaperCollection", back_populates="paper")


class Interpretation(Base):
    __tablename__ = "interpretations"

    id = Column(String, primary_key=True, default=generate_uuid)
    paper_id = Column(String, ForeignKey("papers.id"), nullable=False)
    content = Column(Text, nullable=False)
    template_used = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    paper = relationship("Paper", back_populates="interpretation")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(String, primary_key=True, default=generate_uuid)
    paper_id = Column(String, ForeignKey("papers.id"), nullable=False)
    role = Column(String, nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    cost = Column(Float, default=0.0)
    time_cost = Column(Float, default=0.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    paper = relationship("Paper", back_populates="chat_messages")


class Note(Base):
    __tablename__ = "notes"

    id = Column(String, primary_key=True, default=generate_uuid)
    paper_id = Column(String, ForeignKey("papers.id"), nullable=False)
    content = Column(Text)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    paper = relationship("Paper", back_populates="notes")


class Collection(Base):
    __tablename__ = "collections"

    id = Column(String, primary_key=True, default=generate_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    parent_id = Column(String, ForeignKey("collections.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="collections")
    parent = relationship("Collection", remote_side=[id], backref="children")
    papers = relationship("PaperCollection", back_populates="collection")


class PaperCollection(Base):
    __tablename__ = "paper_collections"

    paper_id = Column(String, ForeignKey("papers.id"), primary_key=True)
    collection_id = Column(String, ForeignKey("collections.id"), primary_key=True)
    added_at = Column(DateTime(timezone=True), server_default=func.now())

    paper = relationship("Paper", back_populates="collections")
    collection = relationship("Collection", back_populates="papers")


class ConferenceSource(Base):
    __tablename__ = "conference_sources"

    id = Column(String, primary_key=True, default=generate_uuid)
    code = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    year = Column(Integer, nullable=False)
    enabled = Column(Boolean, default=True)
    paper_count = Column(Integer, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    papers = relationship("ConferencePaper", back_populates="conference")


class ConferencePaper(Base):
    __tablename__ = "conference_papers"

    id = Column(String, primary_key=True, default=generate_uuid)
    conference_id = Column(String, ForeignKey("conference_sources.id"), nullable=False)
    title = Column(String, nullable=False)
    abstract = Column(Text, nullable=False)
    authors = Column(Text)
    official_url = Column(String)
    openreview_url = Column(String)
    arxiv_id = Column(String)
    arxiv_url = Column(String)
    keywords = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    conference = relationship("ConferenceSource", back_populates="papers")


class DeepResearchReport(Base):
    __tablename__ = "deep_research_reports"

    id = Column(String, primary_key=True, default=generate_uuid)
    task_id = Column(String, ForeignKey("tasks.id"), nullable=False, unique=True)
    query = Column(Text, nullable=True)
    source_type = Column(String, nullable=False, default="task")
    source_meta = Column(Text, nullable=True)
    model_name = Column(String, nullable=True)
    status = Column(String, nullable=False, default="completed")
    progress_stage = Column(String, nullable=True)
    progress_message = Column(Text, nullable=True)
    progress_completed = Column(Integer, nullable=False, default=0)
    progress_total = Column(Integer, nullable=False, default=0)
    error = Column(Text, nullable=True)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    task = relationship("Task", back_populates="deep_research_report")


class PackBuildJob(Base):
    __tablename__ = "pack_build_jobs"

    id = Column(String, primary_key=True, default=generate_uuid)
    status = Column(String, nullable=False, default="queued")
    version = Column(String, nullable=False, default="v1")
    requested_conferences_json = Column(Text, nullable=True)
    requested_years_json = Column(Text, nullable=True)
    total_targets = Column(Integer, nullable=False, default=0)
    completed_targets = Column(Integer, nullable=False, default=0)
    failed_targets = Column(Integer, nullable=False, default=0)
    current_conference = Column(String, nullable=True)
    current_year = Column(Integer, nullable=True)
    current_stage = Column(String, nullable=True)
    current_step_completed = Column(Integer, nullable=False, default=0)
    current_step_total = Column(Integer, nullable=False, default=0)
    progress_message = Column(Text, nullable=True)
    target_states_json = Column(Text, nullable=False, default="[]")
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
