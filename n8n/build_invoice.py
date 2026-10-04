"""Builds 1-invoice-intake-and-approval.workflow.json for the Northfield Hardware internal AP invoice desk demo."""
import json

COLUMNS = [
    "Received", "Submitted By", "Vendor", "Invoice Number", "Invoice Date", "Due Date", "Currency",
    "Subtotal", "Tax", "Total", "PO Number", "Status", "Review Reasons",
    "Reviewer Note", "AI Quality Score", "AI Changes", "Summary", "Paid",
]
CH = "#invoice-approvals"
R = "$('Apply Quality Review').first().json"
F = "$('Finalize Record').first().json"

EXTRACT_SYSTEM = (
    "You extract data from vendor invoices for a bookkeeping firm. "
    "Reply with ONLY a JSON object, no markdown, using exactly these keys: "
    "vendor (string), invoice_number (string), invoice_date (YYYY-MM-DD), due_date (YYYY-MM-DD, or empty string if absent), "
    "currency (3-letter code), po_number (string, empty if absent), payment_terms (string), "
    "subtotal (number), tax (number, 0 if none), total (number), "
    "line_items (array of {description, quantity, unit_price, amount}), "
    "confidence (\"high\", \"medium\" or \"low\", based on how clearly the document states these values). "
    "Copy numbers exactly as printed, even if they look wrong. Never calculate or correct them. "
    "Use an empty string or 0 for anything the document does not state. Never guess."
)
EXTRACT_USER = "=Invoice text:\n{{ ($json.text || '').slice(0, 12000) }}"

QC_SYSTEM = (
    "You are a quality reviewer for an accounts payable team. You are given the raw text of a vendor invoice and the data a previous step extracted from it. "
    "Check the extracted data against the raw text. Reply with ONLY a JSON object with these keys: "
    "verdict (\"ok\" or \"concern\"), score (integer 0 to 100, how confident you are that the extracted data is accurate and complete), "
    "issues (array of short plain-language strings, only real problems such as a value that does not match the text, a suspicious or unusual item, or something that looks altered), "
    "changes (array of {field, from, to, reason} for small clean-ups only, where field is one of vendor, po_number or payment_terms, such as fixing capitalization or stray spacing so the vendor name is consistent). "
    "Never change amounts, dates or invoice numbers. Do not invent problems. If everything matches, return verdict ok, an empty issues array and an empty changes array."
)
QC_USER = "=Raw invoice text:\n{{ ($('Read PDF Text').first().json.text || '').slice(0, 12000) }}\n\nExtracted data:\n{{ JSON.stringify({ vendor: $json.vendor, invoice_number: $json.invoiceNumber, invoice_date: $json.invoiceDate, due_date: $json.dueDate, po_number: $json.poNumber, payment_terms: $json.terms, subtotal: $json.subtotal, tax: $json.tax, total: $json.total, line_items: $json.lineItems }) }}"

APPLY_QC = r"""const base = $('Parse and Check').first().json;
const raw = String($input.first().json.text ?? '');
let q = null;
try { q = JSON.parse(raw.replace(/```json|```/g, '').trim()); } catch (e) { q = null; }
const out = { ...base, qcScore: null, changes: [] };
const reasons = [...(base.reasons || [])];
if (!q) {
  reasons.push('The AI quality review could not be completed');
} else {
  out.qcScore = Number.isFinite(Number(q.score)) ? Number(q.score) : null;
  const allowed = { vendor: 'vendor', po_number: 'poNumber', payment_terms: 'terms' };
  for (const c of (Array.isArray(q.changes) ? q.changes : [])) {
    const key = allowed[c && c.field];
    if (key && c.to && String(base[key]) === String(c.from) && String(c.to) !== String(c.from)) {
      out[key] = String(c.to);
      out.changes.push({ field: c.field, from: String(c.from), to: String(c.to), reason: String(c.reason || '') });
    }
  }
  if (q.verdict === 'concern') {
    for (const i of (Array.isArray(q.issues) ? q.issues : [])) reasons.push('AI review: ' + String(i));
  }
  if (out.qcScore !== null && out.qcScore < 70) reasons.push('AI quality score is low (' + out.qcScore + ' of 100)');
}
out.reasons = reasons;
out.needsReview = reasons.length > 0;
out.qcIssues = reasons.filter(r => r.startsWith('AI review:') || r.startsWith('AI quality') || r.startsWith('The AI quality')).map(r => r.replace(/^AI review: /, ''));
return [{ json: out }];"""

