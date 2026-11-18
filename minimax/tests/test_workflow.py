import pytest
from sdd.core import PowerContext, digest

def test_state_requires_complete_fields():
    with pytest.raises(ValueError, match="Missing"):
        PowerContext().save({"task_id":"x"})

def test_content_digest_changes():
    assert digest("spec V1") != digest("spec V2")


def test_credential_file_is_not_executed(tmp_path, monkeypatch):
    from sdd.provider import load_env
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    marker=tmp_path/"must-not-exist"
    config=tmp_path/"api.env"
    config.write_text("MINIMAX_API_KEY='$(touch "+str(marker)+")'\n")
    config.chmod(0o600)
    load_env(config)
    assert not marker.exists()


def test_credential_file_requires_private_permissions(tmp_path):
    from sdd.provider import load_env
    config=tmp_path/"api.env"
    config.write_text("MINIMAX_API_KEY=fixture-only\n")
    config.chmod(0o644)
    with pytest.raises(ValueError,match="600"):load_env(config)


def test_rejects_unofficial_provider_before_sending(monkeypatch):
    from sdd.provider import request
    monkeypatch.setenv("MINIMAX_ENDPOINT","https://example.invalid/v1/chat/completions")
    with pytest.raises(ValueError,match="official"):request([])


def test_audit_redacts_configured_secret(tmp_path,monkeypatch):
    from sdd.core import audit
    monkeypatch.setenv("SDD_EVIDENCE",str(tmp_path))
    monkeypatch.setenv("MINIMAX_API_KEY","fixture-secret-value")
    audit("redaction-test",content={"nested":"fixture-secret-value"})
    text=(tmp_path/"events.jsonl").read_text()
    assert "fixture-secret-value" not in text and "[REDACTED]" in text
