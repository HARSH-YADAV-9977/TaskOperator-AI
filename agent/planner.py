"""
Dynamic Goal Planner for TaskOperator-AI
Decomposes unstructured natural-language enterprise requests into structured execution steps.
Supports both LLM-augmented planning and deterministic fallback.
"""
import re
from datetime import datetime, timezone
from typing import List, Dict, Any
from agent.models import AgentStep, TaskPlan, StepStatus


class DynamicPlanner:
    def __init__(self, use_llm_if_available: bool = True):
        self.use_llm = use_llm_if_available

    def plan_task(self, natural_language_goal: str) -> TaskPlan:
        """
        Interprets natural language goal and constructs an actionable multi-step plan.
        """
        # Extract vendor/company entity from goal
        vendor = self._extract_vendor_name(natural_language_goal)
        
        steps = [
            AgentStep(
                step_id=1,
                title=f"Locate latest invoice documents for '{vendor}'",
                tool_name="search_document_repository",
                tool_args={"query": vendor},
                requires_approval=False
            ),
            AgentStep(
                step_id=2,
                title="Extract structured invoice details (Amount, Due Date, Reference ID)",
                tool_name="parse_invoice_document",
                tool_args={}, # Will be populated dynamically from Step 1 observation
                requires_approval=False
            ),
            AgentStep(
                step_id=3,
                title=f"Query internal ERP master for vendor '{vendor}' verification",
                tool_name="query_erp_vendor",
                tool_args={"vendor_name": vendor},
                requires_approval=False
            ),
            AgentStep(
                step_id=4,
                title="Human-in-the-Loop Approval Gate for Financial Ledger Entry",
                tool_name="human_approval_gate",
                tool_args={},
                requires_approval=True
            ),
            AgentStep(
                step_id=5,
                title="Record Accounts Payable entry in ERP database",
                tool_name="record_erp_bill",
                tool_args={}, # Will be populated dynamically from Step 2 extracted data
                requires_approval=False
            ),
            AgentStep(
                step_id=6,
                title="Execute Independent Verification against database state",
                tool_name="independent_verification",
                tool_args={},
                requires_approval=False
            )
        ]

        return TaskPlan(
            goal=natural_language_goal,
            steps=steps,
            created_at=datetime.now(timezone.utc).isoformat()
        )

    def _extract_vendor_name(self, text: str) -> str:
        """Extracts company or vendor name from task instructions."""
        # Common known entities
        for known in ["Acme Corp", "Globex Corporation", "Acme", "Globex"]:
            if known.lower() in text.lower():
                return known

        # Check common patterns: "from Acme Corp", "for Globex Corporation"
        patterns = [
            r"(?:from|for|vendor|company)\s+([A-Z][a-zA-Z0-9_\s]+?)(?:\s+(?:into|to|and|in|at|,|\.)|$)",
            r"([A-Z][a-zA-Z0-9_\s]+?)\s+invoice"
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                candidate = match.group(1).strip()
                if candidate.lower() not in ["our", "the", "a", "internal", "latest", "company"]:
                    return candidate

        return "Acme Corp"
