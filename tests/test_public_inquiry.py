import json
import unittest
from dataclasses import replace
from datetime import date, time
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from services.inquiries import InquiryAnswers, VenueInput
from services.public_inquiry import (
    PublicAuthorizationError, PublicConflictError, PublicInquiryError, PublicThrottleError,
    PublicValidationError, PublicVerificationError, local_inquiry_time, public_snapshot,
    submit_public_inquiry, verify_public_inquiry,
)
from services.public_inquiry_adapter import load_public_config
from services.turnstile import verify_turnstile


def answers():
    return InquiryAnswers("  Public Customer  ", date(2020, 6, 14), 30, "email",
                          email=" PUBLIC@example.invalid ", venue=VenueInput(city=" Omaha "))


class PublicInquiryTests(unittest.TestCase):
    def setUp(self):
        self.answers = answers()
        self.request = str(uuid4())
        self.session = str(uuid4())
        self.verify = MagicMock()
        self.proof = verify_public_inquiry(self.answers, request_id=self.request, token="token", verify=self.verify)
        self.client = MagicMock()
        self.client.rpc.return_value.execute.return_value.data = [{
            "accepted": True, "request_id": self.request, "replayed": False}]

    def save(self, answers=None, **overrides):
        kwargs = dict(request_id=self.request, session_id=self.session, verification=self.proof,
                      client=self.client, gateway_secret="test-only-gateway-secret")
        return submit_public_inquiry(answers or self.answers, **(kwargs | overrides))

    def test_public_contract_preserves_answers_and_accepts_past_large_requests(self):
        receipt = self.save()
        self.assertEqual(receipt.request_id, self.request)
        rpc, payload = self.client.rpc.call_args.args
        self.assertEqual(rpc, "create_public_inquiry")
        self.assertEqual(set(payload), {"p_request_id", "p_snapshot", "p_session_id", "p_gateway_secret"})
        snapshot = payload["p_snapshot"]["answers"]
        self.assertEqual(snapshot["customer_name"], "  Public Customer  ")
        self.assertEqual(snapshot["email"], " PUBLIC@example.invalid ")
        self.assertEqual(snapshot["venue"]["city"], " Omaha ")
        self.assertIsNone(snapshot["venue"]["state"])

    def test_limits_and_required_contact(self):
        for change in ({"customer_name": "x" * 201}, {"email": "x" * 250 + "@a.com"},
                       {"rental_notes": "x" * 4001}, {"venue": VenueInput(name="x" * 201)},
                       {"requested_bench_count": 2147483648}, {"preferred_contact_method": "text"},
                       {"requested_bench_count": None}, {"event_date": None}):
            with self.subTest(change=change.keys()), self.assertRaises(PublicValidationError):
                public_snapshot(replace(self.answers, **change))
        public_snapshot(replace(self.answers, customer_name="x" * 200, rental_notes="x" * 4000))
        with self.assertRaises(PublicValidationError):
            public_snapshot(replace(self.answers, timing_notes="😀"*4000, rental_notes="😀"*4000,
                delivery_instructions="😀"*4000, pickup_instructions="😀"*4000, facebook_identity="😀"*500))

    def test_proof_binds_request_and_original_text(self):
        for change in ({"customer_name": "Public Customer"}, {"rental_notes": "Changed"}):
            with self.assertRaises(PublicVerificationError):
                self.save(replace(self.answers, **change))
        with self.assertRaises(PublicVerificationError):
            self.save(request_id=str(uuid4()))
        self.client.rpc.assert_not_called()

    def test_unknown_retry_has_identical_payload_and_reuses_verification(self):
        self.client.rpc.return_value.execute.side_effect = [TimeoutError("private data"),
            SimpleNamespace(data=[{"accepted": True, "request_id": self.request, "replayed": True}])]
        with self.assertRaises(PublicInquiryError) as caught:
            self.save()
        self.assertNotIn("private data", str(caught.exception))
        self.assertTrue(self.save().replayed)
        self.assertEqual(self.client.rpc.call_args_list[0], self.client.rpc.call_args_list[1])
        self.verify.assert_called_once()

    def test_database_errors_are_safe_and_distinct(self):
        for code, expected in (("42501", PublicAuthorizationError), ("P5401", PublicThrottleError),
                               ("P5104", PublicConflictError), ("P5101", PublicValidationError),
                               ("XX000", PublicInquiryError)):
            error = RuntimeError("private database message")
            error.code = code
            self.client.rpc.return_value.execute.side_effect = error
            with self.subTest(code=code), self.assertRaises(expected) as caught:
                self.save()
            self.assertNotIn("private database message", str(caught.exception))

    def test_receipt_must_match_and_expose_only_public_fields(self):
        for row in ({"accepted": True, "request_id": str(uuid4()), "replayed": False},
                    {"accepted": True, "request_id": self.request, "replayed": 1},
                    {"accepted": True, "request_id": self.request, "replayed": False, "booking_id": "private"},
                    None, []):
            self.client.rpc.return_value.execute.return_value.data = row
            with self.assertRaises(PublicInquiryError):
                self.save()

    def test_dst_and_partial_times(self):
        self.assertIsNone(local_inquiry_time(None, None))
        for day, clock in ((date(2026, 3, 8), time(2, 30)), (None, time(12)),
                           (date(2026, 11, 1), time(1, 30)), (date(9999, 12, 31), time(23))):
            with self.assertRaises(PublicValidationError):
                local_inquiry_time(day, clock)
        first = local_inquiry_time(date(2026, 11, 1), time(1, 30), "First occurrence")
        second = local_inquiry_time(date(2026, 11, 1), time(1, 30), "Second occurrence")
        self.assertNotEqual(first.utcoffset(), second.utcoffset())


