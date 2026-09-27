import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.bookings import (
    BookingFilters,
    BookingServiceError,
    filter_bookings,
    get_booking_detail,
    group_active_leads,
    list_active_leads,
    list_bookings,
)


class BookingServiceTests(unittest.TestCase):
    @patch("services.bookings.get_supabase_client")
    def test_lists_active_leads_with_expected_query(self, get_client):
        leads = [{"id": "one", "stage": "lead"}]
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.eq.return_value.order.return_value.execute.return_value = SimpleNamespace(
            data=leads
        )
        get_client.return_value = client

        self.assertEqual(list_active_leads(), leads)
        client.table.assert_called_once_with("bookings")
        selected_fields = client.table.return_value.select.call_args.args[0]
        self.assertIn("booking_number", selected_fields)
        self.assertIn("requested_bench_count", selected_fields)
        self.assertIn(
            "primary_customer:customers!bookings_primary_customer_id_fkey",
            selected_fields,
        )
        query.eq.assert_called_once_with("stage", "lead")
        query.eq.return_value.order.assert_called_once_with("event_date")

    @patch("services.bookings.get_supabase_client")
    def test_returns_empty_list(self, get_client):
        client = MagicMock()
        ordered_query = (
            client.table.return_value.select.return_value.eq.return_value.order.return_value
        )
        ordered_query.execute.return_value = SimpleNamespace(data=[])
        get_client.return_value = client

        self.assertEqual(list_active_leads(), [])

    @patch("services.bookings.get_supabase_client")
    def test_translates_supabase_errors(self, get_client):
        client = MagicMock()
        client.table.side_effect = RuntimeError("database unavailable")
        get_client.return_value = client

        with self.assertRaises(BookingServiceError) as context:
            list_active_leads()

        self.assertIsInstance(context.exception.__cause__, RuntimeError)

    @patch("services.bookings.get_supabase_client")
    def test_lists_all_bookings_with_search_projection(self, get_client):
        bookings = [{"booking_number": "BR-2027-001", "stage": "lead"}]
        client = MagicMock()
        query = client.table.return_value.select.return_value
        query.order.return_value.execute.return_value = SimpleNamespace(data=bookings)
        get_client.return_value = client

        self.assertEqual(list_bookings(), bookings)
        client.table.assert_called_once_with("bookings")
        selected_fields = client.table.return_value.select.call_args.args[0]
        self.assertIn("booking_number", selected_fields)
        self.assertIn("legal_name", selected_fields)
        self.assertIn("email", selected_fields)
        self.assertIn("phone", selected_fields)
        self.assertIn("identity_type", selected_fields)
        self.assertIn("display_value", selected_fields)
        query.order.assert_called_once_with("event_date")

    @patch("services.bookings.get_supabase_client")
    def test_all_bookings_translates_supabase_errors(self, get_client):
        get_client.return_value.table.side_effect = RuntimeError("database unavailable")

        with self.assertRaises(BookingServiceError) as context:
            list_bookings()

        self.assertIsInstance(context.exception.__cause__, RuntimeError)

    @patch("services.bookings.get_supabase_client")
    def test_gets_booking_detail_with_expected_projection(self, get_client):
        booking = {"booking_number": "BR-2027-001", "stage": "lead"}
        client = MagicMock()
        query = client.table.return_value.select.return_value
        filtered_identities = query.eq.return_value.eq.return_value
        filtered_identities.limit.return_value.execute.return_value = SimpleNamespace(
            data=[booking]
        )
        get_client.return_value = client

        self.assertEqual(get_booking_detail("BR-2027-001"), booking)
        client.table.assert_called_once_with("bookings")
        selected_fields = client.table.return_value.select.call_args.args[0]
        self.assertIn("facebook_conversation_url", selected_fields)
        self.assertIn("preferred_contact_method", selected_fields)
        self.assertIn("cancellation_reason", selected_fields)
        self.assertIn("lost_reason", selected_fields)
        self.assertIn(
            "primary_customer:customers!bookings_primary_customer_id_fkey(\n        id,",
            selected_fields,
        )
        self.assertIn(
            "facebook_identities:customer_identities!customer_identities_customer_id_fkey",
            selected_fields,
        )
        query.eq.assert_called_once_with("booking_number", "BR-2027-001")
        query.eq.return_value.eq.assert_called_once_with(
            "primary_customer.facebook_identities.identity_type", "facebook"
        )
        filtered_identities.limit.assert_called_once_with(1)

    @patch("services.bookings.get_supabase_client")
    def test_booking_detail_returns_none_when_not_found(self, get_client):
        limited = (
            get_client.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value
        )
        limited.execute.return_value = SimpleNamespace(data=[])
        self.assertIsNone(get_booking_detail("BR-2027-999"))

    @patch("services.bookings.get_supabase_client")
    def test_booking_detail_translates_malformed_response(self, get_client):
        limited = (
            get_client.return_value.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value
        )
        limited.execute.return_value = SimpleNamespace(data={"unexpected": True})

        with self.assertRaises(BookingServiceError) as context:
            get_booking_detail("BR-2027-001")

        self.assertIsInstance(context.exception.__cause__, ValueError)


class ActiveLeadGroupingTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2027, 6, 14)

    def test_groups_and_orders_upcoming_and_past_leads(self):
        leads = [
            {"booking_number": "future-later", "event_date": "2027-07-01"},
            {"booking_number": "past-older", "event_date": "2027-05-01"},
            {"booking_number": "today", "event_date": "2027-06-14"},
            {"booking_number": "past-recent", "event_date": "2027-06-13"},
            {"booking_number": "future-near", "event_date": "2027-06-20"},
        ]

        upcoming, past = group_active_leads(leads, self.today)

        self.assertEqual(
            [lead["booking_number"] for lead in upcoming],
            ["today", "future-near", "future-later"],
        )
        self.assertEqual(
            [lead["booking_number"] for lead in past],
            ["past-recent", "past-older"],
        )

    def test_places_missing_and_invalid_dates_after_dated_past_leads(self):
        leads = [
            {"booking_number": "missing", "event_date": None},
            {"booking_number": "past", "event_date": "2027-06-10"},
            {"booking_number": "invalid", "event_date": "not-a-date"},
        ]

        upcoming, past = group_active_leads(leads, self.today)

        self.assertEqual(upcoming, [])
        self.assertEqual(past[0]["booking_number"], "past")
        self.assertCountEqual(
            [lead["booking_number"] for lead in past[1:]],
            ["missing", "invalid"],
        )


class BookingFilterTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2027, 6, 14)
        self.booking = {
            "booking_number": "BR-2027-014",
            "stage": "lead",
            "event_date": "2027-06-20",
            "requested_bench_count": 12,
            "primary_customer": {
                "preferred_name": "Liz Smith",
                "legal_name": "Elizabeth Smith",
                "email": "Liz@Example.com",
                "phone": "(402) 555-0199",
                "facebook_identities": [
                    {
                        "identity_type": "facebook",
                        "display_value": "Liz Benches",
                    },
                    {
                        "identity_type": "venmo",
                        "display_value": "not-searchable",
                    },
                ],
            },
        }

    def test_searches_recognizable_booking_and_customer_values(self):
        for query in (
            "br-2027-014",
            "LIZ SMITH",
            "elizabeth",
            "liz@example.com",
            "4025550199",
            "liz benches",
        ):
            with self.subTest(query=query):
                self.assertEqual(
                    filter_bookings(
                        [self.booking],
                        BookingFilters(search_text=query),
                        self.today,
                    ),
                    [self.booking],
                )

    def test_does_not_search_non_facebook_identity_values(self):
        self.assertEqual(
            filter_bookings(
                [self.booking],
                BookingFilters(search_text="not-searchable"),
                self.today,
            ),
            [],
        )

    def test_combines_multiple_stages_and_inclusive_date_filters(self):
        other_stage = {**self.booking, "booking_number": "other", "stage": "lost"}
        excluded_stage = {
            **self.booking,
            "booking_number": "excluded",
            "stage": "cancelled",
        }
        before_range = {
            **self.booking,
            "booking_number": "before",
            "event_date": "2027-06-13",
        }
        end_boundary = {
            **self.booking,
            "booking_number": "boundary",
            "event_date": "2027-06-30",
        }
        malformed = {
            **self.booking,
            "booking_number": "malformed",
            "event_date": "unknown",
        }
        filters = BookingFilters(
            search_text="liz",
            stages=("lead", "lost"),
            start_date=date(2027, 6, 20),
            end_date=date(2027, 6, 30),
        )

        results = filter_bookings(
            [
                malformed,
                end_boundary,
                before_range,
                other_stage,
                excluded_stage,
                self.booking,
            ],
            filters,
            self.today,
        )

        self.assertEqual(
            [booking["booking_number"] for booking in results],
            ["other", "BR-2027-014", "boundary"],
        )

    def test_orders_upcoming_then_past_and_problem_records(self):
        bookings = [
            {**self.booking, "booking_number": "future", "event_date": "2027-06-20"},
            {**self.booking, "booking_number": "past", "event_date": "2027-06-13"},
            {**self.booking, "booking_number": "today", "event_date": "2027-06-14"},
            {**self.booking, "booking_number": "invalid", "event_date": None},
        ]

        results = filter_bookings(bookings, BookingFilters(), self.today)

        self.assertEqual(
            [booking["booking_number"] for booking in results],
            ["today", "future", "past", "invalid"],
        )


if __name__ == "__main__":
    unittest.main()
