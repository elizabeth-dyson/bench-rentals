"""Business rules import and execute without Streamlit or Supabase."""

import json
import subprocess
import sys
import unittest
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone

from services.inquiries import (
    BUSINESS_TIME_ZONE, InquiryAnswers, VenueInput, delivery_method_for_preference,
    normalize_inquiry, snapshot_inquiry_answers, validate_inquiry_input,
)


def inquiry(**changes):
    return replace(InquiryAnswers(
        customer_name=" Jamie ", event_date=date(2027, 6, 14),
        requested_bench_count=12, preferred_contact_method="email",
        email=" JAMIE@example.com ",
    ), **changes)


class InquiryTests(unittest.TestCase):
    def test_module_import_has_no_ui_or_client_dependency(self):
        result = subprocess.run(
            [sys.executable, "-c", "import sys; import services.inquiries; "
             "assert 'streamlit' not in sys.modules; "
             "assert 'supabase' not in sys.modules; "
             "assert 'services.supabase' not in sys.modules"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_minimum_and_each_contact_method(self):
        for method, contact in (
            ("email", {"email": "a@example.com"}),
            ("phone", {"phone": "402-555-0100"}),
            ("text", {"phone": "402-555-0100"}),
            ("facebook", {"facebook_identity": "Jamie Smith"}),
        ):
            with self.subTest(method=method):
                answers = replace(inquiry(email=None), preferred_contact_method=method, **contact)
                self.assertEqual(validate_inquiry_input(answers), [])

    def test_invalid_minimum_and_optional_inputs(self):
        for changes in (
            {"customer_name": " "}, {"email": None}, {"email": "invalid"},
            {"phone": "123"}, {"phone": "letters only"}, {"preferred_contact_method": "text"},
            {"preferred_contact_method": "invalid"}, {"source": "invalid"},
            {"requested_bench_count": 0}, {"requested_bench_count": -1},
            {"requested_bench_count": True}, {"requested_bench_count": 1.5},
            {"event_date": datetime(2027, 6, 14)}, {"event_date": None},
            {"delivery_preference": "third_party"}, {"venue": "Venue"},
            {"venue": VenueInput(postal_code=12345)}, {"timing_notes": 12},
        ):
            with self.subTest(changes=changes):
                self.assertTrue(validate_inquiry_input(inquiry(**changes)))

    def test_no_capacity_or_future_date_requirement(self):
        self.assertEqual(validate_inquiry_input(inquiry(
            event_date=date(2000, 1, 1), requested_bench_count=1000,
        )), [])

    def test_partial_venue_and_unknown_values(self):
        answers = inquiry(venue=VenueInput(name="  Community hall ", city="Lincoln"))
        working = normalize_inquiry(answers)
        self.assertEqual(working.venue, VenueInput(name="Community hall", city="Lincoln"))
        self.assertEqual(working.source, "other")
        self.assertIsNone(working.venue.state)
        self.assertIsNone(normalize_inquiry(inquiry(venue=VenueInput(name=" "))).venue)
        self.assertIsNone(delivery_method_for_preference("unsure"))
        for preference in ("parent_delivery", "customer_pickup"):
            self.assertEqual(delivery_method_for_preference(preference), preference)
        with self.assertRaises(ValueError):
            delivery_method_for_preference("third_party")

    def test_optional_timing_and_chicago_normalization(self):
        stamp = datetime(2027, 6, 14, 18, tzinfo=timezone.utc)
        answers = inquiry(event_start_at=stamp, timing_notes=" Around noon ")
        self.assertEqual(validate_inquiry_input(answers), [])
        normalized = normalize_inquiry(answers)
        self.assertEqual(normalized.event_start_at.hour, 13)
        self.assertEqual(normalized.event_start_at.tzinfo, BUSINESS_TIME_ZONE)
        self.assertEqual(normalized.timing_notes, "Around noon")
        self.assertEqual(snapshot_inquiry_answers(answers)["answers"]["event_start_at"], stamp.isoformat())

    def test_invalid_timestamps_and_order(self):
        for value in ("noon", date(2027, 6, 14), datetime(2027, 6, 14, 12),
                      datetime(2027, 3, 14, 2, 30, tzinfo=BUSINESS_TIME_ZONE)):
            with self.subTest(value=value):
                self.assertTrue(validate_inquiry_input(inquiry(event_start_at=value)))
        delivery = datetime(2027, 6, 14, 18, tzinfo=timezone.utc)
        earlier = datetime(2027, 6, 14, 12, tzinfo=BUSINESS_TIME_ZONE)
        self.assertTrue(validate_inquiry_input(inquiry(delivery_at=delivery, pickup_at=earlier)))
        self.assertEqual(validate_inquiry_input(inquiry(delivery_at=delivery, pickup_at=delivery)), [])
        # Compare real instants across the repeated fall DST hour, not wall times.
        late = datetime(2027, 11, 7, 1, 15, tzinfo=BUSINESS_TIME_ZONE, fold=1)
        early = datetime(2027, 11, 7, 1, 45, tzinfo=BUSINESS_TIME_ZONE, fold=0)
        self.assertTrue(validate_inquiry_input(inquiry(delivery_at=late, pickup_at=early)))

    def test_snapshot_keeps_original_text_separate_from_working_values(self):
        answers = inquiry(
            phone=" (402) 555-0100 ", facebook_identity=" Jamie   Smith ",
            venue=VenueInput(name=" Town Hall "), rental_notes="  First line\n Second line  ",
            delivery_instructions=" South door ", pickup_instructions=" Call first ",
        )
        snapshot = snapshot_inquiry_answers(answers)
        working = normalize_inquiry(answers)
        self.assertEqual(working.customer_name, "Jamie")
        self.assertEqual(working.email, "jamie@example.com")
        self.assertEqual(working.phone, "4025550100")
        self.assertEqual(working.facebook_identity, "jamie smith")
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["answers"]["event_date"], "2027-06-14")
        self.assertEqual(snapshot["answers"]["customer_name"], " Jamie ")
        self.assertEqual(snapshot["answers"]["rental_notes"], "  First line\n Second line  ")
        self.assertIsNone(snapshot["answers"]["source"])
        self.assertEqual(snapshot["answers"]["venue"]["name"], " Town Hall ")
        self.assertEqual(json.loads(json.dumps(snapshot)), snapshot)
        snapshot["answers"]["venue"]["name"] = "Changed"
        self.assertEqual(answers.venue.name, " Town Hall ")

    def test_snapshot_excludes_extra_staff_fields(self):
        @dataclass(frozen=True)
        class StaffAnswers(InquiryAnswers):
            internal_notes: str = "private"
            existing_customer_id: str = "private-id"

        answers = StaffAnswers("Jamie", date(2027, 6, 14), 12, "email", email="a@b.com")
        snapshot = snapshot_inquiry_answers(answers)
        self.assertNotIn("internal_notes", snapshot["answers"])
        self.assertNotIn("existing_customer_id", snapshot["answers"])

    def test_invalid_answers_cannot_be_normalized_or_snapshotted(self):
        for operation in (normalize_inquiry, snapshot_inquiry_answers):
            with self.assertRaises(ValueError):
                operation(inquiry(requested_bench_count=0))


if __name__ == "__main__":
    unittest.main()
