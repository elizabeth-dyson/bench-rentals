from collections.abc import Mapping
from dataclasses import asdict
from datetime import date, datetime
import re
from typing import Any
from urllib.parse import quote, urlparse

import streamlit as st

from components.presentation import render_booking_summary, render_stage_badge
from services.bookings import (
    BOOKING_STAGES,
    BookingFilters,
    BookingRecord,
    BookingServiceError,
    filter_bookings,
    get_booking_detail,
    get_business_date,
    group_active_leads,
    list_active_leads,
    list_bookings,
)
from services.leads import (
    CustomerMatch,
    LeadCreateInput,
    LeadDispositionInput,
    LeadDispositionResult,
    LeadServiceError,
    LeadUpdateInput,
    create_lead,
    find_customer_matches,
    normalize_email,
    normalize_facebook,
    normalize_phone,
    set_lead_disposition,
    update_lead,
    validate_lead_disposition,
    validate_lead_input,
)
from utils.formatting import (
    format_bench_count as _format_bench_count,
    format_booking_date,
    format_booking_source,
    format_booking_stage,
    format_contact_method,
    format_customer_name,
    is_valid_booking_number,
)
from utils.scrolling import request_scroll_to_top


_SEARCH_FILTERS_KEY = "booking_search_filters"
_SEARCH_WIDGET_KEYS = (
    "booking_search_text",
    "booking_search_stages",
    "booking_search_stage",
    "booking_search_dates",
)
_DISPOSITION_REASON_PREFIX = "lead_disposition_reason_"
_DISPOSITION_CLEAR_KEY = "lead_disposition_clear_draft"


def render_bookings() -> None:
    """Render the Bookings workspace and lead-creation flow."""
    form_mode = (
        st.session_state.get("lead_flow_step")
        or st.query_params.get("mode") == "edit"
    )
    with st.container(width=760 if form_mode else 1150):
        _render_bookings_workspace()


def _render_bookings_workspace() -> None:
    selected_booking = st.query_params.get("booking")
    if selected_booking is not None:
        _render_booking_detail(selected_booking)
        return

    success_number = st.session_state.pop("lead_success_number", None)
    if success_number:
        st.success(f"Lead {success_number} was created.")

    flow_step = st.session_state.get("lead_flow_step")
    if flow_step:
        if st.button("Cancel", icon=":material/close:"):
            _clear_lead_flow()
            request_scroll_to_top()
            st.rerun()
        if flow_step == "form":
            _render_create_lead_form()
        else:
            _render_lead_review()
        return

    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container():
            st.title("Bookings")
            st.caption("Keep every inquiry moving, from first contact to next steps.")
        add_lead = st.button(
            "Add lead", icon=":material/add:", type="primary", width="content"
        )
    if add_lead:
        st.session_state["lead_flow_step"] = "form"
        request_scroll_to_top()
        st.rerun()
        return

    if _render_search_controls():
        return

    filters = _get_applied_booking_filters()
    try:
        with st.spinner("Loading bookings..."):
            if filters is None:
                bookings = list_active_leads()
            else:
                all_bookings = list_bookings()
                bookings = filter_bookings(
                    all_bookings,
                    filters,
                    get_business_date(),
                )
    except BookingServiceError:
        st.error("Bookings couldn't be loaded. Please try again.")
        if st.button("Try again", width="stretch"):
            st.rerun()
        return

    if filters is not None:
        if not all_bookings:
            st.info("No bookings yet.")
            return
        if not bookings:
            st.info("No bookings match these filters.")
            return

        booking_label = "booking" if len(bookings) == 1 else "bookings"
        st.subheader(f"Search results ({len(bookings)} {booking_label})")
        for booking in bookings:
            _render_booking_card(booking)
        return

    if not bookings:
        st.info("No active leads.")
        return

    lead_label = "lead" if len(bookings) == 1 else "leads"
    st.subheader(f"Active leads ({len(bookings)} {lead_label})")

    upcoming, past_or_problem = group_active_leads(bookings, get_business_date())

    for lead in upcoming:
        _render_booking_card(lead)

    if past_or_problem:
        st.subheader("Past leads needing attention")
        st.warning(
            "These leads have a past or missing event date and may need follow-up."
        )
        for lead in past_or_problem:
            _render_booking_card(lead)


