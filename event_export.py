import csv
from pathlib import Path

from .backtest import load_bars
from .strategy import ReferenceStrategy


def export_events(data_path: str | Path, output_path: str | Path) -> int:
    bars = load_bars(data_path)
    events = ReferenceStrategy().process(bars)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow([
            "timestamp",
            "bar_index",
            "event_type",
            "direction",
            "price",
        ])

        for event in events:
            writer.writerow([
                event.timestamp.isoformat(),
                event.bar_index,
                event.event_type.value,
                event.direction.value,
                event.price,
            ])

    return len(events)
