"""Local-only Flask presentation layer. No AI services or external assets."""
from datetime import datetime
from pathlib import Path
import secrets
import sqlite3
from urllib.parse import urlsplit
from uuid import uuid4

from flask import Flask, flash, redirect, render_template, request, session, url_for
from werkzeug.exceptions import HTTPException

from .domain import DomainError, STATUSES
from .store import Store


def create_app(database_path=None, clock=None):
    app = Flask(__name__)
    app.config.update(SECRET_KEY=secrets.token_hex(32), MAX_CONTENT_LENGTH=100_000,
                      SESSION_COOKIE_NAME='repair_desk_session', SESSION_COOKIE_HTTPONLY=True,
                      SESSION_COOKIE_SAMESITE='Strict')
    shop = Store(database_path or Path(__file__).parent / 'data' / 'repair_shop.sqlite3', clock=clock)
    app.extensions['shop'] = shop

    @app.before_request
    def boundary():
        if urlsplit(request.host_url).hostname not in ('localhost', '127.0.0.1', '::1'):
            raise DomainError('Open Repair Desk on this computer.', status=403)
        session.setdefault('csrf_token', secrets.token_urlsafe(32))
        if request.method == 'POST':
            origin = request.headers.get('Origin')
            if origin and origin != request.host_url.rstrip('/'):
                raise DomainError('Submit changes from the local application.', status=403)
            token = request.form.get('csrf_token', '')
            if not secrets.compare_digest(token, session['csrf_token']):
                raise DomainError('This form has expired. Refresh the page and try again.', status=403)

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'same-origin',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
        return response

    @app.context_processor
    def shared():
        try:
            settings = shop.settings()
        except sqlite3.Error:
            settings = {'currency': None, 'locked': True}
        return dict(settings=settings, statuses=STATUSES, errors={}, error=None, data={},
                    csrf_token=session.get('csrf_token', ''), current_path=request.path)

    @app.template_filter('cash')
    def cash(value):
        return f'{int(value)//100}.{int(value)%100:02d}'

    @app.template_filter('date_label')
    def date_label(value):
        if not value:
            return '—'
        return datetime.fromisoformat(value).strftime('%d %b %Y')

    @app.template_filter('status_class')
    def status_class(value):
        return value.lower().replace(' ', '-')

    def page(template, **values):
        return render_template(template, **values)

    def fields():
        return {key: value for key, value in request.form.items() if key not in ('csrf_token', 'request_token', 'confirmed')}

    def attempt(action, render, success, message):
        try:
            result = action()
        except DomainError as error:
            return render(error), error.status
        except (sqlite3.Error, OSError):
            error = DomainError('Your change could not be saved. Your entries are still here. Check disk space and try again.', status=503)
            return render(error), 503
        flash(message, 'success')
        return redirect(success(result), code=303)

    def require_confirmation():
        if request.form.get('confirmed') != 'yes':
            raise DomainError('Review and confirm this action first.')

    @app.errorhandler(DomainError)
    def domain_error(error):
        return page('error.html', title='Record not found' if error.status == 404 else 'Action not completed',
                    message=error.message), error.status

    @app.errorhandler(sqlite3.Error)
    @app.errorhandler(OSError)
    def storage_error(error):
        return page('error.html', title='Your records are temporarily unavailable',
                    message='Check available disk space and try again. No change has been confirmed.'), 503

    @app.errorhandler(HTTPException)
    def http_error(error):
        return page('error.html', title='Page not available', message='Return to the dashboard to continue.'), error.code

    @app.errorhandler(Exception)
    def unexpected(error):
        app.logger.error('Unexpected request failure: %s', type(error).__name__)
        return page('error.html', title='Something went wrong', message='Your change was not confirmed. Refresh the page to check your saved records.'), 500

    @app.get('/')
    def dashboard():
        return page('dashboard.html', title='Dashboard', summary=shop.dashboard(), people_count=len(shop.people('customers')))

    @app.route('/currency', methods=['GET', 'POST'])
    def currency():
        def render(error=None):
            return page('currency.html', title='Shop currency', data=fields() if request.method == 'POST' else shop.settings(), error=error)
        if request.method == 'POST':
            return attempt(lambda: shop.set_currency(request.form.get('currency', '')), render,
                           lambda _: url_for('dashboard'), 'Shop currency saved.')
        return render()

    @app.get('/customers')
    def customers():
        return page('people.html', title='Customers', kind='customers', people=shop.people('customers'))

    @app.get('/technicians')
    def technicians():
        return page('people.html', title='Technicians', kind='technicians', people=shop.people('technicians'))

    @app.route('/customers/new', methods=['GET', 'POST'])
    @app.route('/customers/<int:id>/edit', methods=['GET', 'POST'])
    @app.route('/technicians/new', methods=['GET', 'POST'])
    @app.route('/technicians/<int:id>/edit', methods=['GET', 'POST'])
    def person_form(id=None):
        kind = 'customers' if request.path.startswith('/customers') else 'technicians'
        original = shop.person(kind, id) if id else {'active': '1'}
        label = 'customer' if kind == 'customers' else 'technician'
        def render(error=None):
            return page('person_form.html', title=('Edit ' if id else 'New ') + label, kind=kind, record_id=id,
                        data=fields() if request.method == 'POST' else original, error=error,
                        errors=error.fields if error else {})
        if request.method == 'POST':
            return attempt(lambda: shop.save_person(kind, fields(), id), render,
                lambda pid: url_for('customer_detail', id=pid) if kind == 'customers' else url_for('technicians'),
                label.capitalize() + ' saved.')
        return render()

    @app.get('/customers/<int:id>')
    def customer_detail(id):
        person = shop.person('customers', id)
        return page('customer.html', title=person['name'], person=person,
                    orders=[o for o in shop.orders() if o['customer_id'] == id])

    @app.route('/customers/<int:id>/delete', methods=['GET', 'POST'])
    def customer_delete(id):
        customer = shop.person('customers', id)
        return confirmation('Delete customer?', f"Delete {customer['name']} from your customer list? Customers with orders cannot be deleted.",
            'Delete customer', url_for('customer_detail', id=id), lambda: shop.delete_customer(id), url_for('customers'), 'Customer deleted.', danger=True)

    @app.get('/orders')
    def orders():
        filters = {key: request.args.get(key, '') for key in ('q', 'status', 'tech')}
        return page('orders.html', title='Repair Orders', orders=shop.orders(**filters), filters=filters,
                    technicians=shop.people('technicians'), total=len(shop.orders()))

    @app.route('/orders/new', methods=['GET', 'POST'])
    @app.route('/orders/<int:id>/edit', methods=['GET', 'POST'])
    def order_form(id=None):
        original = shop.order(id) if id else {}
        if id:
            shop.mutable(original)
            original['price'] = cash(original['price_minor'])
        if not shop.settings()['currency'] and request.method == 'GET':
            flash('Choose the shop currency before creating an order.', 'info')
            return redirect(url_for('currency'))
        token = request.form.get('request_token', '') if request.method == 'POST' else uuid4().hex
        def render(error=None):
            return page('order_form.html', title='Edit order' if id else 'New repair order', record=original, record_id=id,
                        data=fields() if request.method == 'POST' else original, error=error, errors=error.fields if error else {},
                        request_token=token, customers=shop.people('customers'), technicians=shop.people('technicians'))
        if request.method == 'POST':
            def save():
                if id:
                    shop.update_order(id, fields())
                    return id
                return shop.create_order(fields(), token)
            return attempt(save, render, lambda oid: url_for('order_detail', id=oid), 'Repair order saved.')
        return render()

    @app.get('/orders/<int:id>')
    def order_detail(id):
        return page('order.html', title='Repair order', order=shop.order(id))

    def confirmation(title, message, action_label, cancel_url, action, success_url, success_message, danger=False, hidden=None):
        def render(error=None):
            return page('confirm.html', title=title, message=message, action_label=action_label,
                        cancel_url=cancel_url, danger=danger, hidden=hidden or {}, error=error)
        if request.method == 'POST':
            def confirmed():
                require_confirmation()
                return action()
            return attempt(confirmed, render, lambda _: success_url, success_message)
        return render()

    @app.route('/orders/<int:id>/status', methods=['GET', 'POST'])
    def status(id):
        doc = shop.order(id)
        value = request.form.get('status') if request.method == 'POST' else request.args.get('status')
        if value == 'Delivered':
            return confirmation('Deliver device?', f"Confirm delivery of {doc['order_no']} to {doc['customer_name']}. The order and its payments will become read-only.",
                'Confirm delivery', url_for('order_detail', id=id), lambda: shop.transition(id, value), url_for('order_detail', id=id),
                'Device delivered. This order is now read-only.', hidden={'status': value})
        if request.method != 'POST':
            raise DomainError('Choose a status action from the order page.')
        return attempt(lambda: shop.transition(id, value),
                       lambda error: page('order.html', title=doc['order_no'], order=shop.order(id), error=error),
                       lambda _: url_for('order_detail', id=id), 'Order status updated.')

    @app.route('/orders/<int:id>/delete', methods=['GET', 'POST'])
    def order_delete(id):
        doc = shop.order(id)
        return confirmation('Delete repair order?', f"Delete {doc['order_no']} for {doc['customer_name']}? Only received orders without payments can be deleted.",
            'Delete order', url_for('order_detail', id=id), lambda: shop.delete_order(id), url_for('orders'), 'Repair order deleted.', danger=True)

    @app.route('/orders/<int:id>/payments/new', methods=['GET', 'POST'])
    def payment_form(id):
        doc = shop.order(id)
        shop.mutable(doc)
        token = request.form.get('request_token', '') if request.method == 'POST' else uuid4().hex
        def render(error=None):
            return page('payment_form.html', title='Add payment', order=doc, request_token=token,
                        data=fields() if request.method == 'POST' else {'pay_date': shop.clock().date().isoformat()},
                        error=error, errors=error.fields if error else {}, today=shop.clock().date().isoformat())
        if request.method == 'POST':
            return attempt(lambda: shop.add_payment(id, fields(), token), render,
                           lambda _: url_for('order_detail', id=id), 'Payment recorded.')
        return render()

    @app.route('/orders/<int:id>/payments/<int:payment_id>/delete', methods=['GET', 'POST'])
    def payment_delete(id, payment_id):
        doc = shop.order(id)
        payment = next((p for p in doc['payments'] if p['id'] == payment_id), None)
        if not payment:
            raise DomainError('This payment could not be found on this order.', status=404)
        amount = shop.settings()['currency'] + ' ' + cash(payment['amount_minor'])
        return confirmation('Delete payment?', f"Remove the payment of {amount} from {doc['order_no']}? Its outstanding balance will increase.",
            'Delete payment', url_for('order_detail', id=id), lambda: shop.delete_payment(id, payment_id),
            url_for('order_detail', id=id), 'Payment deleted.', danger=True)

    return app
