import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

from views.bookings import (
    _format_bench_count,
    _render_lead_disposition_dialog_content,
    render_bookings,
)
from services.bookings import BookingFilters, BookingServiceError
from services.leads import (
    LeadDispositionInput,
    LeadDispositionResult,
    LeadServiceError,
)


class BookingsPageTests(unittest.TestCase):
    def setUp(self):
        self.streamlit = patch("views.bookings.st").start()
        patch("components.presentation.st", self.streamlit).start()
        self.inquiry_link = patch("views.bookings.render_configured_inquiry_link").start()
        self.streamlit.session_state = {}
        self.streamlit.query_params = {}
        self.list_active_leads = patch("views.bookings.list_active_leads").start()
        self.list_bookings = patch("views.bookings.list_bookings").start()
        self.filter_bookings = patch("views.bookings.filter_bookings").start()
        self.get_booking_detail = patch("views.bookings.get_booking_detail").start()
        self.find_customer_matches = patch(
            "views.bookings.find_customer_matches"
        ).start()
        self.client = MagicMock()
        patch("views.bookings.get_supabase_client", return_value=self.client).start()
        self.update_lead = patch("views.bookings.update_lead").start()
        self.set_lead_disposition = patch(
            "views.bookings.set_lead_disposition"
        ).start()
        self.disposition_dialog = patch(
            "views.bookings._render_lead_disposition_dialog"
        ).start()
        self.request_scroll = patch(
            "views.bookings.request_scroll_to_top"
        ).start()
        patch(
            "views.bookings.get_business_date",
            return_value=date(2027, 6, 14),
        ).start()
        self.addCleanup(patch.stopall)
        self.streamlit.spinner.return_value = MagicMock()
        self.streamlit.container.return_value = MagicMock()
        self.streamlit.button.return_value = False
        self.streamlit.form_submit_button.return_value = False

    def test_renders_empty_state(self):
        self.list_active_leads.return_value = []

        render_bookings()

        self.inquiry_link.assert_called_once_with(key="bookings_inquiry_link")
        self.streamlit.info.assert_called_once_with("No active leads.")
        self.assertFalse(any(
            item.kwargs.get("key", "").startswith("view_booking_")
            for item in self.streamlit.button.call_args_list
        ))

    def test_renders_active_lead_count_and_cards(self):
        self.list_active_leads.return_value = [
            self._lead("BR-2027-001", "2027-06-14", 1, "Liz"),
            self._lead("BR-2027-002", "2027-06-20", 12, "Pat"),
        ]

        render_bookings()

        self.streamlit.subheader.assert_any_call("Active leads (2 leads)")
        self.streamlit.caption.assert_any_call("BR-2027-001")
        self.streamlit.caption.assert_any_call("BR-2027-002")
        self.streamlit.write.assert_has_calls(
            [
                call("Jun 14, 2027"),
                call("1 bench"),
                call("Jun 20, 2027"),
                call("12 benches"),
            ]
        )
        self.streamlit.button.assert_has_calls(
            [
                call(
                    "View details",
                    key="view_booking_BR-2027-001",
                    icon=":material/arrow_forward:",
                    width="content",
                ),
                call(
                    "View details",
                    key="view_booking_BR-2027-002",
                    icon=":material/arrow_forward:",
                    width="content",
                ),
            ]
        )

    def test_view_details_sets_booking_query_parameter(self):
        self.list_active_leads.return_value = [
            self._lead("BR-2027-001", "2027-06-14", 1, "Liz")
        ]
        self.streamlit.button.side_effect = [False, True]

        render_bookings()

        self.assertEqual(self.streamlit.query_params["booking"], "BR-2027-001")
        self.request_scroll.assert_called_once_with()
        self.streamlit.rerun.assert_called_once_with()

    def test_renders_past_leads_warning_after_upcoming_cards(self):
        self.list_active_leads.return_value = [
            self._lead("future", "2027-06-20", 10, "Future"),
            self._lead("past", "2027-06-10", 8, "Past"),
        ]

        render_bookings()

        self.streamlit.subheader.assert_any_call("Active leads (2 leads)")
        self.streamlit.subheader.assert_any_call("Past leads needing attention")
        self.streamlit.warning.assert_called_once()
        displayed = [
            item.args[0] for item in self.streamlit.caption.call_args_list
            if item.args[0] in {"future", "past"}
        ]
        self.assertEqual(displayed, ["future", "past"])

    def test_renders_safe_error_and_retry(self):
        self.list_active_leads.side_effect = BookingServiceError("hidden detail")
        self.streamlit.button.return_value = False

        render_bookings()

        self.streamlit.error.assert_called_once_with(
            "Bookings couldn't be loaded. Please try again."
        )
        self.streamlit.button.assert_any_call(
            "Try again", width="stretch"
        )
        self.streamlit.exception.assert_not_called()

    def test_retry_reruns_page(self):
        self.list_active_leads.side_effect = BookingServiceError("hidden detail")
        self.streamlit.button.side_effect = [False, True]

        render_bookings()

        self.streamlit.rerun.assert_called_once_with()

    def test_blank_search_submission_activates_all_bookings_view(self):
        self.streamlit.text_input.return_value = ""
        self.streamlit.multiselect.return_value = []
        self.streamlit.date_input.return_value = ()
        self.streamlit.form_submit_button.return_value = True

        render_bookings()

        self.assertEqual(
            self.streamlit.session_state["booking_search_filters"],
            BookingFilters(),
        )
        self.streamlit.rerun.assert_called_once_with()
        self.list_active_leads.assert_not_called()
        self.list_bookings.assert_not_called()

    def test_search_submission_accepts_multiple_stages(self):
        self.streamlit.text_input.return_value = ""
        self.streamlit.multiselect.return_value = ["lost", "cancelled"]
        self.streamlit.date_input.return_value = ()
        self.streamlit.form_submit_button.return_value = True

        render_bookings()

        self.assertEqual(
            self.streamlit.session_state["booking_search_filters"],
            BookingFilters(stages=("lost", "cancelled")),
        )
        self.streamlit.rerun.assert_called_once_with()

    def test_search_submission_rejects_unknown_stage(self):
        self.streamlit.text_input.return_value = ""
        self.streamlit.multiselect.return_value = ["not-a-stage"]
        self.streamlit.date_input.return_value = ()
        self.streamlit.form_submit_button.return_value = True

        render_bookings()

        self.streamlit.error.assert_called_once_with("Choose valid booking stages.")
        self.assertNotIn("booking_search_filters", self.streamlit.session_state)
        self.streamlit.rerun.assert_not_called()

    def test_search_mode_renders_filtered_booking_results(self):
        filters = BookingFilters(search_text="liz", stages=("lost", "cancelled"))
        self.streamlit.session_state["booking_search_filters"] = filters
        all_bookings = [
            self._lead("BR-2027-001", "2027-06-14", 1, "Liz")
        ]
        result = {**all_bookings[0], "stage": "lost"}
        self.list_bookings.return_value = all_bookings
        self.filter_bookings.return_value = [result]

        render_bookings()

        self.list_active_leads.assert_not_called()
        self.list_bookings.assert_called_once_with()
        self.filter_bookings.assert_called_once_with(
            all_bookings,
            filters,
            date(2027, 6, 14),
        )
        self.streamlit.subheader.assert_any_call(
            "Search results (1 booking)"
        )
        self.streamlit.badge.assert_any_call("Lost", color="gray")

    def test_search_mode_distinguishes_empty_database_and_no_matches(self):
        self.streamlit.session_state["booking_search_filters"] = BookingFilters()
        self.list_bookings.return_value = []
        self.filter_bookings.return_value = []

        render_bookings()

        self.streamlit.info.assert_called_once_with("No bookings yet.")

        self.streamlit.reset_mock()
        self.streamlit.session_state["booking_search_filters"] = BookingFilters(
            search_text="missing"
        )
        self.streamlit.button.return_value = False
        self.streamlit.form_submit_button.return_value = False
        self.list_bookings.return_value = [
            self._lead("BR-2027-001", "2027-06-14", 1, "Liz")
        ]
        self.filter_bookings.return_value = []

        render_bookings()

        self.streamlit.info.assert_called_once_with(
            "No bookings match these filters."
        )

    def test_clear_filters_returns_to_active_leads_view(self):
        self.streamlit.session_state.update(
            {
                "booking_search_filters": BookingFilters(search_text="liz"),
                "booking_search_text": "liz",
                "booking_search_stages": ["lost", "cancelled"],
                "booking_search_dates": (),
            }
        )
        self.list_bookings.return_value = []
        self.filter_bookings.return_value = []

        render_bookings()

        clear_call = next(
            item
            for item in self.streamlit.button.call_args_list
            if item.args and item.args[0] == "Clear filters"
        )
        clear_call.kwargs["on_click"]()
        self.assertFalse(
            any(
                key.startswith("booking_search_")
                for key in self.streamlit.session_state
            )
        )

    def test_rejects_incomplete_search_date_range(self):
        self.streamlit.text_input.return_value = ""
        self.streamlit.multiselect.return_value = []
        self.streamlit.date_input.return_value = (date(2027, 6, 14),)
        self.streamlit.form_submit_button.return_value = True

        render_bookings()

        self.streamlit.error.assert_called_once_with(
            "Choose both a start and end date, or clear the date range."
        )
        self.assertNotIn("booking_search_filters", self.streamlit.session_state)
        self.list_active_leads.assert_called_once_with()

    def test_formats_invalid_bench_counts_safely(self):
        self.assertEqual(_format_bench_count(None), "Bench count unavailable")
        self.assertEqual(_format_bench_count(0), "Bench count unavailable")
        self.assertEqual(_format_bench_count(True), "Bench count unavailable")

    def test_renders_populated_booking_detail(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        self.get_booking_detail.return_value = {
            "booking_number": "BR-2027-001",
            "stage": "lead",
            "source": "facebook_marketplace",
            "event_type": "Wedding",
            "event_date": "2027-06-14",
            "requested_bench_count": 12,
            "facebook_conversation_url": "https://facebook.com/messages/1",
            "customer_notes": "Call after 5",
            "internal_notes": None,
            "primary_customer": {
                "id": "customer-1",
                "preferred_name": "Liz",
                "email": "liz@example.com",
                "phone": "402-555-0100",
                "preferred_contact_method": "text",
                "facebook_identities": [
                    {
                        "id": "identity-1",
                        "display_value": "Liz Example",
                        "profile_url": "https://facebook.com/liz",
                        "is_primary_for_type": True,
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ],
            },
        }

        render_bookings()

        self.get_booking_detail.assert_called_once_with("BR-2027-001")
        self.streamlit.title.assert_called_once_with("Liz")
        self.streamlit.link_button.assert_has_calls(
            [
                call(
                    "liz@example.com",
                    "mailto:liz@example.com",
                    icon=":material/mail:",
                    width="stretch",
                ),
                call(
                    "402-555-0100",
                    "tel:4025550100",
                    icon=":material/call:",
                    width="stretch",
                ),
            ]
        )
        self.streamlit.button.assert_any_call(
            "Edit lead",
            key="edit_lead",
            icon=":material/edit:",
            type="primary",
            width="content",
        )

    def test_edit_button_sets_edit_mode(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        self.get_booking_detail.return_value = self._booking_detail()
        self.streamlit.button.side_effect = [False, True]

        render_bookings()

        self.assertEqual(self.streamlit.query_params["mode"], "edit")
        self.streamlit.rerun.assert_called_once_with()

    def test_edit_mode_prepopulates_shared_customer_form(self):
        self.streamlit.query_params.update(
            {"booking": "BR-2027-001", "mode": "edit"}
        )
        self.get_booking_detail.return_value = self._booking_detail()

        render_bookings()

        self.assertEqual(self.streamlit.session_state["edit_customer_name"], "Liz")
        self.assertEqual(
            self.streamlit.session_state["edit_facebook_identity"], "Liz Example"
        )
        self.assertEqual(self.streamlit.session_state["edit_bench_count"], 12)
        self.streamlit.info.assert_called_with(
            "Customer name and contact changes update this shared customer everywhere "
            "they appear."
        )

    def test_non_lead_record_does_not_offer_editing(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        booking = self._booking_detail()
        booking["stage"] = "confirmed"
        self.get_booking_detail.return_value = booking

        render_bookings()

        edit_calls = [
            item for item in self.streamlit.button.call_args_list
            if item.args and item.args[0] == "Edit lead"
        ]
        self.assertEqual(edit_calls, [])

    def test_lead_status_actions_open_confirmation_dialog(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        self.get_booking_detail.return_value = self._booking_detail()
        self.streamlit.button.side_effect = [False, False, True, False]

        render_bookings()

        self.disposition_dialog.assert_called_once_with(
            "BR-2027-001",
            "Liz",
            "lead",
            "lost",
        )
        self.streamlit.button.assert_any_call(
            "Mark cancelled",
            key="mark_lead_cancelled",
            icon=":material/cancel:",
            width="stretch",
        )

    def test_closed_lead_shows_reason_and_restore_action(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        booking = self._booking_detail()
        booking.update(stage="cancelled", cancellation_reason="Event was cancelled")
        self.get_booking_detail.return_value = booking
        self.streamlit.button.side_effect = [False, True]

        render_bookings()

        self.streamlit.write.assert_any_call("Status: Cancelled")
        self.streamlit.write.assert_any_call("Reason: Event was cancelled")
        self.disposition_dialog.assert_called_once_with(
            "BR-2027-001",
            "Liz",
            "cancelled",
            "lead",
        )

    def test_closed_legacy_lead_uses_reason_fallback(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        booking = self._booking_detail()
        booking.update(stage="lost", lost_reason=None)
        self.get_booking_detail.return_value = booking

        render_bookings()

        self.streamlit.write.assert_any_call("Reason: Not provided")

    def test_disposition_success_message_uses_resulting_stage(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        booking = self._booking_detail()
        booking.update(stage="lost", lost_reason="No response")
        self.get_booking_detail.return_value = booking
        self.streamlit.session_state["lead_disposition_success"] = (
            LeadDispositionResult(
                booking_number="BR-2027-001",
                stage="lost",
            )
        )

        render_bookings()

        self.streamlit.success.assert_called_once_with(
            "Lead BR-2027-001 was marked lost."
        )

    def test_later_workflow_stage_has_no_disposition_controls(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        booking = self._booking_detail()
        booking["stage"] = "confirmed"
        self.get_booking_detail.return_value = booking

        render_bookings()

        labels = [
            item.args[0]
            for item in self.streamlit.button.call_args_list
            if item.args
        ]
        self.assertNotIn("Mark lost", labels)
        self.assertNotIn("Mark cancelled", labels)
        self.assertNotIn("Restore to lead", labels)

    def test_disposition_dialog_requires_closure_reason(self):
        self.streamlit.text_area.return_value = " "
        self.streamlit.form_submit_button.side_effect = [True, False]

        _render_lead_disposition_dialog_content(
            "BR-2027-001",
            "Liz",
            "lead",
            "lost",
        )

        self.streamlit.error.assert_called_once_with(
            "Enter a reason before closing the lead."
        )
        self.set_lead_disposition.assert_not_called()

    def test_disposition_dialog_saves_and_refreshes_detail(self):
        self.streamlit.text_area.return_value = "  Customer chose another company.  "
        self.streamlit.form_submit_button.side_effect = [True, False]
        result = LeadDispositionResult(
            booking_number="BR-2027-001",
            stage="lost",
        )
        self.set_lead_disposition.return_value = result

        _render_lead_disposition_dialog_content(
            "BR-2027-001",
            "Liz",
            "lead",
            "lost",
        )

        self.set_lead_disposition.assert_called_once_with(
            LeadDispositionInput(
                booking_number="BR-2027-001",
                target_stage="lost",
                reason="  Customer chose another company.  ",
            )
        )
        self.assertEqual(
            self.streamlit.session_state["lead_disposition_success"],
            result,
        )
        self.assertTrue(
            self.streamlit.session_state["lead_disposition_clear_draft"]
        )
        self.streamlit.rerun.assert_called_once_with()

    def test_disposition_error_preserves_reason_for_retry(self):
        reason_key = "lead_disposition_reason_BR-2027-001_cancelled"
        self.streamlit.session_state[reason_key] = "Customer cancelled the event"
        self.streamlit.text_area.return_value = "Customer cancelled the event"
        self.streamlit.form_submit_button.side_effect = [True, False]
        self.set_lead_disposition.side_effect = LeadServiceError("hidden")

        _render_lead_disposition_dialog_content(
            "BR-2027-001",
            "Liz",
            "lead",
            "cancelled",
        )

        self.assertEqual(
            self.streamlit.session_state[reason_key],
            "Customer cancelled the event",
        )
        self.assertNotIn(
            "lead_disposition_clear_draft",
            self.streamlit.session_state,
        )
        self.streamlit.error.assert_called_once_with(
            "The lead status couldn't be changed. Please try again."
        )

    def test_disposition_dialog_can_keep_current_status(self):
        self.streamlit.text_area.return_value = "Changed plans"
        self.streamlit.form_submit_button.side_effect = [False, True]

        _render_lead_disposition_dialog_content(
            "BR-2027-001",
            "Liz",
            "lead",
            "cancelled",
        )

        self.set_lead_disposition.assert_not_called()
        self.assertTrue(
            self.streamlit.session_state["lead_disposition_clear_draft"]
        )
        self.streamlit.rerun.assert_called_once_with()

    def test_restore_confirmation_sends_no_reason(self):
        self.streamlit.form_submit_button.side_effect = [True, False]
        self.set_lead_disposition.return_value = LeadDispositionResult(
            booking_number="BR-2027-001",
            stage="lead",
        )

        _render_lead_disposition_dialog_content(
            "BR-2027-001",
            "Liz",
            "lost",
            "lead",
        )

        self.set_lead_disposition.assert_called_once_with(
            LeadDispositionInput(
                booking_number="BR-2027-001",
                target_stage="lead",
                reason=None,
            )
        )
        self.streamlit.text_area.assert_not_called()

    def test_cancel_with_changes_requires_confirmation(self):
        self.streamlit.query_params.update(
            {"booking": "BR-2027-001", "mode": "edit"}
        )
        self.get_booking_detail.return_value = self._booking_detail()
        self._configure_edit_form(customer_name="Elizabeth")
        self.streamlit.form_submit_button.side_effect = [False, True]

        render_bookings()

        self.assertTrue(self.streamlit.session_state["edit_discard_pending"])
        self.assertEqual(
            self.streamlit.session_state["edit_pending_draft"].customer_name,
            "Elizabeth",
        )
        self.assertEqual(self.streamlit.query_params["mode"], "edit")

    def test_cancel_without_changes_returns_to_detail(self):
        self.streamlit.query_params.update(
            {"booking": "BR-2027-001", "mode": "edit"}
        )
        self.get_booking_detail.return_value = self._booking_detail()
        self._configure_edit_form()
        self.streamlit.form_submit_button.side_effect = [False, True]

        render_bookings()

        self.assertNotIn("mode", self.streamlit.query_params)
        self.assertFalse(
            any(key.startswith("edit_") for key in self.streamlit.session_state)
        )
        self.streamlit.rerun.assert_called_once_with()

    def test_successful_edit_returns_to_refreshed_detail(self):
        self.streamlit.query_params.update(
            {"booking": "BR-2027-001", "mode": "edit"}
        )
        self.get_booking_detail.return_value = self._booking_detail()
        self._configure_edit_form(customer_name="Elizabeth")
        self.streamlit.form_submit_button.side_effect = [True, False]
        self.find_customer_matches.return_value = []
        self.update_lead.return_value = SimpleNamespace(
            booking_number="BR-2027-001"
        )

        render_bookings()

        self.update_lead.assert_called_once()
        self.assertNotIn("mode", self.streamlit.query_params)
        self.assertEqual(
            self.streamlit.session_state["lead_update_success"], "BR-2027-001"
        )
        self.streamlit.rerun.assert_called_once_with()

    def test_renders_invalid_and_unknown_booking_states(self):
        self.streamlit.query_params["booking"] = "invalid"
        render_bookings()
        self.streamlit.info.assert_called_once_with("This booking link isn't valid.")
        self.get_booking_detail.assert_not_called()

        self.streamlit.reset_mock()
        self.streamlit.session_state = {}
        self.streamlit.query_params = {"booking": "BR-2027-999"}
        self.streamlit.button.return_value = False
        self.get_booking_detail.return_value = None
        render_bookings()
        self.streamlit.info.assert_called_once_with(
            "No booking exists with that booking number."
        )

    def test_detail_error_retries_without_clearing_route(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        self.get_booking_detail.side_effect = BookingServiceError("hidden")
        self.streamlit.button.side_effect = [False, True]

        render_bookings()

        self.assertEqual(self.streamlit.query_params["booking"], "BR-2027-001")
        self.streamlit.error.assert_called_once_with(
            "This booking couldn't be loaded. Please try again."
        )
        self.streamlit.rerun.assert_called_once_with()

    def test_back_to_bookings_clears_route(self):
        self.streamlit.query_params["booking"] = "BR-2027-001"
        filters = BookingFilters(search_text="liz")
        self.streamlit.session_state["booking_search_filters"] = filters
        self.streamlit.button.return_value = True

        render_bookings()

        self.assertNotIn("booking", self.streamlit.query_params)
        self.assertEqual(
            self.streamlit.session_state["booking_search_filters"],
            filters,
        )
        self.get_booking_detail.assert_not_called()
        self.streamlit.rerun.assert_called_once_with()

    @staticmethod
    def _lead(number, event_date, bench_count, customer_name):
        return {
            "id": "hidden-id",
            "booking_number": number,
            "stage": "lead",
            "event_date": event_date,
            "requested_bench_count": bench_count,
            "primary_customer": {"preferred_name": customer_name},
        }

    @staticmethod
    def _booking_detail():
        return {
            "booking_number": "BR-2027-001",
            "stage": "lead",
            "source": "facebook_marketplace",
            "event_type": "Wedding",
            "event_date": "2027-06-14",
            "requested_bench_count": 12,
            "facebook_conversation_url": "https://facebook.com/messages/1",
            "customer_notes": "Call after 5",
            "internal_notes": None,
            "primary_customer": {
                "id": "customer-1",
                "preferred_name": "Liz",
                "email": "liz@example.com",
                "phone": "402-555-0100",
                "preferred_contact_method": "text",
                "facebook_identities": [
                    {
                        "id": "identity-1",
                        "display_value": "Liz Example",
                        "profile_url": "https://facebook.com/liz",
                        "is_primary_for_type": True,
                        "created_at": "2026-01-01T00:00:00Z",
                    }
                ],
            },
        }

    def _configure_edit_form(self, customer_name="Liz"):
        self.streamlit.text_input.side_effect = [
            customer_name,
            "liz@example.com",
            "402-555-0100",
            "Liz Example",
            "Wedding",
            "https://facebook.com/messages/1",
        ]
        self.streamlit.date_input.return_value = date(2027, 6, 14)
        self.streamlit.number_input.return_value = 12
        self.streamlit.selectbox.side_effect = ["text", "facebook_marketplace"]
        self.streamlit.text_area.side_effect = ["Call after 5", ""]


if __name__ == "__main__":
    unittest.main()
