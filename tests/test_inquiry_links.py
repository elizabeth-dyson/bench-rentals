import subprocess
import sys
import unittest
from copy import deepcopy
from datetime import date
from unittest.mock import MagicMock, patch

from streamlit.errors import StreamlitSecretNotFoundError
from streamlit.testing.v1 import AppTest

from components.inquiry_link import render_configured_inquiry_link
from services.bookings import BookingServiceError
from services.inquiry_links import validate_public_inquiry_url


PUBLIC_URL = "https://rentals.example.com/inquiry"


def link_test_app():
    from components.inquiry_link import render_configured_inquiry_link

    render_configured_inquiry_link(key="test_inquiry_link")


def home_test_app():
    from views.home import render_home

    render_home()


def bookings_test_app():
    from views.bookings import render_bookings

    render_bookings()


class InquiryUrlTests(unittest.TestCase):
    def test_missing_and_blank_configuration(self):
        for value in (None, "", " \t\n "):
            with self.subTest(value=value):
                self.assertIsNone(validate_public_inquiry_url(value))

    def test_valid_urls_are_preserved_except_surrounding_whitespace(self):
        for value in (
            PUBLIC_URL, "https://rentals.example.com/", "https://rentals.example.com",
            "https://rentals.example.com:8443/forms/inquiry",
            "https://rentals.example.com/event%20inquiry", "https://[::1]/inquiry",
        ):
            with self.subTest(value=value):
                self.assertEqual(validate_public_inquiry_url(" \n" + value + "\t "), value)

    def test_invalid_urls_and_configuration_types(self):
        for value in (
            True, 42, {}, "/inquiry", "rentals.example.com/inquiry", "https://",
            "http://rentals.example.com/inquiry", "javascript:alert(1)",
            "https:///inquiry", "https://user@rentals.example.com/inquiry",
            "https://user:secret@rentals.example.com/inquiry",
            "https://@rentals.example.com/inquiry", PUBLIC_URL + "?booking=123",
            PUBLIC_URL + "?", PUBLIC_URL + "#section", PUBLIC_URL + "#",
            "https://rentals.example.com/in quiry", "https://ren\ttals.example.com/inquiry",
            "https://rentals.example.com/in\nquiry", PUBLIC_URL + "\x00",
            "https://rentals.example.com\\@other.example.com/inquiry",
            "https://rentals.example.com:bad/inquiry", "https://rentals.example.com:99999/inquiry",
            "https://rentals.example.com:/inquiry", "https://[broken/inquiry",
            "https://bad..example.com/inquiry", "https://-bad.example.com/inquiry",
            "https://rentals.example.com/%oops",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    validate_public_inquiry_url(value)

    def test_helper_imports_without_streamlit_or_database_client(self):
        result = subprocess.run(
            [sys.executable, "-c", "import sys; import services.inquiry_links; "
             "assert 'streamlit' not in sys.modules; assert 'supabase' not in sys.modules"],
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


class InquiryLinkComponentTests(unittest.TestCase):
    def setUp(self):
        self.st = patch("components.inquiry_link.st").start()
        self.st.secrets = {}
        self.st.session_state = {"draft": "unsaved", "filter": "upcoming"}
        self.st.query_params = {"booking": "BR-2027-001"}
        self.addCleanup(patch.stopall)

    def test_missing_setting_disables_control_without_a_link(self):
        render_configured_inquiry_link(key="test")
        self.assertTrue(self.st.popover.call_args.kwargs["disabled"])
        self.st.caption.assert_called_once_with("Inquiry form sharing isn’t available yet.")
        self.st.code.assert_not_called()

    def test_invalid_setting_is_not_shown_or_logged_as_success(self):
        self.st.secrets = {"PUBLIC_INQUIRY_URL": "https://staff:secret@example.com/?booking=1"}
        render_configured_inquiry_link(key="test")
        self.assertTrue(self.st.popover.call_args.kwargs["disabled"])
        self.st.caption.assert_called_once_with("The inquiry link is unavailable.")
        self.st.code.assert_not_called()
        self.st.success.assert_not_called()

    def test_missing_secrets_file_is_unconfigured(self):
        self.st.secrets = MagicMock()
        self.st.secrets.get.side_effect = StreamlitSecretNotFoundError("No secrets")
        render_configured_inquiry_link(key="test")
        self.st.caption.assert_called_once_with("Inquiry form sharing isn’t available yet.")

    def test_malformed_secrets_are_unavailable_without_exposing_error(self):
        self.st.secrets = MagicMock()
        error = StreamlitSecretNotFoundError("Private parsing detail")
        error.__cause__ = ValueError("Malformed TOML")
        self.st.secrets.get.side_effect = error
        render_configured_inquiry_link(key="test")
        self.st.caption.assert_called_once_with("The inquiry link is unavailable.")
        self.st.code.assert_not_called()

    def test_link_does_not_change_state_or_imply_sending(self):
        original_state = deepcopy(self.st.session_state)
        original_route = deepcopy(self.st.query_params)
        self.st.secrets = {"PUBLIC_INQUIRY_URL": " " + PUBLIC_URL + " "}
        render_configured_inquiry_link(key="test")
        self.assertFalse(self.st.popover.call_args.kwargs["disabled"])
        self.assertEqual(self.st.popover.call_args.kwargs["on_change"], "ignore")
        self.st.code.assert_called_once_with(PUBLIC_URL, language=None, wrap_lines=True)
        self.assertEqual(self.st.session_state, original_state)
        self.assertEqual(self.st.query_params, original_route)
        self.st.rerun.assert_not_called()
        self.st.switch_page.assert_not_called()
        self.st.success.assert_not_called()


class InquiryLinkAppTests(unittest.TestCase):
    def test_native_panel_and_configuration_states(self):
        for setting, disabled, message in (
            (None, True, "Inquiry form sharing isn’t available yet."),
            (" ", True, "Inquiry form sharing isn’t available yet."),
            ("http://bad.example.com", True, "The inquiry link is unavailable."),
            (PUBLIC_URL, False, "Use the copy icon, then paste the link into your conversation."),
        ):
            with self.subTest(setting=setting):
                app = AppTest.from_function(link_test_app)
                if setting is not None:
                    app.secrets["PUBLIC_INQUIRY_URL"] = setting
                app.run()
                self.assertEqual(list(app.exception), [])
                self.assertEqual(app.get("popover")[0].proto.popover.disabled, disabled)
                self.assertIn(message, [element.value for element in app.caption])
                self.assertEqual([element.value for element in app.code], [] if disabled else [PUBLIC_URL])

    def test_link_renders_before_empty_or_failed_page_loads_without_writes(self):
        for page, module in ((home_test_app, "views.home"), (bookings_test_app, "views.bookings")):
            for failed in (False, True):
                with self.subTest(page=module, failed=failed), patch(
                    f"{module}.list_active_leads", return_value=[],
                    side_effect=BookingServiceError("Synthetic failure") if failed else None,
                ) as load, patch("views.home.get_authenticated_user_display_name", return_value="Operator"), patch(
                    f"{module}.get_business_date", return_value=date(2027, 6, 14)
                ), patch("services.supabase.get_supabase_client") as client, patch(
                    "views.bookings.get_supabase_client"
                ) as write_client:
                    app = AppTest.from_function(page)
                    app.secrets["PUBLIC_INQUIRY_URL"] = PUBLIC_URL
                    app.session_state["unrelated_draft"] = {"notes": "Keep this"}
                    app.run()
                    self.assertEqual(list(app.exception), [])
                    self.assertEqual([element.value for element in app.code], [PUBLIC_URL])
                    self.assertEqual(len(app.get("popover")), 1)
                    self.assertEqual(app.session_state["unrelated_draft"], {"notes": "Keep this"})
                    self.assertEqual(len(app.error), 1 if failed else 0)
                    load.assert_called_once()
                    client.assert_not_called()
                    write_client.assert_not_called()


if __name__ == "__main__":
    unittest.main()