def _render_search_controls() -> bool:
    """Render search controls and return whether this run should stop."""
    applied_filters = _get_applied_booking_filters()
    initial_filters = applied_filters or BookingFilters()
    st.session_state.setdefault(
        "booking_search_text",
        initial_filters.search_text,
    )
    st.session_state.setdefault(
        "booking_search_stages",
        list(initial_filters.stages),
    )
    st.session_state.setdefault(
        "booking_search_dates",
        (
            (initial_filters.start_date, initial_filters.end_date)
            if initial_filters.start_date and initial_filters.end_date
            else ()
        ),
    )

    with st.expander("Search and filters", expanded=applied_filters is not None):
        st.caption("Leave every field blank to show all bookings.")
        with st.form("booking_search_form"):
            search_text = st.text_input(
                "Search",
                placeholder="Customer, contact, or booking number",
                key="booking_search_text",
                persist_state="session",
            )
            stages = st.multiselect(
                "Stages",
                BOOKING_STAGES,
                format_func=format_booking_stage,
                placeholder="All stages",
                key="booking_search_stages",
                persist_state="session",
            )
            date_range = st.date_input(
                "Event date range",
                key="booking_search_dates",
                format="MM/DD/YYYY",
                persist_state="session",
            )
            submitted = st.form_submit_button(
                "Apply filters",
                icon=":material/search:",
                width="stretch",
            )

    if submitted:
        dates = _search_date_bounds(date_range)
        if dates is None:
            st.error("Choose both a start and end date, or clear the date range.")
            return False
        if not isinstance(stages, (list, tuple)) or any(
            stage not in BOOKING_STAGES for stage in stages
        ):
            st.error("Choose valid booking stages.")
            return False

        start_date, end_date = dates
        if start_date and end_date and start_date > end_date:
            st.error("The start date must be on or before the end date.")
            return False

        st.session_state[_SEARCH_FILTERS_KEY] = BookingFilters(
            search_text=search_text.strip(),
            stages=tuple(stages),
            start_date=start_date,
            end_date=end_date,
        )
        request_scroll_to_top()
        st.rerun()
        return True

    if applied_filters is not None:
        st.button(
            "Clear filters",
            icon=":material/filter_alt_off:",
            width="stretch",
            on_click=_clear_booking_search_state,
        )

    return False


def _get_applied_booking_filters() -> BookingFilters | None:
    filters = st.session_state.get(_SEARCH_FILTERS_KEY)
    return filters if isinstance(filters, BookingFilters) else None


def _search_date_bounds(value: Any) -> tuple[date | None, date | None] | None:
    if value in (None, (), []):
        return None, None
    if not isinstance(value, (tuple, list)) or len(value) != 2:
        return None
    start_date, end_date = value
    if not isinstance(start_date, date) or not isinstance(end_date, date):
        return None
    return start_date, end_date


def _clear_booking_search_state() -> None:
    st.session_state.pop(_SEARCH_FILTERS_KEY, None)
    for key in _SEARCH_WIDGET_KEYS:
        st.session_state.pop(key, None)
    request_scroll_to_top()


