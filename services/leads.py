import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any

from services.inquiries import (
    ALLOWED_CONTACT_METHODS,
    ALLOWED_SOURCES,
    normalize_email,
    normalize_facebook,
    normalize_phone,
    validate_contact_event,
)
from services.supabase import get_supabase_client

if TYPE_CHECKING:
    from supabase import Client


ALLOWED_DISPOSITION_STAGES = {"lead", "lost", "cancelled"}


class LeadServiceError(RuntimeError):
    """Raised when a lead operation fails."""


@dataclass(frozen=True)
class LeadCreateInput:
    customer_name: str
    event_date: date
    requested_bench_count: int
    preferred_contact_method: str
    source: str = "facebook_marketplace"
    email: str | None = None
    phone: str | None = None
    facebook_identity: str | None = None
    event_type: str | None = None
    facebook_conversation_url: str | None = None
    customer_notes: str | None = None
    internal_notes: str | None = None
    existing_customer_id: str | None = None


@dataclass(frozen=True)
class LeadCreateResult:
    booking_id: str
    booking_number: str


@dataclass(frozen=True)
class LeadUpdateInput:
    booking_number: str
    customer_id: str
    customer_name: str
    event_date: date
    requested_bench_count: int
    preferred_contact_method: str
    source: str
    email: str | None = None
    phone: str | None = None
    facebook_identity: str | None = None
    event_type: str | None = None
    facebook_conversation_url: str | None = None
    customer_notes: str | None = None
    internal_notes: str | None = None


@dataclass(frozen=True)
class LeadUpdateResult:
    booking_number: str


@dataclass(frozen=True)
class LeadDispositionInput:
    booking_number: str
    target_stage: str
    reason: str | None = None


@dataclass(frozen=True)
class LeadDispositionResult:
    booking_number: str
    stage: str


@dataclass(frozen=True)
class CustomerMatch:
    customer_id: str
    display_name: str
    email: str | None
    phone: str | None
    matched_on: tuple[str, ...]


def validate_lead_input(lead: LeadCreateInput | LeadUpdateInput) -> list[str]:
    errors = validate_contact_event(
        customer_name=lead.customer_name, event_date=lead.event_date,
        requested_bench_count=lead.requested_bench_count,
        preferred_contact_method=lead.preferred_contact_method,
        email=lead.email, phone=lead.phone, facebook_identity=lead.facebook_identity,
    )
    if lead.source not in ALLOWED_SOURCES:
        errors.append("Choose a valid lead source.")
    return errors


def validate_lead_disposition(disposition: LeadDispositionInput) -> list[str]:
    """Validate an allowed Phase 4 lead disposition target and its reason."""
    errors: list[str] = []
    if not re.fullmatch(r"BR-\d{4}-\d{3,}", disposition.booking_number.strip()):
        errors.append("Choose a valid booking.")
    if disposition.target_stage not in ALLOWED_DISPOSITION_STAGES:
        errors.append("Choose a valid lead status.")
    if disposition.target_stage in {"lost", "cancelled"} and not (
        disposition.reason or ""
    ).strip():
        errors.append("Enter a reason before closing the lead.")
    return errors


def find_customer_matches(
    *,
    email: str | None,
    phone: str | None,
    facebook_identity: str | None,
    exclude_customer_id: str | None = None,
) -> list[CustomerMatch]:
    """Find exact normalized contact matches without matching by name alone."""
    target_email = normalize_email(email)
    target_phone = normalize_phone(phone)
    target_facebook = normalize_facebook(facebook_identity)

    try:
        client = get_supabase_client()
        customers_response = (
            client.table("customers")
            .select("id,preferred_name,legal_name,email,phone")
            .eq("is_archived", False)
            .execute()
        )
        identities_response = (
            client.table("customer_identities")
            .select("customer_id,display_value")
            .eq("identity_type", "facebook")
            .execute()
            if target_facebook
            else None
        )
    except Exception as error:
        raise LeadServiceError("Unable to check existing customers.") from error

    matched_reasons: dict[str, set[str]] = {}
    customers: dict[str, dict[str, Any]] = {}
    for customer in customers_response.data or []:
        customer_id = customer.get("id")
        if not customer_id:
            continue
        customers[customer_id] = customer
        if target_email and normalize_email(customer.get("email")) == target_email:
            matched_reasons.setdefault(customer_id, set()).add("email")
        if target_phone and normalize_phone(customer.get("phone")) == target_phone:
            matched_reasons.setdefault(customer_id, set()).add("phone")

    for identity in (identities_response.data if identities_response else []) or []:
        customer_id = identity.get("customer_id")
        if (
            customer_id in customers
            and target_facebook
            and normalize_facebook(identity.get("display_value")) == target_facebook
        ):
            matched_reasons.setdefault(customer_id, set()).add("Facebook")

    matches = []
    for customer_id, reasons in matched_reasons.items():
        if customer_id == exclude_customer_id:
            continue
        customer = customers[customer_id]
        display_name = (
            customer.get("preferred_name")
            or customer.get("legal_name")
            or customer.get("email")
            or customer.get("phone")
            or "Unknown customer"
        )
        matches.append(
            CustomerMatch(
                customer_id=customer_id,
                display_name=display_name,
                email=customer.get("email"),
                phone=customer.get("phone"),
                matched_on=tuple(sorted(reasons)),
            )
        )
    return sorted(matches, key=lambda match: match.display_name.casefold())


