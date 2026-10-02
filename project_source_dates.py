"""Explicit source date candidates; candidates never assign event occurrence dates."""
import re
import unicodedata
from email.utils import parsedate_to_datetime
from datetime import date


def explicit_dates(text):
    text = unicodedata.normalize('NFKC', text or '')
    candidates = set(re.findall(r'(?<!\d)\d{4}-\d{2}-\d{2}(?!\d)', text or ''))
    for year, month, day in re.findall(r'(?<!\d)(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日(?!前|后|内|起|之前|之后)', text or ''):
        try:
            candidates.add(date(int(year), int(month), int(day)).isoformat())
        except ValueError:
            continue
    # Only explicit mail header lines; never infer a date from filenames or prose.
    for header in re.findall(r'(?im)^\s*Date\s*[:：]\s*(.+)$', text):
        try:
            candidates.add(parsedate_to_datetime(header.strip()).date().isoformat())
        except (ValueError, TypeError, OverflowError):
            continue
    valid = []
    for candidate in candidates:
        try:
            parsed = date.fromisoformat(candidate)
            if parsed.isoformat() == candidate and parsed <= date.today():
                valid.append(candidate)
        except (ValueError, TypeError):
            continue
    return sorted(valid)


def supported_dates(source):
    # Digest prose is generated text. Only dates captured from the original
    # source may authorize a date when the source was extracted.
    candidates = source.get('original_dates', []) if source.get('extracted') else explicit_dates(source.get('content', ''))
    return explicit_dates('\n'.join([source.get('date', ''), *candidates]))
