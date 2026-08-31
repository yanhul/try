from dataclasses import dataclass


@dataclass(frozen=True)
class WalkForwardWindow:
    train_start: int
    train_end: int
    test_start: int
    test_end: int


def generate_walk_forward(
    n: int,
    train_size: int,
    test_size: int,
    step: int | None = None,
):
    if n <= 0 or train_size <= 0 or test_size <= 0:
        raise ValueError("sizes must be positive")

    if step is None:
        step = test_size

    if step <= 0:
        raise ValueError("step must be positive")

    windows = []
    start = 0

    while start + train_size + test_size <= n:
        train_end = start + train_size
        test_end = train_end + test_size

        windows.append(
            WalkForwardWindow(
                start,
                train_end,
                train_end,
                test_end,
            )
        )

        start += step

    if not windows:
        raise ValueError("dataset too small")

    return tuple(windows)
