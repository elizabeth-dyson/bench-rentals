"""Shared native Streamlit presentation for the rental workspace."""

from collections.abc import Mapping

import streamlit as st

from services.bookings import BookingRecord
from utils.formatting import (
    format_bench_count,
    format_booking_date,
    format_booking_stage,
    format_customer_name,
    is_valid_booking_number,
)


def render_wordmark() -> None:
    st.markdown("### :material/event_seat: Bench Rental Manager")


def render_stage_badge(stage: str | None) -> None:
    color = {"lead": "blue", "lost": "gray", "cancelled": "red"}.get(
        stage, "gray"
    )
    st.badge(format_booking_stage(stage), color=color)


def render_booking_summary(booking: BookingRecord, *, key_prefix: str) -> bool:
    """Render a compact, wrapping summary and return whether it was opened."""
    customer = booking.get("primary_customer")
    customer_record = customer if isinstance(customer, Mapping) else None
    booking_number = booking.get("booking_number")
    with st.container(border=True, gap="small"):
        with st.container(horizontal=True, vertical_alignment="center", gap="small"):
            with st.container(width=280, gap=None):
                st.subheader(format_customer_name(customer_record))
                st.caption(booking_number or "Booking number not set")
            with st.container(width=200, gap=None):
                st.caption("Event date")
                st.write(format_booking_date(booking.get("event_date")))
            with st.container(width=170, gap=None):
                st.caption("Requested")
                st.write(format_bench_count(booking.get("requested_bench_count")))
            render_stage_badge(booking.get("stage"))
            if is_valid_booking_number(booking_number):
                return st.button(
                    "View details",
                    key=f"{key_prefix}_{booking_number}",
                    icon=":material/arrow_forward:",
                    width="content",
                )
    return False
