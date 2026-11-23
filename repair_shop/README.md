# Repair Desk

A local workshop manager for customers, technicians, repair orders, and payments. The interface is in English. Choose Chinese yuan (CNY) or US dollar (USD) for the shop before the first repair order.

No AI account, API key, subscription, or internet connection is needed to use the installed app. All assets and records stay on this computer.

## Open on this computer

Double-click **Start Repair Desk.cmd**, then open **http://127.0.0.1:5001/**. Keep the launcher window open while working. If the app is already running, open the URL directly. Close the launcher window or press Ctrl+C to stop a server started with it.

The launcher uses this folder's `.venv` if available, otherwise the existing Python environment in the parent project. It does not load the study application's configuration or API credentials.

From PowerShell in this directory:

```powershell
& '../.venv/Scripts/python.exe' run.py
```

If port 5001 is occupied, use `run.py --port 5003` and open http://127.0.0.1:5003/. Do not stop an unrelated application to free a port.

## First repair

1. Open **Shop currency**, choose CNY or USD, and select **Save currency**. The currency can change only when no repair orders exist; the app never converts amounts.
2. Open **Customers → Add customer**. Enter the customer's name and phone number. Email is optional.
3. Open **Technicians → Add technician**. Enter the technician's name and phone number; keep them Active to receive assignments.
4. Open **Repair Orders → New repair order**. Select the customer, enter the device and problem, assign a technician if known, and enter the agreed price. A price of 0 is allowed until the cost is known.
5. Use **Start repair**, then **Mark ready**. If more work is needed, choose **Return to repair**.
6. Use **Add payment** for deposits or the full price. Enter the amount, payment date, and optional note. The app calculates what remains.
7. When Ready and fully paid, choose **Deliver device** and review the confirmation. Delivered orders and their payments become read-only.

## Rules to know

- A technician is required before repair work starts. Inactive technicians keep their existing orders but cannot receive new assignments.
- Each customer's phone number must be unique in the customer list. Technician phone numbers are unique separately. Spaces, parentheses, hyphens, and Arabic digits are normalized; local and international country-code forms are not automatically merged.
- Money accepts at most two decimal places, without thousands separators, and uses exact integer arithmetic. The maximum entered amount is 9,999,999,999.99. A payment must be positive and cannot exceed the remaining balance.
- Payment dates run from the order's local reception date through the current local date. Check the computer's clock if dates appear wrong.
- After the first payment, the order's customer is fixed, even if that payment is removed. A price cannot be reduced below the amount already paid.
- Incorrect payments can be deleted with confirmation before delivery. Enter a replacement payment afterward. There is no electronic payment processing or refund function.
- An order can be deleted only while Received and without payments. Customers can be deleted only without linked orders. Technicians are deactivated, not deleted.
- Dashboard totals are all-time recorded collections and outstanding balances; they are not profit, tax, or monthly accounting reports.

## Storage and recovery

Records are saved in `data/repair_shop.sqlite3` inside this directory. The original study application has a separate database and remains intact.

To make a manual backup, stop the Repair Desk server first, then copy this database to a safe location. Automatic backup, cloud sync, accounts, public hosting, attachments, and exports are outside this release.

Validation or failed saving shows an English message without claiming success. Unsaved inputs are not guaranteed after leaving or refreshing the page. If a form expires after a server restart, refresh it before entering a new operation. Use only one active browser session for the shop.

## Set up on another computer

Install Python 3.12 or later. From the directory containing this README:

```powershell
python -m venv .venv
& '.venv/Scripts/python.exe' -m pip install -r requirements.txt
& '.venv/Scripts/python.exe' run.py
```

Internet access is needed for initial dependency installation unless packages are already available. Routine use needs no internet. On macOS/Linux, use `.venv/bin/python` and run `run.py` directly.

## Development and verification

The approved requirements are in SPEC.md, and implementation/test decisions are in IMPLEMENTATION_PLAN.md. Tests were authored and exercised before application implementation.

```powershell
& '../.venv/Scripts/python.exe' -m pytest -q
```

For a new environment, install requirements-dev.txt first. Browser acceptance checks use Node, Playwright, and Microsoft Edge: `node tests/browser_check.cjs` with Playwright available in NODE_PATH. They start an isolated server and a temporary database; no demo records are inserted into the user's shop.

See reports/VERIFICATION.md for results and limitations. Preview screenshots other than live-dashboard.png use synthetic customer and repair records.
