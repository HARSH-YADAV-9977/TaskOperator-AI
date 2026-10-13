// TaskOperator-AI Client Dashboard Script

const API_BASE = "http://localhost:5000/api";

const goalInput = document.getElementById("task-goal-input");
const btnStart = document.getElementById("btn-start-task");
const btnStep = document.getElementById("btn-step-task");
const btnResetErp = document.getElementById("btn-reset-erp");
const autoApproveToggle = document.getElementById("auto-approve-toggle");

const statusBadge = document.getElementById("agent-status-badge");
const stepsTimeline = document.getElementById("steps-timeline");
const stepCountBadge = document.getElementById("step-count-badge");

const terminalBody = document.getElementById("terminal-body");
const erpTableBody = document.getElementById("erp-table-body");

const verifBadge = document.getElementById("verif-status-badge");
const verifChecksList = document.getElementById("verif-checks-list");
const proofBox = document.getElementById("proof-box");
const proofHashCode = document.getElementById("proof-hash-code");

const approvalModal = document.getElementById("approval-modal");
const approvalDetailsCard = document.getElementById("approval-details-card");
const btnApproveModal = document.getElementById("btn-approve-modal");
const btnRejectModal = document.getElementById("btn-reject-modal");

let currentTaskState = null;

// Presets
window.setPreset = function(type) {
    if (type === 'Acme Corp') {
        goalInput.value = "Find the latest invoice from Acme Corp, extract the amount and due date, enter it into our internal system, and tell me once it is done.";
    } else if (type === 'Globex Corporation') {
        goalInput.value = "Process the latest invoice from Globex Corporation, verify vendor registration, and record into company ERP ledger.";
    } else if (type === 'Edge Case') {
        goalInput.value = "Find invoice for Acme Corp with non-standard currency formatting, extract parameters, and safely record into system.";
    }
};

// Clear terminal
window.clearLogs = function() {
    terminalBody.innerHTML = '<div class="log-line system">[SYSTEM READY] Logs cleared.</div>';
};

function addLog(msg, type = "normal") {
    const line = document.createElement("div");
    line.className = `log-line ${type}`;
    line.textContent = msg;
    terminalBody.appendChild(line);
    terminalBody.scrollTop = terminalBody.scrollHeight;
}

// Start Autonomous Execution
async function handleRunTask() {
    const goal = goalInput.value.trim();
    if (!goal) return alert("Please specify a business task goal.");

    setAgentStatus("running", "PLANNING & RUNNING");
    btnStart.disabled = true;
    btnStep.disabled = true;

    try {
        addLog(`[INITIALIZE] Submitting goal: "${goal}"`, "system");
        
        // 1. Initialize Task
        const initRes = await fetch(`${API_BASE}/task/start`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ goal })
        });
        const initData = await initRes.json();
        currentTaskState = initData.state;
        renderPlanSteps(currentTaskState);
        addLog(`[PLAN CREATED] ${currentTaskState.plan.steps.length} sub-actions decomposed.`, "system");

        // 2. Run to completion (or pause at approval)
        const autoApprove = autoApproveToggle.checked;
        const runRes = await fetch(`${API_BASE}/task/run-all`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ auto_approve: autoApprove })
        });
        const runData = await runRes.json();
        currentTaskState = runData.state;

        renderPlanSteps(currentTaskState);
        await updateERPTable();

        if (runData.status === "AWAITING_APPROVAL") {
            setAgentStatus("waiting", "AWAITING APPROVAL");
            showApprovalModal(currentTaskState);
        } else if (runData.status === "COMPLETED") {
            setAgentStatus("success", "TASK COMPLETED & VERIFIED");
            renderVerification(currentTaskState.verification_result);
            addLog(`[VERIFIED] Task finished with independent database verification proof.`, "success");
            btnStart.disabled = false;
        } else {
            setAgentStatus("idle", "AGENT HALTED");
            btnStart.disabled = false;
        }

    } catch (err) {
        addLog(`[ERROR] Network or execution failure: ${err.message}`, "error");
        setAgentStatus("idle", "AGENT ERROR");
        btnStart.disabled = false;
    }
}

// Step-by-step execution
async function handleStepTask() {
    if (!currentTaskState) return;
    try {
        const autoApprove = autoApproveToggle.checked;
        const res = await fetch(`${API_BASE}/task/step`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ auto_approve: autoApprove })
        });
        const data = await res.json();
        currentTaskState = data.state;
        renderPlanSteps(currentTaskState);
        await updateERPTable();

        if (data.step_result?.status === "AWAITING_APPROVAL") {
            showApprovalModal(currentTaskState);
        } else if (currentTaskState.is_completed) {
            setAgentStatus("success", "TASK COMPLETED & VERIFIED");
            renderVerification(currentTaskState.verification_result);
        }
    } catch (err) {
        addLog(`[STEP ERROR] ${err.message}`, "error");
    }
}

