"""Shared inquiry answers and pure rules; no UI, client, or persistence access.

Snapshots describe customer answers only. Working-value normalization must never
be applied to the original answers before building their submission snapshot.
"""

import re
from dataclasses import dataclass, fields, replace
from datetime import date, datetime, timezone
from typing import Literal, TypedDict
from zoneinfo import ZoneInfo


BUSINESS_TIME_ZONE = ZoneInfo("America/Chicago")
ALLOWED_CONTACT_METHODS = frozenset({"email", "facebook", "phone", "text"})
ALLOWED_SOURCES = frozenset({
    "facebook_marketplace", "facebook_referral", "word_of_mouth",
    "repeat_customer", "other",
})
DeliveryPreference = Literal["parent_delivery", "customer_pickup", "unsure"]
EntryMethod = Literal["public_form", "staff_entered"]


@dataclass(frozen=True)
class VenueInput:
    name: str | None = None
    address_line_1: str | None = None
    address_line_2: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None


@dataclass(frozen=True)
class InquiryAnswers:
    customer_name: str
    event_date: date
    requested_bench_count: int
    preferred_contact_method: str
    email: str | None = None
    phone: str | None = None
    facebook_identity: str | None = None
    event_type: str | None = None
    source: str | None = None
    venue: VenueInput | None = None
    delivery_preference: DeliveryPreference = "unsure"
    delivery_at: datetime | None = None
    setup_complete_by: datetime | None = None
    event_start_at: datetime | None = None
    pickup_at: datetime | None = None
    rehearsal_at: datetime | None = None
    timing_notes: str | None = None
    rental_notes: str | None = None
    delivery_instructions: str | None = None
    pickup_instructions: str | None = None


@dataclass(frozen=True)
class StaffInquiryContext:
    """Trusted staff context, never part of customer answers or their snapshot.

Attribution must eventually come from the authenticated boundary, not from a
customer form. Customer-wide note editing is not enabled by this model.
"""

    existing_customer_id: str | None = None
    customer_profile_notes: str | None = None
    internal_notes: str | None = None
    facebook_conversation_url: str | None = None


type SnapshotValue = str | int | None | dict[str, "SnapshotValue"]


class InquirySnapshot(TypedDict):
    schema_version: Literal[1]
    answers: dict[str, SnapshotValue]


def clean_text(value: str | None) -> str | None:
    return (value or "").strip() or None


def normalize_email(value: str | None) -> str | None:
    return (value or "").strip().lower() or None


def normalize_phone(value: str | None) -> str | None:
    return re.sub(r"\D", "", value or "") or None


def normalize_facebook(value: str | None) -> str | None:
    return " ".join((value or "").strip().lower().split()) or None


def validate_contact_event(
    *, customer_name: str, event_date: date, requested_bench_count: int,
    preferred_contact_method: str, email: str | None, phone: str | None,
    facebook_identity: str | None,
) -> list[str]:
    """The shared minimum, also used by the existing lead workflow."""
    errors: list[str] = []
    if not isinstance(customer_name, str) or not customer_name.strip():
        errors.append("Enter the customer's name.")
    if not isinstance(event_date, date) or isinstance(event_date, datetime):
        errors.append("Choose an event date.")
    if (not isinstance(requested_bench_count, int)
            or isinstance(requested_bench_count, bool) or requested_bench_count < 1):
        errors.append("Requested benches must be at least 1.")
    if not isinstance(preferred_contact_method, str) or preferred_contact_method not in ALLOWED_CONTACT_METHODS:
        errors.append("Choose a valid preferred contact method.")
    for label, value in (("email", email), ("phone", phone), ("Facebook identity", facebook_identity)):
        if value is not None and not isinstance(value, str):
            errors.append(f"Enter a valid {label}.")
    email = normalize_email(email) if isinstance(email, str) else None
    phone_was_supplied = isinstance(phone, str) and bool(phone.strip())
    phone = normalize_phone(phone) if isinstance(phone, str) else None
    facebook = normalize_facebook(facebook_identity) if isinstance(facebook_identity, str) else None
    if email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        errors.append("Enter a valid email address.")
    if phone_was_supplied and (not phone or not 7 <= len(phone) <= 15):
        errors.append("Enter a valid phone number.")
    if not any((email, phone, facebook)):
        errors.append("Enter at least one contact method.")
    available_methods = set()
    if email:
        available_methods.add("email")
    if phone:
        available_methods.update(("text", "phone"))
    if facebook:
        available_methods.add("facebook")
    if (isinstance(preferred_contact_method, str)
            and preferred_contact_method in ALLOWED_CONTACT_METHODS
            and preferred_contact_method not in available_methods):
        errors.append("The preferred contact method must have contact information.")
    return errors


