"""Pure summary calculations for the current lead-management dashboard."""

from dataclasses import dataclass
from datetime import date, timedelta

from services.bookings import (
    BookingFilters,
    BookingRecord,
    filter_bookings,
    group_active_leads,
)


@dataclass(frozen=True)
class HomeSummary:
    active_count: int
    next_30_days_count: int
    attention_count: int
    upcoming: list[BookingRecord]
    needs_attention: list[BookingRecord]


def summarize_leads(leads: list[BookingRecord], business_date: date) -> HomeSummary:
    """Summarize lead-stage inquiries using the same date rules as Bookings."""
    active = [lead for lead in leads if lead.get("stage") == "lead"]
    upcoming, attention = group_active_leads(active, business_date)
    next_month = filter_bookings(
        active,
        BookingFilters(
            start_date=business_date,
            end_date=business_date + timedelta(days=29),
        ),
        business_date,
    )
    return HomeSummary(
        active_count=len(active),
        next_30_days_count=len(next_month),
        attention_count=len(attention),
        upcoming=upcoming[:5],
        needs_attention=attention[:5],
    )