PARSE = r"""const input = $input.first().json;
const raw = String(input.text ?? '');
let d = null;
try { d = JSON.parse(raw.replace(/```json|```/g, '').trim()); } catch (e) { d = null; }
const submittedBy = String((($('Invoice Upload').first().json.body) || {}).submittedBy || '').slice(0, 80);
const reasons = [];
if (!d) reasons.push('Could not read the invoice details');
d = d || {};
const num = (v) => { const n = Number(String(v ?? '').replace(/[^0-9.\-]/g, '')); return Number.isFinite(n) && String(v ?? '') !== '' ? n : null; };
const items = Array.isArray(d.line_items) ? d.line_items : [];
const subtotal = num(d.subtotal);
const tax = num(d.tax) ?? 0;
const total = num(d.total);
const itemsSum = items.reduce((s, i) => s + (num(i.amount) || 0), 0);
const money = (n) => (n === null ? '?' : n.toFixed(2));

if (!d.vendor) reasons.push('Missing vendor');
if (!d.invoice_number) reasons.push('Missing invoice number');
if (total === null) reasons.push('Missing total');
if (!d.due_date) reasons.push('Missing due date');
if (items.length && subtotal !== null && Math.abs(itemsSum - subtotal) > 0.02) {
  reasons.push(`Line items add up to ${money(itemsSum)} but the subtotal says ${money(subtotal)}`);
}
if (subtotal !== null && total !== null && Math.abs(subtotal + tax - total) > 0.02) {
  reasons.push(`Subtotal plus tax is ${money(subtotal + tax)} but the total says ${money(total)}`);
}
if (total !== null && total > 1000) reasons.push('Over the $1,000 auto-approval limit');
if (total !== null && total > 500 && !d.po_number) reasons.push('No PO number on an invoice over $500');
if (d.confidence === 'low') reasons.push('The AI marked its own reading as low confidence');

if (d.due_date) {
  const due = new Date(d.due_date);
  if (!isNaN(due) && due < new Date(new Date().toDateString())) reasons.push('Already past due');
}

const sd = $getWorkflowStaticData('global');
sd.seen = sd.seen || {};
if (d.vendor && d.invoice_number) {
  const key = String(d.vendor).toLowerCase().trim() + '|' + String(d.invoice_number).toLowerCase().trim();
  if (sd.seen[key]) reasons.push('Possible duplicate: this invoice was already processed');
  else sd.seen[key] = new Date().toISOString();
}

const needsReview = reasons.length > 0;
return [{ json: {
  submittedBy,
  vendor: d.vendor || '',
  invoiceNumber: d.invoice_number || '',
  invoiceDate: d.invoice_date || '',
  dueDate: d.due_date || '',
  currency: d.currency || 'USD',
  subtotal, tax, total,
  poNumber: d.po_number || '',
  terms: d.payment_terms || '',
  lineItems: items,
  confidence: d.confidence || '',
  reasons,
  needsReview,
  received: new Date().toISOString(),
  summary: `${d.vendor || 'Unknown vendor'} invoice ${d.invoice_number || '?'} for ${d.currency || 'USD'} ${money(total)}, due ${d.due_date || 'unknown'}`
}}];"""

FINALIZE = r"""const base = $('Apply Quality Review').first().json;
const s = $input.first().json;
const sd = $getWorkflowStaticData('global');
sd.decisions = sd.decisions || {};
if (base.vendor && base.invoiceNumber) {
  sd.decisions[String(base.vendor).toLowerCase().trim() + '|' + String(base.invoiceNumber).toLowerCase().trim()] = s.status;
}
return [{ json: {
  ...base,
  status: s.status,
  reviewNote: s.reviewNote || '',
  reasonsText: (base.reasons || []).join('; '),
  changesText: (base.changes || []).map(c => `${c.field}: ${c.from} -> ${c.to}`).join('; ')
}}];"""

