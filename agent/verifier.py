"""
Independent Verification Engine
Crucial evaluation criterion: Independently inspects underlying system state
to verify that the intended business outcome was actually achieved.
"""
import hashlib
import json
from typing import Dict, Any
from sandbox.erp_system import EnterpriseERPSystem


class IndependentVerifier:
    def __init__(self, erp_system: EnterpriseERPSystem = None):
        self.erp = erp_system or EnterpriseERPSystem()

    def verify_invoice_task(self, expected_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Independently checks database state without relying on agent's internal memory.
        
        Args:
            expected_data: Dict containing 'invoice_number', 'amount', 'vendor_name'
            
        Returns:
            Dict containing verification status, check breakdown, and cryptographic proof hash.
        """
        invoice_number = expected_data.get("invoice_number")
        expected_amount = expected_data.get("amount")
        expected_vendor = expected_data.get("vendor_name")

        if not invoice_number:
            return {
                "verified": False,
                "reason": "Missing invoice_number to perform independent verification.",
                "evidence": None
            }

        # Directly query the raw database state
        db_record = self.erp.direct_state_check(invoice_number)

        if not db_record:
            return {
                "verified": False,
                "reason": f"Verification Failed: Record {invoice_number} does not exist in ERP database.",
                "evidence": {"found_in_database": False}
            }

        checks = {}
        
        # 1. Verification of Existence
        checks["record_exists"] = True

        # 2. Verification of Amount Precision
        actual_amount = db_record["amount"]
        amount_match = abs(actual_amount - float(expected_amount)) < 0.001
        checks["amount_exact_match"] = amount_match

        # 3. Verification of Vendor Matching
        actual_vendor = db_record["vendor_name"]
        vendor_match = expected_vendor.lower() in actual_vendor.lower()
        checks["vendor_match"] = vendor_match

        # 4. Verification of Status Validity
        status_valid = db_record["status"] in ["RECORDED", "PENDING_APPROVAL"]
        checks["status_valid"] = status_valid

        all_passed = all(checks.values())

        # Generate Cryptographic Proof Hash for auditability
        proof_payload = f"{db_record['invoice_number']}|{actual_amount}|{actual_vendor}|{db_record['created_at']}"
        proof_hash = hashlib.sha256(proof_payload.encode("utf-8")).hexdigest()

        return {
            "verified": all_passed,
            "verification_checks": checks,
            "evidence": {
                "db_record_id": db_record["id"],
                "invoice_number": db_record["invoice_number"],
                "verified_vendor": actual_vendor,
                "verified_amount": actual_amount,
                "currency": db_record["currency"],
                "due_date": db_record["due_date"],
                "system_status": db_record["status"],
                "recorded_at": db_record["created_at"]
            },
            "proof_hash": proof_hash,
            "summary": "Outcome verified against primary database ledger." if all_passed else "Verification checks failed."
        }
