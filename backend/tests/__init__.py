"""Backend test suite.

A package rather than a bare directory so shared constants in ``conftest`` can
be imported by name. ``pytest.mark.parametrize`` needs them at module level,
where a fixture cannot reach.
"""
