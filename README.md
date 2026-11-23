# Repair Desk

A local computer repair shop manager built with Python, Flask, SQLite, HTML, CSS, and JavaScript. English interface with a choice of CNY or USD.

## Features

- Customer and technician records
- Repair orders from Received through Delivered
- Partial payments and exact outstanding balances
- Dashboard, search, and filters
- Local storage without a paid API

## Run locally

Install Python 3.12 or later, then run these commands from the repository root:

```powershell
cd repair_shop
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe run.py
```

Open http://127.0.0.1:5001/ in your browser. On Windows, after setup you can also double-click `repair_shop/Start Repair Desk.cmd`.

On macOS or Linux, replace `.venv\Scripts\python.exe` with `.venv/bin/python`.

The app creates a new local database on first run. Customer records, payment records, API keys, and private configuration are not included in this repository.

## Documentation and presentation

- [User guide](repair_shop/README.md)
- [Specification](repair_shop/SPEC.md)
- [Implementation plan](repair_shop/IMPLEMENTATION_PLAN.md)
- [Verification record](repair_shop/reports/VERIFICATION.md)
- [Standalone presentation](repair_shop/presentation/index.html) — download and open in a browser

## Tests

From the `repair_shop` directory:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.venv\Scripts\python.exe -m pytest -q
```

## Hosting scope

This version runs on one computer for one user. GitHub stores the source code; GitHub Pages cannot run the Flask application or SQLite business workflow. Public deployment would need a suitable Python host and additional authentication and deployment work.
