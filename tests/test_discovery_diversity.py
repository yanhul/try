from research.discovery.population_engine import round3_diversity
from research.provider_router import discovery_fingerprint


def item(family, title):
    return {
        "family": family,
        "title": title,
        "lineage": {"rounds": []},
    }


def test_round3_interleaves_families_deterministically():
    items = [
        item("mean_reversion", "mean-a"),
        item("mean_reversion", "mean-b"),
        item("smc_ict", "smc-a"),
        item("volatility", "vol-a"),
    ]
    out = round3_diversity(items)
    assert [(x["family"], x["title"]) for x in out] == [
        ("mean_reversion", "mean-a"),
        ("smc_ict", "smc-a"),
        ("volatility", "vol-a"),
        ("mean_reversion", "mean-b"),
    ]


def test_discovery_fingerprint_distinguishes_executable_variants():
    a = {"discovery_spec": {"operator": "zscore", "left": "close", "window": 20, "threshold": 2, "direction": "above"}}
    b = {"discovery_spec": {"operator": "zscore", "left": "close", "window": 50, "threshold": 2, "direction": "above"}}
    assert discovery_fingerprint(a) != discovery_fingerprint(b)
    assert discovery_fingerprint(a) == discovery_fingerprint(a)
