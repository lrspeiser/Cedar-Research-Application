from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    ForeignKey,
    DateTime,
    Boolean,
    UniqueConstraint,
    JSON,
    Index,
)
from sqlalchemy.orm import declarative_base, relationship

# Central declarative base for all ORM models
Base = declarative_base()


class Project(Base):
    __tablename__ = "projects"  # Central registry only
    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    branches = relationship("Branch", back_populates="project", cascade="all, delete-orphan")


class Branch(Base):
    __tablename__ = "branches"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    is_default = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    project = relationship("Project", back_populates="branches")

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_branch_name"),
    )


class Thread(Base):
    __tablename__ = "threads"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    project = relationship("Project")
    branch = relationship("Branch")


class ThreadMessage(Base):
    __tablename__ = "thread_messages"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=False, index=True)
    thread_id = Column(Integer, ForeignKey("threads.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' | 'assistant' | 'system'
    content = Column(Text, nullable=False)
    display_title = Column(String(255))  # short title for the bubble
    payload_json = Column(JSON)          # structured prompt/result payload
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    thread = relationship("Thread")

    __table_args__ = (
        Index("ix_thread_messages_project_thread", "project_id", "thread_id", "created_at"),
    )


class FileEntry(Base):
    __tablename__ = "files"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    filename = Column(String(512), nullable=False)  # storage name on disk
    display_name = Column(String(255), nullable=False)  # original filename
    file_type = Column(String(50))  # e.g., jpg, pdf, json (derived)
    structure = Column(String(50))  # images, sources, code, tabular (LLM-chosen)
    mime_type = Column(String(100))
    size_bytes = Column(Integer)
    storage_path = Column(String(1024))  # absolute/relative path on disk
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    metadata_json = Column(JSON)  # extracted metadata from interpreter
    # AI classification outputs
    ai_title = Column(String(255))
    ai_description = Column(Text)
    ai_category = Column(String(255))
    # Processing flag for UI spinner
    ai_processing = Column(Boolean, default=False)

    project = relationship("Project")
    branch = relationship("Branch")

    __table_args__ = (
        Index("ix_files_project_branch", "project_id", "branch_id"),
    )


class Dataset(Base):
    __tablename__ = "datasets"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    project = relationship("Project")
    branch = relationship("Branch")


class Setting(Base):
    __tablename__ = "settings"
    key = Column(String(255), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class Version(Base):
    __tablename__ = "versions"
    id = Column(Integer, primary_key=True)
    entity_type = Column(String(50), nullable=False)  # "project" | "branch" | "thread" | "file" | etc.
    entity_id = Column(Integer, nullable=False)
    version_num = Column(Integer, nullable=False)
    data = Column(JSON)  # snapshot of entity data (lightweight for now)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "version_num", name="uq_version_key"),
        Index("ix_versions_entity", "entity_type", "entity_id"),
    )


class ChangelogEntry(Base):
    __tablename__ = "changelog_entries"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=False, index=True)
    action = Column(String(255), nullable=False)
    input_json = Column(JSON)    # what we submitted (prompts, commands, SQL, etc.)
    output_json = Column(JSON)   # results (success payloads or errors)
    summary_text = Column(Text)  # LLM-produced human summary (gpt-5-nano)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_changelog_project_branch", "project_id", "branch_id", "created_at"),
    )


class SQLUndoLog(Base):
    __tablename__ = "sql_undo_log"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False)
    branch_id = Column(Integer, nullable=False)
    table_name = Column(String(255), nullable=False)
    op = Column(String(20), nullable=False)  # insert | update | delete
    sql_text = Column(Text)
    pk_columns = Column(JSON)  # list of PK column names
    rows_before = Column(JSON)  # list of row dicts
    rows_after = Column(JSON)   # list of row dicts
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_undo_project_branch", "project_id", "branch_id", "created_at"),
    )


class Note(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, nullable=False, index=True)
    branch_id = Column(Integer, nullable=False, index=True)
    content = Column(Text, nullable=False)
    tags = Column(JSON)  # optional list of strings
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_notes_project_branch", "project_id", "branch_id", "created_at"),
    )
