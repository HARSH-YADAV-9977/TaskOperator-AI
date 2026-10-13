"""
Automated Test Suite for TaskOperator-AI
Tests autonomy, execution, recovery, human-in-the-loop, and independent verification.
"""
import os
import unittest
import tempfile
from agent.operator import AutonomousOperator
from agent.models import StepStatus
from agent.verifier import IndependentVerifier
from sandbox.erp_system import EnterpriseERPSystem


class TestTaskOperator(unittest.TestCase):
    def setUp(self):
        # Use isolated test database
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.temp_db.close()
        self.erp = EnterpriseERPSystem(db_path=self.temp_db.name)
        self.operator = AutonomousOperator(erp_system=self.erp)

    def tearDown(self):
        if os.path.exists(self.temp_db.name):
            try:
                os.remove(self.temp_db.name)
            except Exception:
                pass

    def test_full_autonomous_loop_execution_and_valid_attributes(self):
        """Tests complete Goal -> Plan -> Execute -> Verify loop and validates ERP record attributes."""
        goal = "Find the latest invoice from Acme Corp, extract the amount and due date, enter it into our internal system, and verify."
        self.operator.initialize_task(goal)
        
        state = self.operator.run_to_completion(auto_approve=True)
        
        self.assertTrue(state.is_completed, "Task should complete successfully")
        self.assertFalse(state.is_failed, "Task should not fail")
        self.assertIsNotNone(state.verification_result, "Verification result must be present")
        self.assertTrue(state.verification_result["verified"], "Independent verifier must confirm database record")

        # Confirm step 5 (record_erp_bill) attributes:
        step5 = state.plan.steps[4]
        self.assertEqual(step5.status, StepStatus.COMPLETED, "Action 05 must be COMPLETED on fresh write, not RECOVERED")
        self.assertIsNotNone(step5.output_data, "Output data must exist")
        self.assertTrue(step5.output_data.get("success"), "Output success must be True")
        
        record = step5.output_data.get("record", {})
        self.assertIsNotNone(record.get("id"), "Persisted record ID must not be None")
        self.assertIsInstance(record.get("id"), int, "Persisted record ID must be an integer")
        self.assertEqual(record.get("status"), "RECORDED", "Persisted record status must be 'RECORDED'")
        
        # Verify observation does NOT contain '#None' or ''None''
        self.assertNotIn("#None", step5.observation, "Observation must not report '#None'")
        self.assertNotIn("'None'", step5.observation, "Observation must not report ''None''")
        self.assertIn(f"ID #{record['id']}", step5.observation, "Observation must report exact record ID")

        # Confirm record directly in DB
        invoices = self.erp.list_invoices()
        self.assertEqual(len(invoices), 1, "Exactly one invoice should be saved in ERP")
        self.assertIn("INV-ACM", invoices[0]["invoice_number"])

    def test_duplicate_invoice_recovery_and_valid_attributes(self):
        """Tests that attempting to record a duplicate invoice recovers cleanly with existing record ID."""
        # Pre-seed duplicate record in ERP
        seeded = self.erp.create_payable_entry(
            invoice_number="INV-ACM-EDGE-2026",
            vendor_name="Acme Corp",
            amount=2450.0,
            currency="USD",
            due_date="2026-10-28"
        )
        self.assertIsNotNone(seeded["id"])

        goal = "Find invoice for Acme Corp and enter into ERP ledger"
        self.operator.initialize_task(goal)
        state = self.operator.run_to_completion(auto_approve=True)

        step5 = state.plan.steps[4]
        # Must be RECOVERED because duplicate was encountered and handled
        self.assertEqual(step5.status, StepStatus.RECOVERED, "Duplicate handling should mark step as RECOVERED")
        self.assertNotIn("#None", step5.observation, "Observation must not report '#None'")
        self.assertNotIn("'None'", step5.observation, "Observation must not report ''None''")
        self.assertIn(f"ID #{seeded['id']}", step5.observation, "Observation must report the actual existing record ID")
        self.assertEqual(step5.output_data["record"]["id"], seeded["id"])

    def test_failed_erp_write_marked_as_failed_not_recovered(self):
        """Tests that an unrecoverable ERP write failure is marked FAILED and halts task."""
        goal = "Process invoice for Acme Corp"
        self.operator.initialize_task(goal)
        
        # Corrupt context memory to force an execution failure in record_erp_bill
        self.operator.step(auto_approve=True) # Step 1: search
        self.operator.step(auto_approve=True) # Step 2: parse
        self.operator.step(auto_approve=True) # Step 3: query vendor
        self.operator.step(auto_approve=True) # Step 4: human approval
        
        # Deliberately remove extracted invoice from context memory before step 5
        self.operator.state.context_memory["extracted_invoice"] = {}
        
        # Step 5: record_erp_bill
        res = self.operator.step(auto_approve=True)
        step5 = self.operator.state.plan.steps[4]
        
        self.assertEqual(step5.status, StepStatus.FAILED, "Failed write must be marked as FAILED")
        self.assertNotEqual(step5.status, StepStatus.RECOVERED, "Failed write must NOT be marked as RECOVERED")
        self.assertNotEqual(step5.status, StepStatus.COMPLETED, "Failed write must NOT be marked as COMPLETED")
        self.assertTrue(self.operator.state.is_failed, "Task state must be marked as failed")

    def test_human_approval_rejection_halts_task(self):
        """Tests that rejecting human approval halts task and prevents ERP write."""
        goal = "Process invoice for Globex Corporation into ERP ledger"
        self.operator.initialize_task(goal)
        
        # Step until approval is requested
        state = self.operator.run_to_completion(auto_approve=False)
        self.assertTrue(state.waiting_for_approval, "Operator must pause at approval gate")
        
        # User explicitly REJECTS
        res = self.operator.submit_human_approval(approved=False)
        self.assertEqual(res.get("status"), "REJECTED_BY_USER")
        self.assertTrue(self.operator.state.is_failed, "Task must be marked as failed/aborted upon rejection")

        # Verify nothing was written to ERP
        invoices = self.erp.list_invoices()
        self.assertEqual(len(invoices), 0, "No invoice should be recorded when user rejects approval")

    def test_independent_verifier_tamper_detection(self):
        """Negative test: Verifier must catch amount mismatches or missing records."""
        verifier = IndependentVerifier(erp_system=self.erp)
        
        # Test 1: Non-existent record
        res1 = verifier.verify_invoice_task({"invoice_number": "NON_EXISTENT_999", "amount": 100.0, "vendor_name": "Acme"})
        self.assertFalse(res1["verified"], "Verifier must fail for missing records")

        # Seed record with 500.0
        self.erp.create_payable_entry("INV-TAMPER-1", "Acme Corp", 500.0, "USD", "2026-10-31")
        
        # Test 2: Mismatched amount
        res2 = verifier.verify_invoice_task({"invoice_number": "INV-TAMPER-1", "amount": 999.0, "vendor_name": "Acme Corp"})
        self.assertFalse(res2["verified"], "Verifier must detect amount discrepancy")
        self.assertFalse(res2["verification_checks"]["amount_exact_match"])


if __name__ == "__main__":
    unittest.main()
