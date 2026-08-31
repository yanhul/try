import pytest

from engine.walk_forward import generate_walk_forward


def test_walk_forward_non_overlapping_test_windows():
    windows = generate_walk_forward(100, 60, 20)

    assert windows[0].train_start == 0
    assert windows[0].train_end == 60
    assert windows[0].test_start == 60
    assert windows[0].test_end == 80

    assert windows[1].train_start == 20
    assert windows[1].train_end == 80
    assert windows[1].test_start == 80
    assert windows[1].test_end == 100


def test_expanding_step():
    windows = generate_walk_forward(100, 40, 20, step=20)

    assert windows[-1].test_end == 100


@pytest.mark.parametrize(
    "n,train,test",
    [
        (0, 10, 5),
        (100, 0, 5),
        (100, 10, 0),
        (10, 10, 5),
    ],
)
def test_invalid_windows(n, train, test):
    with pytest.raises(ValueError):
        generate_walk_forward(n, train, test)


def test_invalid_step():
    with pytest.raises(ValueError):
        generate_walk_forward(100, 50, 20, step=0)
