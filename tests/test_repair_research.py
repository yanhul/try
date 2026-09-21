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


def test_research_source_uses_immutable_commit_and_run_id(monkeypatch, tmp_path):
    import research.repair_research as rr
    rr.DIR=tmp_path/"repair_research"; rr.HISTORY=rr.DIR/"history"; rr.LATEST=rr.DIR/"latest.json"; rr.STATE=rr.DIR/"state.json"
    monkeypatch.setattr(rr, "search_repositories", lambda q: [{"full_name":"example/repo","html_url":"https://github.com/example/repo","default_branch":"main","name":"repo","description":"x","stargazers_count":99}])
    monkeypatch.setattr(rr, "repository_head", lambda full, ref: "a"*40)
    monkeypatch.setattr(rr, "readme", lambda full, ref: "repair evidence")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    result=run({"error":"provider_router malformed_candidate","step":"controller","ci_failure_log_tail":"x"})
    assert result["status"]=="EVIDENCE_COLLECTED"
    assert result["sources"][0]["source_sha"]=="a"*40
    assert result["sources"][0]["source_immutable"] is True
    assert result["research_attempt_id"].endswith("-12345")
