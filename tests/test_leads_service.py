import unittest
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.leads import (
    CustomerMatch,
    LeadCreateInput,
    LeadDispositionInput,
    LeadServiceError,
    LeadUpdateInput,
    create_lead,
    find_customer_matches,
    normalize_email,
    normalize_facebook,
    normalize_phone,
    set_lead_disposition,
    update_lead,
    validate_lead_disposition,
    validate_lead_input,
)


def valid_lead(**overrides):
    values = {
        "customer_name": "Jamie Smith",
        "event_date": date(2027, 6, 14),
        "requested_bench_count": 12,
        "preferred_contact_method": "email",
        "email": "jamie@example.com",
    }
    values.update(overrides)
    return LeadCreateInput(**values)


class LeadValidationTests(unittest.TestCase):
    def test_normalizes_contact_values(self):
        self.assertEqual(normalize_email(" JAMIE@Example.COM "), "jamie@example.com")
        self.assertEqual(normalize_phone("(402) 555-0123"), "4025550123")
        self.assertEqual(normalize_facebook("  Jamie   Smith "), "jamie smith")

    def test_accepts_valid_contact_combinations(self):
        self.assertEqual(validate_lead_input(valid_lead()), [])
        self.assertEqual(
            validate_lead_input(
                valid_lead(
                    email=None,
                    phone="402-555-0123",
                    preferred_contact_method="text",
                )
            ),
            [],
        )
        self.assertEqual(
            validate_lead_input(
                valid_lead(
                    email=None,
                    facebook_identity="Jamie Smith",
                    preferred_contact_method="facebook",
                )
            ),
            [],
        )

    def test_rejects_missing_and_inconsistent_values(self):
        errors = validate_lead_input(
            valid_lead(
                customer_name=" ",
                requested_bench_count=0,
                email="bad-email",
                preferred_contact_method="phone",
            )
        )
        self.assertIn("Enter the customer's name.", errors)
        self.assertIn("Requested benches must be at least 1.", errors)
        self.assertIn("Enter a valid email address.", errors)
        self.assertIn(
            "The preferred contact method must have contact information.", errors
        )

    def test_validates_lead_disposition_targets_and_reasons(self):
        for target in ("lost", "cancelled"):
            with self.subTest(target=target):
                self.assertEqual(
                    validate_lead_disposition(
                        LeadDispositionInput(
                            booking_number="BR-2027-001",
                            target_stage=target,
                            reason="Customer changed plans",
                        )
                    ),
                    [],
                )
        self.assertEqual(
            validate_lead_disposition(
                LeadDispositionInput(
                    booking_number="BR-2027-001",
                    target_stage="lead",
                )
            ),
            [],
        )

    def test_rejects_invalid_disposition_values(self):
        errors = validate_lead_disposition(
            LeadDispositionInput(
                booking_number="invalid",
                target_stage="confirmed",
                reason=" ",
            )
        )
        self.assertIn("Choose a valid booking.", errors)
        self.assertIn("Choose a valid lead status.", errors)

        for target in ("lost", "cancelled"):
            with self.subTest(target=target):
                errors = validate_lead_disposition(
                    LeadDispositionInput(
                        booking_number="BR-2027-001",
                        target_stage=target,
                        reason=" ",
                    )
                )
                self.assertIn("Enter a reason before closing the lead.", errors)


class CustomerMatchingTests(unittest.TestCase):
    @patch("services.leads.get_supabase_client")
    def test_matches_contacts_and_deduplicates_customer(self, get_client):
        client = MagicMock()
        customer_query = client.table.return_value.select.return_value.eq.return_value
        identity_query = client.table.return_value.select.return_value.eq.return_value
        customer_query.execute.side_effect = [
            SimpleNamespace(
                data=[
                    {
                        "id": "customer-1",
                        "preferred_name": "Jamie",
                        "legal_name": None,
                        "email": "JAMIE@example.com",
                        "phone": "(402) 555-0123",
                    }
                ]
            ),
            SimpleNamespace(
                data=[
                    {
                        "customer_id": "customer-1",
                        "display_value": "Jamie Smith",
                    }
                ]
            ),
        ]
        get_client.return_value = client

        matches = find_customer_matches(
            email="jamie@example.com",
            phone="4025550123",
            facebook_identity=" jamie smith ",
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].customer_id, "customer-1")
        self.assertEqual(matches[0].matched_on, ("Facebook", "email", "phone"))

    @patch("services.leads.get_supabase_client")
    def test_customer_matching_excludes_current_customer(self, get_client):
        client = MagicMock()
        query = client.table.return_value.select.return_value.eq.return_value
        query.execute.return_value = SimpleNamespace(
            data=[
                {
                    "id": "customer-1",
                    "preferred_name": "Jamie",
                    "email": "jamie@example.com",
                    "phone": None,
                }
            ]
        )
        get_client.return_value = client

        matches = find_customer_matches(
            email="jamie@example.com",
            phone=None,
            facebook_identity=None,
            exclude_customer_id="customer-1",
        )

        self.assertEqual(matches, [])

    @patch("services.leads.get_supabase_client")
    def test_translates_lookup_failure(self, get_client):
        get_client.return_value.table.side_effect = RuntimeError("hidden")
        with self.assertRaises(LeadServiceError) as context:
            find_customer_matches(email="a@b.com", phone=None, facebook_identity=None)
        self.assertIsInstance(context.exception.__cause__, RuntimeError)


