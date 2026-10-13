import json
import os
import unittest
from unittest.mock import patch

from research import repair_checkpoint


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
            return _Response({"persisted": True, "version": 1})
        with patch.object(repair_checkpoint.urllib.request, "urlopen", fake_urlopen):
            result = repair_checkpoint.persist_checkpoint(
                request_id="try-ci-repair:42", repository="yanhul/try", sha="a" * 40,
                attempt=1, phase="OBSERVE", state="WORKING",
            )
        self.assertTrue(result["persisted"])
        self.assertEqual(seen["url"], "https://try.example.workers.dev/v1/repair/checkpoint")
        self.assertEqual(seen["authorization"], "Bearer secret-test-token")
        self.assertEqual(seen["payload"]["sha"], "a" * 40)

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


if __name__ == "__main__":
    unittest.main()
