"""Tests for database layer, models, relationships, and transaction isolation."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.base import utc_now
from app.models.task import Task, TaskStatus, TaskPriority
from app.models.session import Session as AppSession, SessionType, SessionStatus
from app.models.execution_log import ExecutionLog, LogLevel


def test_task_model_crud(db_session: Session):
    """Test creating, reading, updating, and querying a Task record."""
    task = Task(
        title="Initial Research Task",
        description="Verify local environment architecture",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)

    assert task.id is not None
    assert task.title == "Initial Research Task"
    assert task.status == TaskStatus.PENDING
    assert task.priority == TaskPriority.HIGH
    assert task.created_at is not None
    assert task.updated_at is not None

    # Retrieve from DB
    retrieved = db_session.execute(select(Task).where(Task.id == task.id)).scalar_one()
    assert retrieved.id == task.id
    assert retrieved.description == "Verify local environment architecture"


def test_session_model_crud(db_session: Session):
    """Test creating and managing application interaction sessions."""
    app_session = AppSession(
        session_type=SessionType.CLI,
        status=SessionStatus.ACTIVE,
        metadata_json='{"client": "powershell", "pid": 1234}'
    )
    db_session.add(app_session)
    db_session.commit()
    db_session.refresh(app_session)

    assert app_session.id is not None
    assert app_session.session_type == SessionType.CLI
    assert app_session.status == SessionStatus.ACTIVE
    assert "powershell" in app_session.metadata_json

    # Update session to terminated
    app_session.status = SessionStatus.TERMINATED
    db_session.commit()
    db_session.refresh(app_session)
    assert app_session.status == SessionStatus.TERMINATED


def test_execution_log_with_task_relationship(db_session: Session):
    """Test ExecutionLog model foreign key link and relationship to Task."""
    task = Task(
        title="Execution Logging Test",
        status=TaskStatus.PLANNING,
        priority=TaskPriority.NORMAL,
    )
    db_session.add(task)
    db_session.commit()

    log_entry = ExecutionLog(
        task_id=task.id,
        event_type="plan_generated",
        level=LogLevel.INFO,
        message="Decomposed goal into 3 subtasks",
        metadata_json='{"subtask_count": 3}'
    )
    db_session.add(log_entry)
    db_session.commit()
    db_session.refresh(task)

    assert len(task.execution_logs) == 1
    assert task.execution_logs[0].event_type == "plan_generated"
    assert task.execution_logs[0].task_id == task.id


def test_database_isolation_between_tests(db_session: Session):
    """Test that in-memory database is clean and isolated per test."""
    tasks = db_session.execute(select(Task)).scalars().all()
    # Should be empty because setup_test_database fixture cleans tables between tests
    assert len(tasks) == 0
