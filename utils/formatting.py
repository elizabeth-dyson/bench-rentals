import re
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any


def format_bench_count(value: Any) -> str:
    """Format a positive bench count with a safe fallback."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        return "Bench count unavailable"
    label = "bench" if value == 1 else "benches"
    return f"{value} {label}"


def format_booking_stage(stage: str | None) -> str:
    """Format a booking stage for display."""
    if not stage or not stage.strip():
        return "Unknown stage"
    return stage.strip().replace("_", " ").title()


def format_booking_date(value: date | datetime | str | None) -> str:
    """Format a booking date consistently, with a safe fallback."""
    parsed_date: date

    if isinstance(value, datetime):
        parsed_date = value.date()
    elif isinstance(value, date):
        parsed_date = value
    elif isinstance(value, str):
        try:
            parsed_date = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return "Date not set"
    else:
        return "Date not set"

    return parsed_date.strftime("%b %d, %Y")


def format_customer_name(customer: Mapping[str, Any] | None) -> str:
    """Return the best available identifying value for a customer."""
    if not isinstance(customer, Mapping):
        return "Unknown customer"

    for field in ("preferred_name", "legal_name", "email", "phone"):
        value = customer.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return "Unknown customer"


def format_booking_source(source: str | None) -> str:
    """Format a lead source for display."""
    if not source or not source.strip():
        return "Not provided"
    return source.strip().replace("_", " ").title()


def format_contact_method(method: str | None) -> str:
    """Format a preferred contact method for display."""
    labels = {
        "email": "Email",
        "facebook": "Facebook",
        "phone": "Phone call",
        "text": "Text message",
    }
    normalized = (method or "").strip().lower()
    return labels.get(normalized, "Not provided")


def is_valid_booking_number(value: Any) -> bool:
    """Return whether a value has the application's public booking-number shape."""
    return isinstance(value, str) and bool(
        re.fullmatch(r"BR-\d{4}-\d{3,}", value.strip())
    )
