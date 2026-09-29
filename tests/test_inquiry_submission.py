"""The submission adapter owns serialization/errors, not Streamlit or matching SQL."""

import subprocess
import sys
import unittest
from dataclasses import replace
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

from services.inquiries import InquiryAnswers, StaffInquiryContext, normalize_inquiry
from services.inquiry_submission import (
    InquiryAuthorizationError, InquiryClosedError, InquiryConflictError,
    InquirySubmissionError, InquiryUnavailableError, InquiryValidationError,
    append_inquiry_submission, create_inquiry,
)


class InquirySubmissionTests(unittest.TestCase):
    def setUp(self):
        self.answers = InquiryAnswers('  Jamie  ', date(2027, 6, 14), 12, 'email', email=' JAMIE@example.com ')
        self.request = uuid4()
        self.booking = uuid4()
        self.submission = uuid4()
        self.client = MagicMock()
        self.row = dict(booking_id=str(self.booking), booking_number='BR-2027-001',
                        submission_id=str(self.submission), submission_number=1, replayed=False)
        self.client.rpc.return_value.execute.return_value.data = [self.row]

    def test_import_does_not_initialize_client_or_ui(self):
        result = subprocess.run([sys.executable, '-c',
            "import sys; import services.inquiry_submission; "
            "assert 'streamlit' not in sys.modules; assert 'supabase' not in sys.modules"],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_creation_preserves_originals_and_separates_staff_context(self):
        result = create_inquiry(self.answers, request_id=self.request, client=self.client,
                                staff_context=StaffInquiryContext(internal_notes=' Private ',
                                    facebook_conversation_url='https://example.com/conversation'))
        rpc, payload = self.client.rpc.call_args.args
        self.assertEqual(rpc, 'create_staff_inquiry')
        self.assertEqual(payload['p_request_id'], str(self.request))
        self.assertEqual(payload['p_snapshot']['answers']['customer_name'], '  Jamie  ')
        self.assertEqual(payload['p_snapshot']['answers']['email'], ' JAMIE@example.com ')
        self.assertIsNone(payload['p_snapshot']['answers']['source'])
        self.assertEqual(normalize_inquiry(self.answers).source, 'other')
        self.assertEqual(payload['p_staff_context']['internal_notes'], ' Private ')
        self.assertNotIn('internal_notes', payload['p_snapshot']['answers'])
        self.assertNotIn('p_actor', payload)
        self.assertNotIn('p_origin', payload)
        self.assertEqual(result.submission_id, str(self.submission))
        self.assertFalse(result.replayed)

    def test_append_and_replay_result(self):
        self.row.update(replayed=True, submission_number=3)
        result = append_inquiry_submission(self.booking, self.answers, request_id=self.request, client=self.client)
        rpc, payload = self.client.rpc.call_args.args
        self.assertEqual(rpc, 'append_staff_inquiry_submission')
        self.assertEqual(payload['p_booking_id'], str(self.booking))
        self.assertNotIn('p_staff_context', payload)
        self.assertTrue(result.replayed)
        self.assertEqual(result.submission_number, 3)

    def test_invalid_answers_ids_and_context_never_call_rpc(self):
        calls = [
            lambda: create_inquiry(replace(self.answers, requested_bench_count=0), request_id=self.request, client=self.client),
            lambda: create_inquiry(self.answers, request_id='bad', client=self.client),
            lambda: append_inquiry_submission('bad', self.answers, request_id=self.request, client=self.client),
            lambda: create_inquiry(self.answers, request_id=self.request, client=self.client,
                                   staff_context=StaffInquiryContext(customer_profile_notes='')),
            lambda: create_inquiry(self.answers, request_id=self.request, client=self.client,
                                   staff_context=StaffInquiryContext(existing_customer_id='bad')),
            lambda: create_inquiry(self.answers, request_id=self.request, client=self.client,
                                   staff_context=StaffInquiryContext(internal_notes=12)),
        ]
        for call in calls:
            with self.subTest(call=call), self.assertRaises(InquiryValidationError):
                call()
        self.client.rpc.assert_not_called()

    def test_client_is_required(self):
        with self.assertRaises(TypeError):
            create_inquiry(self.answers, request_id=self.request)
        with self.assertRaises(TypeError):
            append_inquiry_submission(self.booking, self.answers, request_id=self.request)

    def test_errors_use_codes_not_sensitive_database_messages(self):
        for code, kind in [('P5101', InquiryValidationError), ('P5102', InquiryUnavailableError),
                           ('P5103', InquiryClosedError), ('P5104', InquiryConflictError),
                           ('42501', InquiryAuthorizationError), ('XX000', InquirySubmissionError)]:
            error = RuntimeError('private customer data')
            error.code = code
            self.client.rpc.return_value.execute.side_effect = error
            with self.subTest(code=code), self.assertRaises(kind) as raised:
                create_inquiry(self.answers, request_id=self.request, client=self.client)
            self.assertNotIn('private customer data', str(raised.exception))

    def test_uncertain_response_can_retry_identical_payload(self):
        self.client.rpc.return_value.execute.side_effect = [TimeoutError(), SimpleNamespace(data=[{**self.row, 'replayed': True}])]
        with self.assertRaises(InquirySubmissionError):
            create_inquiry(self.answers, request_id=self.request, client=self.client)
        result = create_inquiry(self.answers, request_id=self.request, client=self.client)
        self.assertTrue(result.replayed)
        self.assertEqual(self.client.rpc.call_args_list[0], self.client.rpc.call_args_list[1])

    def test_malformed_response_is_uncertain_not_success(self):
        for response in [None, [], [self.row, self.row], {}, {**self.row, 'replayed': 'false'},
                         {**self.row, 'submission_number': True}, {**self.row, 'submission_id': 'bad'}]:
            self.client.rpc.return_value.execute.return_value.data = response
            with self.subTest(response=response), self.assertRaises(InquirySubmissionError):
                create_inquiry(self.answers, request_id=self.request, client=self.client)


if __name__ == '__main__':
    unittest.main()
