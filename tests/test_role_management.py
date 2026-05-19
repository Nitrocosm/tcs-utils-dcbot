"""Unit tests for the pure helpers in modules/role_management.py."""
import textwrap

from modules.role_management import _parse_relations_from_text


def test_parse_relations_single_parent_with_children():
    content = textwrap.dedent('''\
        - <@&123>
            - <@&456>
            - <@&789>
    ''')
    assert _parse_relations_from_text(content) == {123: [456, 789]}


def test_parse_relations_multiple_parents():
    content = textwrap.dedent('''\
        - <@&100>
            - <@&101>
        - <@&200>
            - <@&201>
            - <@&202>
    ''')
    assert _parse_relations_from_text(content) == {
        100: [101],
        200: [201, 202],
    }


def test_parse_relations_empty():
    assert _parse_relations_from_text('') == {}


def test_parse_relations_blank_lines_dont_reset():
    content = textwrap.dedent('''\
        - <@&100>

            - <@&101>
    ''')
    # blank lines are skipped; current_parent stays set; child still attaches
    assert _parse_relations_from_text(content) == {100: [101]}


def test_parse_relations_comment_resets_context():
    content = textwrap.dedent('''\
        - <@&100>
            - <@&101>
        this is a comment
            - <@&999>
    ''')
    # non-empty non-bullet line resets current_parent so the dangling child
    # belongs to no one and is dropped
    assert _parse_relations_from_text(content) == {100: [101]}


def test_parse_relations_parent_without_children():
    content = textwrap.dedent('''\
        - <@&42>
    ''')
    # known parent, zero children -> still present with empty list
    assert _parse_relations_from_text(content) == {42: []}
