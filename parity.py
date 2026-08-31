import csv
from dataclasses import dataclass
from pathlib import Path


PARITY_COLUMNS = {
    "timestamp",
    "bar_index",
    "event_type",
    "direction",
    "price",
}


@dataclass(frozen=True)
class ParityEvent:
    timestamp: str
    bar_index: int
    event_type: str
    direction: str
    price: float


def load_events(path: str | Path) -> list[ParityEvent]:
    path = Path(path)

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        missing = PARITY_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise ValueError(
                "missing parity columns: "
                + ", ".join(sorted(missing))
            )

        events = []

        for row_number, row in enumerate(reader, start=2):
            try:
                events.append(
                    ParityEvent(
                        timestamp=row["timestamp"],
                        bar_index=int(row["bar_index"]),
                        event_type=row["event_type"],
                        direction=row["direction"],
                        price=float(row["price"]),
                    )
                )
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"invalid parity event at CSV row {row_number}"
                ) from exc

    return events


def compare_events(
    reference: list[ParityEvent],
    candidate: list[ParityEvent],
    *,
    price_tolerance: float = 0.0,
) -> list[dict]:
    differences = []

    count = max(len(reference), len(candidate))

    for i in range(count):
        ref = reference[i] if i < len(reference) else None
        cand = candidate[i] if i < len(candidate) else None

        if ref is None:
            differences.append(
                {
                    "index": i,
                    "type": "EXTRA_CANDIDATE_EVENT",
                    "candidate": cand,
                }
            )
            continue

        if cand is None:
            differences.append(
                {
                    "index": i,
                    "type": "MISSING_CANDIDATE_EVENT",
                    "reference": ref,
                }
            )
            continue

        fields = (
            "timestamp",
            "bar_index",
            "event_type",
            "direction",
        )

        for field in fields:
            ref_value = getattr(ref, field)
            cand_value = getattr(cand, field)

            if ref_value != cand_value:
                differences.append(
                    {
                        "index": i,
                        "type": "FIELD_MISMATCH",
                        "field": field,
                        "reference": ref_value,
                        "candidate": cand_value,
                    }
                )

        if abs(ref.price - cand.price) > price_tolerance:
            differences.append(
                {
                    "index": i,
                    "type": "FIELD_MISMATCH",
                    "field": "price",
                    "reference": ref.price,
                    "candidate": cand.price,
                    "tolerance": price_tolerance,
                }
            )

    return differences
