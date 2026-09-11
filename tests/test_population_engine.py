from research.discovery.population_engine import classify, round1_source_quality, round2_feasibility, round3_diversity


def item(title, description="", source="github"):
    return {"source": source, "title": title, "description": description, "url": f"https://example.test/{title}", "lineage": {"rounds": []}}


def test_classifies_core_strategy_families():
    assert classify(item("Liquidity sweep ICT FVG crypto")) == "smc_ict"
    assert classify(item("Funding basis carry strategy")) == "funding_basis_carry"
    assert classify(item("Order book imbalance microprice")) == "order_flow"


def test_rounds_narrow_without_performance_selection():
    raw = [
        item("trend strategy", "momentum breakout"),
        item("funding strategy", "funding basis carry"),
        item("trend strategy", "momentum breakout"),
    ]
    r1 = round1_source_quality(raw)
    executable, deferred = round2_feasibility(r1)
    survivors = round3_diversity(executable)
    assert len(r1) == 2
    assert len(executable) == 1
    assert len(deferred) == 1
    assert len(survivors) == 1
    assert survivors[0]["family"] == "momentum_trend"
    assert all("decision" in r for r in survivors[0]["lineage"]["rounds"])
