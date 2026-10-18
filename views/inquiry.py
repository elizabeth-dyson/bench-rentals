"""Signed-out initial inquiry form; no internal client or booking reads."""

from dataclasses import dataclass, field
from datetime import date
from functools import partial
from uuid import uuid4

import streamlit as st

from components.turnstile import render_turnstile
from services.inquiries import InquiryAnswers, VenueInput
from services.public_inquiry import (
    PublicInquiryError, PublicInquiryReceipt, PublicValidationError, PublicVerificationError,
    PublicThrottleError, PublicAuthorizationError, PublicConflictError, VerifiedInquiry,
    local_inquiry_time, public_snapshot, submit_public_inquiry, verify_public_inquiry,
)
from services.public_inquiry_adapter import PublicInquiryConfig, create_public_client, load_public_config
from services.turnstile import verify_turnstile


NOTICE = "This requests a quote. It does not confirm a rental or reserve benches."
CONTACT_LABELS = {"email": "Email", "text": "Text message", "phone": "Phone call", "facebook": "Facebook"}
DELIVERY_LABELS = {"unsure": "Unsure", "parent_delivery": "Family delivery", "customer_pickup": "Customer pickup"}
SOURCE_LABELS = {
    "facebook_marketplace": "Facebook Marketplace", "facebook_referral": "Facebook referral",
    "word_of_mouth": "Word of mouth", "repeat_customer": "Repeat customer", "other": "Other",
}
TIMES = {"delivery_at": "Requested delivery", "pickup_at": "Requested pickup"}


@dataclass
class InquiryDraft:
    session_id: str = field(default_factory=lambda: str(uuid4()))
    request_id: str | None = None
    answers: InquiryAnswers | None = None
    verification: VerifiedInquiry | None = None
    uncertain: bool = False
    receipt: PublicInquiryReceipt | None = None
    reviewing: bool = False
    challenge: int = 0
    # Separate from widgets, whose values Streamlit removes when not rendered.
    fields: dict = field(default_factory=dict)


def _form(draft: InquiryDraft) -> None:
    def text(name, label, maximum=200, area=False):
        widget = st.text_area if area else st.text_input
        return widget(label, value=draft.fields.get(name, ""), max_chars=maximum, key="inquiry_" + name)

    with st.form("public_inquiry_answers"):
        st.subheader("Your contact details")
        values = {"customer_name": text("customer_name", "Your name")}
        values["preferred_contact_method"] = st.selectbox(
            "How should we contact you?", list(CONTACT_LABELS),
            index=list(CONTACT_LABELS).index(draft.fields["preferred_contact_method"]) if draft.fields.get("preferred_contact_method") else None,
            format_func=CONTACT_LABELS.get, key="inquiry_contact_method",
        )
        values.update(email=text("email", "Email (if using email)", 254),
                      phone=text("phone", "Phone (if using text or calls)", 50),
                      facebook_identity=text("facebook_identity", "Facebook name or profile (if using Facebook)", 500))
        st.subheader("Your event")
        values["event_date"] = st.date_input("Event date", value=draft.fields.get("event_date"),
                                             min_value=date(1, 1, 1), max_value=date(9999, 12, 31), key="inquiry_event_date")
        values["requested_bench_count"] = st.number_input(
            "Requested benches", min_value=1, max_value=2147483647,
            value=draft.fields.get("requested_bench_count"), step=1, key="inquiry_bench_count")
        values["event_type"] = text("event_type", "Event type (optional)")
        values["source"] = st.selectbox("How did you hear about us? (optional)", list(SOURCE_LABELS),
            index=list(SOURCE_LABELS).index(draft.fields["source"]) if draft.fields.get("source") else None,
            format_func=SOURCE_LABELS.get, key="inquiry_source")
        with st.expander("Venue and delivery preferences (optional)"):
            for name, label in (("name", "Venue name"), ("address_line_1", "Address"),
                                ("address_line_2", "Address line 2"), ("city", "City"),
                                ("state", "State"), ("postal_code", "Postal code")):
                values["venue_" + name] = text("venue_" + name, label)
            values["delivery_preference"] = st.selectbox("Delivery preference", list(DELIVERY_LABELS),
                index=list(DELIVERY_LABELS).index(draft.fields.get("delivery_preference", "unsure")),
                format_func=DELIVERY_LABELS.get, key="inquiry_delivery_preference")
        with st.expander("Requested timing (optional)"):
            st.caption("Delivery and pickup times are in the Chicago time zone. These are requests, not confirmed appointments. Leave unknown dates and times blank.")
            for name, label in TIMES.items():
                values[name + "_day"] = st.date_input(label + " date", value=draft.fields.get(name + "_day"),
                    min_value=date(1, 1, 1), max_value=date(9999, 12, 31), key="inquiry_" + name + "_day")
                values[name + "_time"] = st.time_input(label + " time", value=draft.fields.get(name + "_time"),
                    format="12h", key="inquiry_" + name + "_time")
        with st.expander("Instructions and other details (optional)"):
            for name, label in (("rental_notes", "Anything else about your rental?"),
                                ("delivery_instructions", "Delivery instructions"), ("pickup_instructions", "Pickup instructions")):
                values[name] = text(name, label, 4000, True)
        reviewed = st.form_submit_button("Review inquiry", type="primary")
    if reviewed:
        draft.fields = values
        try:
            timing = {}
            for name, label in TIMES.items():
                try:
                    timing[name] = local_inquiry_time(values[name + "_day"], values[name + "_time"], "First occurrence")
                except PublicValidationError as error:
                    raise PublicValidationError(f"{label}: {error}") from None
            answer_values = {name: values[name] for name in (
                "customer_name", "preferred_contact_method", "email", "phone", "facebook_identity",
                "event_date", "requested_bench_count", "event_type", "source", "delivery_preference",
                "rental_notes", "delivery_instructions", "pickup_instructions")}
            answer_values["venue"] = VenueInput(**{name: values["venue_" + name] for name in VenueInput.__dataclass_fields__})
            answers = InquiryAnswers(**answer_values, **timing)
            public_snapshot(answers)
        except PublicValidationError as error:
            st.error(str(error))
            return
        draft.answers, draft.request_id = answers, str(uuid4())
        draft.verification, draft.reviewing, draft.uncertain = None, True, False
        draft.challenge += 1
        st.rerun()


