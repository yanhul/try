import json
import os
import unittest
from unittest.mock import patch

from research import repair_checkpoint
from research.autonomous_repair import select_resume_attempt


class _Response:
    status = 200
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class RepairCheckpointClientTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            "TRY_REPAIR_PROVIDER_URL": "https://try.example.workers.dev",
            "TRY_REPAIR_PROVIDER_TOKEN": "secret-test-token",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_persists_checkpoint_with_identity_and_auth(self):
        seen = {}
        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["authorization"] = request.get_header("Authorization")
            seen["payload"] = json.loads(request.data.decode("utf-8"))
            seen["timeout"] = timeout
            return _Response({
                "persisted": True, "version": 1,
                "request_id": "try-ci-repair:42", "repository": "yanhul/try",
                "sha": "a" * 40, "attempt": 1, "phase": "OBSERVE",
                "state": "WORKING", "evidence_digest": None, "reason": None,
            })
        with patch.object(repair_checkpoint.urllib.request, "urlopen", fake_urlopen):
            result = repair_checkpoint.persist_checkpoint(
                request_id="try-ci-repair:42", repository="yanhul/try", sha="a" * 40,
                attempt=1, phase="OBSERVE", state="WORKING",
            )
        self.assertTrue(result["persisted"])
        self.assertEqual(seen["url"], "https://try.example.workers.dev/v1/repair/checkpoint")
        self.assertEqual(seen["authorization"], "Bearer secret-test-token")
        self.assertEqual(seen["payload"]["sha"], "a" * 40)

    def test_checkpoint_ack_must_match_requested_transition(self):
        def fake_urlopen(request, timeout):
            return _Response({
                "persisted": True, "version": 1,
                "request_id": "different-request", "repository": "yanhul/try",
                "sha": "a" * 40, "attempt": 1, "phase": "OBSERVE",
                "state": "WORKING", "evidence_digest": None, "reason": None,
            })
        with patch.object(repair_checkpoint.urllib.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(repair_checkpoint.RepairCheckpointError, "ack_mismatch:request_id"):
                repair_checkpoint.persist_checkpoint(
                    request_id="try-ci-repair:42", repository="yanhul/try", sha="a" * 40,
                    attempt=1, phase="OBSERVE", state="WORKING",
                )

    def test_invalid_request_id_rejected_before_network(self):
        for request_id in ("", "contains/slash", "x" * 161, "has space"):
            with self.subTest(request_id=request_id):
                with patch.object(repair_checkpoint.urllib.request, "urlopen") as call:
                    with self.assertRaisesRegex(repair_checkpoint.RepairCheckpointError, "request_id_invalid"):
                        repair_checkpoint.persist_checkpoint(
                            request_id=request_id, repository="yanhul/try", sha="a" * 40,
                            attempt=1, phase="OBSERVE", state="WORKING",
                        )
                call.assert_not_called()

    def test_done_without_digest_fails_before_network(self):
        with patch.object(repair_checkpoint.urllib.request, "urlopen") as call:
            with self.assertRaisesRegex(repair_checkpoint.RepairCheckpointError, "done_requires_persisted_evidence"):
                repair_checkpoint.persist_checkpoint(
                    request_id="try-ci-repair:42", repository="yanhul/try", sha="a" * 40,
                    attempt=1, phase="PERSIST", state="DONE",
                )
        call.assert_not_called()

    def test_missing_provider_credentials_fail_closed(self):
        with patch.dict(os.environ, {"TRY_REPAIR_PROVIDER_URL": "", "TRY_REPAIR_PROVIDER_TOKEN": ""}):
            with self.assertRaisesRegex(repair_checkpoint.RepairCheckpointError, "not_configured"):
                repair_checkpoint.persist_checkpoint(
                    request_id="try-ci-repair:42", repository="yanhul/try", sha="a" * 40,
                    attempt=1, phase="OBSERVE", state="WORKING",
                )



    def test_reads_existing_checkpoint_with_auth(self):
        seen = {}
        record = {"schema": 1, "request_id": "try-ci-repair:42", "repository": "yanhul/try",
                  "sha": "a" * 40, "attempt": 1, "phase": "VERIFY",
                  "state": "BLOCKED", "version": 5, "reason": "test-blocked"}
        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["authorization"] = request.get_header("Authorization")
            seen["timeout"] = timeout
            return _Response(record)
        with patch.object(repair_checkpoint.urllib.request, "urlopen", fake_urlopen):
            result = repair_checkpoint.get_checkpoint(request_id="try-ci-repair:42")
        self.assertEqual(result, record)
        self.assertEqual(seen["url"], "https://try.example.workers.dev/v1/repair/checkpoint/try-ci-repair:42")
        self.assertEqual(seen["authorization"], "Bearer secret-test-token")

    def test_missing_checkpoint_returns_none(self):
        def fake_urlopen(request, timeout):
            raise repair_checkpoint.urllib.error.HTTPError(
                request.full_url, 404, "not found", {}, None
            )
        with patch.object(repair_checkpoint.urllib.request, "urlopen", fake_urlopen):
            self.assertIsNone(repair_checkpoint.get_checkpoint(request_id="try-ci-repair:42"))

    def test_checkpoint_read_rejects_identity_mismatch(self):
        def fake_urlopen(request, timeout):
            return _Response({"request_id": "different-request"})
        with patch.object(repair_checkpoint.urllib.request, "urlopen", fake_urlopen):
            with self.assertRaisesRegex(repair_checkpoint.RepairCheckpointError, "identity_mismatch"):
                repair_checkpoint.get_checkpoint(request_id="try-ci-repair:42")

    def test_checkpoint_read_rejects_incomplete_or_invalid_record(self):
        invalid_records = [
            {"request_id": "try-ci-repair:42"},
            {"request_id": "try-ci-repair:42", "repository": "yanhul/try", "sha": "bad",
             "attempt": 1, "phase": "VERIFY", "state": "BLOCKED", "version": 1,
             "reason": "failed"},
            {"request_id": "try-ci-repair:42", "repository": "yanhul/try", "sha": "a" * 40,
             "attempt": True, "phase": "VERIFY", "state": "BLOCKED", "version": 1,
             "reason": "failed"},
            {"request_id": "try-ci-repair:42", "repository": "yanhul/try", "sha": "a" * 40,
             "attempt": 1, "phase": "PERSIST", "state": "DONE", "version": 1},
            {"request_id": "try-ci-repair:42", "repository": "yanhul/try", "sha": "a" * 40,
             "attempt": 1, "phase": "VERIFY", "state": "BLOCKED", "version": 1},
        ]
        for record in invalid_records:
            with self.subTest(record=record):
                with patch.object(repair_checkpoint.urllib.request, "urlopen", lambda request, timeout: _Response(record)):
                    with self.assertRaises(repair_checkpoint.RepairCheckpointError):
                        repair_checkpoint.get_checkpoint(request_id="try-ci-repair:42")


    def test_resume_starts_at_one_without_checkpoint(self):
        self.assertEqual(select_resume_attempt(None, repository="yanhul/try", sha="a" * 40), 1)

    def test_resume_advances_only_from_matching_blocked_checkpoint(self):
        prior = {"repository": "yanhul/try", "sha": "a" * 40,
                 "attempt": 1, "phase": "VERIFY", "state": "BLOCKED"}
        self.assertEqual(select_resume_attempt(prior, repository="yanhul/try", sha="a" * 40), 2)

    def test_resume_rejects_working_checkpoint_after_interruption(self):
        prior = {"repository": "yanhul/try", "sha": "a" * 40,
                 "attempt": 1, "phase": "VERIFY", "state": "WORKING"}
        with self.assertRaisesRegex(repair_checkpoint.RepairCheckpointError, "checkpoint_not_resumable"):
            select_resume_attempt(prior, repository="yanhul/try", sha="a" * 40)

    def test_resume_rejects_identity_change_and_exhausted_budget(self):
        prior = {"repository": "yanhul/try", "sha": "a" * 40,
                 "attempt": 1, "phase": "VERIFY", "state": "BLOCKED"}
        with self.assertRaisesRegex(repair_checkpoint.RepairCheckpointError, "identity_conflict"):
            select_resume_attempt(prior, repository="yanhul/try", sha="b" * 40)
        prior["attempt"] = 3
        with self.assertRaisesRegex(repair_checkpoint.RepairCheckpointError, "budget_exhausted"):
            select_resume_attempt(prior, repository="yanhul/try", sha="a" * 40)

if __name__ == "__main__":
    unittest.main()
