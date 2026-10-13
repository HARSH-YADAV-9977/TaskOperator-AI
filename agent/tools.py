"""
Execution Tools for TaskOperator-AI
Tools interact with file storage, document parsers, and ERP database.
"""
import os
import re
import json
from datetime import datetime
from typing import Dict, Any, List
from sandbox.erp_system import EnterpriseERPSystem

INVOICE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sandbox", "storage", "invoices")


class ToolRegistry:
    def __init__(self, erp_system: EnterpriseERPSystem = None):
        self.erp = erp_system or EnterpriseERPSystem()

    def search_document_repository(self, query: str) -> Dict[str, Any]:
        """
        Searches document storage for files matching vendor name or query keywords.
        """
        matched_files = []
        if not os.path.exists(INVOICE_DIR):
            return {"status": "error", "message": f"Storage directory {INVOICE_DIR} not found"}

        for filename in os.listdir(INVOICE_DIR):
            if filename.endswith(".json"):
                full_path = os.path.join(INVOICE_DIR, filename)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    vendor = data.get("vendor", "")
                    inv_no = data.get("invoice_number", "")
                    
                    # Fuzzy / keyword match against query
                    q_clean = query.lower()
                    if (q_clean in vendor.lower() or 
                        q_clean in filename.lower() or 
                        q_clean in inv_no.lower()):
                        matched_files.append({
                            "filename": filename,
                            "filepath": full_path,
                            "vendor": vendor,
                            "invoice_number": inv_no,
                            "issue_date": data.get("issue_date")
                        })
                except Exception as e:
                    continue

        # Sort by issue date descending to retrieve 'latest'
        matched_files.sort(key=lambda x: str(x.get("issue_date", "")), reverse=True)

        if not matched_files:
            return {
                "success": False,
                "found_count": 0,
                "files": [],
                "message": f"No documents found matching query: '{query}'"
            }

        return {
            "success": True,
            "found_count": len(matched_files),
            "files": matched_files,
            "selected_latest": matched_files[0]
        }

    def parse_invoice_document(self, filepath: str) -> Dict[str, Any]:
        """
        Parses document and extracts structured invoice data.
        Includes robust normalization for currency strings and varied date formats.
        """
        if not os.path.exists(filepath):
            return {"success": False, "error": f"File path not found: {filepath}"}

        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        vendor = data.get("vendor", "Unknown Vendor")
        invoice_number = data.get("invoice_number")
        due_date = data.get("due_date")
        currency = data.get("currency", "USD")
        
        # Determine amount (handle raw strings like '$ 2,450.00' or floats)
        raw_amt = data.get("total_amount")
        if raw_amt is None and "amount_raw_string" in data:
            raw_amt = data["amount_raw_string"]

        normalized_amount = None
        if isinstance(raw_amt, (int, float)):
            normalized_amount = float(raw_amt)
        elif isinstance(raw_amt, str):
            # Clean string with regex: remove $, commas, spaces
            cleaned = re.sub(r"[^\d.]", "", raw_amt)
            if cleaned:
                normalized_amount = float(cleaned)
        
        # Standardize currency if symbol given
        if currency == "$":
            currency = "USD"
            
        # Normalize date to YYYY-MM-DD
        normalized_date = due_date
        if due_date and "/" in due_date:
            try:
                # Handle MM/DD/YYYY
                dt = datetime.strptime(due_date, "%m/%d/%Y")
                normalized_date = dt.strftime("%Y-%m-%d")
            except ValueError:
                pass

        if not invoice_number or normalized_amount is None:
            return {
                "success": False,
                "error": "Failed to extract mandatory invoice parameters (invoice_number or amount)"
            }

        return {
            "success": True,
            "extracted_data": {
                "vendor_name": vendor,
                "invoice_number": invoice_number,
                "amount": normalized_amount,
                "currency": currency,
                "due_date": normalized_date,
                "raw_source": filepath
            }
        }

    def query_erp_vendor(self, vendor_name: str) -> Dict[str, Any]:
        """Queries company ERP system for registered vendor status."""
        vendor_info = self.erp.query_vendor(vendor_name)
        if vendor_info:
            return {"success": True, "registered": True, "vendor": vendor_info}
        return {"success": True, "registered": False, "message": f"Vendor '{vendor_name}' not yet registered in ERP master."}

    def record_erp_bill(self, invoice_number: str, vendor_name: str, amount: float,
                        currency: str, due_date: str) -> Dict[str, Any]:
        """
        Executes action to record accounts payable bill in ERP ledger.
        """
        try:
            record = self.erp.create_payable_entry(
                invoice_number=invoice_number,
                vendor_name=vendor_name,
                amount=amount,
                currency=currency,
                due_date=due_date,
                status="RECORDED"
            )
            return {"success": True, "record": record}
        except ValueError as val_err:
            return {"success": False, "error_type": "DUPLICATE", "message": str(val_err)}
        except Exception as e:
            return {"success": False, "error_type": "EXECUTION_ERROR", "message": str(e)}