class LeadCreationTests(unittest.TestCase):
    @patch("services.leads.get_supabase_client")
    def test_calls_rpc_and_returns_result(self, get_client):
        client = MagicMock()
        client.rpc.return_value.execute.return_value = SimpleNamespace(
            data=[{"booking_id": "booking-1", "booking_number": "BR-2027-001"}]
        )
        get_client.return_value = client
        lead = valid_lead(existing_customer_id="customer-1")

        result = create_lead(lead)

        self.assertEqual(result.booking_number, "BR-2027-001")
        rpc_name, payload = client.rpc.call_args.args
        self.assertEqual(rpc_name, "create_lead")
        self.assertEqual(payload["p_existing_customer_id"], "customer-1")
        self.assertEqual(payload["p_event_date"], "2027-06-14")

    @patch("services.leads.get_supabase_client")
    def test_translates_malformed_rpc_response(self, get_client):
        get_client.return_value.rpc.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        with self.assertRaises(LeadServiceError) as context:
            create_lead(valid_lead())
        self.assertIsInstance(context.exception.__cause__, ValueError)


class LeadUpdateTests(unittest.TestCase):
    @patch("services.leads.get_supabase_client")
    def test_calls_update_rpc_and_returns_booking_number(self, get_client):
        client = MagicMock()
        client.rpc.return_value.execute.return_value = SimpleNamespace(
            data=[{"booking_number": "BR-2027-001"}]
        )
        get_client.return_value = client
        lead = LeadUpdateInput(
            booking_number="BR-2027-001",
            customer_id="customer-1",
            customer_name="Jamie Smith",
            event_date=date(2028, 7, 1),
            requested_bench_count=14,
            preferred_contact_method="email",
            source="word_of_mouth",
            email=" JAMIE@example.com ",
        )

        result = update_lead(lead)

        self.assertEqual(result.booking_number, "BR-2027-001")
        rpc_name, payload = client.rpc.call_args.args
        self.assertEqual(rpc_name, "update_lead")
        self.assertEqual(payload["p_booking_number"], "BR-2027-001")
        self.assertEqual(payload["p_event_date"], "2028-07-01")
        self.assertEqual(payload["p_email"], "jamie@example.com")

    @patch("services.leads.get_supabase_client")
    def test_update_translates_malformed_response(self, get_client):
        get_client.return_value.rpc.return_value.execute.return_value = SimpleNamespace(
            data=[]
        )
        lead = LeadUpdateInput(
            booking_number="BR-2027-001",
            customer_id="customer-1",
            customer_name="Jamie",
            event_date=date(2027, 6, 14),
            requested_bench_count=12,
            preferred_contact_method="email",
            source="facebook_marketplace",
            email="jamie@example.com",
        )

        with self.assertRaises(LeadServiceError) as context:
            update_lead(lead)

        self.assertIsInstance(context.exception.__cause__, ValueError)

    @patch("services.leads.get_supabase_client")
    def test_calls_disposition_rpc_with_normalized_payload(self, get_client):
        client = MagicMock()
        client.rpc.return_value.execute.return_value = SimpleNamespace(
            data=[{"booking_number": "BR-2027-001", "stage": "lost"}]
        )
        get_client.return_value = client

        result = set_lead_disposition(
            LeadDispositionInput(
                booking_number=" BR-2027-001 ",
                target_stage="lost",
                reason="  Customer chose another company.  ",
            )
        )

        self.assertEqual(result.booking_number, "BR-2027-001")
        self.assertEqual(result.stage, "lost")
        client.rpc.assert_called_once_with(
            "set_lead_disposition",
            {
                "p_booking_number": "BR-2027-001",
                "p_target_stage": "lost",
                "p_reason": "Customer chose another company.",
            },
        )

    @patch("services.leads.get_supabase_client")
    def test_restore_payload_clears_reason(self, get_client):
        client = MagicMock()
        client.rpc.return_value.execute.return_value = SimpleNamespace(
            data={"booking_number": "BR-2027-001", "stage": "lead"}
        )
        get_client.return_value = client

        result = set_lead_disposition(
            LeadDispositionInput(
                booking_number="BR-2027-001",
                target_stage="lead",
                reason=None,
            )
        )

        self.assertEqual(result.stage, "lead")
        payload = client.rpc.call_args.args[1]
        self.assertIsNone(payload["p_reason"])

    @patch("services.leads.get_supabase_client")
    def test_disposition_translates_malformed_response(self, get_client):
        get_client.return_value.rpc.return_value.execute.return_value = SimpleNamespace(
            data=[{"booking_number": "BR-2027-001", "stage": "cancelled"}]
        )

        with self.assertRaises(LeadServiceError) as context:
            set_lead_disposition(
                LeadDispositionInput(
                    booking_number="BR-2027-001",
                    target_stage="lost",
                    reason="No response",
                )
            )

        self.assertIsInstance(context.exception.__cause__, ValueError)

    @patch("services.leads.get_supabase_client")
    def test_disposition_translates_supabase_failure(self, get_client):
        get_client.return_value.rpc.return_value.execute.side_effect = RuntimeError(
            "database unavailable"
        )

        with self.assertRaises(LeadServiceError) as context:
            set_lead_disposition(
                LeadDispositionInput(
                    booking_number="BR-2027-001",
                    target_stage="cancelled",
                    reason="Event was cancelled",
                )
            )

        self.assertIsInstance(context.exception.__cause__, RuntimeError)


if __name__ == "__main__":
    unittest.main()