// Render steps
function renderPlanSteps(state) {
    if (!state || !state.plan) return;
    const steps = state.plan.steps;
    stepCountBadge.textContent = `${steps.length} Steps`;
    stepsTimeline.innerHTML = "";

    steps.forEach((s, idx) => {
        const isCurrent = idx === state.current_step_index && !state.is_completed;
        const card = document.createElement("div");
        card.className = `step-card ${s.status.toLowerCase()} ${isCurrent ? 'active' : ''}`;
        
        card.innerHTML = `
            <div class="step-top">
                <span class="step-id">ACTION 0${s.step_id}</span>
                <span class="step-status-tag tag-${s.status.toLowerCase()}">${s.status}</span>
            </div>
            <div class="step-title">${s.title}</div>
            <div class="step-tool">Tool: ${s.tool_name}</div>
            ${s.observation ? `<div class="step-obs">${s.observation}</div>` : ''}
        `;
        stepsTimeline.appendChild(card);
    });

    // Append latest logs
    if (state.logs && state.logs.length) {
        state.logs.forEach(l => {
            // avoid spamming duplicates
            if (!terminalBody.innerText.includes(l)) {
                addLog(l);
            }
        });
    }
}

function showApprovalModal(state) {
    const extracted = state.context_memory?.extracted_invoice || {};
    approvalDetailsCard.innerHTML = `
        <div class="approval-row"><span class="approval-label">Vendor:</span> <span class="approval-val">${extracted.vendor_name || 'N/A'}</span></div>
        <div class="approval-row"><span class="approval-label">Invoice Ref:</span> <span class="approval-val">${extracted.invoice_number || 'N/A'}</span></div>
        <div class="approval-row"><span class="approval-label">Payable Amount:</span> <span class="approval-val">${extracted.currency || 'USD'} ${extracted.amount || '0.00'}</span></div>
        <div class="approval-row"><span class="approval-label">Due Date:</span> <span class="approval-val">${extracted.due_date || 'N/A'}</span></div>
    `;
    approvalModal.classList.remove("hidden");
}

async function handleApproval(approved) {
    approvalModal.classList.add("hidden");
    addLog(`[HUMAN INPUT] Operator selected: ${approved ? 'APPROVED' : 'REJECTED'}`, approved ? "success" : "error");

    try {
        const res = await fetch(`${API_BASE}/task/approve`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ approved })
        });
        const data = await res.json();
        currentTaskState = data.state;
        renderPlanSteps(currentTaskState);
        await updateERPTable();

        if (approved && !currentTaskState.is_completed) {
            // finish remaining
            await handleRunTask();
        } else {
            btnStart.disabled = false;
        }
    } catch (err) {
        addLog(`[APPROVAL ERROR] ${err.message}`, "error");
        btnStart.disabled = false;
    }
}

function renderVerification(verif) {
    if (!verif) return;
    if (verif.verified) {
        verifBadge.className = "badge-verif badge-verif-passed";
        verifBadge.textContent = "INDEPENDENTLY VERIFIED";
        
        verifChecksList.innerHTML = `
            <div class="check-item"><span class="check-icon">✅</span> Record Exists in SQLite (ID: #${verif.evidence?.db_record_id})</div>
            <div class="check-item"><span class="check-icon">✅</span> Exact Amount Match ($${verif.evidence?.verified_amount})</div>
            <div class="check-item"><span class="check-icon">✅</span> Vendor Identity Validated (${verif.evidence?.verified_vendor})</div>
            <div class="check-item"><span class="check-icon">✅</span> Status Recorded in General Ledger</div>
        `;

        proofBox.style.display = "flex";
        proofHashCode.textContent = verif.proof_hash;
    } else {
        verifBadge.className = "badge-verif badge-verif-failed";
        verifBadge.textContent = "VERIFICATION FAILED";
        proofBox.style.display = "none";
    }
}

async function updateERPTable() {
    try {
        const res = await fetch(`${API_BASE}/erp/invoices`);
        const data = await res.json();
        const invoices = data.invoices || [];

        if (invoices.length === 0) {
            erpTableBody.innerHTML = `<tr><td colspan="6" class="text-center text-muted">No records in ledger. Run task to record.</td></tr>`;
            return;
        }

        erpTableBody.innerHTML = invoices.map(inv => `
            <tr>
                <td>#${inv.id}</td>
                <td><strong>${inv.invoice_number}</strong></td>
                <td>${inv.vendor_name}</td>
                <td><strong>${inv.currency} ${inv.amount.toFixed(2)}</strong></td>
                <td>${inv.due_date}</td>
                <td><span class="badge-status-recorded">${inv.status}</span></td>
            </tr>
        `).join("");
    } catch (e) {
        console.error("Failed to fetch ERP invoices:", e);
    }
}

async function handleResetErp() {
    if (!confirm("Reset simulated ERP database and audit records?")) return;
    try {
        await fetch(`${API_BASE}/erp/reset`, { method: "POST" });
        await updateERPTable();
        addLog("[RESET] ERP Database wiped clean for demonstration.", "system");
        verifBadge.className = "badge-verif badge-verif-pending";
        verifBadge.textContent = "AWAITING EXECUTION";
        proofBox.style.display = "none";
    } catch (e) {
        alert("Failed to reset ERP: " + e.message);
    }
}

function setAgentStatus(type, text) {
    statusBadge.className = `status-indicator status-${type}`;
    statusBadge.querySelector(".text").textContent = text;
}

// Listeners
btnStart.addEventListener("click", handleRunTask);
btnStep.addEventListener("click", handleStepTask);
btnResetErp.addEventListener("click", handleResetErp);
btnApproveModal.addEventListener("click", () => handleApproval(true));
btnRejectModal.addEventListener("click", () => handleApproval(false));

// Init
updateERPTable();
