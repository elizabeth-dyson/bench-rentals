import unittest
from unittest.mock import MagicMock, patch

from components.auth import logout


class LogoutTests(unittest.TestCase):
    def test_logout_clears_auth_flow_state_and_query_parameters(self):
        streamlit = patch("components.auth.st").start()
        clear_client = patch("components.auth.clear_supabase_client").start()
        get_client = patch("components.auth.get_supabase_client").start()
        request_scroll = patch("components.auth.request_scroll_to_top").start()
        self.addCleanup(patch.stopall)
        client = MagicMock()
        get_client.return_value = client
        streamlit.session_state = {
            "authenticated_user": object(),
            "lead_flow_step": "review",
            "booking_search_filters": object(),
            "booking_search_text": "liz",
            "unrelated": "keep",
        }
        streamlit.query_params = {"booking": "BR-2027-001"}

        logout()

        client.auth.sign_out.assert_called_once_with()
        self.assertNotIn("authenticated_user", streamlit.session_state)
        self.assertNotIn("lead_flow_step", streamlit.session_state)
        self.assertNotIn("booking_search_filters", streamlit.session_state)
        self.assertNotIn("booking_search_text", streamlit.session_state)
        self.assertEqual(streamlit.session_state["unrelated"], "keep")
        self.assertEqual(streamlit.query_params, {})
        clear_client.assert_called_once_with()
        request_scroll.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
