"""Unit tests for the Learning-feed keyword filter (proposal 003)."""

from src.services.learning_filter import is_learning_content


class TestIsLearningContent:
    def test_matches_agent_keyword_in_title(self):
        assert is_learning_content("New autonomous coding agent released", "")

    def test_matches_mcp_keyword(self):
        assert is_learning_content(
            "A new MCP server for your dev workflow", ""
        )

    def test_matches_claude_code_in_content_only(self):
        assert is_learning_content(
            "Weekly roundup", "This week's highlight: Claude Code skills."
        )

    def test_matches_case_insensitively(self):
        assert is_learning_content("AGENTIC WORKFLOWS ARE HERE", "")

    def test_does_not_match_generic_ai_news(self):
        assert not is_learning_content(
            "OpenAI raises new funding round",
            "The company announced a new valuation today.",
        )

    def test_does_not_match_unrelated_tech_news(self):
        assert not is_learning_content(
            "Stock market rally continues", "Tech stocks rose today."
        )

    def test_empty_title_and_content_does_not_match(self):
        assert not is_learning_content("", "")

    def test_none_content_does_not_crash(self):
        assert not is_learning_content("Just a title", None)  # type: ignore[arg-type]

    def test_substring_does_not_false_positive(self):
        # "agent" should not spuriously match words that merely contain
        # similar letters (guards against overly loose regex).
        assert not is_learning_content("Real estate agentry conference", "")
