import json
from pathlib import Path

from research.discovery.population_engine import classify, normalize, round2_feasibility


def test_china_a_share_classification_is_first_class():
    item = {
        "source": "github",
        "url": "https://github.com/example/a-share",
        "title": "A-share limit-up factor research",
        "description": "China A-share T+1 limit up cross-sectional factor backtest",
        "query": "China A-share limit-up strategy",
    }
    assert classify(item) == "china_a_share"
    normalized = normalize(item)
    assert normalized["family"] == "china_a_share"
    assert normalized["market"] == "CN_A_SHARE"


def test_china_a_share_is_executable_but_market_constraints_are_not_synthetic_data():
    item = normalize({
        "source": "github",
        "url": "https://github.com/example/a-share",
        "title": "China A-share factor model",
        "description": "A-share factor research with T+1 and limit-up rules",
        "query": "A-share factor research",
    })
    executable, deferred = round2_feasibility([item])
    assert len(executable) == 1
    assert not deferred
    assert executable[0]["family"] == "china_a_share"


def test_seed_contains_multiple_distinct_china_systems():
    path = Path("research/discovery/china_a_share_sources.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    sources = payload["sources"]
    assert len(sources) >= 8
    assert len({x["url"] for x in sources}) == len(sources)
    assert all(x["source"] == "github" for x in sources)