def _render_create_lead_form() -> None:
    st.title("Add a lead")
    st.caption("Enter what you know now. Optional details can be updated later.")

    with st.form("create_lead_form", enter_to_submit=False):
        st.markdown("#### Customer and event")
        customer_name = st.text_input("Customer name", key="lead_customer_name")
        event_date = st.date_input(
            "Event date",
            value="today",
            format="MM/DD/YYYY",
            key="lead_event_date",
        )
        bench_count = st.number_input(
            "Requested benches",
            min_value=1,
            step=1,
            key="lead_bench_count",
        )

        st.markdown("#### Contact information")
        email = st.text_input("Email", key="lead_email")
        phone = st.text_input("Phone", key="lead_phone")
        facebook = st.text_input(
            "Facebook name or handle",
            key="lead_facebook_identity",
        )
        preferred_method = st.selectbox(
            "Preferred contact method",
            ("facebook", "text", "phone", "email"),
            format_func=lambda value: {
                "facebook": "Facebook",
                "text": "Text",
                "phone": "Phone call",
                "email": "Email",
            }[value],
            key="lead_preferred_contact_method",
        )

        st.markdown("#### Inquiry details")
        source = st.selectbox(
            "Lead source",
            (
                "facebook_marketplace",
                "facebook_referral",
                "word_of_mouth",
                "repeat_customer",
                "other",
            ),
            format_func=lambda value: value.replace("_", " ").title(),
            key="lead_source",
        )
        event_type = st.text_input(
            "Event type (optional)",
            placeholder="Wedding, graduation, party...",
            key="lead_event_type",
        )
        conversation_url = st.text_input(
            "Facebook conversation URL (optional)",
            key="lead_facebook_conversation_url",
        )
        st.markdown("#### Notes")
        customer_notes = st.text_area(
            "Customer notes (optional)",
            key="lead_customer_notes",
        )
        internal_notes = st.text_area(
            "Internal notes (optional)",
            key="lead_internal_notes",
        )
        submitted = st.form_submit_button(
            "Review lead", type="primary", width="stretch"
        )

    if not submitted:
        return

    lead = LeadCreateInput(
        customer_name=customer_name,
        event_date=event_date,
        requested_bench_count=int(bench_count),
        preferred_contact_method=preferred_method,
        source=source,
        email=email,
        phone=phone,
        facebook_identity=facebook,
        event_type=event_type,
        facebook_conversation_url=conversation_url,
        customer_notes=customer_notes,
        internal_notes=internal_notes,
    )
    errors = validate_lead_input(lead)
    if errors:
        for error in errors:
            st.error(error)
        return

    try:
        with st.spinner("Checking existing customers..."):
            matches = find_customer_matches(
                email=lead.email,
                phone=lead.phone,
                facebook_identity=lead.facebook_identity,
            )
    except LeadServiceError:
        st.error("Existing customers couldn't be checked. Please try again.")
        return

    st.session_state["lead_pending_input"] = lead
    st.session_state["lead_customer_matches"] = matches
    st.session_state["lead_flow_step"] = "review"
    request_scroll_to_top()
    st.rerun()


def _render_lead_review() -> None:
    lead = st.session_state.get("lead_pending_input")
    matches = st.session_state.get("lead_customer_matches", [])
    if not isinstance(lead, LeadCreateInput):
        _clear_lead_flow()
        request_scroll_to_top()
        st.rerun()
        return

    st.title("Review lead")
    with st.container(border=True):
        st.markdown(f"### {lead.customer_name}")
        st.write(f"Event date: {format_booking_date(lead.event_date)}")
        st.write(f"Benches requested: {_format_bench_count(lead.requested_bench_count)}")
        st.write(f"Preferred contact: {format_booking_stage(lead.preferred_contact_method)}")

    new_customer_value = "__new_customer__"
    options = [match.customer_id for match in matches] + [new_customer_value]
    match_by_id = {match.customer_id: match for match in matches}

    if matches:
        st.warning("We found customer contact information that may already exist.")
        for match in matches:
            _render_customer_match(match)
        selection_label = "Choose which customer to use"
    else:
        st.info("No existing customer matches were found.")
        selection_label = "Customer record"

    with st.form("confirm_create_lead_form"):
        selection = st.radio(
            selection_label,
            options,
            format_func=lambda value: (
                "Create a new customer"
                if value == new_customer_value
                else f"Reuse {match_by_id[value].display_name}"
            ),
            index=len(options) - 1,
            key="lead_customer_selection",
        )
        submitted = st.form_submit_button(
            "Create lead", type="primary", width="stretch"
        )

    if not submitted:
        return

    selected_customer_id = None if selection == new_customer_value else selection
    reviewed_lead = LeadCreateInput(
        **{
            **lead.__dict__,
            "existing_customer_id": selected_customer_id,
        }
    )
    try:
        with st.spinner("Creating lead..."):
            result = create_lead(reviewed_lead)
    except LeadServiceError:
        st.error("The lead couldn't be created. Please try again.")
        return

    _clear_lead_flow()
    _clear_booking_search_state()
    st.session_state["lead_success_number"] = result.booking_number
    request_scroll_to_top()
    st.rerun()