DUE_SOON = r"""const rows = $input.all().map(i => i.json).filter(r => r && r['Vendor']);
const today = new Date(new Date().toDateString());
const soon = rows.filter(r => {
  const ok = /approved/i.test(String(r['Status'] || ''));
  const unpaid = !String(r['Paid'] || '').trim();
  const due = new Date(r['Due Date']);
  if (!ok || !unpaid || isNaN(due)) return false;
  const days = Math.round((due - today) / 86400000);
  return days >= 0 && days <= 3;
});
const text = soon.length
  ? `:calendar: *Invoices due in the next 3 days*\n` + soon.map(r => `• ${r['Vendor']} ${r['Invoice Number']}  ${r['Currency'] || ''} ${r['Total']}  due ${r['Due Date']}`).join('\n')
  : ':calendar: *Invoices due in the next 3 days*\nNothing due soon.';
return [{ json: { text } }];"""


LOOKUP = r"""const key = String(($input.first().json.query || {}).key || '').toLowerCase().trim();
const sd = $getWorkflowStaticData('global');
return [{ json: { status: (sd.decisions || {})[key] || 'pending' } }];"""


def ifnode(name, left, op_type, op, pos, right=""):
    nid = name.lower().replace(" ", "-").replace("?", "")
    return {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose", "version": 2},
                "conditions": [{
                    "id": nid,
                    "operator": {"type": op_type, "operation": op, **({"singleValue": True} if op in ("true", "false", "notEmpty") else {})},
                    "leftValue": left,
                    "rightValue": right,
                }],
                "combinator": "and",
            },
            "options": {},
        },
        "id": nid, "name": name, "type": "n8n-nodes-base.if", "typeVersion": 2.2, "position": pos,
    }


def slack(name, text, pos):
    return {
        "parameters": {
            "select": "channel",
            "channelId": {"__rl": True, "value": CH, "mode": "name"},
            "text": text,
            "otherOptions": {"includeLinkToWorkflow": False},
        },
        "id": name.lower().replace(" ", "-"), "name": name,
        "type": "n8n-nodes-base.slack", "typeVersion": 2.3, "position": pos,
    }


def setstatus(name, status, note, pos):
    return {
        "parameters": {
            "assignments": {"assignments": [
                {"id": "s1", "name": "status", "value": status, "type": "string"},
                {"id": "s2", "name": "reviewNote", "value": note, "type": "string"},
            ]},
            "includeOtherFields": False,
            "options": {},
        },
        "id": name.lower().replace(" ", "-").replace(":", ""), "name": name,
        "type": "n8n-nodes-base.set", "typeVersion": 3.4, "position": pos,
    }


def sheets_schema():
    return [{"id": c, "displayName": c, "required": False, "defaultMatch": False, "display": True,
             "type": "string", "canBeUsedToMatch": True} for c in COLUMNS]


def sticky(title, body, pos, w, h, color):
    return {
        "parameters": {"content": f"## {title}\n{body}", "height": h, "width": w, "color": color},
        "id": "note-" + title.lower().replace(" ", "-").replace(".", ""),
        "name": "Note " + title,
        "type": "n8n-nodes-base.stickyNote", "typeVersion": 1, "position": pos,
    }


def sheet_doc():
    return {"__rl": True, "value": "", "mode": "url"}


def sheet_tab():
    return {"__rl": True, "value": "gid=0", "mode": "list", "cachedResultName": "Sheet1"}


def respond(name, body, pos):
    return {
        "parameters": {
            "respondWith": "json",
            "responseBody": body,
            "options": {"responseHeaders": {"entries": [{"name": "Access-Control-Allow-Origin", "value": "*"}]}},
        },
        "id": name.lower().replace(" ", "-"), "name": name,
        "type": "n8n-nodes-base.respondToWebhook", "typeVersion": 1.1, "position": pos,
    }


