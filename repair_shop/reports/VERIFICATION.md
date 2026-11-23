# Repair Desk — verification record

Completed: 2026-11-02 (Asia/Shanghai). Approved requirements: SPEC.md v0.2.

## SDD evidence

The specification was approved before the implementation plan. The plan and pytest contracts were written before application files. An initial test-fixture directory issue was corrected before implementation; the validated initial run collected all 67 tests and produced **67 expected failures, no collection/setup errors**, because implementation modules were absent. See initial-tests.xml.

The browser acceptance script was also defined before UI implementation. A later network-failure regression was reproduced before adding form recovery.

## Automated results

- **67 pytest tests passed** in the final run (5.83 seconds). Tests cover input normalization, Unicode data, exact money arithmetic, both currencies, persistence and currency locking, relationships, customer/technician restrictions, order lifecycle, payment dates/balances, delivered-order immutability, deletion limits, combined search, dashboard totals, replay and concurrent submissions, transactional rollback, CSRF/origin/host restrictions, escaped output, and safe errors with preserved inputs. See current-tests.xml.
- Pytest reported one environment warning: its optional cache could not update an existing cache file. This did not affect test execution or the JUnit report. Application data was not involved.
- **11 browser checks passed** in Microsoft Edge. The journey covers currency selection, customer validation and Unicode names, technician creation with the keyboard, order creation, a simulated failed network request with retained inputs and the same submission token, partial payment, cancellation of deletion, final settlement, delivery confirmation, reload, and search/clear filters. See browser-results.json.
- The browser suite checks seven main views at **360, 768, and 1440 CSS pixels**, including forms and settings. No horizontal page overflow was found. Rendered visible text passed measured contrast checks on the checked views. No external browser requests or uncaught JavaScript errors were observed.

## Problems found and resolved

- Browser form submissions were rejected under the initial referrer policy. Using same-origin referrer policy preserves legitimate local form requests while retaining CSRF and origin validation.
- Native navigation on a failed POST could hide the open form. Enhanced local POST handling now retains values and the request token on connection failure, allows retry, and prevents duplicate saved orders/payments through transactional receipts.
- The currency action is available in the top bar as well as desktop navigation, so it remains reachable on narrow screens.
- Browser selectors were corrected to inspect the specific phone error and accommodate required/optional field labels; no application rule was weakened to satisfy tests.

## Visual inspection and isolation

Inspected desktop dashboard, mobile delivered order, and mobile new-order form screenshots. Controls, labels, payment amounts, and Unicode customer names were readable; layouts did not clip primary actions.

Test screenshots show synthetic records, including an intentionally inert script string used to test text escaping. These are not production/customer data. Tests use unique databases under .test-work and never seed the real shop database.

A content-hash comparison confirmed that the previous application's .env, study database, HTML, CSS, and JavaScript were unchanged (five files). Repair Desk does not read the API key or contact an AI provider.

The actual local server was started on http://127.0.0.1:5001/ and independently verified to return HTTP 200 with the Repair Desk dashboard. live-dashboard.png captures this real, unseeded workspace. The user still chooses CNY or USD; no currency or customer records were entered on their behalf.

## Scope and limitations

This is a single-user local application. It has no public deployment, authentication roles, automatic backups, tax accounting, electronic payment processing, or cloud synchronization. Keep the server local and follow README.md for a manual database backup. Unsaved inputs are not guaranteed after closing or refreshing a page. A restarted server invalidates old forms; refresh before submitting.

The passing checks establish the tested behavior, not compatibility with every browser, operating system, or possible data size. The local Flask server is used for this one-computer workflow.
