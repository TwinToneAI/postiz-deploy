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
T0 = "2026-10-28T10:00:00Z"
T1 = "2026-10-28T10:05:00Z"
BOT = "chatgpt-codex-connector[bot]"
CODEX = {"id": CODEX_BOT_ID, "type": "Bot", "login": BOT}
IMPOSTOR = {"id": 42, "type": "User", "login": "untrusted-codex-user"}
BAD_TYPES = [
    '{"code_review": ["completed"]}',
    "[1, 2]",
    '{"code_review": {"status": 1, "commit_sha": "x"}}',
    '{"code_review": {"status": "completed", "commit_sha": 7}}',
]


def pr(**kw):
    base = {"head": {"sha": HEAD}, "user": {"login": "jamesrowdyy"}}
    base["draft"] = False
    base.update(kw)
    return base


def raw_marker(payload, at=T0, user=CODEX):
    body = f"summary <!-- codex-review-state:v1 {payload} -->"
    return {"id": 1, "user": user, "updated_at": at, "body": body}


def marker(status, sha, at=T0, user=CODEX):
    review = {"status": status, "commit_sha": sha}
    return raw_marker(json.dumps({"code_review": review}), at, user)


def receipt(sha, at=T0, user=CODEX):
    body = f"<!-- codex-review-receipt --> Reviewed commit: `{sha[:7]}`"
    return {"id": 2, "user": user, "updated_at": at, "body": body}


def review(sha, at=T0, user=CODEX):
    return {"user": user, "commit_id": sha, "submitted_at": at}


def state_of(comments, reviews=(), **kw):
    return decide(pr(**kw), list(comments), list(reviews))[0]


class Decide(unittest.TestCase):
    def test_completed_marker_on_head_passes(self):
        self.assertEqual(state_of([marker("completed", HEAD)]), "success")

    def test_running_marker_beats_newer_review(self):
        comments = [marker("running", HEAD, at=T0)]
        reviews = [review(HEAD, at=T1)]
        self.assertEqual(state_of(comments, reviews), "pending")

    def test_running_marker_beats_newer_receipt(self):
        comments = [marker("running", HEAD, at=T0), receipt(HEAD, at=T1)]
        self.assertEqual(state_of(comments), "pending")

    def test_marker_on_older_commit_is_pending(self):
        comments = [marker("completed", OLD)]
        self.assertEqual(state_of(comments, [review(HEAD)]), "pending")

    def test_head_receipt_wins_over_newer_old_receipt(self):
        comments = [receipt(HEAD, at=T0), receipt(OLD, at=T1)]
        self.assertEqual(state_of(comments), "success")

    def test_head_review_wins_over_newer_old_review(self):
        reviews = [review(HEAD, at=T0), review(OLD, at=T1)]
        self.assertEqual(state_of([], reviews), "success")

    def test_only_old_evidence_is_pending(self):
        self.assertEqual(state_of([receipt(OLD)], [review(OLD)]), "pending")

    def test_impostor_signals_are_ignored(self):
        fake = [marker("completed", HEAD, user=IMPOSTOR)]
        fake.append(receipt(HEAD, user=IMPOSTOR))
        reviews = [review(HEAD, user=IMPOSTOR)]
        self.assertEqual(state_of(fake, reviews), "pending")

    def test_malformed_marker_is_reported_and_blocks(self):
        comments = [raw_marker("{not json}")]
        state, desc, warnings = decide(pr(), comments, [review(HEAD)])
        self.assertEqual(state, "pending")
        self.assertIn("unreadable", desc)
        self.assertTrue(warnings)

    def test_unparseable_marker_blocks_legacy_fallback(self):
        comments = [raw_marker("not-json-at-all"), receipt(HEAD)]
        state, _, warnings = decide(pr(), comments, [review(HEAD)])
        self.assertEqual(state, "pending")
        self.assertTrue(warnings)

    def test_wrong_field_types_block(self):
        for payload in BAD_TYPES:
            with self.subTest(payload=payload):
                comments = [raw_marker(payload)]
                state, _, warnings = decide(pr(), comments, [review(HEAD)])
                self.assertEqual(state, "pending")
                self.assertTrue(warnings)

    def test_dependabot_passes(self):
        bot = {"login": "dependabot[bot]"}
        self.assertEqual(state_of([], user=bot), "success")

    def test_draft_is_pending(self):
        comments = [marker("completed", HEAD)]
        self.assertEqual(state_of(comments, draft=True), "pending")

    def test_nothing_is_pending(self):
        self.assertEqual(state_of([]), "pending")


if __name__ == "__main__":
    unittest.main()