def _render_customer_match(match: CustomerMatch) -> None:
    with st.container(border=True):
        st.markdown(f"**{match.display_name}**")
        contact_parts = [value for value in (match.email, match.phone) if value]
        if contact_parts:
            st.caption(" · ".join(contact_parts))
        st.caption(f"Matched on: {', '.join(match.matched_on)}")


def _clear_lead_flow() -> None:
    for key in list(st.session_state):
        if key.startswith("lead_") and key != "lead_success_number":
            del st.session_state[key]


def _render_booking_card(booking: BookingRecord) -> None:
    if render_booking_summary(booking, key_prefix="view_booking"):
        st.query_params["booking"] = booking["booking_number"]
        request_scroll_to_top()
        st.rerun()


def _render_booking_detail(booking_number: Any) -> None:
    _clear_disposition_draft_if_requested()
    edit_mode = st.query_params.get("mode") == "edit"
    if not edit_mode and st.button(
        "Back to bookings",
        key="back_to_bookings",
        icon=":material/arrow_back:",
        width="content",
    ):
        _clear_booking_route()
        request_scroll_to_top()
        st.rerun()
        return

    if not is_valid_booking_number(booking_number):
        st.title("Booking not found")
        st.info("This booking link isn't valid.")
        return

    try:
        with st.spinner("Loading booking details..."):
            booking = get_booking_detail(booking_number.strip())
    except BookingServiceError:
        st.title("Booking details")
        st.error("This booking couldn't be loaded. Please try again.")
        if st.button(
            "Try again",
            key="retry_booking_detail",
            icon=":material/refresh:",
            width="stretch",
        ):
            st.rerun()
        return

    if booking is None:
        st.title("Booking not found")
        st.info("No booking exists with that booking number.")
        return

    if edit_mode and booking.get("stage") == "lead":
        _render_edit_lead(booking)
        return
    if edit_mode:
        _clear_edit_route_parameter()
        st.warning("Only lead-stage bookings can be edited here.")

    customer = booking.get("primary_customer")
    customer_record = customer if isinstance(customer, Mapping) else None
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container():
            st.title(format_customer_name(customer_record))
            st.caption(booking.get("booking_number") or "Booking number not set")
            render_stage_badge(booking.get("stage"))
        if booking.get("stage") == "lead" and st.button(
            "Edit lead",
            key="edit_lead",
            icon=":material/edit:",
            type="primary",
            width="content",
        ):
            _clear_edit_state()
            st.query_params["mode"] = "edit"
            request_scroll_to_top()
            st.rerun()
            return

    success_number = st.session_state.pop("lead_update_success", None)
    if success_number:
        st.success(f"Lead {success_number} was updated.")
    disposition_success = st.session_state.pop("lead_disposition_success", None)
    if isinstance(disposition_success, LeadDispositionResult):
        success_messages = {
            "lost": f"Lead {disposition_success.booking_number} was marked lost.",
            "cancelled": (
                f"Lead {disposition_success.booking_number} was marked cancelled."
            ),
            "lead": f"Lead {disposition_success.booking_number} was restored.",
        }
        st.success(success_messages[disposition_success.stage])

    with st.container(horizontal=True, vertical_alignment="top"):
        with st.container(width=540):
            _render_contact_details(customer_record, booking)
        with st.container(width=540):
            _render_event_details(booking)
    _render_notes(booking)

    _render_lead_status(
        booking,
        format_customer_name(customer_record),
    )