def create_lead(lead: LeadCreateInput, *, client: "Client") -> LeadCreateResult:
    errors = validate_lead_input(lead)
    if errors:
        raise ValueError(" ".join(errors))

    payload = {
        "p_customer_name": lead.customer_name.strip(),
        "p_event_date": lead.event_date.isoformat(),
        "p_requested_bench_count": lead.requested_bench_count,
        "p_preferred_contact_method": lead.preferred_contact_method,
        "p_source": lead.source,
        "p_email": normalize_email(lead.email),
        "p_phone": (lead.phone or "").strip() or None,
        "p_facebook_identity": (lead.facebook_identity or "").strip() or None,
        "p_event_type": (lead.event_type or "").strip() or None,
        "p_facebook_conversation_url": (
            (lead.facebook_conversation_url or "").strip() or None
        ),
        "p_customer_notes": (lead.customer_notes or "").strip() or None,
        "p_internal_notes": (lead.internal_notes or "").strip() or None,
        "p_existing_customer_id": lead.existing_customer_id,
    }

    try:
        response = client.rpc("create_lead", payload).execute()
        data = response.data
        row = data[0] if isinstance(data, list) and data else data
        if not isinstance(row, dict):
            raise ValueError("The create_lead RPC returned no result.")
        booking_id = row.get("booking_id")
        booking_number = row.get("booking_number")
        if not booking_id or not booking_number:
            raise ValueError("The create_lead RPC returned an incomplete result.")
    except Exception as error:
        raise LeadServiceError("Unable to create the lead.") from error

    return LeadCreateResult(
        booking_id=str(booking_id),
        booking_number=str(booking_number),
    )


def update_lead(lead: LeadUpdateInput, *, client: "Client") -> LeadUpdateResult:
    """Atomically update an existing lead and its shared customer."""
    errors = validate_lead_input(lead)
    if errors:
        raise ValueError(" ".join(errors))

    payload = {
        "p_booking_number": lead.booking_number,
        "p_customer_name": lead.customer_name.strip(),
        "p_event_date": lead.event_date.isoformat(),
        "p_requested_bench_count": lead.requested_bench_count,
        "p_preferred_contact_method": lead.preferred_contact_method,
        "p_source": lead.source,
        "p_email": normalize_email(lead.email),
        "p_phone": (lead.phone or "").strip() or None,
        "p_facebook_identity": (lead.facebook_identity or "").strip() or None,
        "p_event_type": (lead.event_type or "").strip() or None,
        "p_facebook_conversation_url": (
            (lead.facebook_conversation_url or "").strip() or None
        ),
        "p_customer_notes": (lead.customer_notes or "").strip() or None,
        "p_internal_notes": (lead.internal_notes or "").strip() or None,
    }

    try:
        response = client.rpc("update_lead", payload).execute()
        data = response.data
        row = data[0] if isinstance(data, list) and data else data
        if not isinstance(row, dict) or not row.get("booking_number"):
            raise ValueError("The update_lead RPC returned an incomplete result.")
    except Exception as error:
        raise LeadServiceError("Unable to update the lead.") from error

    return LeadUpdateResult(booking_number=str(row["booking_number"]))


def set_lead_disposition(
    disposition: LeadDispositionInput,
) -> LeadDispositionResult:
    """Atomically close or restore a lead through the guarded RPC."""
    errors = validate_lead_disposition(disposition)
    if errors:
        raise ValueError(" ".join(errors))

    payload = {
        "p_booking_number": disposition.booking_number.strip(),
        "p_target_stage": disposition.target_stage,
        "p_reason": (disposition.reason or "").strip() or None,
    }

    try:
        response = get_supabase_client().rpc(
            "set_lead_disposition",
            payload,
        ).execute()
        data = response.data
        row = data[0] if isinstance(data, list) and data else data
        if (
            not isinstance(row, dict)
            or not row.get("booking_number")
            or row.get("stage") != disposition.target_stage
        ):
            raise ValueError(
                "The set_lead_disposition RPC returned an incomplete result."
            )
    except Exception as error:
        raise LeadServiceError("Unable to change the lead status.") from error

    return LeadDispositionResult(
        booking_number=str(row["booking_number"]),
        stage=str(row["stage"]),
    )
