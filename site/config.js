// 1) Paste the Production URL of the "Invoice Upload" webhook node (ends in /webhook/ledgerline-invoice).
//    Leave as-is to run the page in preview mode with sample answers.
window.LEDGERLINE_UPLOAD_URL = 'https://chaparraldrai.app.n8n.cloud/webhook/ledgerline-invoice';

// 2) Optional: the link to the finance Google Sheet. Adds an "Open the finance sheet" button on results.
window.LEDGERLINE_SHEET_URL = '';

// 3) Demo login for the internal app. This is NOT real security (it is visible in the page source).
//    Change these to your own email and a simple password.
window.LEDGERLINE_LOGIN = {
  email: 'kerwin.alleyne@gmail.com',
  password: 'invoices123',
  userName: 'Kerwin A',            // the fictional employee who is "signed in"
  userRole: 'Accounts Payable',
  showHint: true                     // shows the demo login under the form
};
