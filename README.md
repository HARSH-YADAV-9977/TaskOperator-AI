# TaskOperator-AI: Autonomous Enterprise Task Worker

> **Submission for CentrAlign AI — AI Engineering Hiring Challenge**  
> **Role:** AI Engineering Intern (Open to Founding Engineer Evaluation)  
> **Repository:** [https://github.com/YOUR_GITHUB_USERNAME/TaskOperator-AI](https://github.com/YOUR_GITHUB_USERNAME/TaskOperator-AI)

---

## 1. Problem Statement & Motivation

Enterprise knowledge workers spend countless hours moving between fragmented systems: searching unstructured document directories, extracting financial data from invoices, verifying records against ERP master databases, getting manager approvals, and updating accounts payable ledgers.

**Objective:**  
Build a working prototype of an autonomous AI task operator that receives a high-level natural-language business objective—such as:
> *"Find the latest invoice from Acme Corp, extract the amount and due date, enter it into our internal system, and tell me once it is done."*

...and autonomously plans, executes, verifies, and provides immutable audit evidence for the completed work with minimal human supervision.

---

## 2. Core Execution Loop

```
  [Natural Language Goal]
             │
             ▼
   ┌───────────────────┐
   │ 1. Dynamic Plan   │ ──> Decomposes intent into actionable sub-tasks (DAG)
   └─────────┬─────────┘
             │
             ▼
   ┌───────────────────┐
   │ 2. Tool Execution │ ──> Search Repository ──> Parse Invoice ──> Query ERP Master
   └─────────┬─────────┘
             │
             ▼
   ┌───────────────────┐
   │ 3. Human Approval │ ──> Halts execution before committing sensitive financial liability
   └─────────┬─────────┘
             │
             ▼
   ┌───────────────────┐
   │ 4. State Recovery │ ──> Sanitizes irregular currency/date formats & recovers
   └─────────┬─────────┘
             │
             ▼
   ┌───────────────────┐
   │ 5. Indep. Verify  │ ──> Independently inspects primary SQLite DB table (not memory)
   └─────────┬─────────┘
             │
             ▼
  [Cryptographic Proof & Diff Audit Evidence]
```

---

## 3. Architecture & Key Modules

The project is structured with modular separation of concerns:

```
TaskOperator-AI/
├── agent/
│   ├── operator.py         # Autonomous loop orchestrator (Plan -> Execute -> Observe -> Verify)
│   ├── planner.py          # Decomposes natural language requests into structured Action DAGs
│   ├── tools.py            # Tool abstractions (file search, regex-resilient parser, ERP caller)
│   ├── verifier.py         # Independent Verifier: directly inspects DB state & computes SHA-256 proof
│   ├── recovery.py         # Failure detection, parameter sanitization, and fallback strategies
│   └── models.py           # Typed Pydantic data schemas for steps, plans, and runtime states
├── sandbox/
│   ├── erp_system.py       # Simulated Enterprise SQLite ERP (Accounts Payable, Vendors, Ledger)
│   └── storage/invoices/   # Real sample documents (standard, Globex, and malformed edge cases)
├── static/                 # Web Dashboard (Vanilla HTML5 / CSS3 / ES6)
├── tests/
│   └── test_agent.py       # Automated unit test suite (5 comprehensive unit tests)
├── app.py                  # Flask REST API & Web Dashboard backend
├── run_cli.py              # CLI runner for headless & automated batch execution
└── requirements.txt        # Minimal, zero-bloat dependencies
```

---

## 4. Technical & Design Decisions

1. **Independent Verification vs. Agent Self-Reporting:**
   * *Decision:* The agent's final status is **never** accepted based merely on its internal scratchpad or tool return values.
   * *Rationale:* LLMs frequently hallucinate success when a tool fails silently. The `IndependentVerifier` queries the raw SQLite database directly to confirm:
     - Record exists in `erp_invoices` table
     - Amount matches the extracted amount down to the exact cent (`abs(db - expected) < 0.001`)
     - Vendor and due dates match
     - Emits a cryptographic SHA-256 proof digest for tamper-evident auditing.

2. **Simulated Sandbox with SQLite:**
   * *Decision:* Built a lightweight, realistic enterprise ERP sandbox using SQLite rather than mocking API calls with arbitrary dictionaries.
   * *Rationale:* Demonstrates actual relational state transitions, persistent ACID transactions, and reproducible audit trails without requiring external paid third-party enterprise credentials.

3. **Human-in-the-Loop (HITL) Safety Gate:**
   * *Decision:* Financial mutations (writing accounts payable) halt and require supervisor confirmation unless `--auto-approve` is explicitly flagged.
   * *Rationale:* Enterprise deployments require strict guardrails for high-risk actions.

4. **Resilient Parsing & Failure Recovery:**
   * *Decision:* `parse_invoice_document` handles non-standard currency symbols (`$`, commas), irregular date formats (`MM/DD/YYYY` vs `YYYY-MM-DD`), and attempts fallback sanitization if initial parameter checks fail.

5. **Zero-Bloat Stack:**
   * *Decision:* Pure Python standard library + Flask + Pydantic. Avoided heavy multi-layer wrappers (like heavy LangChain boilerplates) to guarantee deterministic debugging, instant startup, and complete transparency during technical interviews.

---

## 5. Engineering Challenges & Diagnostic Debugging

During development and stress-testing, key edge-case challenges were identified and engineered for reliability:

### Challenge 1: The "False Recovery" & Missing Record Reporting Bug
* **Symptom:** In edge cases where an invoice had already been inserted, Action 05 initially displayed `"Successfully created ERP ledger entry ID #None with status 'None'"` while marking the step as `RECOVERED`.
* **Root Cause:**
  1. When duplicate insertion failed, the recovery engine suggested verifying the existing record, but `_execute_tool` called the write tool again rather than querying the existing ERP record.
  2. The recovery block did not check whether the secondary attempt succeeded before setting `step.status = RECOVERED`.
  3. Observation formatting assumed `result["record"]` was populated and read `None` values without validation.
* **Resolution:**
  - Added `get_existing_bill` tool handler when recovery suggests `verify_existing`.
  - Enforced a hard verification in `operator.step()`: if a recovery re-attempt fails, the step is strictly marked `FAILED` with `is_failed = True`. A failed write is **never** labeled as `COMPLETED` or `RECOVERED`.
  - Added strict assertions in `_format_observation` to prevent formatting null IDs or statuses.

### Challenge 2: State Resumption in Human Approval
* **Symptom:** Approving an action from the UI was previously triggering a full task re-initialization rather than resuming the in-flight task.
* **Resolution:** Frontend `handleApproval` now calls the `/api/task/run-all` resumption endpoint with `auto_approve: true`, ensuring existing context memory is preserved and remaining steps execute seamlessly.

---

## 6. Lessons Learned

1. **Autonomy Requires Strict Verification Boundaries:** An autonomous agent cannot evaluate its own success. Separating the execution loop from an out-of-band verification engine that queries ground truth is the single most effective way to eliminate hallucinations.
2. **Deterministic Fallbacks Beat Fragile Prompts:** Relying entirely on LLM prompt obedience for mathematical parsing or SQL insertion produces unpredictable edge-case failures. A hybrid system where the LLM handles ambiguity while deterministic, typed Python tools handle mutations and state transitions is substantially more reliable.

---

## 7. Quick Start & Setup Instructions

### Prerequisites
- Python 3.10+ (Tested on Python 3.13)
- `pip`

### Step 1: Clone and Navigate
```bash
git clone https://github.com/YOUR_GITHUB_USERNAME/TaskOperator-AI.git
cd TaskOperator-AI
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Run the Automated Test Suite
```bash
python -m unittest tests/test_agent.py -v
```
*Output: All 5 unit tests pass in ~0.24s.*

---

## 8. Execution Options

### Option A: Interactive Web Dashboard
Run the local web dashboard:
```bash
python app.py
```
Open **[http://localhost:5000](http://localhost:5000)** in your browser:
- Select a preset task or enter a custom prompt.
- Watch live step-by-step progress, interactive approval modal, live SQLite table updates, and independent verification badges.

### Option B: Terminal CLI (Headless Mode)
Run the agent directly from your terminal:
```bash
# Clean run with automated approval
python run_cli.py --auto-approve --reset-db

# Or with interactive human approval prompt:
python run_cli.py
```

---

## 9. Known Limitations

- **Document Formats:** Current prototype processes structured JSON/Text representations of invoices. OCR for raw scanned PDF/images is not yet integrated.
- **Single-Agent Architecture:** All actions are currently orchestrated by a single central operator loop rather than a swarm of specialized sub-agents.
- **Rule-Augmented Semantic Planner:** The planner uses deterministic entity extraction combined with action decomposition templates to ensure 100% offline reliability without token costs.

---

## 10. What Would Be Built Next (Roadmap)

1. **Multimodal Browser Automation (Playwright/Computer Use):** Connect the tool registry to Playwright to automate actual web-based ERP interfaces (e.g., SAP, NetSuite, or QuickBooks).
2. **Dynamic DAG Re-Planning:** If an intermediate tool observation yields unexpected findings (e.g., vendor credit balance exists), dynamically restructure remaining steps to deduct credit before recording.
3. **Long-Term Memory & Policy Vector Store:** Persistent vector storage of company operational policies (e.g., "Invoices over $5,000 require VP finance sign-off").

---

## 11. Assumptions Made

- Company ERP master table is accessible via local standard database connections.
- Invoices for processing are deposited in accessible company document storage.
- Standard payment terms apply if not overridden by the vendor master catalog.

---

## 12. Tech Stack & External Components

- **Backend:** Python 3.13, Flask 3.1.1, Flask-CORS 6.0.1
- **Schemas & Validation:** Pydantic 2.11.7
- **Database Sandbox:** SQLite 3 (Standard Library)
- **Frontend Dashboard:** Modern Vanilla HTML5, CSS3 (Glassmorphism / Dark Mode), ES6 JavaScript
