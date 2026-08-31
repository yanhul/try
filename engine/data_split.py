from dataclasses import dataclass


@dataclass(frozen=True)
class DataSplit:
    name: str
    start: int
    end: int


def chronological_split(n: int, is_ratio=0.60, validation_ratio=0.20):
    if n < 3:
        raise ValueError("dataset too small")

    if not 0 < is_ratio < 1:
        raise ValueError("invalid IS ratio")

    if not 0 < validation_ratio < 1:
        raise ValueError("invalid validation ratio")

    if is_ratio + validation_ratio >= 1:
        raise ValueError("IS + validation must be < 1")

    is_end = int(n * is_ratio)
    validation_end = int(n * (is_ratio + validation_ratio))

    return (
        DataSplit("IS", 0, is_end),
        DataSplit("VALIDATION", is_end, validation_end),
        DataSplit("OOS", validation_end, n),
    )


def validate_splits(splits, n):
    if len(splits) != 3:
        raise ValueError("expected IS/VALIDATION/OOS")

    if splits[0].name != "IS":
        raise ValueError("first split must be IS")

    if splits[1].name != "VALIDATION":
        raise ValueError("second split must be VALIDATION")

    if splits[2].name != "OOS":
        raise ValueError("third split must be OOS")

    if splits[0].start != 0:
        raise ValueError("IS must start at zero")

    for left, right in zip(splits, splits[1:]):
        if left.end != right.start:
            raise ValueError("splits overlap or contain a gap")

    if splits[-1].end != n:
        raise ValueError("OOS must end at dataset boundary")

    if any(s.start < 0 or s.end > n or s.start >= s.end for s in splits):
        raise ValueError("invalid split bounds")

    return True