_TIMESTAMP_FIELDS = (
    "delivery_at", "setup_complete_by", "event_start_at", "pickup_at", "rehearsal_at",
)
_OPTIONAL_TEXT_FIELDS = (
    "event_type", "source", "timing_notes", "rental_notes",
    "delivery_instructions", "pickup_instructions",
)


def _valid_timestamp(value: object) -> bool:
    if not isinstance(value, datetime) or value.tzinfo is None:
        return False
    try:
        if value.utcoffset() is None:
            return False
        # Round-trip catches nonexistent wall times in a ZoneInfo zone (spring DST).
        restored = value.astimezone(timezone.utc).astimezone(value.tzinfo)
        # Also ensure the working representation can be expressed in Chicago.
        value.astimezone(BUSINESS_TIME_ZONE)
        return restored.replace(tzinfo=None) == value.replace(tzinfo=None)
    except (OverflowError, ValueError):
        return False


def validate_inquiry_input(answers: InquiryAnswers) -> list[str]:
    errors = validate_contact_event(
        customer_name=answers.customer_name, event_date=answers.event_date,
        requested_bench_count=answers.requested_bench_count,
        preferred_contact_method=answers.preferred_contact_method,
        email=answers.email, phone=answers.phone,
        facebook_identity=answers.facebook_identity,
    )
    for name in _OPTIONAL_TEXT_FIELDS:
        value = getattr(answers, name)
        if value is not None and not isinstance(value, str):
            errors.append(f"{name.replace('_', ' ').capitalize()} must be text.")
    if isinstance(answers.source, str) and clean_text(answers.source) not in (None, *ALLOWED_SOURCES):
        errors.append("Choose a valid referral source.")
    if answers.delivery_preference not in ("parent_delivery", "customer_pickup", "unsure"):
        errors.append("Choose delivery, customer pickup, or unsure.")
    if answers.venue is not None:
        if not isinstance(answers.venue, VenueInput):
            errors.append("Enter valid venue details.")
        else:
            for field in fields(VenueInput):
                value = getattr(answers.venue, field.name)
                if value is not None and not isinstance(value, str):
                    errors.append(f"Venue {field.name.replace('_', ' ')} must be text.")
    for name in _TIMESTAMP_FIELDS:
        value = getattr(answers, name)
        if value is not None and not _valid_timestamp(value):
            errors.append(f"{name.replace('_', ' ').capitalize()} must be a valid timezone-aware timestamp.")
    if (_valid_timestamp(answers.delivery_at) and _valid_timestamp(answers.pickup_at)
            and answers.pickup_at.astimezone(timezone.utc) < answers.delivery_at.astimezone(timezone.utc)):
        errors.append("Pickup must not be before delivery.")
    return errors


def delivery_method_for_preference(preference: DeliveryPreference) -> str | None:
    if preference == "unsure":
        return None
    if preference in ("parent_delivery", "customer_pickup"):
        return preference
    raise ValueError("Choose delivery, customer pickup, or unsure.")


def normalize_inquiry(answers: InquiryAnswers) -> InquiryAnswers:
    """Return a separate working copy; never mutate original answers."""
    errors = validate_inquiry_input(answers)
    if errors:
        raise ValueError(" ".join(errors))
    venue = None
    if answers.venue is not None:
        values = {field.name: clean_text(getattr(answers.venue, field.name)) for field in fields(VenueInput)}
        if any(values.values()):
            venue = VenueInput(**values)
    return replace(
        answers,
        customer_name=answers.customer_name.strip(),
        email=normalize_email(answers.email), phone=normalize_phone(answers.phone),
        facebook_identity=normalize_facebook(answers.facebook_identity),
        venue=venue,
        **{name: (clean_text(getattr(answers, name)) or ("other" if name == "source" else None))
           for name in _OPTIONAL_TEXT_FIELDS},
        **{name: (getattr(answers, name).astimezone(BUSINESS_TIME_ZONE)
                  if getattr(answers, name) is not None else None)
           for name in _TIMESTAMP_FIELDS},
    )


def snapshot_inquiry_answers(answers: InquiryAnswers) -> InquirySnapshot:
    """Serialize v1 answers before normalization, with an explicit field allowlist.

Only fields declared on InquiryAnswers/VenueInput are included, even if a
caller passes a subclass containing additional staff-only attributes.
"""
    errors = validate_inquiry_input(answers)
    if errors:
        raise ValueError(" ".join(errors))
    result: dict[str, SnapshotValue] = {}
    for field in fields(InquiryAnswers):
        value = getattr(answers, field.name)
        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, VenueInput):
            value = {f.name: getattr(value, f.name) for f in fields(VenueInput)}
        result[field.name] = value
    return {"schema_version": 1, "answers": result}
