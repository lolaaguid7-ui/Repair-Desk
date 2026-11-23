"""Input and money rules. No network or floating-point money arithmetic."""
import re
import unicodedata

STATUSES = ('Received', 'In Repair', 'Ready', 'Delivered')


class DomainError(Exception):
    def __init__(self, message, fields=None, status=400):
        super().__init__(message)
        self.message, self.fields, self.status = message, fields or {}, status


def invalid(field, message):
    return DomainError(message, {field: message})


def digits(value):
    return ''.join(str(unicodedata.decimal(c)) if c.isdecimal() else c for c in value)


def text(value, field, minimum=0, maximum=100):
    if not isinstance(value, str):
        raise invalid(field, 'Enter text in this field.')
    value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise invalid(field, f'Enter between {minimum} and {maximum} characters.')
    return value


def phone(value):
    value = digits(text(value, 'phone', 1, 80))
    value = re.sub(r'[\s()\-]', '', value)
    if not re.fullmatch(r'\+?[0-9]{7,15}', value):
        raise invalid('phone', 'Enter 7–15 digits, with an optional + at the beginning.')
    return value


def money(value, field='price'):
    if not isinstance(value, str):
        raise invalid(field, 'Enter an amount with up to two decimal places.')
    value = digits(value.strip()).replace('٫', '.')
    if not re.fullmatch(r'[0-9]{1,10}(?:\.[0-9]{1,2})?', value):
        raise invalid(field, 'Use a non-negative amount, up to 9,999,999,999.99, with no thousands separators.')
    whole, _, fraction = value.partition('.')
    return int(whole) * 100 + int(fraction.ljust(2, '0'))


def person_data(kind, data):
    result = {'name': text(data.get('name', ''), 'name', 2, 100), 'phone': phone(data.get('phone', ''))}
    if kind == 'customers':
        email = text(data.get('email', ''), 'email', 0, 254)
        if email and not re.fullmatch(r'[^\s@]+@[^\s@.]+(?:\.[^\s@.]+)+', email):
            raise invalid('email', 'Enter a valid email address, or leave this field empty.')
        result['email'] = email
    else:
        active = data.get('active', True)
        if active not in (True, False, '1', '0', 1, 0):
            raise invalid('active', 'Choose active or inactive.')
        result['active'] = int(active in (True, '1', 1))
    return result


def identifier(value, field, optional=False):
    if optional and value in ('', None):
        return None
    if isinstance(value, bool) or not re.fullmatch(r'[0-9]{1,12}', str(value)) or int(value) < 1:
        raise invalid(field, 'Choose an existing record.')
    return int(value)
