"""Task planner producing structured, validated execution plans using Phase 3 AI Provider and Tool Registry."""

import json
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from pydantic import ValidationError

from app.ai.prompts import VENORA_SYSTEM_INSTRUCTIONS
from app.ai.provider import BaseAIProvider
from app.ai.schemas import ChatMessage, MessageRole
from app.ai.tools import create_default_tool_registry
from app.ai.tools.registry import ToolRegistry
from app.core.config import Settings, get_settings
from app.core.errors import PlanValidationError, StepDependencyError
from app.models.task_step import StepStatus
from app.orchestration.schemas import PlanStatus, StepPlan, TaskPlan

logger = logging.getLogger("venora.orchestration.planner")

PLANNER_SYSTEM_INSTRUCTION = """You are VENORA AI's Task Planner.
Your role is to analyze a user goal and decompose it into a sequential list of steps using ONLY authorized tools.

AVAILABLE TOOLS AND PERMITTED ROLES:
{tool_descriptions}

CRITICAL RULES FOR PLANNING:
1. Output MUST be a valid JSON object matching this schema:
   {{
     "summary": "High level summary of the plan",
     "steps": [
       {{
         "step_id": "step_1",
         "sequence_number": 1,
         "description": "Clear action description",
         "action_type": "tool_call",
         "tool_name": "exact_registered_tool_name",
         "arguments": {{ "param_key": "param_value" }},
         "dependencies": [],
         "approval_required": false,
         "timeout_seconds": 30.0
       }}
     ]
   }}
2. Tool Names: Use ONLY tools that exist in the provided list. Do NOT invent tool names.
3. Arguments: Ensure all arguments strictly adhere to tool parameter specifications.
4. Security: Never generate arbitrary shell commands, scripts, or unauthorized paths.
5. Step dependencies: steps can only depend on earlier sequence steps (no cycles, no forward dependencies).
6. Return purely raw JSON without markdown formatting or code fences.
"""


