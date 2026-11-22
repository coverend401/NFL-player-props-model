"""Pin archive UI regressions independently of the changing live research slate."""

from contextlib import contextmanager
from datetime import UTC, datetime
from unittest.mock import patch


@contextmanager
def archived_week11():
    from research_platform.inference_release import resolve_research_release

    def resolve(root):
        return resolve_research_release(
            root, pointer="tests/fixtures/week11_research_pointer.json"
        )

    with (
        patch.dict(
            "os.environ",
            {
                "NFL_RESEARCH_INFERENCE_POINTER": "tests/fixtures/week11_research_pointer.json"
            },
        ),
        patch(
            "research_platform.inference_release.resolve_research_release",
            side_effect=resolve,
        ),
        patch("research_platform.r8.datetime") as clock,
        patch("research_platform.sunday_script_ui.datetime") as script_clock,
        patch("research_platform.enhanced_ui.datetime") as enhanced_clock,
        # Archived component tests exercise rendering, not live admission. The
        # unmocked real-entrypoint fail-closed test is test_selection_integrity.
        patch("research_platform.selection_integrity.block_reason", return_value=None),
    ):
        clock.now.return_value = datetime(2026, 11, 20, 23, tzinfo=UTC)
        script_clock.now.return_value = datetime(2026, 11, 20, 23, tzinfo=UTC)
        enhanced_clock.now.return_value = datetime(2026, 11, 22, 8, tzinfo=UTC)
        yield
