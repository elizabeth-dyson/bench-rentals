import streamlit as st

from components.auth import get_authenticated_user_display_name
from components.presentation import render_booking_summary
from services.bookings import BookingServiceError, get_business_date, list_active_leads
from services.home import summarize_leads
from utils.scrolling import request_scroll_to_top
from views.bookings import render_bookings


def render_home() -> None:
    """Render the authenticated home screen."""
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container():
            st.title("Home")
            st.write(f"Welcome back, {get_authenticated_user_display_name()}.")
        if st.button("View bookings", icon=":material/event_note:"):
            _open_bookings()
            return
    st.caption("Your inquiries at a glance. Leads are not confirmed reservations.")

    try:
        with st.spinner("Loading your workspace..."):
            summary = summarize_leads(list_active_leads(), get_business_date())
    except BookingServiceError:
        st.error("Your workspace couldn't be loaded. Please try again.")
        if st.button("Try again", key="home_retry"):
            st.rerun()
        return

    with st.container(horizontal=True):
        st.metric("Active leads", summary.active_count, border=True)
        st.metric(
            "Inquiries · next 30 days", summary.next_30_days_count, border=True,
            help="Event dates from today through the next 29 days, in Central time.",
        )
        st.metric(
            "Needs attention", summary.attention_count, border=True,
            help="Active leads with a past, missing, or invalid event date.",
        )

    if not summary.active_count:
        st.info("No active leads yet. Open Bookings to add your first inquiry.")
        return

    st.subheader("Upcoming inquiries")
    st.caption("The next five active leads by event date.")
    if not summary.upcoming:
        st.caption("No upcoming inquiries.")
    for lead in summary.upcoming:
        if render_booking_summary(lead, key_prefix="home_upcoming"):
            _open_bookings(lead["booking_number"])
            return

    st.subheader("Needs attention")
    st.caption("Past or missing event dates. Review these inquiries to keep your list current.")
    if not summary.needs_attention:
        st.caption("You're up to date. No leads need date review.")
    for lead in summary.needs_attention:
        if render_booking_summary(lead, key_prefix="home_attention"):
            _open_bookings(lead["booking_number"])
            return
    if summary.attention_count > 5:
        st.caption(f"Showing 5 of {summary.attention_count}. View Bookings for the full list.")


def _open_bookings(booking_number: str | None = None) -> None:
    request_scroll_to_top()
    st.switch_page(
        st.Page(render_bookings, title="Bookings", url_path="bookings"),
        query_params={"booking": booking_number} if booking_number else None,
    )
