"""Exercise native Streamlit rendering and navigation with synthetic data only."""

import unittest
from copy import deepcopy
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from streamlit.testing.v1 import AppTest

from services.leads import LeadDispositionResult, LeadServiceError


APP = Path(__file__).resolve().parents[1] / "app.py"
TODAY = date(2027, 6, 14)
USER = SimpleNamespace(email="operator@example.com", user_metadata={"display_name": "Operator"})
BOOKING = {
    "booking_number": "BR-2027-001",
    "stage": "lead",
    "event_date": TODAY.isoformat(),
    "requested_bench_count": 12,
    "source": "word_of_mouth",
    "event_type": "Wedding",
    "customer_notes": "Call after 5",
    "internal_notes": "Example inquiry",
    "primary_customer": {
        "id": "example-customer",
        "preferred_name": "Example Customer",
        "email": "customer@example.com",
        "phone": "402-555-0100",
        "preferred_contact_method": "email",
        "facebook_identities": [],
    },
}


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()


def bookings_test_app():
    """Render Bookings directly so AppTest reruns stay on the callable page."""
    from views.bookings import render_bookings

    render_bookings()


class AppWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.records = [deepcopy(BOOKING)]
        self.addCleanup(patch.stopall)
        for module in ("views.home", "views.bookings"):
            patch(f"{module}.get_business_date", return_value=TODAY).start()
            patch(
                f"{module}.list_active_leads",
                side_effect=lambda: [r for r in self.records if r["stage"] == "lead"],
            ).start()
        patch("views.bookings.list_bookings", side_effect=lambda: self.records).start()
        patch(
            "views.bookings.get_booking_detail",
            side_effect=lambda number: next(
                (deepcopy(r) for r in self.records if r["booking_number"] == number), None
            ),
        ).start()
        patch("views.bookings.find_customer_matches", return_value=[]).start()
        self.update = patch("views.bookings.update_lead", side_effect=self._update).start()
        self.create = patch("views.bookings.create_lead", side_effect=self._create).start()
        self.disposition = patch(
            "views.bookings.set_lead_disposition", side_effect=self._dispose
        ).start()
        self.client = MagicMock()
        patch("views.bookings.get_supabase_client", return_value=self.client).start()
        self.client.auth.sign_in_with_password.return_value = SimpleNamespace(
            user=USER, session=object()
        )
        patch("components.auth.get_supabase_client", return_value=self.client).start()
        patch("components.auth.clear_supabase_client").start()

    def _update(self, draft, *, client):
        self.assertIs(client, self.client)
        record = next(r for r in self.records if r["booking_number"] == draft.booking_number)
        record["primary_customer"]["preferred_name"] = draft.customer_name
        record["customer_notes"] = draft.customer_notes
        record["internal_notes"] = draft.internal_notes
        return SimpleNamespace(booking_number=draft.booking_number)

    def _create(self, draft, *, client):
        self.assertIs(client, self.client)
        record = deepcopy(BOOKING)
        record["booking_number"] = "BR-2027-002"
        record["primary_customer"]["preferred_name"] = draft.customer_name
        record["event_date"] = draft.event_date.isoformat()
        record["requested_bench_count"] = draft.requested_bench_count
        record["customer_notes"] = draft.customer_notes
        record["internal_notes"] = draft.internal_notes
        self.records.append(record)
        return SimpleNamespace(booking_number=record["booking_number"])

    def _dispose(self, disposition):
        record = next(r for r in self.records if r["booking_number"] == disposition.booking_number)
        record["stage"] = disposition.target_stage
        record["lost_reason"] = disposition.reason
        return LeadDispositionResult(
            booking_number=disposition.booking_number, stage=disposition.target_stage
        )

    def assert_clean(self, app):
        self.assertEqual([error.message for error in app.exception], [])

    def test_sign_in_home_navigation_and_logout(self):
        app = AppTest.from_file(str(APP)).run()
        self.assert_clean(app)
        self.assertEqual(len(app.text_input), 2)
        app.text_input[0].set_value("operator@example.com")
        app.text_input[1].set_value("example-password")
        click(app, "Sign in")
        self.assert_clean(app)
        self.assertEqual([metric.value for metric in app.metric], ["1", "1", "0"])
        click(app, "View details")
        self.assert_clean(app)
        self.assertEqual(app.query_params["booking"], ["BR-2027-001"])
        self.assertEqual(app.title[0].value, "Example Customer")
        click(app, "Log out")
        self.assert_clean(app)
        self.assertEqual(len(app.text_input), 2)
        self.assertEqual(app.query_params, {})

    def test_create_find_and_edit(self):
        app = AppTest.from_function(bookings_test_app).run()
        click(app, "Add lead")
        self.assert_clean(app)
        app.text_input(key="lead_customer_name").set_value("New Customer")
        app.date_input(key="lead_event_date").set_value(TODAY)
        app.text_input(key="lead_email").set_value("new@example.com")
        app.selectbox(key="lead_preferred_contact_method").select("email")
        click(app, "Review lead")
        self.assert_clean(app)
        click(app, "Create lead")
        self.assert_clean(app)
        self.create.assert_called_once()

        app.text_input(key="booking_search_text").set_value("New Customer")
        click(app, "Apply filters")
        self.assert_clean(app)
        self.assertEqual(len([b for b in app.button if b.label == "View details"]), 1)
        click(app, "View details")
        click(app, "Edit lead")
        self.assert_clean(app)
        app.text_input(key="edit_customer_name").set_value("Updated Customer")
        click(app, "Save changes")
        self.assert_clean(app)
        self.update.assert_called_once()
        self.assertEqual(app.title[0].value, "Updated Customer")

    def test_failed_create_preserves_distinct_notes_for_retry(self):
        app = AppTest.from_function(bookings_test_app).run()
        click(app, "Add lead")
        self.assertEqual(app.text_area(key="lead_customer_notes").label, "Rental notes (optional)")
        app.text_input(key="lead_customer_name").set_value("New Customer")
        app.date_input(key="lead_event_date").set_value(TODAY)
        app.text_input(key="lead_email").set_value("new@example.com")
        app.selectbox(key="lead_preferred_contact_method").select("email")
        app.text_area(key="lead_customer_notes").set_value("Use the south door")
        app.text_area(key="lead_internal_notes").set_value("Staff context only")
        click(app, "Review lead")
        self.create.side_effect = LeadServiceError("Synthetic failure")
        click(app, "Create lead")
        self.assert_clean(app)
        self.assertTrue(app.error)
        self.assertEqual(len(self.records), 1)
        failed_draft = self.create.call_args.args[0]
        self.assertEqual(failed_draft.customer_notes, "Use the south door")
        self.assertEqual(failed_draft.internal_notes, "Staff context only")
        self.create.side_effect = self._create
        click(app, "Create lead")
        self.assert_clean(app)
        self.assertEqual(self.create.call_args.args[0], failed_draft)
        self.assertEqual(len(self.records), 2)
        self.assertEqual(self.records[-1]["customer_notes"], "Use the south door")
        self.assertEqual(self.records[-1]["internal_notes"], "Staff context only")

    def test_failed_edit_preserves_notes_and_retry_updates_detail(self):
        app = AppTest.from_function(bookings_test_app).run()
        click(app, "View details")
        self.assertIn("**Rental notes**", [element.value for element in app.markdown])
        click(app, "Edit lead")
        self.assertEqual(app.text_area(key="edit_customer_notes").label, "Rental notes (optional)")
        app.text_area(key="edit_customer_notes").set_value("Rental request")
        app.text_area(key="edit_internal_notes").set_value("Private follow-up")
        self.update.side_effect = LeadServiceError("Synthetic failure")
        click(app, "Save changes")
        self.assert_clean(app)
        self.assertTrue(app.error)
        self.assertEqual(app.text_area(key="edit_customer_notes").value, "Rental request")
        self.assertEqual(app.text_area(key="edit_internal_notes").value, "Private follow-up")
        self.assertEqual(self.records[0]["customer_notes"], "Call after 5")
        self.update.side_effect = self._update
        click(app, "Save changes")
        self.assert_clean(app)
        self.assertEqual(self.records[0]["customer_notes"], "Rental request")
        self.assertEqual(self.records[0]["internal_notes"], "Private follow-up")
        displayed = [element.value for element in app.markdown]
        self.assertIn("Rental request", displayed)
        self.assertIn("Private follow-up", displayed)

    def test_connection_failure_preserves_edit_for_retry(self):
        app = AppTest.from_function(bookings_test_app).run()
        click(app, "View details")
        click(app, "Edit lead")
        app.text_area(key="edit_customer_notes").set_value("Keep this request")
        with patch("views.bookings.get_supabase_client", side_effect=RuntimeError("Synthetic connection failure")):
            click(app, "Save changes")
        self.assert_clean(app)
        self.assertTrue(app.error)
        self.assertEqual(app.text_area(key="edit_customer_notes").value, "Keep this request")
        self.update.assert_not_called()
        click(app, "Save changes")
        self.assert_clean(app)
        self.assertEqual(self.records[0]["customer_notes"], "Keep this request")


if __name__ == "__main__":
    unittest.main()