def _review(draft: InquiryDraft, config: PublicInquiryConfig) -> None:
    answers = draft.answers
    st.subheader("Review your inquiry")
    # Use plain text for customer-provided values; do not interpret their markup.
    for label, value in (("Name", answers.customer_name), ("Event date", answers.event_date),
                         ("Requested benches", answers.requested_bench_count),
                         ("Preferred contact", CONTACT_LABELS[answers.preferred_contact_method])):
        st.text(f"{label}: {value}")
    with st.expander("All submitted details", expanded=True):
        for name, value in public_snapshot(answers)["answers"].items():
            if name in {"customer_name", "event_date", "requested_bench_count", "preferred_contact_method"}:
                continue
            if name == "venue":
                if value:
                    for field_name, field_value in value.items():
                        if field_value:
                            st.text(f"Venue {field_name.replace('_', ' ')}: {field_value}")
            elif name in TIMES and value:
                local_time = getattr(answers, name)
                st.text(f"{TIMES[name]}: {local_time.strftime('%b %d, %Y at %I:%M %p')} (Chicago time)")
            elif value:
                label_value = DELIVERY_LABELS.get(value, value) if name == "delivery_preference" else SOURCE_LABELS.get(value, value) if name == "source" else value
                st.text(f"{name.replace('_', ' ').capitalize()}: {label_value}")
    if not draft.uncertain and st.button("Edit answers"):
        draft.reviewing, draft.verification = False, None
        st.rerun()
    if draft.uncertain:
        st.warning("The save is not confirmed yet. Retry these same answers; do not refresh or start another inquiry.")
        st.caption("Request reference: " + draft.request_id)
    token = ""
    if draft.verification is None:
        if st.button("Restart verification"):
            draft.challenge += 1
            st.rerun()
        token = render_turnstile(config.site_key, key=f"inquiry_challenge_{draft.challenge}")
    if st.button("Retry submission" if draft.uncertain else "Submit inquiry", type="primary"):
        try:
            if draft.verification is None:
                draft.verification = verify_public_inquiry(answers, request_id=draft.request_id, token=token,
                    verify=partial(verify_turnstile, secret=config.turnstile_secret, hostname=config.hostname))
            # A failure to initialize the client happens before any save.
            try:
                client = create_public_client(config)
            except Exception:
                st.error("Inquiry submission is temporarily unavailable. Your answers are still here.")
                return
            draft.receipt = submit_public_inquiry(answers, request_id=draft.request_id, session_id=draft.session_id,
                verification=draft.verification, client=client, gateway_secret=config.gateway_secret)
        except PublicVerificationError as error:
            draft.challenge += 1
            st.error(str(error))
        except (PublicValidationError, PublicThrottleError, PublicAuthorizationError, PublicConflictError) as error:
            # A later rejection cannot resolve an earlier uncertain transaction.
            st.error(str(error))
        except PublicInquiryError:
            draft.uncertain = True
            st.rerun()
        else:
            st.rerun()


def render_inquiry() -> None:
    st.title("Request a bench rental quote")
    st.info(NOTICE)
    config = load_public_config()
    if config is None:
        st.warning("The inquiry form is temporarily unavailable. Please contact us through your existing conversation.")
        return
    draft = st.session_state.setdefault("public_inquiry_draft", InquiryDraft())
    if draft.receipt:
        st.success("Your inquiry was received.")
        st.caption("Request reference: " + draft.receipt.request_id)
        if st.button("Start another inquiry"):
            # Retain session budget identity, even across separate inquiries.
            st.session_state["public_inquiry_draft"] = InquiryDraft(session_id=draft.session_id, challenge=draft.challenge + 1)
            for key in list(st.session_state):
                if key.startswith("inquiry_"):
                    del st.session_state[key]
            st.rerun()
    elif draft.reviewing:
        _review(draft, config)
    else:
        _form(draft)
