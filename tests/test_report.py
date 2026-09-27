from hermes_skill_drift.report import plain, render


def test_bidi_and_inline_newlines_are_visible_not_active():
    result = plain("safe\u202eevil\u2066\n# forged heading")
    assert "\u202e" not in result and "\u2066" not in result and "\n" not in result
    assert "\\u202e" in result and "\\u000a" in result
    assert plain("first\nsecond", multiline=True) == "first\nsecond"


def test_warning_groups_are_not_reported_as_broken_skills():
    report = {
        "status": "partial",
        "before_commit": "a" * 40,
        "after_commit": "b" * 40,
        "repo": "example",
        "coverage": {},
        "findings": [],
        "skill_changes_since_snapshot": [],
        "limitations": [],
        "warnings": [
            "before: tools/a.py: dynamic tool at line 4 is not statically resolvable",
            "after: tools/b.py: dynamic tool at line 9 is not statically resolvable",
        ],
    }
    result = render(report, "markdown")
    assert "2: dynamic tool" in result
    assert "not a count of broken skills" in result
    assert "tools/a.py" in result
