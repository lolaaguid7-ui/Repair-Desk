# Repair Desk — implementation and test plan

Approved baseline: SPEC.md v0.2, 2026-11-01. English interface; one local user; CNY or USD selected before orders. No network services or AI credentials.

## Architecture

- Python 3.12+, Flask (existing installed 3.1.3), standard-library SQLite. Standalone package inside repair_shop with its own data directory and launcher on 127.0.0.1:5001.
- Server-rendered Jinja templates with shared navy navigation, blue actions, responsive tables/cards, and local CSS/SVG. Local JavaScript enhances POST forms to retain inputs and submission identity on network failures; ordinary forms remain usable without JavaScript. Confirmation uses review pages.
- Domain validators normalize Unicode digits, validate text/phone/email/money, and return English field errors. Money uses integer minor units; JSON/float conversion is never used for calculations. Amounts above 9,999,999,999.99 are rejected to keep input and arithmetic bounded.
- A Store/service layer owns SQLite transactions and foreign-key constraints. BEGIN IMMEDIATE serializes mutations and rechecks currency, balance, status, and references before writing. Each connection has foreign_keys enabled and a bounded busy timeout.
- Tables: settings, customers, technicians, orders, payments, receipts. Customer and technician phones have separate unique constraints. orders carries customer_locked once the first payment succeeds, even if that payment is later removed. Delivered orders and their payments cannot be modified. Receipts prevent replay from recreating deleted resources.
- Idempotent order/payment creation takes an opaque form token. Receipts bind action, token, payload fingerprint, and resulting resource ID in the same transaction. Same token/body replays the prior result; different body conflicts. Validation or failed writes do not reserve the token. Refresh after success uses redirect-after-post.
- Currency is an explicit setting. It is changeable only without any saved orders, persists across restart, and is applied consistently to all monetary labels. No conversion.
- Request boundary: loopback hosts only, same-origin checks on writes, session CSRF token in forms, escaped template output, restrictive CSP, no external assets. Raw errors never reach the UI. Secrets from the old application are never read.
- Forms preserve submitted values and their creation token on validation/storage failure. Every destructive action and delivery uses a review page with explicit confirmation and a cancel link. This also works with the keyboard and without JavaScript.
- Local timestamps come from the computer's timezone, stored with an offset. A clock can be injected in tests. Form date defaults and validation use that same clock; date display is unambiguous (e.g. 01 Nov 2026).

## Public contracts defined before implementation

Store(path, clock=None) methods: settings(), set_currency(code), people(kind), person(kind,id), save_person(kind,data,id=None), delete_customer(id), orders(q='',status='',tech=''), order(id), create_order(data,token), update_order(id,data), transition(id,status), delete_order(id), add_payment(id,data,token), delete_payment(id,payment_id), dashboard(). Each returns dictionaries/lists or an ID; DomainError carries message/fields/status. Missing records raise 404. Business validation uses 400 or 409. SQLite errors propagate to Flask's safe storage handler.

Routes: /, /orders, /orders/new, /orders/<id>, /orders/<id>/edit, /orders/<id>/status, /orders/<id>/delete, /orders/<id>/payments/new, /orders/<id>/payments/<payment_id>/delete, /customers, /customers/new, /customers/<id>, /customers/<id>/edit, /customers/<id>/delete, /technicians, /technicians/new, /technicians/<id>/edit, /currency. Mutations accept POST and CSRF only; confirmation routes show a GET review page before POST. No GET changes data.

## Testing sequence and coverage

1. Write pytest unit and integration tests before application files. Use delayed imports to produce explicit expected failures while implementation is absent, rather than collection errors. Confirm tests collect and assertions express spec behavior. Preserve initial JUnit report.
2. Domain tests cover normalization, Unicode names, text limits, email validation, exact amounts, negative/zero/precision/separator rejection (AC02/06).
3. Store tests cover both currencies and persistence, customer/technician relations, phone uniqueness, lifecycle transitions, customer locking, immutable delivery, payment date/balance rules, replay including deleted resources, combined search/filter/sort, delete restrictions, dashboard arithmetic, transactional rollback and concurrent submissions (AC01–12/15–16).
4. Flask tests cover page delivery, English markup, local assets, offline operation, CSRF/host/origin boundary, full form journey, field errors and input retention, confirmation GET/cancel behavior, missing records, XSS escaping, and safe storage failures (AC01/02/10/12–14).
5. Before UI implementation, define a browser acceptance script using a temporary database and isolated server. Verify currency selection, customer/fixer creation, order editing and statuses, partial/full payment, cancellation/delivery, both currency displays, no external requests, form retry identity, keyboard flow, and no horizontal overflow at 360/768/1440 pixels. Capture previews and measure visible-text contrast.
6. Implement, run pytest and browser checks, inspect screenshots, fix observed issues, then run relevant checks again. Verify the old study app data/config hashes are unchanged. Start the real app with an empty database and provide its local URL and launcher.

## Deliverables

Source and tests, README with launch/usage/storage instructions, Start Repair Desk.cmd, requirements files, initial/final pytest reports, browser result summary, desktop/mobile screenshots, and a concise verification record under reports/. Test databases are separate from real shop data.
