"""
Simulated Enterprise ERP System (Accounts Payable, Ledger & Vendor Management)
Uses SQLite for authentic state persistence and independent verifiability.
"""
import os
import sqlite3
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

DB_FILE = os.path.join(os.path.dirname(__file__), "enterprise_erp.db")


class EnterpriseERPSystem:
    def __init__(self, db_path: str = DB_FILE):
        self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Vendors Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS vendors (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    payment_terms TEXT,
                    currency TEXT DEFAULT 'USD'
                )
            """)
            
            # Invoices / Accounts Payable Ledger Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS erp_invoices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    invoice_number TEXT UNIQUE NOT NULL,
                    vendor_name TEXT NOT NULL,
                    amount REAL NOT NULL,
                    currency TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    status TEXT NOT NULL, -- PENDING_APPROVAL, RECORDED, PAID
                    created_at TEXT NOT NULL,
                    metadata_json TEXT
                )
            """)
            
            # Audit Trail Table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS audit_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    entity_id TEXT,
                    performed_by TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    details_json TEXT
                )
            """)

            # Seed default vendor if not exists
            cursor.execute("INSERT OR IGNORE INTO vendors (id, name, payment_terms, currency) VALUES (?, ?, ?, ?)",
                           ("VEND-001", "Acme Corp", "Net 30", "USD"))
            cursor.execute("INSERT OR IGNORE INTO vendors (id, name, payment_terms, currency) VALUES (?, ?, ?, ?)",
                           ("VEND-002", "Globex Corporation", "Net 15", "USD"))
            conn.commit()

    def reset_database(self):
        """Reset ERP records for reproducible test demonstrations."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM erp_invoices")
            cursor.execute("DELETE FROM audit_logs")
            conn.commit()

    def query_vendor(self, vendor_name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM vendors WHERE LOWER(name) LIKE LOWER(?)", (f"%{vendor_name}%",))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def query_invoice(self, invoice_number: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM erp_invoices WHERE invoice_number = ?", (invoice_number,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None

    def list_invoices(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM erp_invoices ORDER BY id DESC")
            return [dict(row) for row in cursor.fetchall()]

    def create_payable_entry(self, invoice_number: str, vendor_name: str, amount: float,
                              currency: str, due_date: str, status: str = "RECORDED",
                              operator: str = "AutonomousAgent") -> Dict[str, Any]:
        """Creates an Accounts Payable entry in the ERP ledger."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check for duplicate
            cursor.execute("SELECT id FROM erp_invoices WHERE invoice_number = ?", (invoice_number,))
            if cursor.fetchone():
                raise ValueError(f"Duplicate Error: Invoice {invoice_number} already recorded in ERP ledger.")

            timestamp = datetime.now(timezone.utc).isoformat()
            cursor.execute("""
                INSERT INTO erp_invoices 
                (invoice_number, vendor_name, amount, currency, due_date, status, created_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (invoice_number, vendor_name, amount, currency, due_date, status, timestamp, json.dumps({"source": "task_worker"})))
            
            entry_id = cursor.lastrowid
            
            # Record in Audit Log
            cursor.execute("""
                INSERT INTO audit_logs (action, entity_id, performed_by, timestamp, details_json)
                VALUES (?, ?, ?, ?, ?)
            """, ("CREATE_INVOICE_RECORD", str(entry_id), operator, timestamp,
                  json.dumps({"amount": amount, "vendor": vendor_name, "invoice_number": invoice_number})))
            
            conn.commit()
            
            return {
                "id": entry_id,
                "invoice_number": invoice_number,
                "vendor_name": vendor_name,
                "amount": amount,
                "currency": currency,
                "due_date": due_date,
                "status": status,
                "created_at": timestamp
            }

    def direct_state_check(self, invoice_number: str) -> Optional[Dict[str, Any]]:
        """Used strictly by the Independent Verifier to inspect raw DB state."""
        return self.query_invoice(invoice_number)
