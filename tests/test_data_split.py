import pytest

from engine.data_split import chronological_split, validate_splits


def test_chronological_split():
    splits = chronological_split(100)

    assert [(s.name, s.start, s.end) for s in splits] == [
        ("IS", 0, 60),
        ("VALIDATION", 60, 80),
        ("OOS", 80, 100),
    ]


def test_no_overlap_or_gap():
    splits = chronological_split(1000)
    assert validate_splits(splits, 1000)


@pytest.mark.parametrize(
    "is_ratio,validation_ratio",
    [
        (0, 0.2),
        (1, 0.2),
        (0.6, 0),
        (0.6, 1),
        (0.8, 0.2),
        (0.7, 0.4),
    ],
)
def test_invalid_ratios(is_ratio, validation_ratio):
    with pytest.raises(ValueError):
        chronological_split(100, is_ratio, validation_ratio)


def test_small_dataset_rejected():
    with pytest.raises(ValueError):
        chronological_split(2)
