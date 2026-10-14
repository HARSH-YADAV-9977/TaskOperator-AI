"""
CLI Interface for TaskOperator-AI
Run the autonomous enterprise task operator directly from the command line.
"""
import sys
import argparse
import json

# Ensure UTF-8 output on Windows consoles
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from agent.operator import AutonomousOperator
from sandbox.erp_system import EnterpriseERPSystem


def main():
    parser = argparse.ArgumentParser(description="TaskOperator-AI: Autonomous Enterprise Task Worker")
    parser.add_argument(
        "--task",
        type=str,
        default="Find the latest invoice from Acme Corp, extract the amount and due date, enter it into our internal system, and verify once it is done.",
        help="Natural language task prompt"
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically grant human approval for financial actions (for automated testing)"
    )
    parser.add_argument(
        "--reset-db",
        action="store_true",
        help="Reset ERP database before execution to demonstrate clean run"
    )
    args = parser.parse_args()

    erp = EnterpriseERPSystem()
    if args.reset_db:
        print("[SETUP] Resetting ERP database records...")
        erp.reset_database()

    print("=" * 70)
    print("🚀 TaskOperator-AI: Autonomous Enterprise Operator")
    print(f"Goal: {args.task}")
    print("=" * 70)

    operator = AutonomousOperator(erp_system=erp)
    state = operator.initialize_task(args.task)

    print(f"\n[PLAN GENERATED] {len(state.plan.steps)} Sub-Actions Planned:")
    for step in state.plan.steps:
        print(f"  Step {step.step_id}: {step.title} (Tool: {step.tool_name})")

    print("\n[EXECUTION BEGINS]")
    while not state.is_completed and not state.is_failed:
        result = operator.step(auto_approve=args.auto_approve)
        
        if result.get("status") == "AWAITING_APPROVAL":
            print("\n" + "!" * 60)
            print("⚠️  HUMAN-IN-THE-LOOP APPROVAL REQUIRED")
            print(f"Prompt: {result['prompt']}")
            print("!" * 60)
            
            choice = input("\nDo you approve recording this transaction in ERP? [y/N]: ").strip().lower()
            if choice == "y":
                operator.submit_human_approval(approved=True)
            else:
                operator.submit_human_approval(approved=False)
                break

    print("\n" + "=" * 70)
    if state.is_completed:
        print("✅ TASK COMPLETED SUCCESSFULLY!")
        print("\n🔍 INDEPENDENT VERIFICATION REPORT:")
        verif = state.verification_result
        if verif:
            print(f"  Verification Status : {'PASSED (VERIFIED)' if verif.get('verified') else 'FAILED'}")
            print(f"  Integrity Digest    : {verif.get('proof_hash')}")
            print(f"  Evidence Summary    : {json.dumps(verif.get('evidence'), indent=4)}")
        else:
            print("  No independent verification report generated.")
    else:
        print("❌ TASK FAILED OR ABORTED.")

    print("=" * 70)


if __name__ == "__main__":
    main()
