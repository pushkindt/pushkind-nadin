from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import flash


def get_filter_timestamps():
    now = datetime.now(tz=timezone.utc)
    today = datetime(now.year, now.month, now.day)
    week = today - timedelta(days=today.weekday())
    month = datetime(now.year, now.month, 1)
    recently = today - timedelta(days=42)
    quarter = datetime(now.year, 3 * ((now.month - 1) // 3) + 1, 1)
    year = datetime(now.year, 1, 1)
    dates = {
        "daily": int(today.timestamp()),
        "weekly": int(week.timestamp()),
        "monthly": int(month.timestamp()),
        "recently": int(recently.timestamp()),
        "quarterly": int(quarter.timestamp()),
        "annually": int(year.timestamp()),
    }
    return dates


def first(items: Iterable) -> Any:
    return next(iter(items or []), None)


def flash_errors(form, category="warning"):
    """Flash all errors for a form."""
    for field, errors in form.errors.items():
        for error in errors:
            flash(f"{getattr(form, field).label.text} - {error}", category)
