"""Transactional local records, balances, lifecycle and replay protection."""
from contextlib import contextmanager
from datetime import datetime, date
import hashlib
import json
from pathlib import Path
import sqlite3

from .domain import DomainError, STATUSES, digits, identifier, invalid, money, person_data, text

SCHEMA = '''
CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), currency TEXT CHECK(currency IN ('CNY','USD')));
INSERT OR IGNORE INTO settings(id,currency) VALUES(1,NULL);
CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT NOT NULL UNIQUE, email TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS technicians (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT NOT NULL UNIQUE, active INTEGER NOT NULL CHECK(active IN (0,1)));
CREATE TABLE IF NOT EXISTS orders (
 id INTEGER PRIMARY KEY AUTOINCREMENT, customer_id INTEGER NOT NULL REFERENCES customers(id),
 tech_id INTEGER REFERENCES technicians(id), device_type TEXT NOT NULL, brand TEXT NOT NULL, problem TEXT NOT NULL,
 price_minor INTEGER NOT NULL CHECK(price_minor>=0), status TEXT NOT NULL CHECK(status IN ('Received','In Repair','Ready','Delivered')),
 received_at TEXT NOT NULL, delivered_at TEXT, customer_locked INTEGER NOT NULL DEFAULT 0 CHECK(customer_locked IN (0,1)));
CREATE TABLE IF NOT EXISTS payments (id INTEGER PRIMARY KEY AUTOINCREMENT, order_id INTEGER NOT NULL REFERENCES orders(id), amount_minor INTEGER NOT NULL CHECK(amount_minor>0), pay_date TEXT NOT NULL, note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS receipts (scope TEXT NOT NULL, token TEXT NOT NULL, fingerprint TEXT NOT NULL, resource_id INTEGER NOT NULL, PRIMARY KEY(scope,token));
CREATE INDEX IF NOT EXISTS orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS orders_technician ON orders(tech_id);
CREATE INDEX IF NOT EXISTS payments_order ON payments(order_id);
'''


