"""Federation security tests — identity verification and bearer token validation."""
import pytest
from unittest.mock import MagicMock
from app.services.federation.identity import verify_tailscale_origin, verify_bearer_token
from app.services.federation.predicates import evaluate_predicate
from app.services.federation.redaction import apply_redactions

def make_request(ip: str):
	req = MagicMock()
	req.client.host = ip
	return req

def test_tailscale_origin_accepted():
	req = make_request("100.64.0.1")
	verify_tailscale_origin(req)  # should not raise

def test_public_ip_rejected():
	req = make_request("1.2.3.4")
	from fastapi import HTTPException
	with pytest.raises(HTTPException) as exc:
		verify_tailscale_origin(req)
	assert exc.value.status_code == 403

def test_bearer_token_valid():
	import hashlib
	token = "test-token-abc123"
	stored = hashlib.sha256(token.encode()).hexdigest()
	assert verify_bearer_token(token, stored) is True

def test_bearer_token_invalid():
	import hashlib
	stored = hashlib.sha256(b"real-token").hexdigest()
	assert verify_bearer_token("wrong-token", stored) is False

def test_predicate_scope_match():
	pred = {"scopes_in": ["work"], "tags_any": [], "tags_none": []}
	assert evaluate_predicate(pred, {"scope": "work"}) is True

def test_predicate_scope_reject():
	pred = {"scopes_in": ["work"], "tags_any": [], "tags_none": []}
	assert evaluate_predicate(pred, {"scope": "family"}) is False

def test_redaction_calendar():
	item = {"scope": "work", "title": "Team standup", "busy": True}
	result = apply_redactions("calendar_availability", item)
	assert "title" not in result
	assert "busy" in result