nodes = [
    sticky("1. Intake", "An AP team member drops a vendor invoice on the internal invoice desk page, which sends it to this webhook. Scanned images with no text are caught early.", [-40, 140], 780, 520, 7),
    sticky("2. AI extraction", "Claude reads the invoice and returns structured data.", [760, 140], 540, 520, 4),
    sticky("3. Checks and AI quality review", "Code checks the math, duplicates, limits and missing fields. A second AI pass compares the data to the original text, scores it and proposes small clean-ups. The result goes straight back to the web page, then clean invoices skip review.", [1320, 20], 560, 700, 6),
    sticky("4. Human review", "A person approves or rejects flagged invoices from a link in Slack.", [1900, 20], 880, 700, 5),
    sticky("5. Log and notify", "Every invoice is stored in the finance Google Sheet with its status, AI score and changes, and a summary posts to Slack.", [2800, 20], 780, 700, 3),
    sticky("Live status", "The web page asks this endpoint whether a flagged invoice has been approved yet, so the client sees the decision appear.", [-40, 1080], 780, 260, 6),
    sticky("Due-soon reminder", "Every weekday morning, Slack lists approved invoices due in the next 3 days.", [-40, 760], 1360, 340, 2),

    {
        "parameters": {
            "httpMethod": "POST",
            "path": "ledgerline-invoice",
            "responseMode": "responseNode",
            "options": {"allowedOrigins": "*"},
        },
        "id": "upload-webhook", "name": "Invoice Upload",
        "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 340], "webhookId": "ledgerline-invoice",
    },
    {
        "parameters": {"httpMethod": "GET", "path": "ledgerline-status", "responseMode": "responseNode", "options": {"allowedOrigins": "*"}},
        "id": "status-webhook", "name": "Status Check",
        "type": "n8n-nodes-base.webhook", "typeVersion": 2, "position": [0, 1160], "webhookId": "ledgerline-status",
    },
    {
        "parameters": {"jsCode": LOOKUP},
        "id": "lookup", "name": "Look Up Decision",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [260, 1160],
    },
    respond("Respond Status", "={{ { status: $json.status } }}", [520, 1160]),
    {
        "parameters": {"operation": "pdf", "binaryPropertyName": "Invoice", "options": {}},
        "id": "extract-pdf", "name": "Read PDF Text",
        "type": "n8n-nodes-base.extractFromFile", "typeVersion": 1, "position": [240, 340],
    },
    ifnode("Text Found?", "={{ ($json.text || '').trim().length > 40 }}", "boolean", "true", [480, 340]),
    respond("Respond Unreadable", "={{ { ok: false, reason: 'unreadable' } }}", [480, 540]),
    slack(
        "Slack Unreadable",
        ":warning: *Invoice could not be read*\nThe PDF has no readable text (it may be a scan). Please upload a text-based PDF or enter it by hand.",
        [720, 540],
    ),

    {
        "parameters": {
            "promptType": "define",
            "text": EXTRACT_USER,
            "messages": {"messageValues": [{"message": EXTRACT_SYSTEM}]},
        },
        "id": "extract-ai", "name": "AI Extract Invoice Data",
        "type": "@n8n/n8n-nodes-langchain.chainLlm", "typeVersion": 1.5, "position": [820, 300],
    },
    {
        "parameters": {
            "model": {"__rl": True, "value": "claude-sonnet-5-5", "mode": "id"},
            "options": {"temperature": 0, "maxTokensToSample": 1500},
        },
        "id": "claude", "name": "Claude",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic", "typeVersion": 1.3, "position": [840, 520],
    },
    {
        "parameters": {
            "promptType": "define",
            "text": QC_USER,
            "messages": {"messageValues": [{"message": QC_SYSTEM}]},
        },
        "id": "qc-ai", "name": "AI Quality Review",
        "type": "@n8n/n8n-nodes-langchain.chainLlm", "typeVersion": 1.5, "position": [1340, 300],
    },
    {
        "parameters": {
            "model": {"__rl": True, "value": "claude-sonnet-5-5", "mode": "id"},
            "options": {"temperature": 0, "maxTokensToSample": 1200},
        },
        "id": "claude-qc", "name": "Claude QC",
        "type": "@n8n/n8n-nodes-langchain.lmChatAnthropic", "typeVersion": 1.3, "position": [1360, 520],
    },
    {
        "parameters": {"jsCode": APPLY_QC},
        "id": "apply-qc", "name": "Apply Quality Review",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1620, 300],
    },
    {
        "parameters": {"jsCode": PARSE},
        "id": "parse", "name": "Parse and Check",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1100, 300],
    },
    respond("Respond Result", "={{ Object.assign({ ok: true }, $json, { reviewUrl: $json.needsReview ? $execution.resumeFormUrl : '' }) }}", [1880, 300]),
    ifnode("Needs Review?", "={{ $json.needsReview }}", "boolean", "true", [2120, 300]),

    # review path
    slack(
        "Slack Review Request",
        "={{ `:mag: *Invoice needs review*\n${" + R + ".summary}\n*Why it was flagged*\n${" + R + ".reasons.map(r => '• ' + r).join('\\n')}\n<${$execution.resumeFormUrl}|Open the review form>` }}",
        [1640, 160],
    ),
    {
        "parameters": {
            "resume": "form",
            "formTitle": "Review invoice",
            "formDescription": "={{ " + R + ".summary + '. Flagged: ' + " + R + ".reasons.join('; ') }}",
            "formFields": {"values": [
                {"fieldLabel": "Decision", "fieldType": "dropdown", "requiredField": True,
                 "fieldOptions": {"values": [{"option": "Approve"}, {"option": "Reject"}]}},
                {"fieldLabel": "Note", "fieldType": "text", "requiredField": False},
            ]},
            "options": {},
        },
        "id": "wait-review", "name": "Wait for Reviewer",
        "type": "n8n-nodes-base.wait", "typeVersion": 1.1, "position": [1900, 160], "webhookId": "ledgerline-review",
    },
    ifnode("Approved?", "={{ $json.Decision }}", "string", "equals", [2140, 160], right="Approve"),
    setstatus("Set Approved", "Approved by reviewer", "={{ $json.Note || '' }}", [2400, 60]),
    setstatus("Set Rejected", "Rejected", "={{ $json.Note || '' }}", [2400, 260]),

    # clean path
    setstatus("Set Auto Approved", "Auto-approved", "", [1900, 460]),

    # converge
    {
        "parameters": {"jsCode": FINALIZE},
        "id": "finalize", "name": "Finalize Record",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [2640, 260],
    },
    {
        "parameters": {
            "resource": "sheet",
            "operation": "append",
            "documentId": sheet_doc(),
            "sheetName": sheet_tab(),
            "columns": {
                "mappingMode": "defineBelow",
                "value": {
                    "Received": "={{ $json.received }}",
                    "Submitted By": "={{ $json.submittedBy }}",
                    "Vendor": "={{ $json.vendor }}",
                    "Invoice Number": "={{ $json.invoiceNumber }}",
                    "Invoice Date": "={{ $json.invoiceDate }}",
                    "Due Date": "={{ $json.dueDate }}",
                    "Currency": "={{ $json.currency }}",
                    "Subtotal": "={{ $json.subtotal }}",
                    "Tax": "={{ $json.tax }}",
                    "Total": "={{ $json.total }}",
                    "PO Number": "={{ $json.poNumber }}",
                    "Status": "={{ $json.status }}",
                    "Review Reasons": "={{ $json.reasonsText }}",
                    "Reviewer Note": "={{ $json.reviewNote }}",
                    "AI Quality Score": "={{ $json.qcScore }}",
                    "AI Changes": "={{ $json.changesText }}",
                    "Summary": "={{ $json.summary }}",
                    "Paid": "",
                },
                "matchingColumns": [],
                "schema": sheets_schema(),
            },
            "options": {},
        },
        "id": "sheets-log", "name": "Log to Google Sheet",
        "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5, "position": [2900, 260],
    },
    slack(
        "Slack Summary",
        "={{ `${" + F + ".status === 'Rejected' ? ':x:' : ':white_check_mark:'} *Invoice ${" + F + ".status}*\n${" + F + ".summary}\nLogged to the invoice sheet.${" + F + ".reviewNote ? '\\nReviewer note: ' + " + F + ".reviewNote : ''}` }}",
        [3160, 260],
    ),

    # due-soon reminder
    {
        "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 9 * * 1-5"}]}},
        "id": "schedule", "name": "Weekday 9 AM",
        "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 900],
    },
    {
        "parameters": {
            "resource": "sheet",
            "operation": "read",
            "documentId": sheet_doc(),
            "sheetName": sheet_tab(),
            "options": {},
        },
        "id": "sheets-read", "name": "Read Invoice Sheet",
        "type": "n8n-nodes-base.googleSheets", "typeVersion": 4.5, "position": [260, 900], "alwaysOutputData": True,
    },
    {
        "parameters": {"jsCode": DUE_SOON},
        "id": "due-soon", "name": "Find Due Soon",
        "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [520, 900], "executeOnce": True,
    },
    slack("Slack Due Soon", "={{ $json.text }}", [780, 900]),
]

