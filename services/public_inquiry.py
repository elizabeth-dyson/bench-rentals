"""Public inquiry contracts and validation. No UI or initialized clients."""

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING, Callable
from uuid import UUID

from services.inquiries import BUSINESS_TIME_ZONE, InquiryAnswers, InquirySnapshot, snapshot_inquiry_answers

if TYPE_CHECKING:
    from supabase import Client


class PublicInquiryError(RuntimeError):
    """An unknown save outcome: keep the exact request for retry."""


class PublicValidationError(ValueError):
    pass


class PublicVerificationError(ValueError):
    pass


class PublicThrottleError(ValueError):
    pass


class PublicAuthorizationError(ValueError):
    pass


class PublicConflictError(ValueError):
    pass


TEXT_LIMITS = {
    "customer_name": 200, "event_type": 200, "email": 254, "phone": 50,
    "facebook_identity": 500, "timing_notes": 4000, "rental_notes": 4000,
    "delivery_instructions": 4000, "pickup_instructions": 4000,
}
MAX_SNAPSHOT_BYTES = 65536
TURNSTILE_ACTION = "initial_inquiry"


@dataclass(frozen=True)
class VerifiedInquiry:
    """Server-only proof bound to a logical request; never deserialize from a browser."""

    request_id: str
    snapshot_digest: str


@dataclass(frozen=True)
class PublicInquiryReceipt:
    request_id: str
    replayed: bool


def public_snapshot(answers: InquiryAnswers) -> InquirySnapshot:
    try:
        snapshot = snapshot_inquiry_answers(answers)
    except (TypeError, ValueError, AttributeError) as error:
        raise PublicValidationError(str(error)) from None
    if answers.requested_bench_count > 2147483647:
        raise PublicValidationError("Requested benches must be no more than 2,147,483,647.")
    for field, limit in TEXT_LIMITS.items():
        value = snapshot["answers"][field]
        if value is not None and len(value) > limit:
            raise PublicValidationError(f"{field.replace('_', ' ').capitalize()} must be {limit:,} characters or fewer.")
    venue = snapshot["answers"]["venue"]
    if venue and any(value is not None and len(value) > 200 for value in venue.values()):
        raise PublicValidationError("Each venue field must be 200 characters or fewer.")
    if len(json.dumps(snapshot, ensure_ascii=False).encode("utf-8")) > MAX_SNAPSHOT_BYTES:
        raise PublicValidationError("The inquiry is too long. Shorten the notes and instructions.")
    return snapshot


def _digest(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _request_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise PublicValidationError("Invalid submission request.") from None


def verify_public_inquiry(
    answers: InquiryAnswers, *, request_id: str, token: str,
    verify: Callable[[str, str], None],
) -> VerifiedInquiry:
    snapshot = public_snapshot(answers)
    request_id = _request_uuid(request_id)
    if not isinstance(token, str) or not 1 <= len(token) <= 2048:
        raise PublicVerificationError("Complete the verification before submitting.")
    # Separate keys for verification attempts: a refreshed token gets a new key.
    verification_id = str(UUID(hashlib.sha256((request_id + token).encode()).hexdigest()[:32]))
    verify(token, verification_id)
    return VerifiedInquiry(request_id, _digest(snapshot))


def submit_public_inquiry(
    answers: InquiryAnswers, *, request_id: str, session_id: str,
    verification: VerifiedInquiry, client: "Client", gateway_secret: str,
) -> PublicInquiryReceipt:
    snapshot = public_snapshot(answers)
    request_id = _request_uuid(request_id)
    session_id = _request_uuid(session_id)
    if (not isinstance(verification, VerifiedInquiry)
            or verification != VerifiedInquiry(request_id, _digest(snapshot))):
        raise PublicVerificationError("Verify these answers before submitting.")
    try:
        data = client.rpc("create_public_inquiry", {
            "p_request_id": request_id, "p_snapshot": snapshot,
            "p_session_id": session_id, "p_gateway_secret": gateway_secret,
        }).execute().data
    except Exception as error:
        kind, message = {
            "P5101": (PublicValidationError, "Check the inquiry answers."),
            "P5104": (PublicConflictError, "This request conflicts with an earlier submission. Keep this reference and contact us."),
            "P5401": (PublicThrottleError, "Too many inquiries right now. Please try again later."),
            "42501": (PublicAuthorizationError, "Inquiry submission is temporarily unavailable. Please try again later."),
        }.get(getattr(error, "code", None), (
            PublicInquiryError, "We could not confirm whether your inquiry was saved. Retry this same submission without refreshing the page.",
        ))
        raise kind(message) from None
    row = data[0] if isinstance(data, list) and len(data) == 1 else data
    if (not isinstance(row, dict) or set(row) != {"accepted", "request_id", "replayed"}
            or row["accepted"] is not True or row["request_id"] != request_id
            or type(row["replayed"]) is not bool):
        raise PublicInquiryError("We could not confirm the receipt. Retry this same submission without refreshing the page.")
    return PublicInquiryReceipt(request_id, row["replayed"])


def local_inquiry_time(day: date | None, clock: time | None, occurrence: str | None = None) -> datetime | None:
    """Resolve customer wall time explicitly, including DST gaps and folds."""
    if day is None and clock is None:
        return None
    if day is None or clock is None:
        raise PublicValidationError("Enter both a date and time, or leave both blank.")
    wall = datetime.combine(day, clock).replace(tzinfo=None)
    candidates = [wall.replace(tzinfo=BUSINESS_TIME_ZONE, fold=fold) for fold in (0, 1)]
    try:
        valid = [candidate for candidate in candidates if candidate.astimezone(timezone.utc).astimezone(
            BUSINESS_TIME_ZONE).replace(tzinfo=None) == wall]
    except (OverflowError, ValueError):
        raise PublicValidationError("That date and time are outside the supported range.") from None
    if not valid:
        raise PublicValidationError("Choose a different time for this date.")
    if len(valid) == 2 and valid[0].utcoffset() != valid[1].utcoffset():
        if occurrence not in ("First occurrence", "Second occurrence"):
            raise PublicValidationError("That time occurs twice in America/Chicago. Choose the first or second occurrence.")
        return valid[occurrence == "Second occurrence"]
    return valid[0]
