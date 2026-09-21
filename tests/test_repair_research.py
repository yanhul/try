from research.repair_research import failure_signature, query_from_failure, run

def test_failure_signature_is_stable():
    f={"error":"ValueError: bad state","step":"controller","ci_failure_log_tail":"x"}
    assert failure_signature(f)==failure_signature(dict(f))

def test_query_excludes_noise():
    q=query_from_failure({"error":"ValueError provider_router malformed_candidate"})
    assert "valueerror" in q
    assert " error " not in f" {q} "

def test_research_budget_is_bounded(monkeypatch, tmp_path):
    import research.repair_research as rr
    rr.DIR=tmp_path/"repair_research"; rr.HISTORY=rr.DIR/"history"; rr.LATEST=rr.DIR/"latest.json"; rr.STATE=rr.DIR/"state.json"
    f={"error":"same failure signature","step":"controller","ci_failure_log_tail":"same"}
    monkeypatch.setattr(rr, "search_repositories", lambda q: [])
    first=run(f); second=run(f); third=run(f); fourth=run(f)
    assert first["status"]=="NO_EVIDENCE"
    assert second["status"]=="NO_EVIDENCE"
    assert third["status"]=="NO_EVIDENCE"
    assert fourth["status"]=="HOLD"

def test_research_is_evidence_only(monkeypatch, tmp_path):
    import research.repair_research as rr
    rr.DIR=tmp_path/"repair_research"; rr.HISTORY=rr.DIR/"history"; rr.LATEST=rr.DIR/"latest.json"; rr.STATE=rr.DIR/"state.json"
    monkeypatch.setattr(rr, "search_repositories", lambda q: [])
    result=run({"error":"repair needed","step":"controller"})
    assert result["status"]=="NO_EVIDENCE"
    assert "continue" not in result
    assert result["research_only"] is True

def test_history_attempts_are_distinct(monkeypatch, tmp_path):
    import research.repair_research as rr
    rr.DIR=tmp_path/"repair_research"; rr.HISTORY=rr.DIR/"history"; rr.LATEST=rr.DIR/"latest.json"; rr.STATE=rr.DIR/"state.json"
    monkeypatch.setattr(rr, "search_repositories", lambda q: [])
    monkeypatch.setenv("GITHUB_RUN_ID","fixed")
    f={"error":"immutable failure","step":"controller"}
    first=run(f); second=run(f)
    assert first["research_attempt_id"] != second["research_attempt_id"]
    assert len(list(rr.HISTORY.glob("*.json"))) == 2