def _render_lead_status(booking: BookingRecord, customer_name: str) -> None:
    stage = booking.get("stage")
    if stage not in {"lead", "lost", "cancelled"}:
        return

    booking_number = booking.get("booking_number")
    if not is_valid_booking_number(booking_number):
        return

    with st.container(border=True):
        st.subheader("Lead status")
        if stage == "lead":
            st.write("This inquiry is currently an active lead.")
            if st.button(
                "Mark lost",
                key="mark_lead_lost",
                icon=":material/thumb_down:",
                width="stretch",
            ):
                _render_lead_disposition_dialog(
                    booking_number,
                    customer_name,
                    stage,
                    "lost",
                )
            if st.button(
                "Mark cancelled",
                key="mark_lead_cancelled",
                icon=":material/cancel:",
                width="stretch",
            ):
                _render_lead_disposition_dialog(
                    booking_number,
                    customer_name,
                    stage,
                    "cancelled",
                )
            return

        reason_field = "lost_reason" if stage == "lost" else "cancellation_reason"
        st.write(f"Status: {format_booking_stage(stage)}")
        st.write(f"Reason: {_display_or_fallback(booking.get(reason_field))}")
        if st.button(
            "Restore to lead",
            key="restore_to_lead",
            icon=":material/restore:",
            type="primary",
            width="stretch",
        ):
            _render_lead_disposition_dialog(
                booking_number,
                customer_name,
                stage,
                "lead",
            )


@st.dialog(
    "Confirm lead status change",
    dismissible=False,
    icon=":material/warning:",
)
def _render_lead_disposition_dialog(
    booking_number: str,
    customer_name: str,
    current_stage: str,
    target_stage: str,
) -> None:
    _render_lead_disposition_dialog_content(
        booking_number,
        customer_name,
        current_stage,
        target_stage,
    )


def _render_lead_disposition_dialog_content(
    booking_number: str,
    customer_name: str,
    current_stage: str,
    target_stage: str,
) -> None:
    target_label = format_booking_stage(target_stage)
    st.write(f"Customer: {customer_name}")
    st.caption(booking_number)

    if target_stage == "lead":
        st.write(
            f"Restore this {format_booking_stage(current_stage).lower()} record "
            "to Active Leads? Its previous closure reason will be cleared."
        )
    else:
        st.write(f"Mark this lead as {target_label.lower()}?")

    reason: str | None = None
    with st.form(
        f"lead_disposition_form_{booking_number}_{target_stage}",
        enter_to_submit=False,
    ):
        if target_stage in {"lost", "cancelled"}:
            reason = st.text_area(
                "Reason",
                placeholder="Why is this lead being closed?",
                key=f"{_DISPOSITION_REASON_PREFIX}{booking_number}_{target_stage}",
                persist_state="session",
            )
        confirmed = st.form_submit_button(
            "Restore lead" if target_stage == "lead" else f"Mark {target_label.lower()}",
            type="primary",
            width="stretch",
        )
        keep_current = st.form_submit_button(
            "Keep current status",
            width="stretch",
        )

    if keep_current:
        st.session_state[_DISPOSITION_CLEAR_KEY] = True
        st.rerun()
        return
    if not confirmed:
        return

    disposition = LeadDispositionInput(
        booking_number=booking_number,
        target_stage=target_stage,
        reason=reason,
    )
    errors = validate_lead_disposition(disposition)
    if errors:
        for error in errors:
            st.error(error)
        return

    try:
        with st.spinner("Updating lead status..."):
            result = set_lead_disposition(disposition)
    except LeadServiceError:
        st.error("The lead status couldn't be changed. Please try again.")
        return

    st.session_state["lead_disposition_success"] = result
    st.session_state[_DISPOSITION_CLEAR_KEY] = True
    request_scroll_to_top()
    st.rerun()


def _clear_disposition_draft_if_requested() -> None:
    if not st.session_state.pop(_DISPOSITION_CLEAR_KEY, False):
        return
    for key in list(st.session_state):
        if key.startswith(_DISPOSITION_REASON_PREFIX):
            del st.session_state[key]


