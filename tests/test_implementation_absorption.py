import json

def test_implementation_absorption_binds_only_local_runtime(tmp_path, monkeypatch):
    import research.discovery.implementation_absorption as impl
    proof={"status":"PASS","absorbed":[{
        "candidate_id":"Q-1","source_id":"SRC-1","source_url":"https://example.test/a",
        "family":"mean_reversion","hypothesis_id":"discovered_primitive",
        "discovery_spec":{"mechanism_family":"mean_reversion","operator":"zscore"},
        "source_digest":"abc"
    }]}
    pp=tmp_path/"proof.json"; out=tmp_path/"impl.json"
    pp.write_text(json.dumps(proof),encoding="utf-8")
    monkeypatch.setattr(impl,"PROOF",pp); monkeypatch.setattr(impl,"OUT",out)
    assert impl.main()==0
    result=json.loads(out.read_text())
    assert result["implemented_count"]==1
    assert result["implemented"][0]["mode"]=="LOCAL_ADAPTER"

def test_implementation_absorption_fails_closed_on_unknown_operator(tmp_path, monkeypatch):
    import research.discovery.implementation_absorption as impl
    proof={"status":"PASS","absorbed":[{
        "candidate_id":"Q-2","source_id":"SRC-2","source_url":"https://example.test/b",
        "family":"mean_reversion","hypothesis_id":"discovered_primitive",
        "discovery_spec":{"mechanism_family":"mean_reversion","operator":"external_magic"},
        "source_digest":"def"
    }]}
    pp=tmp_path/"proof.json"; out=tmp_path/"impl.json"
    pp.write_text(json.dumps(proof),encoding="utf-8")
    monkeypatch.setattr(impl,"PROOF",pp); monkeypatch.setattr(impl,"OUT",out)
    assert impl.main()==0
    result=json.loads(out.read_text())
    assert result["implemented_count"]==0
    assert result["blocked"][0]["reason"]=="local_operator_runtime_missing"


def test_implementation_absorption_allows_governed_partial_result(tmp_path, monkeypatch):
    import research.discovery.implementation_absorption as impl
    proof={"status":"PASS","absorbed":[
        {"candidate_id":"Q-1","source_id":"SRC-1","source_url":"https://example.test/a","family":"mean_reversion","hypothesis_id":"discovered_primitive","discovery_spec":{"mechanism_family":"mean_reversion","operator":"zscore"},"source_digest":"abc"},
        {"candidate_id":"Q-2","source_id":"SRC-2","source_url":"https://example.test/b","family":"volatility","hypothesis_id":"discovered_primitive","discovery_spec":{"mechanism_family":"volatility","operator":"zscore"},"source_digest":"def"}]}
    pp=tmp_path/"proof.json"; out=tmp_path/"impl.json"
    pp.write_text(json.dumps(proof),encoding="utf-8")
    monkeypatch.setattr(impl,"PROOF",pp); monkeypatch.setattr(impl,"OUT",out)
    assert impl.main()==0
    result=json.loads(out.read_text())
    assert result["status"]=="PARTIAL"
    assert result["implemented_count"]==1
    assert result["blocked_count"]==1

def test_implementation_absorption_uses_source_family_when_spec_is_absent(tmp_path, monkeypatch):
    import research.discovery.implementation_absorption as impl
    proof={"status":"PASS","absorbed":[{
        "candidate_id":"Q-3","source_id":"SRC-3","source_url":"https://example.test/c",
        "family":"mean_reversion","hypothesis_id":"mechanism_family","source_digest":"ghi"
    }]}
    pp=tmp_path/"proof.json"; out=tmp_path/"impl.json"
    pp.write_text(json.dumps(proof),encoding="utf-8")
    monkeypatch.setattr(impl,"PROOF",pp); monkeypatch.setattr(impl,"OUT",out)
    assert impl.main()==0
    result=json.loads(out.read_text())
    assert result["implemented_count"]==1
    assert result["implemented"][0]["family"]=="mean_reversion"
