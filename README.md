# Northfield Hardware demo: internal AP invoice desk with AI review

A portfolio demo of an internal tool for a fictional company. The accounts payable team drops in vendor invoices (PDFs). The system reads them with AI, has a second AI pass check the work, runs rule checks, stores everything in a finance Google Sheet, and sends flagged invoices to a reviewer in Slack.

```
site/index.html        Northfield Hardware company page (public home page, with a Login button)
site/portal.html       Invoice Desk: demo login + drop-in page with live progress and results
site/case-study.html   One-page write-up
site/config.js         Webhook URL, optional sheet link, demo login
n8n/1-invoice-intake-and-approval.workflow.json   The workflow (36 nodes, 7 are sticky-note labels)
n8n/build_invoice.py   Regenerates the JSON if you edit prompts or limits
sheet-template.csv     Header row for the finance Google Sheet (18 columns)
```

There are no sample invoices in this package. Use any text-based invoice PDFs (not scans, and not real client data for a public demo). Make a few test invoices yourself, such as one clean one, one over $1,000, and one where the line items do not add up to the subtotal.

The workflow was built from n8n's node format but has not been run inside n8n yet. Expect small field fixes on first import.

## What happens to an invoice
1. **Upload:** the page sends the PDF to an n8n webhook, along with who submitted it.
2. **Read:** the PDF text is extracted. Scans with no text are rejected with a clear message.
3. **AI extraction:** Claude returns vendor, invoice number, dates, PO, subtotal, tax, total and line items. It copies numbers exactly and never calculates.
4. **Rule checks (code):** missing fields, line items vs subtotal, subtotal + tax vs total, over $1,000, no PO over $500, past due, duplicate invoice.
5. **AI quality review:** a second Claude call compares the extracted data to the original text, gives a 0 to 100 confidence score, flags real problems, and may make small clean-ups to vendor, PO or payment terms (for example fixing capitalization). It can never change amounts, dates or invoice numbers. A low score or a concern sends the invoice to review.
6. **Reply to the page:** the result goes back right away, so the page shows what was read, what was checked, the AI score and any changes.
7. **Route:** clean invoices are auto-approved. Flagged ones post to Slack with the reasons and a review link, then wait for Approve or Reject plus a note.
8. **Store:** every invoice is appended to the Google Sheet with status, reasons, reviewer note, AI score and AI changes. A summary posts to Slack.
9. **Reminder:** weekdays at 9 am, approved unpaid invoices due within 3 days are posted to Slack.

## Setup (about 25 minutes)
1. Create a Google Sheet. Paste the row from `sheet-template.csv` as row 1 (18 columns).
2. In Slack, create `#invoice-approvals` and invite your Lead Alerts bot (`/invite @Lead Alerts`).
3. In n8n: Import from file. Connect credentials: both **Claude** model nodes (Anthropic), all **Slack** nodes (Access Token), both **Google Sheets** nodes (Google sign-in, then pick your sheet and first tab).
4. Open the **Invoice Upload** webhook node. Allowed Origins is already `*` for the demo.
5. Publish the workflow and copy the **Production URL** (ends in `/webhook/ledgerline-invoice`).
6. Open `site/config.js`. Paste the webhook URL. Optionally paste the finance sheet link (adds an "Open the finance sheet" button). Set your own demo email and a simple password, and the employee name shown after sign-in. The login is for show only and is visible in the page source.
7. Run the site: `cd site && python3 -m http.server 8080`, then open http://localhost:8080. The **Login** button goes to `portal.html`.

Without a webhook URL the page runs in **Preview mode** with rotating canned results (a clean invoice with an AI change, one with a math problem, one over the limit), so you can see the design first. Add `?mock=1` to force it.

Quick test without the page: `curl -X POST "YOUR_URL" -F "Invoice=@your-invoice.pdf" -F "submittedBy=Dana Reyes"`

## Live approval status on the page
After a flagged invoice is sent, the page shows "Waiting for the reviewer" and checks a second webhook (`Status Check`, path `ledgerline-status`) every few seconds. When you approve or reject in the Slack review form, the banner and the log row change. The status URL is built from the upload URL automatically. This only works once the workflow is published. Duplicate detection also only works in published runs.

## Recording order (60 seconds)
Show the company home page and click Login (5s) > sign in and drop in an invoice, show the steps, results and AI score (20s) > drop in a flagged one, show the Slack message, approve it, watch the page update (20s) > the Google Sheet row and the n8n canvas with the green run (15s).
