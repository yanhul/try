# Gemini Free Tier — TRY provider contract

## Ownership boundary

- TRY owns the Gemini API credential and performs model inference.
- AIOS sends bounded source/evidence to the TRY bridge and receives an **untrusted proposal**.
- AIOS alone decides whether a proposal is authorized, applies any patch, runs trusted tests, verifies evidence, and promotes or blocks the result.
- Gemini output is never an authority decision, execution receipt, or PASS assertion.

## Configuration

Configure these values in the Cloudflare Worker environment:

- `GEMINI_API_KEY`: secret created for the Gemini Developer API; store only as a Worker secret.
- `GEMINI_MODEL`: optional model selection; the current default is `gemini-3.1-flash-lite`.
- `TRY_PROVIDER_TOKEN`: separate secret authenticating AIOS-to-TRY requests.

Do not put credentials in Git, Worker plaintext variables, AIOS state, request payloads, or logs.

## Free-tier behavior

- The Worker uses the Gemini OpenAI-compatible chat-completions endpoint and its Bearer-key authentication format. The API key is already associated with a Google AI Studio project; this request does not need a separate project ID. Do not copy that header format to Gemini's native `:generateContent` endpoint.
- Google applies quota by project/model and may change limits or eligibility. This repository deliberately does not hard-code a claimed requests-per-day or tokens-per-minute allowance.
- HTTP 429 is a hard quota stop: no automatic retry and no provider substitution.
- Only transient HTTP 500/502/503/504 responses are retried, with the bounded retry policy in the Worker.
- A quota or provider failure returns a blocked/retryable result to the caller; it must not be interpreted as an empty successful proposal.
- No automatic fallback to another LLM provider is allowed. Any future provider change requires an explicit policy/configuration decision and separate tests.

## Verification levels

1. Unit tests with a fake transport verify endpoint, authentication header, model selection, request schema, configuration validation, and quota handling. They do not call Google.
2. Worker smoke tests verify the deployed endpoint and AIOS-to-TRY bridge. They do not prove a live Gemini request unless the proposal path actually reaches Gemini.
3. Real E2E requires a valid TRY-owned `GEMINI_API_KEY`, deployed Worker, bridge token, and an actual model response. Missing credentials must be reported as BLOCKED, not PASS.

## References

- [Gemini API documentation](https://ai.google.dev/gemini-api/docs)
- [OpenAI compatibility documentation](https://ai.google.dev/gemini-api/docs/openai)