class TaskPlanner:
    """Decomposes natural-language user goals into validated, structured task plans."""

    def __init__(
        self,
        provider: Optional[BaseAIProvider] = None,
        tool_registry: Optional[ToolRegistry] = None,
        settings: Optional[Settings] = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.provider = provider
        self.tool_registry = tool_registry or create_default_tool_registry(settings=self.settings)

    def validate_plan_structure(self, steps: List[StepPlan]) -> None:
        """Validate step order, uniqueness, dependencies, cycle freedom, and registered tool arguments."""
        if not steps:
            raise PlanValidationError("Task plan must contain at least one step.")

        if len(steps) > self.settings.MAX_PLAN_STEPS:
            raise PlanValidationError(
                f"Plan step count ({len(steps)}) exceeds maximum allowed ({self.settings.MAX_PLAN_STEPS})."
            )

        seen_step_ids: Set[str] = set()
        seen_seq_nums: Set[int] = set()

        for step in steps:
            # Step ID uniqueness
            if step.step_id in seen_step_ids:
                raise PlanValidationError(f"Duplicate step_id '{step.step_id}' found in plan.")
            seen_step_ids.add(step.step_id)

            # Sequence number validation
            if step.sequence_number in seen_seq_nums:
                raise PlanValidationError(f"Duplicate sequence_number '{step.sequence_number}' found in plan.")
            seen_seq_nums.add(step.sequence_number)

            # Self dependency check
            if step.step_id in step.dependencies:
                raise StepDependencyError(f"Step '{step.step_id}' cannot depend on itself.")

            # Forward or non-existent dependency check
            for dep in step.dependencies:
                if dep not in seen_step_ids:
                    raise StepDependencyError(
                        f"Step '{step.step_id}' depends on step '{dep}', which does not exist prior to this step."
                    )

            # Tool existence and argument validation
            if step.tool_name:
                if not self.tool_registry.has_tool(step.tool_name):
                    raise PlanValidationError(f"Step '{step.step_id}' requests unknown tool '{step.tool_name}'.")

                tool = self.tool_registry.get_tool(step.tool_name)
                # Populate permissions automatically from registered tool definition
                if tool.required_permission and tool.required_permission not in step.required_permissions:
                    step.required_permissions.append(tool.required_permission)

                # Validate arguments against Pydantic args schema
                try:
                    self.tool_registry.validate_arguments(step.tool_name, step.arguments)
                except Exception as exc:
                    raise PlanValidationError(
                        f"Step '{step.step_id}' has invalid arguments for tool '{step.tool_name}': {exc}"
                    )

    async def plan(self, task_id: int, user_goal: str) -> TaskPlan:
        """Generate structured plan from user goal using AI provider, or rule-based fallback."""
        clean_goal = user_goal.strip()
        if not clean_goal:
            raise PlanValidationError("User goal cannot be empty.")

        # If provider is configured, use LLM planning
        if self.provider and self.provider.is_configured():
            try:
                plan_obj = await self._plan_with_llm(task_id, clean_goal)
                self.validate_plan_structure(plan_obj.steps)
                return plan_obj
            except Exception as exc:
                logger.warning(f"LLM planning failed or invalid: {exc}. Falling back to heuristic planning.")

        # Deterministic heuristic fallback planner
        return self._plan_heuristic(task_id, clean_goal)

    async def _plan_with_llm(self, task_id: int, user_goal: str) -> TaskPlan:
        """Prompt LLM provider to produce structured plan JSON."""
        tool_defs = self.tool_registry.get_tool_definitions()
        descriptions_str = json.dumps([t["function"] for t in tool_defs], indent=2)

        sys_prompt = PLANNER_SYSTEM_INSTRUCTION.format(tool_descriptions=descriptions_str)
        messages = [
            ChatMessage(
                role=MessageRole.USER,
                content=f"Create an execution plan for this goal: {user_goal}",
            )
        ]

        resp = await self.provider.generate_response(
            messages=messages,
            system_instruction=sys_prompt,
        )

        content = (resp.message or "").strip()
        # Strip potential markdown formatting
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()

        data = json.loads(content)
        raw_steps = data.get("steps", [])
        parsed_steps: List[StepPlan] = []

        for idx, s in enumerate(raw_steps, start=1):
            parsed_steps.append(
                StepPlan(
                    step_id=s.get("step_id") or f"step_{idx}",
                    sequence_number=s.get("sequence_number") or idx,
                    description=s.get("description") or f"Execute action {idx}",
                    action_type=s.get("action_type") or "tool_call",
                    tool_name=s.get("tool_name"),
                    arguments=s.get("arguments") or {},
                    dependencies=s.get("dependencies") or [],
                    required_permissions=s.get("required_permissions") or [],
                    approval_required=s.get("approval_required") or False,
                    timeout_seconds=float(s.get("timeout_seconds") or 30.0),
                    status=StepStatus.PENDING,
                )
            )

        return TaskPlan(
            plan_id=f"plan_{secrets.token_hex(6)}",
            task_id=task_id,
            user_goal=user_goal,
            summary=data.get("summary") or f"Plan for: {user_goal}",
            created_at=datetime.now(timezone.utc),
            execution_mode="sequential",
            steps=parsed_steps,
            execution_limits={
                "max_steps": self.settings.MAX_PLAN_STEPS,
                "timeout_seconds": self.settings.MAX_TASK_DURATION_SECONDS,
            },
            plan_status=PlanStatus.VALIDATED,
        )

    def _plan_heuristic(self, task_id: int, user_goal: str) -> TaskPlan:
        """Deterministic heuristic fallback when LLM is unavailable or for offline tasks."""
        goal_lower = user_goal.lower()
        steps: List[StepPlan] = []
        seq = 1

        # Check for multiple application launches in goal
        app_candidates = ["notepad", "calc", "cmd", "explorer"]
        found_apps = [app for app in app_candidates if app in goal_lower or (app == "calc" and "calculator" in goal_lower)]

        if found_apps:
            for app in found_apps:
                steps.append(
                    StepPlan(
                        step_id=f"step_launch_{app}",
                        sequence_number=seq,
                        description=f"Launch application '{app}'",
                        action_type="tool_call",
                        tool_name="launch_application",
                        arguments={"app_id": app},
                        dependencies=[f"step_launch_{found_apps[idx-1]}" for idx in range(1, len(steps)+1)][:1] if steps else [],
                        required_permissions=["desktop.applications.launch"],
                        timeout_seconds=15.0,
                    )
                )
                seq += 1
        elif "document" in goal_lower or "files" in goal_lower or "search" in goal_lower:
            if "search" in goal_lower:
                steps.append(
                    StepPlan(
                        step_id="step_search_documents",
                        sequence_number=1,
                        description="Search indexed documents",
                        action_type="tool_call",
                        tool_name="search_documents",
                        arguments={"query": user_goal},
                        dependencies=[],
                        required_permissions=["document.search"],
                        timeout_seconds=15.0,
                    )
                )
            else:
                steps.append(
                    StepPlan(
                        step_id="step_list_documents",
                        sequence_number=1,
                        description="List authorized documents",
                        action_type="tool_call",
                        tool_name="list_authorized_documents",
                        arguments={},
                        dependencies=[],
                        required_permissions=["document.read"],
                        timeout_seconds=15.0,
                    )
                )
        elif "list" in goal_lower or "what" in goal_lower:
            steps.append(
                StepPlan(
                    step_id="step_list_apps",
                    sequence_number=1,
                    description="List approved applications",
                    action_type="tool_call",
                    tool_name="list_applications",
                    arguments={},
                    dependencies=[],
                    required_permissions=["desktop.applications.list"],
                    timeout_seconds=10.0,
                )
            )
        else:
            # Default single capability check
            steps.append(
                StepPlan(
                    step_id="step_check_capabilities",
                    sequence_number=1,
                    description="Inspect desktop subsystem capabilities",
                    action_type="tool_call",
                    tool_name="desktop_capabilities",
                    arguments={},
                    dependencies=[],
                    required_permissions=["desktop.capabilities.read"],
                    timeout_seconds=10.0,
                )
            )

        self.validate_plan_structure(steps)

        return TaskPlan(
            plan_id=f"plan_{secrets.token_hex(6)}",
            task_id=task_id,
            user_goal=user_goal,
            summary=f"Automated execution plan for: {user_goal}",
            created_at=datetime.now(timezone.utc),
            execution_mode="sequential",
            steps=steps,
            execution_limits={
                "max_steps": self.settings.MAX_PLAN_STEPS,
                "timeout_seconds": self.settings.MAX_TASK_DURATION_SECONDS,
            },
            plan_status=PlanStatus.VALIDATED,
        )
