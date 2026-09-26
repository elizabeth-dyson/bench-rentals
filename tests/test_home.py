import unittest
from datetime import date, timedelta
from unittest.mock import patch

from services.bookings import BookingServiceError
from services.home import summarize_leads
from views.home import render_home


TODAY = date(2027, 6, 14)


def lead(number, event_date, stage="lead"):
    return {
        "booking_number": number,
        "event_date": event_date,
        "stage": stage,
        "requested_bench_count": 12,
        "primary_customer": {"preferred_name": "Example Customer"},
    }


class HomeSummaryTests(unittest.TestCase):
    def test_date_boundaries_and_closed_records(self):
        records = [
            lead("today", TODAY),
            lead("last", (TODAY + timedelta(days=29)).isoformat()),
            lead("outside", TODAY + timedelta(days=30)),
            lead("past", TODAY - timedelta(days=1)),
            lead("missing", None),
            lead("invalid", "not-a-date"),
            lead("closed", TODAY, "lost"),
        ]
        summary = summarize_leads(records, TODAY)
        self.assertEqual(summary.active_count, 6)
        self.assertEqual(summary.next_30_days_count, 2)
        self.assertEqual(summary.attention_count, 3)
        self.assertEqual(
            [record["booking_number"] for record in summary.upcoming],
            ["today", "last", "outside"],
        )
        self.assertEqual(
            [record["booking_number"] for record in summary.needs_attention],
            ["past", "missing", "invalid"],
        )

    def test_preview_limits_do_not_limit_totals(self):
        records = [lead(str(i), TODAY + timedelta(days=i)) for i in range(-8, 8)]
        summary = summarize_leads(list(reversed(records)), TODAY)
        self.assertEqual(summary.active_count, 16)
        self.assertEqual(summary.next_30_days_count, 8)
        self.assertEqual(summary.attention_count, 8)
        self.assertEqual(len(summary.upcoming), 5)
        self.assertEqual(len(summary.needs_attention), 5)
        self.assertEqual(summary.upcoming[0]["booking_number"], "0")
        self.assertEqual(summary.needs_attention[0]["booking_number"], "-1")

    def test_empty_summary(self):
        summary = summarize_leads([], TODAY)
        self.assertEqual(summary.active_count, 0)
        self.assertEqual(summary.next_30_days_count, 0)
        self.assertEqual(summary.attention_count, 0)
        self.assertEqual(summary.upcoming, [])
        self.assertEqual(summary.needs_attention, [])


class HomePageTests(unittest.TestCase):
    def setUp(self):
        self.st = patch("views.home.st").start()
        patch("components.presentation.st", self.st).start()
        patch("views.home.get_authenticated_user_display_name", return_value="Liz").start()
        patch("views.home.get_business_date", return_value=TODAY).start()
        self.load = patch("views.home.list_active_leads", return_value=[]).start()
        self.scroll = patch("views.home.request_scroll_to_top").start()
        self.st.button.return_value = False
        self.addCleanup(patch.stopall)

    def test_empty_home_shows_zero_counts_and_guidance(self):
        render_home()
        self.assertEqual([c.args[1] for c in self.st.metric.call_args_list], [0, 0, 0])
        self.st.info.assert_called_once()

    def test_failure_shows_retry_without_false_zero_counts(self):
        self.load.side_effect = BookingServiceError("private database detail")
        self.st.button.side_effect = [False, True]
        render_home()
        self.st.metric.assert_not_called()
        self.st.error.assert_called_once_with(
            "Your workspace couldn't be loaded. Please try again."
        )
        self.st.rerun.assert_called_once()

    def test_detail_action_switches_page_with_booking_number(self):
        self.load.return_value = [lead("BR-2027-001", TODAY)]
        self.st.button.side_effect = [False, True]
        render_home()
        self.st.switch_page.assert_called_once_with(
            self.st.Page.return_value, query_params={"booking": "BR-2027-001"}
        )
        self.scroll.assert_called_once()

    def test_view_bookings_clears_route_query(self):
        self.st.button.return_value = True
        render_home()
        self.st.switch_page.assert_called_once_with(
            self.st.Page.return_value, query_params=None
        )
        self.load.assert_not_called()

    def test_counts_and_attention_preview(self):
        self.load.return_value = [
            lead(f"BR-2027-{i:03d}", TODAY - timedelta(days=i))
            for i in range(1, 8)
        ]
        render_home()
        self.assertEqual([c.args[1] for c in self.st.metric.call_args_list], [7, 0, 7])
        detail_buttons = [
            c for c in self.st.button.call_args_list if c.args[0] == "View details"
        ]
        self.assertEqual(len(detail_buttons), 5)
        self.st.caption.assert_any_call("Showing 5 of 7. View Bookings for the full list.")


if __name__ == "__main__":
    unittest.main()