def _render_edit_lead(booking: BookingRecord) -> None:
    original = _lead_update_from_booking(booking)
    if original is None:
        st.title("Edit lead")
        st.error("This lead doesn't have enough customer information to edit safely.")
        if st.button("Return to details", width="stretch"):
            _exit_edit_mode()
        return

    if st.session_state.get("edit_discard_pending"):
        _render_discard_confirmation()
        return

    _initialize_edit_state(original)
    st.title("Edit lead")
    st.caption(original.booking_number)
    st.info(
        "Customer name and contact changes update this shared customer everywhere "
        "they appear."
    )

    with st.form("edit_lead_form", enter_to_submit=False):
        st.markdown("#### Customer and event")
        customer_name = st.text_input("Customer name", key="edit_customer_name")
        event_date_value = st.date_input(
            "Event date", format="MM/DD/YYYY", key="edit_event_date"
        )
        bench_count = st.number_input(
            "Requested benches", min_value=1, step=1, key="edit_bench_count"
        )
        st.markdown("#### Contact information")
        email = st.text_input("Email", key="edit_email")
        phone = st.text_input("Phone", key="edit_phone")
        facebook = st.text_input(
            "Primary Facebook name or handle", key="edit_facebook_identity"
        )
        preferred_method = st.selectbox(
            "Preferred contact method",
            ("facebook", "text", "phone", "email"),
            format_func=lambda value: {
                "facebook": "Facebook",
                "text": "Text",
                "phone": "Phone call",
                "email": "Email",
            }[value],
            key="edit_preferred_contact_method",
        )
        st.markdown("#### Inquiry details")
        source = st.selectbox(
            "Lead source",
            (
                "facebook_marketplace",
                "facebook_referral",
                "word_of_mouth",
                "repeat_customer",
                "other",
            ),
            format_func=lambda value: value.replace("_", " ").title(),
            key="edit_source",
        )
        event_type = st.text_input("Event type (optional)", key="edit_event_type")
        conversation_url = st.text_input(
            "Facebook conversation URL (optional)",
            key="edit_facebook_conversation_url",
        )
        st.markdown("#### Notes")
        customer_notes = st.text_area(
            "Customer notes (optional)", key="edit_customer_notes"
        )
        internal_notes = st.text_area(
            "Internal notes (optional)", key="edit_internal_notes"
        )
        save_submitted = st.form_submit_button(
            "Save changes", type="primary", width="stretch"
        )
        cancel_submitted = st.form_submit_button("Cancel", width="stretch")

    draft = LeadUpdateInput(
        booking_number=original.booking_number,
        customer_id=original.customer_id,
        customer_name=customer_name,
        event_date=event_date_value,
        requested_bench_count=int(bench_count),
        preferred_contact_method=preferred_method,
        source=source,
        email=email,
        phone=phone,
        facebook_identity=facebook,
        event_type=event_type,
        facebook_conversation_url=conversation_url,
        customer_notes=customer_notes,
        internal_notes=internal_notes,
    )

    if cancel_submitted:
        if _normalized_update(draft) == st.session_state["edit_original"]:
            _exit_edit_mode()
        else:
            st.session_state["edit_pending_draft"] = draft
            st.session_state["edit_discard_pending"] = True
            request_scroll_to_top()
            st.rerun()
        return
    if not save_submitted:
        return

    errors = validate_lead_input(draft)
    if errors:
        for error in errors:
            st.error(error)
        return

    try:
        with st.spinner("Checking customer contact information..."):
            matches = find_customer_matches(
                email=draft.email,
                phone=draft.phone,
                facebook_identity=draft.facebook_identity,
                exclude_customer_id=draft.customer_id,
            )
    except LeadServiceError:
        st.error("Customer contact information couldn't be checked. Please try again.")
        return
    if matches:
        names = ", ".join(match.display_name for match in matches)
        st.error(
            "That contact information belongs to another customer: "
            f"{names}. No changes were saved."
        )
        return

    try:
        with st.spinner("Saving changes..."):
            result = update_lead(draft)
    except LeadServiceError:
        st.error("The lead couldn't be updated. Please try again.")
        return

    _clear_edit_state()
    _clear_edit_route_parameter()
    st.session_state["lead_update_success"] = result.booking_number
    st.rerun()


