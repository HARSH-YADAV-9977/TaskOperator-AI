"""
Data models and schemas for TaskOperator-AI
"""
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class StepStatus(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERED = "RECOVERED"


class AgentStep(BaseModel):
    step_id: int
    title: str
    tool_name: str
    tool_args: Dict[str, Any] = Field(default_factory=dict)
    status: StepStatus = StepStatus.PENDING
    observation: Optional[str] = None
    output_data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    recovery_attempts: int = 0
    requires_approval: bool = False


class TaskPlan(BaseModel):
    goal: str
    steps: List[AgentStep]
    created_at: str


class ExecutionState(BaseModel):
    task_id: str
    goal: str
    plan: Optional[TaskPlan] = None
    current_step_index: int = 0
    context_memory: Dict[str, Any] = Field(default_factory=dict)
    logs: List[str] = Field(default_factory=list)
    is_completed: bool = False
    is_failed: bool = False
    waiting_for_approval: bool = False
    approval_prompt: Optional[str] = None
    verification_result: Optional[Dict[str, Any]] = None
