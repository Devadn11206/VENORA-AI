"""Pydantic schemas for Task validation, serialization, and API responses."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskPriority, TaskStatus


class TaskBase(BaseModel):
    """Base schema for task properties."""
    title: str = Field(..., min_length=1, max_length=255, description="Brief title of the task")
    description: Optional[str] = Field(default=None, description="Detailed explanation or context")
    priority: TaskPriority = Field(default=TaskPriority.NORMAL, description="Execution priority")


class TaskCreate(TaskBase):
    """Schema for creating a new task."""
    pass


class TaskUpdate(BaseModel):
    """Schema for updating permitted task fields."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=255, description="Updated task title")
    description: Optional[str] = Field(default=None, description="Updated task description")
    priority: Optional[TaskPriority] = Field(default=None, description="Updated task priority")
    status: Optional[TaskStatus] = Field(default=None, description="Target task status")


class TaskResponse(BaseModel):
    """Schema for serialized task response."""
    id: int
    title: str
    description: Optional[str] = None
    status: TaskStatus
    priority: TaskPriority
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PaginatedTasksResponse(BaseModel):
    """Paginated list response schema for tasks."""
    items: List[TaskResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