def _render_discard_confirmation() -> None:
    st.title("Discard changes?")
    st.warning("You have unsaved changes to this lead.")
    if st.button(
        "Discard changes",
        key="confirm_discard_edit",
        icon=":material/delete:",
        width="stretch",
    ):
        _exit_edit_mode()
        return
    if st.button(
        "Continue editing",
        key="continue_editing",
        icon=":material/arrow_back:",
        width="stretch",
    ):
        draft = st.session_state.get("edit_pending_draft")
        _clear_edit_widget_values()
        if isinstance(draft, LeadUpdateInput):
            _set_edit_widget_values(draft)
        st.session_state.pop("edit_pending_draft", None)
        st.session_state.pop("edit_discard_pending", None)
        request_scroll_to_top()
        st.rerun()


def _lead_update_from_booking(booking: BookingRecord) -> LeadUpdateInput | None:
    customer = booking.get("primary_customer")
    if not isinstance(customer, Mapping):
        return None
    customer_id = _clean_text(customer.get("id"))
    booking_number = _clean_text(booking.get("booking_number"))
    event_date_value = _parse_date(booking.get("event_date"))
    bench_count = booking.get("requested_bench_count")
    if (
        not customer_id
        or not booking_number
        or event_date_value is None
        or not isinstance(bench_count, int)
        or isinstance(bench_count, bool)
    ):
        return None

    identities = customer.get("facebook_identities")
    facebook_identity = None
    if isinstance(identities, list):
        valid_identities = [item for item in identities if isinstance(item, Mapping)]
        valid_identities.sort(
            key=lambda item: (
                not bool(item.get("is_primary_for_type")),
                str(item.get("created_at") or ""),
            )
        )
        if valid_identities:
            facebook_identity = _clean_text(valid_identities[0].get("display_value"))

    return LeadUpdateInput(
        booking_number=booking_number,
        customer_id=customer_id,
        customer_name=format_customer_name(customer),
        event_date=event_date_value,
        requested_bench_count=bench_count,
        preferred_contact_method=(
            _clean_text(customer.get("preferred_contact_method")) or "facebook"
        ),
        source=_clean_text(booking.get("source")) or "facebook_marketplace",
        email=_clean_text(customer.get("email")),
        phone=_clean_text(customer.get("phone")),
        facebook_identity=facebook_identity,
        event_type=_clean_text(booking.get("event_type")),
        facebook_conversation_url=_clean_text(
            booking.get("facebook_conversation_url")
        ),
        customer_notes=_clean_text(booking.get("customer_notes")),
        internal_notes=_clean_text(booking.get("internal_notes")),
    )


def _initialize_edit_state(original: LeadUpdateInput) -> None:
    if st.session_state.get("edit_booking_number") == original.booking_number:
        return
    _clear_edit_state()
    st.session_state["edit_booking_number"] = original.booking_number
    st.session_state["edit_original"] = _normalized_update(original)
    _set_edit_widget_values(original)


def _set_edit_widget_values(lead: LeadUpdateInput) -> None:
    st.session_state.update(
        {
            "edit_customer_name": lead.customer_name,
            "edit_event_date": lead.event_date,
            "edit_bench_count": lead.requested_bench_count,
            "edit_email": lead.email or "",
            "edit_phone": lead.phone or "",
            "edit_facebook_identity": lead.facebook_identity or "",
            "edit_preferred_contact_method": lead.preferred_contact_method,
            "edit_source": lead.source,
            "edit_event_type": lead.event_type or "",
            "edit_facebook_conversation_url": lead.facebook_conversation_url or "",
            "edit_customer_notes": lead.customer_notes or "",
            "edit_internal_notes": lead.internal_notes or "",
        }
    )


def _normalized_update(lead: LeadUpdateInput) -> dict[str, Any]:
    values = asdict(lead)
    values.update(
        customer_name=lead.customer_name.strip(),
        email=normalize_email(lead.email),
        phone=normalize_phone(lead.phone),
        facebook_identity=normalize_facebook(lead.facebook_identity),
        event_type=_clean_text(lead.event_type),
        facebook_conversation_url=_clean_text(lead.facebook_conversation_url),
        customer_notes=_clean_text(lead.customer_notes),
        internal_notes=_clean_text(lead.internal_notes),
    )
    return values


def _exit_edit_mode() -> None:
    _clear_edit_state()
    _clear_edit_route_parameter()
    request_scroll_to_top()
    st.rerun()