class TurnstileTests(unittest.TestCase):
    def test_checks_hostname_action_and_success(self):
        good = {"success": True, "hostname": "example.com", "action": "initial_inquiry"}
        for result in (good, good | {"success": False}, good | {"hostname": "evil.example"}, good | {"action": "login"}, []):
            opener = MagicMock()
            opener.return_value.__enter__.return_value.read.return_value = json.dumps(result).encode()
            if result == good:
                verify_turnstile("token", "uuid", secret="secret", hostname="example.com", opener=opener)
                payload = json.loads(opener.call_args.args[0].data)
                self.assertEqual(payload["idempotency_key"], "uuid")
            else:
                with self.assertRaises(PublicVerificationError):
                    verify_turnstile("token", "uuid", secret="secret", hostname="example.com", opener=opener)

    def test_network_failure_fails_closed(self):
        with self.assertRaises(PublicVerificationError):
            verify_turnstile("token", "uuid", secret="secret", hostname="example.com", opener=MagicMock(side_effect=TimeoutError))

    def test_config_disabled_missing_or_privileged_key_fails_closed(self):
        good = dict(PUBLIC_INQUIRY_ENABLED=True, SUPABASE_URL="https://example.supabase.co",
                    PUBLIC_SUPABASE_ANON_KEY="sb_publishable_test", PUBLIC_INQUIRY_GATEWAY_SECRET="x"*43,
                    TURNSTILE_SITE_KEY="site", TURNSTILE_SECRET_KEY="secret", PUBLIC_INQUIRY_HOSTNAME="example.com")
        for config in ({}, good, good | {"PUBLIC_INQUIRY_ENABLED": "true"}, good | {"PUBLIC_SUPABASE_ANON_KEY": "sb_secret_private"},
                       good | {"PUBLIC_INQUIRY_GATEWAY_SECRET": "short"}, good | {"TURNSTILE_SECRET_KEY": ""}):
            with patch("services.public_inquiry_adapter.st.secrets", config):
                self.assertEqual(load_public_config() is not None, config == good)


if __name__ == "__main__":
    unittest.main()
