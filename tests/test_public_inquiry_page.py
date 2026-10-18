import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from streamlit.runtime.context import ContextProxy
from streamlit.testing.v1 import AppTest
from streamlit.util import calc_hash

from services.public_inquiry_adapter import PublicInquiryConfig


CONFIG = PublicInquiryConfig("https://example.supabase.co", "sb_publishable_test", "x"*43,
                             "site", "secret", "example.com")


def public_test_app():
    from views.inquiry import render_inquiry
    render_inquiry()


def turnstile_test_app():
    # Each AppTest owns a new component registry; reload the module in that runtime.
    from importlib import reload
    import components.turnstile as turnstile
    reload(turnstile).render_turnstile("synthetic-site-key", key="test_challenge")


def click(app, label):
    next(button for button in app.button if button.label == label).click().run()


class PublicInquiryPageTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch("views.inquiry.load_public_config", return_value=CONFIG).start()
        patch("views.inquiry.render_turnstile", return_value="synthetic-token").start()
        self.verify = patch("views.inquiry.verify_turnstile").start()
        self.client = MagicMock()
        patch("views.inquiry.create_public_client", return_value=self.client).start()
        self.client.rpc.side_effect = self.rpc
        self.payloads = []
        self.fail = False

    def rpc(self, name, payload):
        self.payloads.append(payload)
        if self.fail:
            raise TimeoutError("synthetic uncertain save")
        return SimpleNamespace(execute=lambda: SimpleNamespace(data=[{
            "accepted": True, "request_id": payload["p_request_id"], "replayed": len(self.payloads) > 1}]))

    def form(self):
        app = AppTest.from_function(public_test_app).run()
        self.assertFalse(app.exception)
        app.text_input(key="inquiry_customer_name").set_value(" Customer ")
        app.text_input(key="inquiry_email").set_value("customer@example.invalid")
        app.selectbox(key="inquiry_contact_method").select("email")
        app.date_input(key="inquiry_event_date").set_value(date(2020, 6, 14))
        app.number_input(key="inquiry_bench_count").set_value(30)
        app.text_area(key="inquiry_rental_notes").set_value(" Keep these notes ")
        return app

    def test_review_edit_and_success(self):
        app = self.form()
        click(app, "Review inquiry")
        self.assertFalse(app.exception)
        click(app, "Edit answers")
        self.assertEqual(app.text_input(key="inquiry_customer_name").value, " Customer ")
        self.assertEqual(app.text_area(key="inquiry_rental_notes").value, " Keep these notes ")
        click(app, "Review inquiry")
        click(app, "Submit inquiry")
        self.assertFalse(app.exception)
        self.assertEqual(app.success[0].value, "Your inquiry was received.")
        app.run()
        self.assertEqual(len(self.payloads), 1)
        session = app.session_state["public_inquiry_draft"].session_id
        click(app, "Start another inquiry")
        self.assertEqual(app.session_state["public_inquiry_draft"].session_id, session)
        self.assertEqual(app.text_input(key="inquiry_customer_name").value, "")

    def test_validation_and_verification_errors_preserve_answers(self):
        app = self.form()
        app.text_input(key="inquiry_email").set_value("bad-email")
        click(app, "Review inquiry")
        self.assertTrue(app.error)
        self.assertEqual(app.text_area(key="inquiry_rental_notes").value, " Keep these notes ")
        app.text_input(key="inquiry_email").set_value("customer@example.invalid")
        click(app, "Review inquiry")
        from services.public_inquiry import PublicVerificationError
        self.verify.side_effect = PublicVerificationError("Try again")
        click(app, "Submit inquiry")
        self.assertTrue(app.error)
        self.assertEqual(len(self.payloads), 0)
        click(app, "Edit answers")
        self.assertEqual(app.text_area(key="inquiry_rental_notes").value, " Keep these notes ")

    def test_uncertain_save_retries_identically_and_freezes_edits(self):
        app = self.form()
        click(app, "Review inquiry")
        self.fail = True
        click(app, "Submit inquiry")
        app.run()
        self.assertNotIn("Edit answers", [button.label for button in app.button])
        self.fail = False
        click(app, "Retry submission")
        self.assertFalse(app.exception)
        self.assertEqual(self.payloads[0], self.payloads[1])
        self.verify.assert_called_once()
        self.assertTrue(app.success)

    def test_direct_public_route_never_restores_staff_or_loads_workspace(self):
        for signed_in in (False, True):
            with self.subTest(signed_in=signed_in), patch.object(ContextProxy, "url", new_callable=PropertyMock, return_value="https://example.com/inquiry"), \
                 patch("services.auth_session.restore_authenticated_session") as restore, \
                 patch("components.navigation.render_navigation") as navigation:
                app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
                # AppTest has no browser URL dispatch for callable pages.
                app._page_hash = calc_hash("inquiry")
                if signed_in:
                    app.session_state["authenticated_user"] = SimpleNamespace(email="private@example.invalid")
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual(app.title[0].value, "Request a bench rental quote")
                restore.assert_not_called()
                navigation.assert_not_called()

    def test_real_component_python_mount(self):
        app = AppTest.from_function(turnstile_test_app).run()
        self.assertFalse(app.exception)

    def test_disabled_form_has_no_submit_or_database_calls(self):
        with patch("views.inquiry.load_public_config", return_value=None):
            app = AppTest.from_function(public_test_app).run()
        self.assertTrue(app.warning)
        self.assertFalse(app.button)
        self.client.rpc.assert_not_called()

    def test_rejection_after_uncertain_response_does_not_unlock_edits(self):
        app = self.form()
        click(app, "Review inquiry")
        self.fail = True
        click(app, "Submit inquiry")
        error = RuntimeError("secret")
        error.code = "42501"
        self.client.rpc.side_effect = error
        click(app, "Retry submission")
        self.assertTrue(app.error)
        self.assertNotIn("secret", app.error[0].value)
        self.assertNotIn("Edit answers", [button.label for button in app.button])
        self.assertTrue(app.session_state["public_inquiry_draft"].uncertain)


if __name__ == "__main__":
    unittest.main()
