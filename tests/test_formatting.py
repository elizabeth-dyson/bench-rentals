import unittest
from datetime import date, datetime, timezone

from utils.formatting import (
    format_booking_date,
    format_booking_source,
    format_booking_stage,
    format_contact_method,
    format_customer_name,
    is_valid_booking_number,
)


class FormattingTests(unittest.TestCase):
    def test_formats_booking_stages(self):
        self.assertEqual(
            format_booking_stage("availability_confirmed"),
            "Availability Confirmed",
        )
        self.assertEqual(format_booking_stage("future_stage"), "Future Stage")
        self.assertEqual(format_booking_stage(None), "Unknown stage")

    def test_formats_booking_dates(self):
        expected = "Jun 14, 2027"
        self.assertEqual(format_booking_date(date(2027, 6, 14)), expected)
        self.assertEqual(
            format_booking_date(datetime(2027, 6, 14, 12, tzinfo=timezone.utc)),
            expected,
        )
        self.assertEqual(format_booking_date("2027-06-14"), expected)
        self.assertEqual(format_booking_date("not-a-date"), "Date not set")
        self.assertEqual(format_booking_date(None), "Date not set")

    def test_customer_name_uses_expected_precedence(self):
        customer = {
            "preferred_name": "  Liz  ",
            "legal_name": "Elizabeth Example",
            "email": "liz@example.com",
            "phone": "402-555-0100",
        }
        self.assertEqual(format_customer_name(customer), "Liz")

        customer["preferred_name"] = ""
        self.assertEqual(format_customer_name(customer), "Elizabeth Example")
        customer["legal_name"] = None
        self.assertEqual(format_customer_name(customer), "liz@example.com")
        customer["email"] = None
        self.assertEqual(format_customer_name(customer), "402-555-0100")

    def test_customer_name_has_safe_fallback(self):
        self.assertEqual(format_customer_name({}), "Unknown customer")
        self.assertEqual(format_customer_name(None), "Unknown customer")
        self.assertEqual(format_customer_name([]), "Unknown customer")

    def test_formats_booking_sources_and_contact_methods(self):
        self.assertEqual(
            format_booking_source("facebook_marketplace"), "Facebook Marketplace"
        )
        self.assertEqual(format_booking_source(None), "Not provided")
        self.assertEqual(format_contact_method("text"), "Text message")
        self.assertEqual(format_contact_method("phone"), "Phone call")
        self.assertEqual(format_contact_method("unexpected"), "Not provided")

    def test_validates_public_booking_number_shape(self):
        self.assertTrue(is_valid_booking_number("BR-2027-001"))
        self.assertTrue(is_valid_booking_number(" BR-2027-1000 "))
        self.assertFalse(is_valid_booking_number("booking-id"))
        self.assertFalse(is_valid_booking_number(None))


if __name__ == "__main__":
    unittest.main()