def _clear_edit_widget_values() -> None:
    for key in list(st.session_state):
        if key.startswith("edit_") and key not in {
            "edit_booking_number",
            "edit_original",
        }:
            del st.session_state[key]


def _clear_edit_state() -> None:
    for key in list(st.session_state):
        if key.startswith("edit_"):
            del st.session_state[key]


def _clear_edit_route_parameter() -> None:
    if "mode" in st.query_params:
        del st.query_params["mode"]


def _parse_date(value: Any) -> date | None:
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


def _render_contact_details(
    customer: Mapping[str, Any] | None,
    booking: BookingRecord,
) -> None:
    with st.container(border=True):
        st.subheader("Contact information")
        st.write(
            "Preferred contact: "
            f"{format_contact_method(_mapping_value(customer, 'preferred_contact_method'))}"
        )

        email = _clean_text(_mapping_value(customer, "email"))
        phone = _clean_text(_mapping_value(customer, "phone"))
        email_target = _email_link_target(email)
        phone_target = _phone_link_target(phone)
        if email_target:
            st.link_button(
                email,
                email_target,
                icon=":material/mail:",
                width="stretch",
            )
        elif email:
            st.write(f"Email: {email}")
        else:
            st.write("Email: Not provided")
        if phone_target:
            st.link_button(
                phone,
                phone_target,
                icon=":material/call:",
                width="stretch",
            )
        elif phone:
            st.write(f"Phone: {phone}")
        else:
            st.write("Phone: Not provided")

        identities = _mapping_value(customer, "facebook_identities")
        facebook_identities = identities if isinstance(identities, list) else []
        if facebook_identities:
            st.markdown("**Facebook**")
            for index, identity in enumerate(facebook_identities):
                if not isinstance(identity, Mapping):
                    continue
                display_value = _clean_text(identity.get("display_value"))
                profile_url = _valid_web_url(identity.get("profile_url"))
                if profile_url:
                    st.link_button(
                        display_value or "Facebook profile",
                        profile_url,
                        key=f"facebook_profile_{index}",
                        icon=":material/person:",
                        width="stretch",
                    )
                elif display_value:
                    st.write(display_value)
        else:
            st.write("Facebook: Not provided")

        conversation_url = _valid_web_url(booking.get("facebook_conversation_url"))
        if conversation_url:
            st.link_button(
                "Open Facebook conversation",
                conversation_url,
                icon=":material/chat:",
                width="stretch",
            )


def _render_event_details(booking: BookingRecord) -> None:
    with st.container(border=True):
        st.subheader("Event details")
        st.write(f"Event date: {format_booking_date(booking.get('event_date'))}")
        st.write(f"Event type: {_display_or_fallback(booking.get('event_type'))}")
        st.write(
            "Benches requested: "
            f"{_format_bench_count(booking.get('requested_bench_count'))}"
        )
        st.write(f"Lead source: {format_booking_source(booking.get('source'))}")


def _render_notes(booking: BookingRecord) -> None:
    with st.container(border=True):
        st.subheader("Notes")
        st.markdown("**Customer notes**")
        st.write(_display_or_fallback(booking.get("customer_notes")))
        st.markdown("**Internal notes**")
        st.write(_display_or_fallback(booking.get("internal_notes")))


def _clear_booking_route() -> None:
    _clear_edit_state()
    if "mode" in st.query_params:
        del st.query_params["mode"]
    if "booking" in st.query_params:
        del st.query_params["booking"]


def _mapping_value(customer: Mapping[str, Any] | None, key: str) -> Any:
    return customer.get(key) if isinstance(customer, Mapping) else None


def _clean_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _display_or_fallback(value: Any) -> str:
    return _clean_text(value) or "Not provided"


def _valid_web_url(value: Any) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    parsed = urlparse(cleaned)
    return cleaned if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _email_link_target(value: str | None) -> str | None:
    if not value or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
        return None
    return f"mailto:{quote(value, safe='@.+')}"


def _phone_link_target(value: str | None) -> str | None:
    if not value:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if not 7 <= len(digits) <= 15:
        return None
    prefix = "+" if value.strip().startswith("+") else ""
    return f"tel:{prefix}{digits}"
