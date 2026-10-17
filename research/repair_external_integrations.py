"""Fail-closed HTTPS clients for the external AIOS issuer and COMMIT adapter.

These clients do not mint authority or publish GitHub changes themselves. The
issuer and adapter must be separately deployed and governed services.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_RECORD_KINDS = ("contracts", "permits", "attestations")


class ExternalIntegrationError(RuntimeError):
    pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ExternalIntegrationError("external_service_redirect_rejected")


def _https_url(value: str, label: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ExternalIntegrationError(f"{label}_must_be_https_without_embedded_credentials")
    if parsed.fragment:
        raise ExternalIntegrationError(f"{label}_fragment_forbidden")
    return value.rstrip("/")


def _request_json(url: str, *, token: str, method: str = "GET",
                  payload: dict[str, Any] | None = None, timeout: int = 20) -> dict[str, Any]:
    if not token:
        raise ExternalIntegrationError("external_service_token_missing")
    data = None if payload is None else json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/json",
        "User-Agent": "TRY-AIOS-ExternalIntegration/1.0",
    }
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(request, timeout=timeout) as response:
            raw = response.read(2_000_001)
            status = response.status
    except urllib.error.HTTPError as exc:
        # Do not include response bodies: a remote service could echo credentials.
        raise ExternalIntegrationError(f"external_service_http_{exc.code}") from exc
    except ExternalIntegrationError:
        raise
    except (OSError, TimeoutError, ValueError) as exc:
        raise ExternalIntegrationError(
            f"external_service_transport_or_protocol:{type(exc).__name__}"
        ) from exc
    if len(raw) > 2_000_000:
        raise ExternalIntegrationError("external_service_response_too_large")
    if status != 200:
        raise ExternalIntegrationError(f"external_service_unexpected_status:{status}")
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ExternalIntegrationError("external_service_response_not_json") from exc
    if not isinstance(result, dict):
        raise ExternalIntegrationError("external_service_response_not_object")
    return result


def fetch_authority_snapshot(*, run_id: str, repository: str, base_sha: str,
                             destination: str | Path) -> dict[str, str]:
    """Fetch issuer-signed records for one exact run and materialize read-only files.

    Expected issuer envelope:
      {schema:1, run_id, repository, base_sha, contract_id, permit_id,
       records:{contracts:{content_b64,sha256}, permits:{...}, attestations:{...}}}
    The independent issuer must enforce caller authorization and run binding.
    This function verifies byte digests and writes only the three expected files.
    """
    endpoint = _https_url(os.environ.get("AIOS_REPAIR_ISSUER_URL", "").strip(),
                          "authority_issuer_url")
    token = os.environ.get("AIOS_REPAIR_ISSUER_READ_TOKEN", "").strip()
    if not run_id.isdecimal():
        raise ExternalIntegrationError("authority_run_id_invalid")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ExternalIntegrationError("authority_repository_invalid")
    if not _SHA.fullmatch(base_sha):
        raise ExternalIntegrationError("authority_base_sha_invalid")
    envelope = _request_json(
        f"{endpoint}/v1/authority/runs/{quote(run_id, safe='')}",
        token=token,
    )
    expected = {"schema": 1, "run_id": run_id, "repository": repository,
                "base_sha": base_sha,}
    for key, value in expected.items():
        if type(envelope.get(key)) is not type(value) or envelope.get(key) != value:
            raise ExternalIntegrationError(f"authority_envelope_identity_mismatch:{key}")
    if envelope.get("verified") is not True or envelope.get("attestation_verified") is not True:
        raise ExternalIntegrationError("authority_verifier_did_not_confirm_attestation")
    store_commit_sha = envelope.get("store_commit_sha")
    if not isinstance(store_commit_sha, str) or not _SHA.fullmatch(store_commit_sha):
        raise ExternalIntegrationError("authority_store_commit_sha_invalid")
    contract_id, permit_id = envelope.get("contract_id"), envelope.get("permit_id")
    if not isinstance(contract_id, str) or not _ID.fullmatch(contract_id):
        raise ExternalIntegrationError("authority_contract_id_invalid")
    if not isinstance(permit_id, str) or not _ID.fullmatch(permit_id):
        raise ExternalIntegrationError("authority_permit_id_invalid")
    records = envelope.get("records")
    if not isinstance(records, dict) or set(records) != set(_RECORD_KINDS):
        raise ExternalIntegrationError("authority_records_set_invalid")

    decoded: dict[str, bytes] = {}
    for kind in _RECORD_KINDS:
        item = records.get(kind)
        if not isinstance(item, dict) or set(item) != {"content_b64", "sha256"}:
            raise ExternalIntegrationError(f"authority_record_envelope_invalid:{kind}")
        encoded, digest = item.get("content_b64"), item.get("sha256")
        if not isinstance(encoded, str) or not isinstance(digest, str) or not _DIGEST.fullmatch(digest):
            raise ExternalIntegrationError(f"authority_record_digest_invalid:{kind}")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise ExternalIntegrationError(f"authority_record_encoding_invalid:{kind}") from exc
        if not raw or hashlib.sha256(raw).hexdigest() != digest:
            raise ExternalIntegrationError(f"authority_record_digest_mismatch:{kind}")
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ExternalIntegrationError(f"authority_record_json_invalid:{kind}") from exc
        if not isinstance(record, dict):
            raise ExternalIntegrationError(f"authority_record_not_object:{kind}")
        decoded[kind] = raw

    # IDs are obtained from the issuer envelope; record contents are verified by
    # the existing AIOS verifier after materialization.
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise ExternalIntegrationError("authority_destination_not_directory")
    paths = {
        "contracts": root / "authority" / "contracts" / f"{contract_id}.json",
        "permits": root / "authority" / "permits" / f"{permit_id}.json",
        "attestations": root / "authority" / "attestations" / f"{permit_id}.json",
    }
    for path in paths.values():
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.parent.resolve().relative_to(root)
        except ValueError as exc:
            raise ExternalIntegrationError("authority_destination_path_escape") from exc
        if path.is_symlink() or path.parent.is_symlink():
            raise ExternalIntegrationError("authority_destination_symlink_rejected")
        if path.exists() and not path.is_file():
            raise ExternalIntegrationError("authority_destination_not_regular_file")
    for kind, path in paths.items():
        # Reject symlinked ancestors as well as a symlink at the leaf.
        try:
            path.resolve(strict=False).relative_to(root)
        except ValueError as exc:
            raise ExternalIntegrationError("authority_destination_path_escape") from exc
        temporary = path.with_name(path.name + ".new")
        if temporary.is_symlink():
            raise ExternalIntegrationError("authority_temporary_path_symlink_rejected")
        temporary.write_bytes(decoded[kind])
        os.replace(temporary, path)
    output = os.environ.get("GITHUB_OUTPUT", "")
    if output:
        with open(output, "a", encoding="utf-8") as stream:
            stream.write(f"contract_id={contract_id}\\n")
            stream.write(f"permit_id={permit_id}\\n")
            stream.write("attestation_verified=true\\n")
            stream.write(f"authority_store_commit_sha={store_commit_sha}\\n")
    return {
        "contract_id": contract_id,
        "permit_id": permit_id,
        "attestation_verified": "true",
        "authority_store_commit_sha": store_commit_sha,
        **{kind + "_sha256": hashlib.sha256(decoded[kind]).hexdigest() for kind in _RECORD_KINDS},
    }


def submit_commit_candidate(*, run_id: str, repository: str, base_sha: str,
                            contract_id: str, permit_id: str, patch_path: str | Path,
                            repair_result_path: str | Path,
                            authority_receipt_path: str | Path) -> dict[str, Any]:
    """Submit an evidence-bound candidate to a separate AIOS COMMIT adapter.

    The adapter, not TRY, must independently validate the permit and evidence,
    then use its dedicated least-privilege GitHub App installation.
    """
    endpoint = _https_url(os.environ.get("AIOS_COMMIT_ADAPTER_URL", "").strip(),
                          "commit_adapter_url")
    token = os.environ.get("AIOS_COMMIT_ADAPTER_TOKEN", "").strip()
    if not run_id.isdecimal() or not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ExternalIntegrationError("commit_candidate_identity_invalid")
    if not _SHA.fullmatch(base_sha) or not _ID.fullmatch(contract_id) or not _ID.fullmatch(permit_id):
        raise ExternalIntegrationError("commit_candidate_authority_identity_invalid")

    def read_bounded(path: str | Path, maximum: int, label: str) -> bytes:
        candidate = Path(path)
        if candidate.is_symlink() or not candidate.is_file():
            raise ExternalIntegrationError(f"{label}_file_unavailable")
        raw = candidate.read_bytes()
        if not raw or len(raw) > maximum:
            raise ExternalIntegrationError(f"{label}_size_invalid")
        return raw

    patch = read_bounded(patch_path, 5_000_000, "patch")
    result_raw = read_bounded(repair_result_path, 1_000_000, "repair_result")
    receipt_raw = read_bounded(authority_receipt_path, 100_000, "authority_receipt")
    try:
        repair_result = json.loads(result_raw.decode("utf-8"))
        receipt = json.loads(receipt_raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise ExternalIntegrationError("commit_candidate_evidence_invalid_json") from exc
    if not isinstance(repair_result, dict) or repair_result.get("status") != "PASS":
        raise ExternalIntegrationError("commit_candidate_repair_not_pass")
    if not isinstance(receipt, dict) or receipt.get("verified") is not True:
        raise ExternalIntegrationError("commit_candidate_authority_receipt_not_verified")
    if str(receipt.get("run_id")) != run_id or receipt.get("contract_id") != contract_id or receipt.get("permit_id") != permit_id:
        raise ExternalIntegrationError("commit_candidate_authority_receipt_identity_mismatch")

    patch_digest = hashlib.sha256(patch).hexdigest()
    result_digest = hashlib.sha256(result_raw).hexdigest()
    receipt_digest = hashlib.sha256(receipt_raw).hexdigest()
    idempotency_key = hashlib.sha256(
        f"{repository}:{base_sha}:{run_id}:{patch_digest}:{receipt_digest}".encode()
    ).hexdigest()
    response = _request_json(
        f"{endpoint}/v1/commit/candidate",
        token=token,
        method="POST",
        payload={
            "schema": 1, "run_id": run_id, "repository": repository,
            "base_sha": base_sha, "contract_id": contract_id, "permit_id": permit_id,
            "patch_b64": base64.b64encode(patch).decode("ascii"),
            "patch_sha256": patch_digest, "repair_result_sha256": result_digest,
            "authority_receipt_sha256": receipt_digest,
            "repair_result_b64": base64.b64encode(result_raw).decode("ascii"),
            "authority_receipt_b64": base64.b64encode(receipt_raw).decode("ascii"),
            "idempotency_key": idempotency_key,
        },
    )
    if response.get("status") != "CREATED":
        # UNKNOWN and BLOCKED are intentionally not retried here.
        raise ExternalIntegrationError("commit_adapter_did_not_confirm_creation")
    if response.get("repository") != repository or response.get("base_sha") != base_sha:
        raise ExternalIntegrationError("commit_adapter_response_identity_mismatch")
    if response.get("patch_sha256") != patch_digest:
        raise ExternalIntegrationError("commit_adapter_patch_digest_mismatch")
    if response.get("draft") is not True or response.get("merged") is not False:
        raise ExternalIntegrationError("commit_adapter_must_create_draft_pr_without_merge")
    head_sha = response.get("head_sha")
    if not isinstance(head_sha, str) or not _SHA.fullmatch(head_sha):
        raise ExternalIntegrationError("commit_adapter_head_sha_invalid")
    pr_url = response.get("pull_request_url")
    parsed = urlsplit(pr_url) if isinstance(pr_url, str) else None
    if (parsed is None or parsed.scheme != "https" or parsed.hostname != "github.com"
            or not parsed.path.startswith(f"/{repository}/pull/")):
        raise ExternalIntegrationError("commit_adapter_pull_request_url_invalid")
    return {
        "status": "CREATED", "repository": repository, "base_sha": base_sha,
        "head_sha": head_sha, "pull_request_url": pr_url,
        "patch_sha256": patch_digest, "idempotency_key": idempotency_key,
    }



def main() -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fetch = sub.add_parser("fetch-authority")
    fetch.add_argument("--run-id", required=True)
    fetch.add_argument("--repository", required=True)
    fetch.add_argument("--base-sha", required=True)
    fetch.add_argument("--destination", required=True)
    commit = sub.add_parser("submit-commit")
    commit.add_argument("--run-id", required=True)
    commit.add_argument("--repository", required=True)
    commit.add_argument("--base-sha", required=True)
    commit.add_argument("--contract-id", required=True)
    commit.add_argument("--permit-id", required=True)
    commit.add_argument("--patch", required=True)
    commit.add_argument("--repair-result", required=True)
    commit.add_argument("--authority-receipt", required=True)
    args = parser.parse_args()
    try:
        if args.command == "fetch-authority":
            result = fetch_authority_snapshot(
                run_id=args.run_id, repository=args.repository, base_sha=args.base_sha,
                destination=args.destination,
            )
            output = os.environ.get("GITHUB_OUTPUT", "")
            if output:
                with open(output, "a", encoding="utf-8") as stream:
                    stream.write(f"contract_id={result['contract_id']}\n")
                    stream.write(f"permit_id={result['permit_id']}\n")
            print(json.dumps({"status": "FETCHED_AND_DIGEST_VERIFIED", **result}, sort_keys=True))
        else:
            result = submit_commit_candidate(
                run_id=args.run_id, repository=args.repository, base_sha=args.base_sha,
                contract_id=args.contract_id, permit_id=args.permit_id,
                patch_path=args.patch, repair_result_path=args.repair_result,
                authority_receipt_path=args.authority_receipt,
            )
            print(json.dumps(result, sort_keys=True))
    except ExternalIntegrationError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