edges = [
    ("Invoice Upload", "Read PDF Text", 0),
    ("Read PDF Text", "Text Found?", 0),
    ("Text Found?", "AI Extract Invoice Data", 0),
    ("Text Found?", "Respond Unreadable", 1),
    ("Respond Unreadable", "Slack Unreadable", 0),
    ("AI Extract Invoice Data", "Parse and Check", 0),
    ("Parse and Check", "AI Quality Review", 0),
    ("AI Quality Review", "Apply Quality Review", 0),
    ("Apply Quality Review", "Respond Result", 0),
    ("Respond Result", "Needs Review?", 0),
    ("Needs Review?", "Slack Review Request", 0),
    ("Needs Review?", "Set Auto Approved", 1),
    ("Slack Review Request", "Wait for Reviewer", 0),
    ("Wait for Reviewer", "Approved?", 0),
    ("Approved?", "Set Approved", 0),
    ("Approved?", "Set Rejected", 1),
    ("Set Approved", "Finalize Record", 0),
    ("Set Rejected", "Finalize Record", 0),
    ("Set Auto Approved", "Finalize Record", 0),
    ("Finalize Record", "Log to Google Sheet", 0),
    ("Log to Google Sheet", "Slack Summary", 0),
    ("Status Check", "Look Up Decision", 0),
    ("Look Up Decision", "Respond Status", 0),
    ("Weekday 9 AM", "Read Invoice Sheet", 0),
    ("Read Invoice Sheet", "Find Due Soon", 0),
    ("Find Due Soon", "Slack Due Soon", 0),
]

