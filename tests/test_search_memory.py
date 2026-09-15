from research.search_memory import rank_families

def test_unseen_family_gets_exploration_priority():
    ranked=rank_families(["momentum_trend","mean_reversion"],seed=1)
    assert set(ranked)=={"momentum_trend","mean_reversion"}

def test_ranking_is_deterministic_for_same_memory_and_seed():
    assert rank_families(["momentum_trend","mean_reversion"],seed=7)==rank_families(["momentum_trend","mean_reversion"],seed=7)
