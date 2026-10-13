"""
Autonomous Task Operator Core
Orchestrates the entire Goal -> Plan -> Execute -> Observe -> Adapt -> Verify loop.
"""
import uuid
import json
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from agent.models import ExecutionState, StepStatus, AgentStep
from agent.planner import DynamicPlanner
from agent.tools import ToolRegistry
from agent.verifier import IndependentVerifier
from agent.recovery import FailureRecoveryEngine
from sandbox.erp_system import EnterpriseERPSystem


class AutonomousOperator:
    def __init__(self, erp_system: Optional[EnterpriseERPSystem] = None):
        self.erp = erp_system or EnterpriseERPSystem()
        self.planner = DynamicPlanner()
        self.tools = ToolRegistry(self.erp)
        self.verifier = IndependentVerifier(self.erp)
        self.recovery = FailureRecoveryEngine()
        self.state: Optional[ExecutionState] = None

    def initialize_task(self, natural_language_goal: str) -> ExecutionState:
        """Initializes a new autonomous task and plans steps."""
        task_id = f"TASK-{uuid.uuid4().hex[:8].upper()}"
        plan = self.planner.plan_task(natural_language_goal)
        
        now_str = datetime.now(timezone.utc).strftime('%H:%M:%S')
        self.state = ExecutionState(
            task_id=task_id,
            goal=natural_language_goal,
            plan=plan,
            current_step_index=0,
            context_memory={"vendor_hint": self.planner._extract_vendor_name(natural_language_goal)},
            logs=[f"[{now_str}] Task initialized: '{natural_language_goal}'",
                  f"[{now_str}] Plan generated: {len(plan.steps)} steps planned."]
        )
        return self.state

    def step(self, auto_approve: bool = False) -> Dict[str, Any]:
        """
        Executes a single step in the plan.
        Supports step-by-step execution, pauses for human approval if required.
        """
        if not self.state or not self.state.plan:
            raise ValueError("Task has not been initialized.")

        if self.state.is_completed:
            return {"status": "ALREADY_COMPLETED", "state": self.state}

        if self.state.current_step_index >= len(self.state.plan.steps):
            self.state.is_completed = True
            return {"status": "COMPLETED", "state": self.state}

        step: AgentStep = self.state.plan.steps[self.state.current_step_index]

        # Check Human Approval Gate
        if step.requires_approval and not auto_approve:
            if not self.state.waiting_for_approval:
                extracted = self.state.context_memory.get("extracted_invoice", {})
                prompt_msg = (
                    f"APPROVE FINANCIAL RECORDING? "
                    f"Vendor: {extracted.get('vendor_name', 'Unknown')}, "
                    f"Invoice: {extracted.get('invoice_number', 'N/A')}, "
                    f"Amount: {extracted.get('currency', 'USD')} {extracted.get('amount', '0.00')}, "
                    f"Due: {extracted.get('due_date', 'N/A')}"
                )
                self.state.waiting_for_approval = True
                self.state.approval_prompt = prompt_msg
                step.status = StepStatus.REQUIRES_APPROVAL
                self._log(f"Paused at Step {step.step_id}: Awaiting human operator approval.")
                return {"status": "AWAITING_APPROVAL", "prompt": prompt_msg, "step": step}

        step.status = StepStatus.IN_PROGRESS
        self._log(f"Executing Step {step.step_id}: {step.title} using tool '{step.tool_name}'")

        try:
            # 1. Execute Tool
            tool_result = self._execute_tool(step)
            
            # 2. Check for tool failure and attempt recovery
            if not tool_result.get("success", True):
                error_msg = tool_result.get("error") or tool_result.get("message", "Tool execution failed")
                can_recover, recovery_desc, revised_args = self.recovery.attempt_recovery(
                    step.tool_name, error_msg, self.state.context_memory
                )
                if can_recover:
                    step.recovery_attempts += 1
                    self._log(f"Recovery Triggered on Step {step.step_id}: {recovery_desc}")
                    # Re-attempt with revised arguments
                    if revised_args:
                        step.tool_args.update(revised_args)
                    tool_result = self._execute_tool(step)

                    # Verify whether re-attempt actually succeeded
                    if tool_result.get("success", False):
                        step.status = StepStatus.RECOVERED
                        self._log(f"Step {step.step_id} recovered successfully.")
                    else:
                        failed_msg = tool_result.get("error") or tool_result.get("message", "Recovery re-attempt failed")
                        step.status = StepStatus.FAILED
                        step.error_message = failed_msg
                        self.state.is_failed = True
                        step.observation = f"Recovery failed: {failed_msg}"
                        self._log(f"Step {step.step_id} recovery failed: {failed_msg}")
                        return {"status": "FAILED", "error": failed_msg}
                else:
                    step.status = StepStatus.FAILED
                    step.error_message = error_msg
                    self.state.is_failed = True
                    step.observation = f"Execution failed: {error_msg}"
                    self._log(f"Step {step.step_id} failed: {error_msg}")
                    return {"status": "FAILED", "error": error_msg}

            # 3. Step Succeeded - Update Observation and Memory
            step.status = StepStatus.COMPLETED if step.status != StepStatus.RECOVERED else StepStatus.RECOVERED
            step.output_data = tool_result
            step.observation = self._format_observation(step.tool_name, tool_result)
            self._log(f"Step {step.step_id} completed. Observation: {step.observation}")

            # Advance to next step
            self.state.current_step_index += 1
            if self.state.current_step_index >= len(self.state.plan.steps):
                self.state.is_completed = True
                self._log("All plan steps completed successfully.")

            return {"status": "STEP_COMPLETED", "step": step, "is_finished": self.state.is_completed}

        except Exception as ex:
            step.status = StepStatus.FAILED
            step.error_message = str(ex)
            self.state.is_failed = True
            self._log(f"Unhandled error in Step {step.step_id}: {str(ex)}")
            return {"status": "ERROR", "error": str(ex)}

    def submit_human_approval(self, approved: bool) -> Dict[str, Any]:
        """Provides human response to approval gate."""
        if not self.state or not self.state.waiting_for_approval:
            return {"success": False, "message": "No step currently awaiting approval."}

        self.state.waiting_for_approval = False
        step = self.state.plan.steps[self.state.current_step_index]

        if approved:
            self._log("Human operator APPROVED action. Proceeding to ledger write.")
            step.requires_approval = False
            return self.step()
        else:
            self._log("Human operator REJECTED action. Task aborted safely.")
            step.status = StepStatus.FAILED
            step.error_message = "Rejected by human supervisor."
            self.state.is_failed = True
            return {"status": "REJECTED_BY_USER"}

    def run_to_completion(self, auto_approve: bool = False, max_steps: int = 10) -> ExecutionState:
        """Executes full autonomous loop until completion or human approval is needed."""
        steps_taken = 0
        while not self.state.is_completed and not self.state.is_failed and steps_taken < max_steps:
            res = self.step(auto_approve=auto_approve)
            if res.get("status") == "AWAITING_APPROVAL":
                break
            steps_taken += 1
        return self.state

    def _execute_tool(self, step: AgentStep) -> Dict[str, Any]:
        """Dispatches tool call based on step definition and context memory."""
        name = step.tool_name

        if name == "search_document_repository":
            query = step.tool_args.get("query") or self.state.context_memory.get("vendor_hint", "")
            res = self.tools.search_document_repository(query)
            if res.get("success") and res.get("selected_latest"):
                self.state.context_memory["latest_file"] = res["selected_latest"]["filepath"]
            return res

        elif name == "parse_invoice_document":
            filepath = self.state.context_memory.get("latest_file")
            if not filepath:
                return {"success": False, "error": "No document filepath found in context memory"}
            res = self.tools.parse_invoice_document(filepath)
            if res.get("success"):
                self.state.context_memory["extracted_invoice"] = res["extracted_data"]
            return res

        elif name == "query_erp_vendor":
            vendor = step.tool_args.get("vendor_name") or self.state.context_memory.get("vendor_hint", "")
            return self.tools.query_erp_vendor(vendor)

        elif name == "human_approval_gate":
            # If reached here in auto_approve mode
            return {"success": True, "message": "Human approval granted."}

        elif name == "record_erp_bill":
            extracted = self.state.context_memory.get("extracted_invoice", {})
            if not extracted:
                return {"success": False, "error": "Missing extracted invoice data in memory"}
            
            # Check if recovery instructed verifying existing record
            if step.tool_args.get("fallback_action") == "verify_existing":
                return self.tools.get_existing_bill(extracted["invoice_number"])

            return self.tools.record_erp_bill(
                invoice_number=extracted["invoice_number"],
                vendor_name=extracted["vendor_name"],
                amount=extracted["amount"],
                currency=extracted["currency"],
                due_date=extracted["due_date"]
            )

        elif name == "independent_verification":
            extracted = self.state.context_memory.get("extracted_invoice", {})
            res = self.verifier.verify_invoice_task(extracted)
            self.state.verification_result = res
            return {"success": res["verified"], "verification_report": res}

        else:
            return {"success": False, "error": f"Unknown tool: {name}"}

    def _format_observation(self, tool_name: str, result: Dict[str, Any]) -> str:
        if tool_name == "search_document_repository":
            return f"Found {result.get('found_count', 0)} document(s). Selected latest: {result.get('selected_latest', {}).get('filename')}"
        elif tool_name == "parse_invoice_document":
            d = result.get("extracted_data", {})
            return f"Extracted Invoice #{d.get('invoice_number')}, Amount: {d.get('currency')} {d.get('amount')}, Due: {d.get('due_date')}"
        elif tool_name == "query_erp_vendor":
            return f"Vendor registered: {result.get('registered')}"
        elif tool_name == "human_approval_gate":
            return "Approval confirmed by operator."
        elif tool_name == "record_erp_bill":
            if not result.get("success", False):
                return f"ERP write failed: {result.get('message') or result.get('error', 'Unknown error')}"
            rec = result.get("record", {})
            rec_id = rec.get("id")
            rec_status = rec.get("status")
            if rec_id is None or rec_status is None:
                return f"ERP write error: Missing persisted record attributes (ID: {rec_id}, Status: {rec_status})"
            if result.get("reused"):
                return f"Detected existing ledger entry. Reused & verified ERP record ID #{rec_id} with status '{rec_status}'."
            return f"Successfully created ERP ledger entry ID #{rec_id} with status '{rec_status}'."
        elif tool_name == "independent_verification":
            rep = result.get("verification_report", {})
            status = "PASS" if rep.get("verified") else "FAIL"
            return f"Independent DB check: {status}. Proof Hash: {rep.get('proof_hash', '')[:16]}..."
        return str(result)

    def _log(self, message: str):
        timestamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        if self.state:
            self.state.logs.append(formatted)
        print(formatted)
