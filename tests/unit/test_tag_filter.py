"""Unit tests for tag-based function filtering in tools/list."""


def filter_by_tags(
    functions_with_tags: list[tuple[str, list[str] | None]], tag_filter: set[str]
) -> list[str]:
    """Reproduce the filtering logic for testing.

    Args:
        functions_with_tags: List of (function_name, tags) tuples.
        tag_filter: Set of lowercase tag strings to match against.

    Returns:
        List of function names that match any tag in the filter.
    """
    if not tag_filter:
        return [name for name, _ in functions_with_tags]

    result = []
    for name, tags in functions_with_tags:
        if not tags:
            continue
        fn_tags = {t.lower() for t in tags}
        if fn_tags & tag_filter:
            result.append(name)
    return result


FUNCTIONS = [
    ("social.post-to-bluesky", ["bluesky", "social"]),
    ("social.scan-brave-mentions", ["monitoring", "social"]),
    ("social.engage-bluesky-feed", ["bluesky"]),
    ("social.send-discord-report", ["discord", "reporting"]),
    ("social.find-shareable-news", ["content", "social"]),
    ("monitor.check-api", ["monitoring", "health"]),
    ("monitor.canary", None),
]


class TestTagFilter:
    def test_single_tag_match(self):
        result = filter_by_tags(FUNCTIONS, {"bluesky"})
        assert result == ["social.post-to-bluesky", "social.engage-bluesky-feed"]

    def test_multi_tag_or_semantics(self):
        result = filter_by_tags(FUNCTIONS, {"bluesky", "discord"})
        assert "social.post-to-bluesky" in result
        assert "social.engage-bluesky-feed" in result
        assert "social.send-discord-report" in result
        assert len(result) == 3

    def test_no_filter_returns_all(self):
        result = filter_by_tags(FUNCTIONS, set())
        assert len(result) == len(FUNCTIONS)

    def test_nonexistent_tag_returns_empty(self):
        result = filter_by_tags(FUNCTIONS, {"nonexistent"})
        assert result == []

    def test_case_insensitive(self):
        mixed_case_fns = [
            ("social.post-to-bluesky", ["Bluesky", "Social"]),
            ("social.engage-bluesky-feed", ["BLUESKY"]),
            ("social.send-discord-report", ["Discord"]),
        ]
        result = filter_by_tags(mixed_case_fns, {"bluesky"})
        assert result == ["social.post-to-bluesky", "social.engage-bluesky-feed"]

    def test_function_with_no_tags_excluded(self):
        result = filter_by_tags(FUNCTIONS, {"monitoring"})
        assert "monitor.canary" not in result
        assert "social.scan-brave-mentions" in result
        assert "monitor.check-api" in result

    def test_function_with_multiple_matching_tags(self):
        result = filter_by_tags(FUNCTIONS, {"bluesky", "social"})
        assert "social.post-to-bluesky" in result
        assert len([r for r in result if r == "social.post-to-bluesky"]) == 1

    def test_broad_tag_returns_many(self):
        result = filter_by_tags(FUNCTIONS, {"social"})
        assert len(result) == 3


class TestTagParsing:
    def test_parse_comma_separated(self):
        raw = "bluesky,social,monitoring"
        tags = {t.strip().lower() for t in raw.split(",") if t.strip()}
        assert tags == {"bluesky", "social", "monitoring"}

    def test_parse_with_whitespace(self):
        raw = " bluesky , social , monitoring "
        tags = {t.strip().lower() for t in raw.split(",") if t.strip()}
        assert tags == {"bluesky", "social", "monitoring"}

    def test_parse_empty_string(self):
        raw = ""
        tags = {t.strip().lower() for t in raw.split(",") if t.strip()}
        assert tags == set()

    def test_parse_single_tag(self):
        raw = "bluesky"
        tags = {t.strip().lower() for t in raw.split(",") if t.strip()}
        assert tags == {"bluesky"}

    def test_parse_trailing_comma(self):
        raw = "bluesky,social,"
        tags = {t.strip().lower() for t in raw.split(",") if t.strip()}
        assert tags == {"bluesky", "social"}
