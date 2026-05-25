"""Unit tests for ``services.trust._classify_403``.

The bug this protects against: GitHub overloads HTTP 403 for two very
different conditions, and the previous code mapped both onto
``GitHubRateLimitError``. The most painful real-world case is the
``autopkg`` org's policy that forbids fine-grained PATs with a lifetime
greater than 366 days — that returns 403 with a clear message about token
lifetime, but the old code logged it as "rate limit exceeded" and made the
operator wait for a phantom reset that was never coming.

These tests pin the new behaviour:
- 403 + ``X-RateLimit-Remaining: 0`` is a real rate-limit hit.
- 403 + body containing "rate limit" is also a rate-limit hit (some
  GitHub error paths set the body before the header).
- Anything else surfaces as ``GitHubForbiddenError`` carrying the
  GitHub-supplied ``message`` so the operator can fix the PAT.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from automunki.services.trust import (
    GitHubForbiddenError,
    GitHubRateLimitError,
    _classify_403,
)


@dataclass
class FakeResponse:
    """Minimal stand-in for an httpx response — only the fields ``_classify_403`` reads."""

    headers: dict[str, str] = field(default_factory=dict)
    text: str = ""


def test_rate_limit_via_remaining_header():
    resp = FakeResponse(
        headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"},
        text='{"message": "API rate limit exceeded for IP 1.2.3.4."}',
    )
    err = _classify_403(resp)
    assert isinstance(err, GitHubRateLimitError)
    assert err.reset_at == 1700000000


def test_rate_limit_via_body_text_when_header_missing():
    # Some primary rate-limit responses don't include the remaining header,
    # but the body always says so. Make sure we still classify them correctly.
    resp = FakeResponse(
        headers={},
        text='{"message": "You have exceeded a secondary rate limit."}',
    )
    err = _classify_403(resp)
    assert isinstance(err, GitHubRateLimitError)
    assert err.reset_at is None


def test_autopkg_org_lifetime_policy_is_forbidden_not_rate_limit():
    # This is the exact body the autopkg org returns when a fine-grained PAT
    # with > 366d lifetime hits one of their public repos. Before this fix
    # the trust service classified it as a rate-limit error and waited.
    body = (
        '{"message": "The \'autopkg\' organization forbids access via a '
        "fine-grained personal access tokens if the token's lifetime is "
        "greater than 366 days. Please adjust your token's lifetime.\", "
        '"documentation_url": "https://docs.github.com/...", "status": "403"}'
    )
    resp = FakeResponse(
        headers={"x-ratelimit-remaining": "4998"},
        text=body,
    )
    err = _classify_403(resp)
    assert isinstance(err, GitHubForbiddenError)
    assert "366 days" in err.github_message


def test_missing_scope_is_forbidden():
    resp = FakeResponse(
        headers={"x-ratelimit-remaining": "4999"},
        text='{"message": "Resource not accessible by personal access token"}',
    )
    err = _classify_403(resp)
    assert isinstance(err, GitHubForbiddenError)
    assert err.github_message == "Resource not accessible by personal access token"


def test_non_json_body_still_yields_forbidden_with_truncated_message():
    resp = FakeResponse(
        headers={"x-ratelimit-remaining": "4999"},
        text="not json " * 100,
    )
    err = _classify_403(resp)
    assert isinstance(err, GitHubForbiddenError)
    # We truncate to 300 chars so structured logs don't blow up.
    assert len(err.github_message) <= 300
