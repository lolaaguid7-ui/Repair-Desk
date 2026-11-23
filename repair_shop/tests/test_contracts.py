"""Executable acceptance contracts, authored before the implementation."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import importlib
import sqlite3
from uuid import uuid4

import pytest

NOW = datetime(2026, 11, 1, 12, 30, tzinfo=timezone(timedelta(hours=8)))


def module(name):
    try:
        return importlib.import_module('repair_shop.' + name)
    except ModuleNotFoundError as error:
        if error.name.startswith('repair_shop'):
            pytest.fail('Expected SDD failure: implementation is not present yet.', pytrace=False)
        raise


def store(tmp_path, currency='CNY'):
    result = module('store').Store(tmp_path / 'shop.db', clock=lambda: NOW)
    if currency:
        result.set_currency(currency)
    return result


def person(s, kind='customers', **values):
    data = {'name': 'Alex Chen', 'phone': '+86 138-0013-8000', 'email': '', 'active': True}
    data.update(values)
    return s.save_person(kind, data)


def order_data(s, **values):
    customers, technicians = s.people('customers'), s.people('technicians')
    data = {'customer_id': customers[0]['id'] if customers else person(s),
            'tech_id': technicians[0]['id'] if technicians else person(s, 'technicians', name='Jordan Lee'),
            'device_type': 'Laptop', 'brand': 'Dell XPS', 'problem': 'Device does not start.', 'price': '150.00'}
    data.update(values)
    return data


def order(s, **values):
    return s.create_order(order_data(s, **values), uuid4().hex)


def payment(s, oid, amount='50', **values):
    data = {'amount': amount, 'pay_date': NOW.date().isoformat(), 'note': ''}
    data.update(values)
    return s.add_payment(oid, data, uuid4().hex)


def rejected(call, status=None):
    with pytest.raises(module('domain').DomainError) as error:
        call()
    if status:
        assert error.value.status == status
    return error.value


@pytest.mark.parametrize('raw,expected', [(' +٨٦ (١٣٨)-٠٠١٣ ٨٠٠٠ ', '+8613800138000'), ('1234567', '1234567'), ('۱۲۳۴۵۶۷', '1234567')])
def test_phone_normalization(raw, expected):
    assert module('domain').phone(raw) == expected


@pytest.mark.parametrize('raw', ['', '123456', '1' * 16, '12a45678', '12+345678', '++1234567'])
def test_invalid_phone(raw):
    rejected(lambda: module('domain').phone(raw))


@pytest.mark.parametrize('raw,expected', [('0', 0), ('150.00', 15000), ('٢٥٫٥٠', 2550), ('0.01', 1), ('9999999999.99', 999999999999)])
def test_exact_money(raw, expected):
    assert module('domain').money(raw) == expected


@pytest.mark.parametrize('raw', ['-1', '0.001', '1,000', '1e3', 'NaN', 'Infinity', '', '10000000000', True, 1.23])
def test_invalid_money(raw):
    rejected(lambda: module('domain').money(raw))


def test_empty_install_and_explicit_currency(tmp_path):
    s = store(tmp_path, None)
    assert s.settings() == {'currency': None, 'locked': False}
    assert not s.orders() and not s.people('customers') and not s.people('technicians')
    assert sum(s.dashboard()['counts'].values()) == 0
    rejected(lambda: order(s))
    for invalid in ['SAR', '', 'cny', 'EUR']:
        rejected(lambda: s.set_currency(invalid))
    assert not s.orders()


@pytest.mark.parametrize('currency', ['CNY', 'USD'])
def test_currency_persistence_and_lock(tmp_path, currency):
    s = store(tmp_path, currency)
    s.set_currency('USD' if currency == 'CNY' else 'CNY')
    s.set_currency(currency)
    oid = order(s)
    restarted = module('store').Store(tmp_path / 'shop.db', clock=lambda: NOW)
    assert restarted.settings() == {'currency': currency, 'locked': True}
    rejected(lambda: restarted.set_currency('USD' if currency == 'CNY' else 'CNY'))
    assert restarted.order(oid)['price_minor'] == 15000
    restarted.delete_order(oid)
    restarted.set_currency('USD' if currency == 'CNY' else 'CNY')


@pytest.mark.parametrize('kind', ['customers', 'technicians'])
def test_people_normalization_unique_phone_and_unicode(tmp_path, kind):
    s = store(tmp_path)
    pid = person(s, kind, name=' 李明 أحمد ')
    assert s.person(kind, pid)['name'] == '李明 أحمد'
    assert s.person(kind, pid)['phone'] == '+8613800138000'
    rejected(lambda: person(s, kind, name='Other', phone='+٨٦١٣٨٠٠١٣٨٠٠٠'))
    assert len(s.people(kind)) == 1
    s.save_person(kind, {'name': 'Updated', 'phone': '1234567', 'email': 'a@example.com', 'active': True}, pid)
    assert s.person(kind, pid)['name'] == 'Updated'


@pytest.mark.parametrize('values', [{'name': 'x'}, {'name': 'x' * 101}, {'phone': 'bad'}, {'email': 'not-an-email'}, {'email': 'x' * 255}])
def test_invalid_customer_fields(tmp_path, values):
    s = store(tmp_path)
    error = rejected(lambda: person(s, **values))
    assert error.fields and not s.people('customers')


def test_people_boundary_lengths_and_independent_phone_lists(tmp_path):
    s = store(tmp_path)
    cid = person(s, name='李明')
    person(s, 'technicians', name='x' * 100)
    assert len(s.people('customers')) == len(s.people('technicians')) == 1
    oid = order(s)
    rejected(lambda: s.delete_customer(cid))
    s.delete_order(oid)
    s.delete_customer(cid)
    rejected(lambda: s.person('customers', cid), 404)


@pytest.mark.parametrize('values', [{'customer_id': 999}, {'tech_id': 999}, {'device_type': 'x'}, {'device_type': 'x' * 61}, {'brand': 'x' * 101}, {'problem': 'tiny'}, {'problem': 'x' * 2001}, {'price': '-1'}])
def test_invalid_order_never_saved(tmp_path, values):
    s = store(tmp_path)
    rejected(lambda: order(s, **values))
    assert not s.orders()


def test_order_boundaries_and_snapshot(tmp_path):
    s = store(tmp_path)
    oid = order(s, device_type='PC', brand='x' * 100, problem='x' * 2000, price='0', tech_id='')
    doc = s.order(oid)
    assert doc['status'] == 'Received' and doc['order_no'] and doc['received_at'] == NOW.isoformat()
    assert doc['delivered_at'] is None and doc['paid_minor'] == doc['balance_minor'] == 0
    rejected(lambda: s.transition(oid, 'In Repair'))


def test_inactive_technician_existing_work_and_reassignment(tmp_path):
    s = store(tmp_path)
    data = order_data(s)
    oid = s.create_order(data, uuid4().hex)
    tech = s.person('technicians', data['tech_id'])
    s.save_person('technicians', {**tech, 'active': False}, tech['id'])
    rejected(lambda: s.create_order(data, uuid4().hex))
    s.transition(oid, 'In Repair')
    s.update_order(oid, {**data, 'brand': 'Lenovo'})
    rejected(lambda: s.update_order(oid, {**data, 'tech_id': ''}))
    second = person(s, 'technicians', name='Sam Wu', phone='12345678')
    s.update_order(oid, {**data, 'tech_id': second})
    rejected(lambda: s.update_order(oid, data))


@pytest.mark.parametrize('currency', ['CNY', 'USD'])
def test_lifecycle_balances_and_immutable_delivery(tmp_path, currency):
    s = store(tmp_path, currency)
    data = order_data(s)
    oid = s.create_order(data, uuid4().hex)
    rejected(lambda: s.transition(oid, 'Ready'))
    s.transition(oid, 'In Repair')
    s.transition(oid, 'Ready')
    s.transition(oid, 'In Repair')
    s.transition(oid, 'Ready')
    pid = payment(s, oid, '50.00')
    payment(s, oid, '٢٥٫٥٠')
    doc = s.order(oid)
    assert (doc['paid_minor'], doc['balance_minor']) == (7550, 7450)
    rejected(lambda: s.transition(oid, 'Delivered'))
    payment(s, oid, '74.50')
    s.transition(oid, 'Delivered')
    assert s.order(oid)['delivered_at'] == NOW.isoformat()
    for action in [lambda: s.update_order(oid, data), lambda: s.delete_order(oid), lambda: s.transition(oid, 'Ready'), lambda: payment(s, oid, '1'), lambda: s.delete_payment(oid, pid)]:
        rejected(action)
    dashboard = s.dashboard()
    assert dashboard['counts']['Delivered'] == 1
    assert dashboard['collected_minor'] == 15000 and dashboard['outstanding_minor'] == 0


@pytest.mark.parametrize('values', [{'amount': '0'}, {'amount': '-1'}, {'amount': '150.01'}, {'amount': '0.001'}, {'pay_date': '2026-10-31'}, {'pay_date': '2026-11-02'}, {'pay_date': 'bad'}, {'pay_date': ''}, {'note': 'x' * 301}])
def test_invalid_payment_is_atomic(tmp_path, values):
    s = store(tmp_path)
    oid = order(s)
    rejected(lambda: payment(s, oid, **values))
    assert s.order(oid)['payments'] == [] and s.order(oid)['balance_minor'] == 15000


def test_customer_lock_survives_deleted_payment_and_price_limit(tmp_path):
    s = store(tmp_path)
    data = order_data(s)
    oid = s.create_order(data, uuid4().hex)
    pid = payment(s, oid)
    second = person(s, name='Other Customer', phone='12345678')
    rejected(lambda: s.update_order(oid, {**data, 'price': '49.99'}))
    rejected(lambda: s.update_order(oid, {**data, 'customer_id': second}))
    s.delete_payment(oid, pid)
    assert s.dashboard()['collected_minor'] == 0
    rejected(lambda: s.update_order(oid, {**data, 'customer_id': second}))
    s.update_order(oid, {**data, 'price': '25'})
    assert s.order(oid)['balance_minor'] == 2500


def test_idempotent_orders_and_payments_including_tombstones(tmp_path):
    s = store(tmp_path)
    data = order_data(s)
    oid = s.create_order(data, 'order-token')
    assert s.create_order(data, 'order-token') == oid
    rejected(lambda: s.create_order({**data, 'price': '10'}, 'order-token'))
    p = {'amount': '25.50', 'pay_date': '2026-11-01', 'note': ''}
    pid = s.add_payment(oid, p, 'payment-token')
    assert s.add_payment(oid, p, 'payment-token') == pid
    rejected(lambda: s.add_payment(oid, {**p, 'amount': '26'}, 'payment-token'))
    s.delete_payment(oid, pid)
    rejected(lambda: s.add_payment(oid, p, 'payment-token'))
    assert not s.order(oid)['payments']
    s.delete_order(oid)
    rejected(lambda: s.create_order(data, 'order-token'))
    assert not s.orders()


def test_same_payment_request_concurrent_and_overpay_race(tmp_path):
    s = store(tmp_path)
    oid = order(s)
    p = {'amount': '100', 'pay_date': '2026-11-01', 'note': ''}
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: s.add_payment(oid, p, 'same-payment'), range(2)))
    assert ids[0] == ids[1] and s.order(oid)['paid_minor'] == 10000
    def pay_once(token):
        try:
            return s.add_payment(oid, {**p, 'amount': '50'}, token)
        except module('domain').DomainError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(pay_once, ['next-1', 'next-2']))
    assert sum(value is not None for value in ids) == 1
    assert s.order(oid)['balance_minor'] == 0


def test_failed_write_rolls_back_payment_lock_and_receipt(tmp_path):
    s = store(tmp_path)
    oid = order(s)
    with sqlite3.connect(tmp_path / 'shop.db') as db:
        db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON receipts BEGIN SELECT RAISE(ABORT, 'simulated failure'); END")
    with pytest.raises(sqlite3.DatabaseError):
        payment(s, oid)
    assert s.order(oid)['paid_minor'] == 0 and not s.order(oid)['customer_locked']
    with sqlite3.connect(tmp_path / 'shop.db') as db:
        db.execute('DROP TRIGGER fail_receipt')
    payment(s, oid)
    assert s.order(oid)['paid_minor'] == 5000


def test_search_combined_filters_sort_and_dashboard_recent(tmp_path):
    s = store(tmp_path)
    first = order(s)
    s.transition(first, 'In Repair')
    second_customer = person(s, name='Zoë 王芳', phone='12345678')
    second_tech = person(s, 'technicians', name='Other Tech', phone='12345679')
    others = [order(s, customer_id=second_customer, tech_id=second_tech) for _ in range(6)]
    assert [d['id'] for d in s.orders()] == list(reversed(others)) + [first]
    assert len(s.orders(q='aLEX', status='In Repair')) == 1
    assert len(s.orders(q='+٨٦ (١٣٨)', tech=str(s.order(first)['tech_id']))) == 1
    assert len(s.orders(q='王芳', status='Received', tech=str(second_tech))) == 6
    assert len(s.orders(q=s.order(first)['order_no'])) == 1
    assert not s.orders(q='missing') and not s.orders(q='Alex', status='Ready')
    assert len(s.dashboard()['recent']) == 5
    assert sum(s.dashboard()['counts'].values()) == 7
    assert s.dashboard()['outstanding_minor'] == 105000


def test_delete_constraints_and_missing_records(tmp_path):
    s = store(tmp_path)
    first, second = order(s), order(s)
    pid = payment(s, first)
    rejected(lambda: s.delete_payment(second, pid), 404)
    rejected(lambda: s.delete_order(first))
    s.transition(second, 'In Repair')
    rejected(lambda: s.delete_order(second))
    rejected(lambda: s.order(999), 404)
    rejected(lambda: s.person('customers', 999), 404)


def app(tmp_path):
    return module('app').create_app(tmp_path / 'http.db', clock=lambda: NOW)


def csrf(client):
    client.get('/')
    with client.session_transaction() as session:
        return session['csrf_token']


def post(client, url, data):
    return client.post(url, data={'csrf_token': csrf(client), **data})


def test_http_local_assets_english_and_boundary(tmp_path):
    application = app(tmp_path)
    client = application.test_client()
    page = client.get('/')
    assert page.status_code == 200 and b'lang="en"' in page.data
    assert b'Dashboard' in page.data and b'Choose currency' in page.data
    for path in ['/static/app.css', '/static/app.js', '/static/favicon.svg']:
        assert client.get(path).status_code == 200
    assert "default-src 'self'" in page.headers['Content-Security-Policy']
    assert client.post('/currency', data={'currency': 'CNY'}).status_code == 403
    assert client.get('/', headers={'Host': 'evil.example'}).status_code == 403
    assert client.post('/currency', data={'csrf_token': csrf(client), 'currency': 'CNY'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/orders/999').status_code == 404
    assert client.get('/customers/999').status_code == 404


@pytest.mark.parametrize('currency', ['CNY', 'USD'])
def test_http_forms_lifecycle_and_confirmation_gets_are_read_only(tmp_path, currency):
    application = app(tmp_path)
    client = application.test_client()
    assert post(client, '/currency', {'currency': currency}).status_code == 303
    assert post(client, '/customers/new', {'name': 'Test Customer', 'phone': '12345678', 'email': ''}).status_code == 303
    assert post(client, '/technicians/new', {'name': 'Test Tech', 'phone': '12345679', 'active': '1'}).status_code == 303
    s = application.extensions['shop']
    data = order_data(s)
    response = post(client, '/orders/new', {**data, 'request_token': 'http-order'})
    assert response.status_code == 303
    oid = s.orders()[0]['id']
    assert f'{currency} 150.00'.encode() in client.get(f'/orders/{oid}').data
    assert client.get(f'/orders/{oid}/delete').status_code == 200
    assert len(s.orders()) == 1
    assert post(client, f'/orders/{oid}/status', {'status': 'In Repair'}).status_code == 303
    assert post(client, f'/orders/{oid}/status', {'status': 'Ready'}).status_code == 303
    assert post(client, f'/orders/{oid}/payments/new', {'amount': '150', 'pay_date': '2026-11-01', 'note': '', 'request_token': 'http-payment'}).status_code == 303
    assert client.get(f'/orders/{oid}/status?status=Delivered').status_code == 200
    assert s.order(oid)['status'] == 'Ready'
    assert post(client, f'/orders/{oid}/status', {'status': 'Delivered'}).status_code == 400
    assert post(client, f'/orders/{oid}/status', {'status': 'Delivered', 'confirmed': 'yes'}).status_code == 303
    assert s.order(oid)['status'] == 'Delivered'


def test_http_errors_preserve_input_escape_html_and_hide_storage_errors(tmp_path, monkeypatch):
    application = app(tmp_path)
    client = application.test_client()
    response = post(client, '/customers/new', {'name': '<script>alert(1)</script>', 'phone': 'bad', 'email': ''})
    assert response.status_code == 400 and b'&lt;script&gt;' in response.data
    assert b'<script>alert(1)</script>' not in response.data and b'value="bad"' in response.data
    s = application.extensions['shop']
    s.set_currency('CNY')
    data = order_data(s)
    def fail(*args):
        raise sqlite3.OperationalError('private diagnostic secret')
    monkeypatch.setattr(s, 'create_order', fail)
    response = post(client, '/orders/new', {**data, 'request_token': 'keep-this-token'})
    assert response.status_code == 503
    assert b'private diagnostic secret' not in response.data
    assert b'keep-this-token' in response.data and b'Dell XPS' in response.data
    assert not s.orders()


def test_restart_keeps_all_shop_records_without_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    s = store(tmp_path)
    oid = order(s)
    payment(s, oid)
    s.transition(oid, 'In Repair')
    before = s.order(oid)
    reopened = module('store').Store(tmp_path / 'shop.db', clock=lambda: NOW)
    assert reopened.order(oid) == before
    assert reopened.settings() == {'currency': 'CNY', 'locked': True}