connections = {}
for a, b, out in edges:
    c = connections.setdefault(a, {"main": []})
    while len(c["main"]) <= out:
        c["main"].append([])
    c["main"][out].append({"node": b, "type": "main", "index": 0})
connections["Claude QC"] = {"ai_languageModel": [[{"node": "AI Quality Review", "type": "ai_languageModel", "index": 0}]]}
connections["Claude"] = {"ai_languageModel": [[{"node": "AI Extract Invoice Data", "type": "ai_languageModel", "index": 0}]]}

SHIFT = {"Slack Review Request","Wait for Reviewer","Approved?","Set Approved","Set Rejected","Set Auto Approved","Finalize Record","Log to Google Sheet","Slack Summary"}
for n in nodes:
    if n["name"] in SHIFT:
        n["position"][0] += 800
for n in nodes:
    if n["name"] == "Note 3. Checks and routing":
        n["position"] = [1060, 20]; n["parameters"]["width"] = 1300
    if n["name"] == "Note 4. Human review":
        n["position"] = [2400, 20]; n["parameters"]["width"] = 1000
    if n["name"] == "Note 5. Log and notify":
        n["position"] = [3400, 20]; n["parameters"]["width"] = 1000
    if n["name"] == "Note 2. AI extraction":
        n["position"] = [760, 140]; n["parameters"]["width"] = 280

wf = {
    "name": "Northfield Hardware - AP Invoice Desk",
    "nodes": nodes,
    "connections": connections,
    "settings": {"executionOrder": "v1"},
    "pinData": {},
}

names = [n["name"] for n in nodes]
assert len(names) == len(set(names)), "duplicate node names"
ids = [n["id"] for n in nodes]
assert len(ids) == len(set(ids)), "duplicate node ids"
for k, v in connections.items():
    assert k in names, k
    for grp in v.values():
        for lst in grp:
            for c in lst:
                assert c["node"] in names, c

json.dump(wf, open("1-invoice-intake-and-approval.workflow.json", "w"), indent=2)
open("../sheet-template.csv", "w").write(",".join(COLUMNS) + "\n")
print(len(nodes), "nodes written;", len(COLUMNS), "sheet columns")
