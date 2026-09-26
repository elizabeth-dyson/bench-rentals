import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from utils.scrolling import render_scroll_to_top, request_scroll_to_top


class ScrollingTests(unittest.TestCase):
    def setUp(self):
        self.streamlit = patch("utils.scrolling.st").start()
        self.addCleanup(patch.stopall)
        self.streamlit.session_state = {}
        self.streamlit.context = SimpleNamespace(url="http://localhost:8502/")
        self.streamlit.query_params = MagicMock()
        self.streamlit.query_params.keys.return_value = []

    def test_first_render_records_route_without_forcing_scroll(self):
        render_scroll_to_top()

        self.streamlit.html.assert_not_called()
        self.assertIn("_app_scroll_route_signature", self.streamlit.session_state)

    def test_explicit_request_scrolls_after_render(self):
        render_scroll_to_top()
        request_scroll_to_top()

        render_scroll_to_top()

        _, kwargs = self.streamlit.html.call_args
        self.assertEqual(kwargs["width"], "content")
        self.assertTrue(kwargs["unsafe_allow_javascript"])
        html = self.streamlit.html.call_args.args[0]
        self.assertIn('[data-testid="stMain"]', html)
        self.assertIn("window.scrollTo", html)

    def test_path_change_scrolls_without_explicit_request(self):
        render_scroll_to_top()
        self.streamlit.context.url = "http://localhost:8502/bookings"

        render_scroll_to_top()

        self.streamlit.html.assert_called_once()

    def test_query_parameter_change_scrolls_without_explicit_request(self):
        render_scroll_to_top()
        self.streamlit.query_params.keys.return_value = ["booking"]
        self.streamlit.query_params.get_all.return_value = ["BR-2026-001"]

        render_scroll_to_top()

        self.streamlit.html.assert_called_once()

    def test_ordinary_rerun_keeps_scroll_position(self):
        render_scroll_to_top()

        render_scroll_to_top()

        self.streamlit.html.assert_not_called()


if __name__ == "__main__":
    unittest.main()
