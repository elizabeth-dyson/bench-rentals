"""Explicit-client staff submission boundary; public access is a later phase.

Keep a request UUID and its original payload across uncertain failures. A new
UUID means a new submission, even when the answers happen to be identical.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from services.inquiries import InquiryAnswers, StaffInquiryContext, snapshot_inquiry_answers

if TYPE_CHECKING:
    from supabase import Client


class InquirySubmissionError(RuntimeError):
    """The save outcome may be uncertain; retry the same request and payload."""


class InquiryValidationError(ValueError):
    pass


class InquiryUnavailableError(InquirySubmissionError):
    pass


class InquiryClosedError(InquirySubmissionError):
    pass


class InquiryConflictError(InquirySubmissionError):
    pass


class InquiryAuthorizationError(InquirySubmissionError):
    pass


@dataclass(frozen=True)
class InquirySubmissionResult:
    booking_id: str
    booking_number: str
    submission_id: str
    submission_number: int
    replayed: bool


def _uuid(value: str | UUID, label: str) -> str:
    try:
        if not isinstance(value, (str, UUID)):
            raise ValueError
        return str(UUID(str(value)))
    except (ValueError, AttributeError) as error:
        raise InquiryValidationError(f"{label} must be a UUID.") from error


def _snapshot(answers: InquiryAnswers) -> dict:
    if not isinstance(answers, InquiryAnswers):
        raise InquiryValidationError("Supply complete inquiry answers.")
    try:
        return snapshot_inquiry_answers(answers)
    except (TypeError, ValueError) as error:
        raise InquiryValidationError(str(error)) from error


def _staff_context(context: StaffInquiryContext | None) -> dict:
    if context is None:
        return {}
    if not isinstance(context, StaffInquiryContext):
        raise InquiryValidationError("Supply valid staff context.")
    if context.customer_profile_notes is not None:
        raise InquiryValidationError("Customer-wide notes cannot be changed by an inquiry submission.")
    for value in (context.internal_notes, context.facebook_conversation_url):
        if value is not None and not isinstance(value, str):
            raise InquiryValidationError("Staff notes and conversation URL must be text.")
    return {
        "existing_customer_id": (
            _uuid(context.existing_customer_id, "Customer ID")
            if context.existing_customer_id is not None else None
        ),
        "internal_notes": context.internal_notes,
        "facebook_conversation_url": context.facebook_conversation_url,
    }


def _save(client: "Client", rpc: str, payload: dict[str, Any]) -> InquirySubmissionResult:
    try:
        data = client.rpc(rpc, payload).execute().data
    except Exception as error:
        # SQLSTATE is the contract. Never display database messages/customer data.
        code = getattr(error, "code", None)
        kind, message = {
            "P5101": (InquiryValidationError, "Check the inquiry answers."),
            "P5102": (InquiryUnavailableError, "The booking or selected customer is unavailable."),
            "P5103": (InquiryClosedError, "Restore the lead before submitting new answers."),
            "P5104": (InquiryConflictError, "This request was already used with different answers or context."),
            "42501": (InquiryAuthorizationError, "Sign in to submit inquiry answers."),
        }.get(code, (InquirySubmissionError, "Unable to confirm the save. Retry with the same request and answers."))
        raise kind(message) from error
    try:
        row = data[0] if isinstance(data, list) and len(data) == 1 else data
        if not isinstance(row, dict):
            raise ValueError
        booking_id = _uuid(row["booking_id"], "Booking ID")
        submission_id = _uuid(row["submission_id"], "Submission ID")
        number = row["submission_number"]
        if type(number) is not int or number < 1 or type(row["replayed"]) is not bool:
            raise ValueError
        if not isinstance(row["booking_number"], str) or not row["booking_number"].strip():
            raise ValueError
        return InquirySubmissionResult(
            booking_id, row["booking_number"], submission_id, number, row["replayed"],
        )
    except (KeyError, TypeError, ValueError) as error:
        raise InquirySubmissionError(
            "Unable to confirm the save. Retry with the same request and answers."
        ) from error


def create_inquiry(
    answers: InquiryAnswers, *, request_id: str | UUID,
    client: "Client", staff_context: StaffInquiryContext | None = None,
) -> InquirySubmissionResult:
    """Create a staff inquiry and its original submission in one transaction."""
    return _save(client, "create_staff_inquiry", {
        "p_request_id": _uuid(request_id, "Request ID"),
        "p_snapshot": _snapshot(answers),
        "p_staff_context": _staff_context(staff_context),
    })


def append_inquiry_submission(
    booking_id: str | UUID, answers: InquiryAnswers, *,
    request_id: str | UUID, client: "Client",
) -> InquirySubmissionResult:
    """Append complete staff-entered answers; never replace working details."""
    return _save(client, "append_staff_inquiry_submission", {
        "p_request_id": _uuid(request_id, "Request ID"),
        "p_booking_id": _uuid(booking_id, "Booking ID"),
        "p_snapshot": _snapshot(answers),
    })
