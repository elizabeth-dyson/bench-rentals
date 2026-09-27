from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from services.supabase import get_supabase_client


_ACTIVE_LEADS_SELECT = """
    id,
    booking_number,
    stage,
    event_date,
    requested_bench_count,
    primary_customer:customers!bookings_primary_customer_id_fkey(
        id,
        preferred_name,
        legal_name,
        email,
        phone
    )
"""
_BOOKING_LIST_SELECT = """
    booking_number,
    stage,
    event_date,
    requested_bench_count,
    primary_customer:customers!bookings_primary_customer_id_fkey(
        preferred_name,
        legal_name,
        email,
        phone,
        facebook_identities:customer_identities!customer_identities_customer_id_fkey(
            identity_type,
            display_value
        )
    )
"""
_BOOKING_DETAIL_SELECT = """
    booking_number,
    stage,
    source,
    event_type,
    event_date,
    requested_bench_count,
    facebook_conversation_url,
    customer_notes,
    internal_notes,
    cancellation_reason,
    lost_reason,
    primary_customer:customers!bookings_primary_customer_id_fkey(
        id,
        preferred_name,
        legal_name,
        email,
        phone,
        preferred_contact_method,
        facebook_identities:customer_identities!customer_identities_customer_id_fkey(
            id,
            display_value,
            profile_url,
            is_primary_for_type,
            created_at
        )
    )
"""
_BUSINESS_TIME_ZONE = ZoneInfo("America/Chicago")

BookingRecord = dict[str, Any]
BOOKING_STAGES = (
    "lead",
    "availability_confirmed",
    "hold",
    "intake_sent",
    "intake_received",
    "pricing_review",
    "quote_sent",
    "quote_accepted",
    "awaiting_confirmation",
    "confirmed",
    "upcoming",
    "delivered",
    "picked_up",
    "completed",
    "cancelled",
    "lost",
)


@dataclass(frozen=True)
class BookingFilters:
    """Applied criteria for the all-bookings workspace."""

    search_text: str = ""
    stages: tuple[str, ...] = ()
    start_date: date | None = None
    end_date: date | None = None


class BookingServiceError(RuntimeError):
    """Raised when booking data cannot be loaded."""


def list_active_leads() -> list[BookingRecord]:
    """Return lead-stage bookings visible to the authenticated user."""
    try:
        response = (
            get_supabase_client()
            .table("bookings")
            .select(_ACTIVE_LEADS_SELECT)
            .eq("stage", "lead")
            .order("event_date")
            .execute()
        )
    except Exception as error:
        raise BookingServiceError("Unable to load bookings.") from error

    return response.data or []


def list_bookings() -> list[BookingRecord]:
    """Return the lightweight booking index visible to the authenticated user."""
    try:
        response = (
            get_supabase_client()
            .table("bookings")
            .select(_BOOKING_LIST_SELECT)
            .order("event_date")
            .execute()
        )
    except Exception as error:
        raise BookingServiceError("Unable to load bookings.") from error

    return response.data or []


def get_booking_detail(booking_number: str) -> BookingRecord | None:
    """Return one booking by its public booking number, or None if not found."""
    try:
        response = (
            get_supabase_client()
            .table("bookings")
            .select(_BOOKING_DETAIL_SELECT)
            .eq("booking_number", booking_number)
            .eq("primary_customer.facebook_identities.identity_type", "facebook")
            .limit(1)
            .execute()
        )
        data = response.data
        if data is None or data == []:
            return None
        if not isinstance(data, list) or not isinstance(data[0], dict):
            raise ValueError("Supabase returned an invalid booking detail response.")
        return data[0]
    except BookingServiceError:
        raise
    except Exception as error:
        raise BookingServiceError("Unable to load booking details.") from error


def get_business_date() -> date:
    """Return today's date in the business's Central time zone."""
    return datetime.now(_BUSINESS_TIME_ZONE).date()


def group_active_leads(
    leads: list[BookingRecord],
    business_date: date,
) -> tuple[list[BookingRecord], list[BookingRecord]]:
    """Split leads into upcoming and past/problem groups in display order."""
    upcoming: list[tuple[date, BookingRecord]] = []
    past_or_problem: list[tuple[date | None, BookingRecord]] = []

    for lead in leads:
        event_date = _parse_event_date(lead.get("event_date"))
        if event_date is not None and event_date >= business_date:
            upcoming.append((event_date, lead))
        else:
            past_or_problem.append((event_date, lead))

    upcoming.sort(key=lambda item: item[0])
    past_or_problem.sort(
        key=lambda item: (item[0] is not None, item[0] or date.min),
        reverse=True,
    )

    return (
        [lead for _, lead in upcoming],
        [lead for _, lead in past_or_problem],
    )


def filter_bookings(
    bookings: list[BookingRecord],
    filters: BookingFilters,
    business_date: date,
) -> list[BookingRecord]:
    """Filter the booking index and return it in business-friendly date order."""
    matches = [
        booking
        for booking in bookings
        if _booking_matches_filters(booking, filters)
    ]
    upcoming, past_or_problem = group_active_leads(matches, business_date)
    return [*upcoming, *past_or_problem]


def _booking_matches_filters(
    booking: BookingRecord,
    filters: BookingFilters,
) -> bool:
    if filters.stages and booking.get("stage") not in filters.stages:
        return False

    event_date = _parse_event_date(booking.get("event_date"))
    if filters.start_date is not None:
        if event_date is None or event_date < filters.start_date:
            return False
    if filters.end_date is not None:
        if event_date is None or event_date > filters.end_date:
            return False

    query = _normalize_search_value(filters.search_text)
    if not query:
        return True

    customer = booking.get("primary_customer")
    customer_record = customer if isinstance(customer, dict) else {}
    searchable_values = [
        booking.get("booking_number"),
        customer_record.get("preferred_name"),
        customer_record.get("legal_name"),
        customer_record.get("email"),
    ]

    identities = customer_record.get("facebook_identities")
    if isinstance(identities, list):
        searchable_values.extend(
            identity.get("display_value")
            for identity in identities
            if isinstance(identity, dict)
            and identity.get("identity_type") == "facebook"
        )

    if any(
        query in _normalize_search_value(value)
        for value in searchable_values
    ):
        return True

    phone = customer_record.get("phone")
    query_digits = _digits_only(filters.search_text)
    return bool(query_digits and query_digits in _digits_only(phone))


def _normalize_search_value(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.casefold().split())


def _digits_only(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(character for character in value if character.isdigit())


def _parse_event_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        except ValueError:
            return None
    return None
