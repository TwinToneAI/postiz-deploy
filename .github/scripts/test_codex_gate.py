"""Tests for codex_gate.decide (stdlib unittest)."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# The import must follow the sys.path insert above so the test finds the gate
# script next to it without packaging; hence E402 is suppressed on purpose.
from codex_gate import CODEX_BOT_ID, decide  # noqa: E402

HEAD = "a" * 40
OLD = "b" * 40
CODEX = {"id": CODEX_BOT_ID, "type": "Bot", "login": "chatgpt-codex-connector[bot]"}
IMPOSTOR = {"id": 42, "type": "User", "login": "untrusted-codex-user"}


def pr(**kw):
    base = {"head": {"sha": HEAD}, "user": {"login": "jamesrowdyy"}, "draft": False}
    base.update(kw)
    return base


def marker(status, sha, at="2026-10-28T10:00:00Z", user=CODEX, raw=None):
    payload = (
        raw
        if raw is not None
        else json.dumps({"code_review": {"status": status, "commit_sha": sha}})
    )
    return {
        "id": 1,
        "user": user,
        "updated_at": at,
        "created_at": at,
        "body": f"summary <!-- codex-review-state:v1 {payload} -->",
    }


def receipt(sha, at="2026-10-28T10:00:00Z", user=CODEX):
    return {
        "id": 2,
        "user": user,
        "created_at": at,
        "updated_at": at,
        "body": f"<!-- codex-review-receipt --> Reviewed commit: `{sha[:7]}`",
    }


def review(sha, at="2026-10-28T10:00:00Z", user=CODEX):
    return {"user": user, "commit_id": sha, "submitted_at": at}


class Decide(unittest.TestCase):
    def test_completed_marker_on_head_passes(self):
        self.assertEqual(decide(pr(), [marker("completed", HEAD)], [])[0], "success")

    def test_running_marker_is_not_overridden_by_newer_review(self):
        state, _, _ = decide(
            pr(),
            [marker("running", HEAD, at="2026-10-28T10:00:00Z")],
            [review(HEAD, at="2026-10-28T10:05:00Z")],
        )
        self.assertEqual(state, "pending")

    def test_running_marker_is_not_overridden_by_newer_receipt(self):
        comments = [
            marker("running", HEAD, at="2026-10-28T10:00:00Z"),
            receipt(HEAD, at="2026-10-28T10:05:00Z"),
        ]
        self.assertEqual(decide(pr(), comments, [])[0], "pending")

    def test_marker_on_older_commit_is_pending(self):
        self.assertEqual(
            decide(pr(), [marker("completed", OLD)], [review(HEAD)])[0], "pending"
        )

    def test_no_marker_receipt_for_head_passes_despite_newer_old_receipt(self):
        comments = [
            receipt(HEAD, at="2026-10-28T10:00:00Z"),
            receipt(OLD, at="2026-10-28T10:09:00Z"),
        ]
        self.assertEqual(decide(pr(), comments, [])[0], "success")

    def test_no_marker_review_for_head_passes_despite_newer_old_review(self):
        reviews = [
            review(HEAD, at="2026-10-28T10:00:00Z"),
            review(OLD, at="2026-10-28T10:09:00Z"),
        ]
        self.assertEqual(decide(pr(), [], reviews)[0], "success")

    def test_no_marker_only_old_evidence_is_pending(self):
        self.assertEqual(decide(pr(), [receipt(OLD)], [review(OLD)])[0], "pending")

    def test_impostor_signals_are_ignored(self):
        comments = [
            marker("completed", HEAD, user=IMPOSTOR),
            receipt(HEAD, user=IMPOSTOR),
        ]
        self.assertEqual(
            decide(pr(), comments, [review(HEAD, user=IMPOSTOR)])[0], "pending"
        )

    def test_malformed_marker_is_reported_and_blocks(self):
        state, desc, warnings = decide(
            pr(), [marker(None, None, raw="{not json}")], [review(HEAD)]
        )
        self.assertEqual(state, "pending")
        self.assertIn("unreadable", desc)
        self.assertTrue(warnings)

    def test_unparseable_marker_blocks_legacy_fallback(self):
        broken = {
            "id": 3,
            "user": CODEX,
            "updated_at": "2026-10-28T10:00:00Z",
            "body": "summary <!-- codex-review-state:v1 not-json-at-all -->",
        }
        state, _, warnings = decide(pr(), [broken, receipt(HEAD)], [review(HEAD)])
        self.assertEqual(state, "pending")
        self.assertTrue(warnings)

    def test_dependabot_passes(self):
        self.assertEqual(
            decide(pr(user={"login": "dependabot[bot]"}), [], [])[0], "success"
        )

    def test_draft_is_pending(self):
        self.assertEqual(
            decide(pr(draft=True), [marker("completed", HEAD)], [])[0], "pending"
        )

    def test_nothing_is_pending(self):
        self.assertEqual(decide(pr(), [], [])[0], "pending")


if __name__ == "__main__":
    unittest.main()
