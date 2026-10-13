"""
Automated Test Suite for TaskOperator-AI
Tests autonomy, execution, recovery, human-in-the-loop, and independent verification.
"""
import os
import unittest
import tempfile
from agent.operator import AutonomousOperator
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

    def test_full_autonomous_loop_execution(self):
        """Tests complete Goal -> Plan -> Execute -> Verify loop."""
        goal = "Find the latest invoice from Acme Corp, extract the amount and due date, enter it into our internal system, and verify."
        self.operator.initialize_task(goal)
        
        state = self.operator.run_to_completion(auto_approve=True)
        
        self.assertTrue(state.is_completed, "Task should complete successfully")
        self.assertFalse(state.is_failed, "Task should not fail")
        self.assertIsNotNone(state.verification_result, "Verification result must be present")
        self.assertTrue(state.verification_result["verified"], "Independent verifier must confirm database record")

        # Confirm record directly in DB
        invoices = self.erp.list_invoices()
        self.assertEqual(len(invoices), 1, "Exactly one invoice should be saved in ERP")
        self.assertIn("INV-ACM", invoices[0]["invoice_number"])

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

    def test_human_approval_gate(self):
        """Tests that operator properly halts for human approval before financial commitment."""
        goal = "Process invoice for Globex Corporation into ERP ledger"
        self.operator.initialize_task(goal)
        
        # Step until approval is requested
        state = self.operator.run_to_completion(auto_approve=False)
        self.assertTrue(state.waiting_for_approval, "Operator must pause at approval gate")
        self.assertIsNotNone(state.approval_prompt)

        # Grant approval
        res = self.operator.submit_human_approval(approved=True)
        self.assertEqual(res.get("status"), "STEP_COMPLETED")

        # Finish remaining steps
        final_state = self.operator.run_to_completion(auto_approve=True)
        self.assertTrue(final_state.is_completed)


if __name__ == "__main__":
    unittest.main()
