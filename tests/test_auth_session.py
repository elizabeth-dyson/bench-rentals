import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.auth_session import (
    USER_SESSION_KEY,
    _AUTH_COOKIE_NAME,
    _decode_refresh_token,
    _encode_refresh_token,
    render_pending_auth_cookie,
    restore_authenticated_session,
)


class AuthSessionTests(unittest.TestCase):
    def setUp(self):
        self.streamlit = patch("services.auth_session.st").start()
        self.get_client = patch(
            "services.auth_session.get_supabase_client"
        ).start()
        self.clear_client = patch(
            "services.auth_session.clear_supabase_client"
        ).start()
        self.addCleanup(patch.stopall)
        self.streamlit.session_state = {}
        self.streamlit.context.cookies = {}

    def test_refresh_token_encoding_round_trip(self):
        token = "refresh-token.with_symbols-123"

        self.assertEqual(_decode_refresh_token(_encode_refresh_token(token)), token)
        self.assertIsNone(_decode_refresh_token("not valid base64!"))

    def test_restores_user_and_rotates_refresh_cookie(self):
        self.streamlit.context.cookies = {
            _AUTH_COOKIE_NAME: _encode_refresh_token("old-refresh-token")
        }
        client = MagicMock()
        user = object()
        session = SimpleNamespace(refresh_token="new-refresh-token")
        client.auth.refresh_session.return_value = SimpleNamespace(
            user=user,
            session=session,
        )
        self.get_client.return_value = client

        restored = restore_authenticated_session()

        self.assertTrue(restored)
        client.auth.refresh_session.assert_called_once_with("old-refresh-token")
        self.assertIs(self.streamlit.session_state[USER_SESSION_KEY], user)
        action = self.streamlit.session_state["_auth_cookie_action"]
        self.assertEqual(
            _decode_refresh_token(action["value"]),
            "new-refresh-token",
        )

    def test_existing_authenticated_session_is_migrated_to_cookie(self):
        user = object()
        self.streamlit.session_state[USER_SESSION_KEY] = user
        self.get_client.return_value.auth.get_session.return_value = SimpleNamespace(
            refresh_token="existing-refresh-token"
        )

        restored = restore_authenticated_session()

        self.assertTrue(restored)
        action = self.streamlit.session_state["_auth_cookie_action"]
        self.assertEqual(
            _decode_refresh_token(action["value"]),
            "existing-refresh-token",
        )
        self.assertTrue(self.streamlit.session_state["_auth_cookie_ready"])

    def test_invalid_cookie_is_removed_without_contacting_supabase(self):
        self.streamlit.context.cookies = {_AUTH_COOKIE_NAME: "invalid!"}

        restored = restore_authenticated_session()

        self.assertFalse(restored)
        self.get_client.assert_not_called()
        self.assertEqual(
            self.streamlit.session_state["_auth_cookie_action"],
            {"value": "", "max_age": 0},
        )

    def test_refresh_failure_clears_client_and_cookie(self):
        self.streamlit.context.cookies = {
            _AUTH_COOKIE_NAME: _encode_refresh_token("expired-refresh-token")
        }
        self.get_client.return_value.auth.refresh_session.side_effect = RuntimeError

        restored = restore_authenticated_session()

        self.assertFalse(restored)
        self.clear_client.assert_called_once_with()
        self.assertEqual(
            self.streamlit.session_state["_auth_cookie_action"],
            {"value": "", "max_age": 0},
        )

    def test_logout_guard_prevents_stale_cookie_restore(self):
        self.streamlit.session_state["_auth_restore_blocked"] = True
        self.streamlit.context.cookies = {
            _AUTH_COOKIE_NAME: _encode_refresh_token("still-in-browser")
        }

        self.assertFalse(restore_authenticated_session())
        self.get_client.assert_not_called()

    def test_renders_secure_cookie_sync_script(self):
        self.streamlit.session_state["_auth_cookie_action"] = {
            "value": "encoded-token",
            "max_age": 30,
        }

        render_pending_auth_cookie()

        html = self.streamlit.html.call_args.args[0]
        self.assertIn("bench_rentals_auth", html)
        self.assertIn("Max-Age=30", html)
        self.assertIn("SameSite=Lax", html)
        self.assertIn("; Secure", html)
        self.assertTrue(self.streamlit.html.call_args.kwargs["unsafe_allow_javascript"])
        self.assertNotIn("_auth_cookie_action", self.streamlit.session_state)


if __name__ == "__main__":
    unittest.main()
