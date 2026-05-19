"""Unit tests for the pure helpers in modules/badges.py."""
import pytest

from modules.badges import DIFFICULTY_PLACEHOLDERS, points_to_difficulty


@pytest.mark.parametrize('points,expected_idx', [
    # below / at-zero bucket
    (-5, 0), (-1, 0), (0, 0),
    # normal (1-2)
    (1, 1), (2, 1),
    # hard (3-4)
    (3, 2), (4, 2),
    # insane (5-7)
    (5, 3), (6, 3), (7, 3),
    # extreme (8-10)
    (8, 4), (9, 4), (10, 4),
    # brutal (11-13)
    (11, 5), (12, 5), (13, 5),
    # maso (14-17)
    (14, 6), (15, 6), (17, 6),
    # legendary (18-23)
    (18, 7), (20, 7), (23, 7),
    # godlike (24+)
    (24, 8), (50, 8), (1000, 8),
])
def test_points_to_difficulty(points, expected_idx):
    assert points_to_difficulty(points) == expected_idx


def test_difficulty_placeholders_has_nine_entries():
    # Indexed by points_to_difficulty(), which can return 0..8 -> 9 buckets.
    assert len(DIFFICULTY_PLACEHOLDERS) == 9


def test_every_difficulty_index_has_a_placeholder():
    # Sanity: for any point value, the index is a valid placeholder lookup.
    for p in range(-3, 30):
        assert DIFFICULTY_PLACEHOLDERS[points_to_difficulty(p)]
