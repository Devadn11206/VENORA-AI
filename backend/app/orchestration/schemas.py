"""Strongly typed Pydantic schemas for Phase 4 Task Orchestration, Structured Plans, and Execution."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.desktop.schemas import VerificationStatus
from app.models.task import TaskPriority, TaskStatus
from app.models.task_step import StepStatus


class PlanStatus(str, Enum):
    """Lifecycle states of a structured task plan."""
    DRAFT = "draft"
    VALIDATED = "validated"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepPlan(BaseModel):
    """Schema for a single planned step within a structured task plan."""
    step_id: str = Field(..., min_length=1, max_length=50, description="Unique identifier for step within plan")
    sequence_number: int = Field(..., ge=1, le=100, description="1-based execution order index")
    description: str = Field(..., min_length=1, max_length=255, description="Clear description of step action")
    action_type: str = Field(default="tool_call", description="Action classifier (e.g. tool_call, verification)")
    tool_name: Optional[str] = Field(default=None, description="Registered tool name to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Validated arguments payload for tool")
    dependencies: List[str] = Field(default_factory=list, description="List of step_ids that must succeed before this step")
    required_permissions: List[str] = Field(default_factory=list, description="Required permissions for execution")
    approval_required: bool = Field(default=False, description="Whether explicit user confirmation is needed")
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0, description="Step execution timeout limit")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Initial step state")


class TaskPlan(BaseModel):
    """Schema representing a complete, validated task plan."""
    plan_id: str
    task_id: int
    user_goal: str
    summary: str
    created_at: datetime
    execution_mode: str = Field(default="sequential", description="Execution concurrency model")
    steps: List[StepPlan] = Field(..., min_length=1, max_length=10, description="Ordered execution steps")
    execution_limits: Dict[str, Any] = Field(default_factory=dict, description="Configured bounds and constraints")
    plan_status: PlanStatus = Field(default=PlanStatus.VALIDATED, description="Plan approval status")

    model_config = ConfigDict(from_attributes=True)


class CreateTaskPlanRequest(BaseModel):
    """API payload for creating an orchestrated task from a user goal."""
    goal: str = Field(..., min_length=1, max_length=2000, description="Natural language user goal or instruction")
    priority: TaskPriority = Field(default=TaskPriority.NORMAL, description="Task execution priority")
    auto_execute: bool = Field(default=False, description="Whether to automatically run if no approval is required")


class StepResponse(BaseModel):
    """Schema for serialized step details in API responses."""
    step_id: str
    sequence_number: int
    description: str
    action_type: str
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    required_permissions: List[str] = Field(default_factory=list)
    approval_required: bool
    timeout_seconds: float
    status: StepStatus
    attempt_count: int
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    verification_status: VerificationStatus

    model_config = ConfigDict(from_attributes=True)


class OrchestratedTaskResponse(BaseModel):
    """Detailed response for an orchestrated task including plan, steps, and progress."""
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
    plan_summary: Optional[str] = None
    current_step_id: Optional[str] = None
    cancellation_requested: bool = False
    
    # Progress fields
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    skipped_steps: int = 0
    progress_percentage: float = 0.0

    steps: List[StepResponse] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class TaskEventResponse(BaseModel):
    """Lifecycle audit event record for a task."""
    id: int
    task_id: int
    event_type: str
    level: str
    message: str
    created_at: datetime
    metadata: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class TaskApprovalRequest(BaseModel):
    """Approval or denial decision payload."""
    decision_reason: Optional[str] = Field(default=None, max_length=500, description="Optional explanation for decision")