class Store:
    def __init__(self, path, clock=None):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock or (lambda: datetime.now().astimezone())
        with self.connection() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self, write=False):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            if write:
                db.execute('BEGIN IMMEDIATE')
            else:
                db.execute('BEGIN')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def row(db, table, record_id):
        if table not in ('customers', 'technicians', 'orders', 'payments'):
            raise DomainError('This record is not available.', status=404)
        value = db.execute(f'SELECT * FROM {table} WHERE id=?', (record_id,)).fetchone()
        if not value:
            raise DomainError('This record could not be found.', status=404)
        return dict(value)

    def settings(self):
        with self.connection() as db:
            return {'currency': db.execute('SELECT currency FROM settings WHERE id=1').fetchone()[0],
                    'locked': bool(db.execute('SELECT 1 FROM orders LIMIT 1').fetchone())}

    def set_currency(self, code):
        if code not in ('CNY', 'USD'):
            raise invalid('currency', 'Choose Chinese yuan (CNY) or US dollar (USD).')
        with self.connection(True) as db:
            current = db.execute('SELECT currency FROM settings WHERE id=1').fetchone()[0]
            if code != current and db.execute('SELECT 1 FROM orders LIMIT 1').fetchone():
                raise DomainError('Currency is locked while repair orders exist.', status=409)
            db.execute('UPDATE settings SET currency=? WHERE id=1', (code,))

    @staticmethod
    def kind(kind):
        if kind not in ('customers', 'technicians'):
            raise DomainError('This page is not available.', status=404)
        return kind

    def people(self, kind):
        kind = self.kind(kind)
        with self.connection() as db:
            return [dict(r) for r in db.execute(f'SELECT * FROM {kind} ORDER BY name COLLATE NOCASE,id')]

    def person(self, kind, record_id):
        with self.connection() as db:
            return self.row(db, self.kind(kind), record_id)

    def save_person(self, kind, data, id=None):
        kind = self.kind(kind)
        values = person_data(kind, data)
        with self.connection(True) as db:
            if id is not None:
                self.row(db, kind, id)
            duplicate = db.execute(f'SELECT id FROM {kind} WHERE phone=?', (values['phone'],)).fetchone()
            if duplicate and duplicate['id'] != id:
                raise invalid('phone', 'This phone number is already registered.')
            if id is None:
                columns = ','.join(values)
                return db.execute(f'INSERT INTO {kind} ({columns}) VALUES ({",".join("?" for _ in values)})', tuple(values.values())).lastrowid
            db.execute(f'UPDATE {kind} SET {",".join(k+"=?" for k in values)} WHERE id=?', (*values.values(), id))
            return id

    def delete_customer(self, id):
        with self.connection(True) as db:
            self.row(db, 'customers', id)
            if db.execute('SELECT 1 FROM orders WHERE customer_id=?', (id,)).fetchone():
                raise DomainError('This customer has repair orders and cannot be deleted.', status=409)
            db.execute('DELETE FROM customers WHERE id=?', (id,))

    @staticmethod
    def order_rows(db):
        rows = db.execute('''SELECT o.*,c.name AS customer_name,c.phone AS customer_phone,t.name AS tech_name,
            COALESCE((SELECT SUM(amount_minor) FROM payments p WHERE p.order_id=o.id),0) AS paid_minor
            FROM orders o JOIN customers c ON o.customer_id=c.id LEFT JOIN technicians t ON o.tech_id=t.id
            ORDER BY o.received_at DESC,o.id DESC''').fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value.update(order_no=f'R-{value["id"]:05d}', balance_minor=value['price_minor']-value['paid_minor'])
            result.append(value)
        return result

    def orders(self, q='', status='', tech=''):
        with self.connection() as db:
            rows = self.order_rows(db)
        query = q.strip().casefold()
        phone_query = ''.join(c for c in digits(query) if c not in ' -()\t\r\n')
        return [r for r in rows if (not status or r['status'] == status)
                and (not tech or str(r['tech_id']) == str(tech))
                and (not query or query in r['customer_name'].casefold() or query in r['order_no'].casefold()
                     or query == str(r['id']) or (phone_query and phone_query in r['customer_phone']))]

    def _order(self, db, id):
        self.row(db, 'orders', id)
        value = next(row for row in self.order_rows(db) if row['id'] == id)
        value['payments'] = [dict(p) for p in db.execute('SELECT * FROM payments WHERE order_id=? ORDER BY pay_date DESC,id DESC', (id,))]
        return value

    def order(self, id):
        with self.connection() as db:
            return self._order(db, id)

    @staticmethod
    def mutable(doc):
        if doc['status'] == 'Delivered':
            raise DomainError('This order is delivered and read-only.', status=409)

    def order_values(self, db, data, previous=None):
        values = {'customer_id': identifier(data.get('customer_id'), 'customer_id'),
                  'tech_id': identifier(data.get('tech_id'), 'tech_id', True),
                  'device_type': text(data.get('device_type', ''), 'device_type', 2, 60),
                  'brand': text(data.get('brand', ''), 'brand', 0, 100),
                  'problem': text(data.get('problem', ''), 'problem', 5, 2000),
                  'price_minor': money(data.get('price', ''), 'price')}
        if not db.execute('SELECT 1 FROM customers WHERE id=?', (values['customer_id'],)).fetchone():
            raise invalid('customer_id', 'Choose an existing customer.')
        if values['tech_id']:
            tech = db.execute('SELECT active FROM technicians WHERE id=?', (values['tech_id'],)).fetchone()
            if not tech or (not tech['active'] and (not previous or previous['tech_id'] != values['tech_id'])):
                raise invalid('tech_id', 'Choose an active technician.')
        if previous:
            if previous['customer_locked'] and values['customer_id'] != previous['customer_id']:
                raise invalid('customer_id', 'The customer cannot change after the first payment.')
            if previous['status'] != 'Received' and not values['tech_id']:
                raise invalid('tech_id', 'An order in repair or ready must have a technician.')
            if values['price_minor'] < previous['paid_minor']:
                raise invalid('price', 'The repair price cannot be lower than the amount already paid.')
        return values

    def replay(self, db, scope, token, data, table):
        token = text(token, 'request_token', 1, 128)
        fingerprint = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        receipt = db.execute('SELECT * FROM receipts WHERE scope=? AND token=?', (scope, token)).fetchone()
        if receipt:
            if receipt['fingerprint'] != fingerprint:
                raise DomainError('This submission was already saved with different values. Open a new form to enter another record.', status=409)
            if not db.execute(f'SELECT 1 FROM {table} WHERE id=?', (receipt['resource_id'],)).fetchone():
                raise DomainError('This submission was saved previously and later deleted. It will not be recreated.', status=409)
            return receipt['resource_id'], fingerprint
        return None, fingerprint

    def create_order(self, data, token):
        with self.connection(True) as db:
            existing, fingerprint = self.replay(db, 'order', token, data, 'orders')
            if existing:
                return existing
            if not db.execute('SELECT currency FROM settings WHERE id=1').fetchone()[0]:
                raise DomainError('Choose the shop currency before creating an order.', {'currency': 'Choose the shop currency first.'})
            values = self.order_values(db, data)
            oid = db.execute('''INSERT INTO orders(customer_id,tech_id,device_type,brand,problem,price_minor,status,received_at)
                VALUES(?,?,?,?,?,?,'Received',?)''', (*values.values(), self.clock().isoformat())).lastrowid
            db.execute('INSERT INTO receipts VALUES(?,?,?,?)', ('order', token.strip(), fingerprint, oid))
            return oid

    def update_order(self, id, data):
        with self.connection(True) as db:
            doc = self._order(db, id)
            self.mutable(doc)
            values = self.order_values(db, data, doc)
            db.execute(f'UPDATE orders SET {",".join(k+"=?" for k in values)} WHERE id=?', (*values.values(), id))

    def transition(self, id, status):
        with self.connection(True) as db:
            doc = self._order(db, id)
            self.mutable(doc)
            allowed = {'Received': ['In Repair'], 'In Repair': ['Ready'], 'Ready': ['In Repair', 'Delivered']}
            if status not in allowed.get(doc['status'], []):
                raise DomainError('That status change is not available for this order.')
            if status == 'In Repair' and not doc['tech_id']:
                raise DomainError('Assign a technician before starting the repair.')
            if status == 'Delivered' and doc['balance_minor']:
                raise DomainError('Record the remaining payment before delivering this device.')
            db.execute('UPDATE orders SET status=?,delivered_at=? WHERE id=?', (status, self.clock().isoformat() if status == 'Delivered' else None, id))

    def delete_order(self, id):
        with self.connection(True) as db:
            doc = self._order(db, id)
            if doc['status'] != 'Received' or doc['payments']:
                raise DomainError('Only received orders without payments can be deleted.', status=409)
            db.execute('DELETE FROM orders WHERE id=?', (id,))

    def add_payment(self, id, data, token):
        with self.connection(True) as db:
            existing, fingerprint = self.replay(db, f'payment:{id}', token, data, 'payments')
            if existing:
                return existing
            doc = self._order(db, id)
            self.mutable(doc)
            amount = money(data.get('amount', ''), 'amount')
            if amount <= 0 or amount > doc['balance_minor']:
                raise invalid('amount', 'Enter an amount greater than zero and no more than the outstanding balance.')
            try:
                raw_date = data.get('pay_date', '')
                paid_on = date.fromisoformat(raw_date)
                if paid_on.isoformat() != raw_date or not datetime.fromisoformat(doc['received_at']).date() <= paid_on <= self.clock().date():
                    raise ValueError()
            except (ValueError, TypeError):
                raise invalid('pay_date', 'Choose a date from the order reception date through today.') from None
            note = text(data.get('note', ''), 'note', 0, 300)
            pid = db.execute('INSERT INTO payments(order_id,amount_minor,pay_date,note) VALUES(?,?,?,?)', (id, amount, paid_on.isoformat(), note)).lastrowid
            db.execute('UPDATE orders SET customer_locked=1 WHERE id=?', (id,))
            db.execute('INSERT INTO receipts VALUES(?,?,?,?)', (f'payment:{id}', token.strip(), fingerprint, pid))
            return pid

    def delete_payment(self, id, payment_id):
        with self.connection(True) as db:
            doc = self._order(db, id)
            self.mutable(doc)
            p = self.row(db, 'payments', payment_id)
            if p['order_id'] != id:
                raise DomainError('This payment could not be found on this order.', status=404)
            db.execute('DELETE FROM payments WHERE id=?', (payment_id,))

    def dashboard(self):
        with self.connection() as db:
            orders = self.order_rows(db)
        return {'counts': {status: sum(o['status'] == status for o in orders) for status in STATUSES},
                'collected_minor': sum(o['paid_minor'] for o in orders),
                'outstanding_minor': sum(o['balance_minor'] for o in orders), 'recent': orders[:5]}
