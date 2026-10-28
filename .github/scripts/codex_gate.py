"""Codex merge gate (TWI2-2681): decide the `codex-gate` status for a PR head.

Run by .github/workflows/codex-gate.yml with GH_TOKEN, REPO and PR set.
Tests: .github/scripts/test_codex_gate.py (stdlib only).

Rules:
- Only the Codex connector app counts (account id 199175422, type Bot).
- Codex keeps one summary comment with a `codex-review-state:v1` marker that it
  edits in place. When that marker exists it is authoritative: success needs
  code_review.status == "completed" and code_review.commit_sha == the head.
  A newer review or receipt never overrides it.
- PRs whose summary predates the marker format have no marker. There, success
  needs a receipt comment or a submitted review that names the exact head.
  Evidence about other commits is ignored, so out-of-order completions cannot
  block or unblock the head.
- An unreadable marker never counts as success, and is reported, not skipped.
- Dependabot PRs pass: Codex does not review dependency bumps.
"""
from __future__ import annotations

import json
import os
import re
import subprocess

CODEX_BOT_ID = 199175422
MARKER_RE = re.compile(r"codex-review-state:v1 (\{.*?\}) -->", re.S)
RECEIPT_RE = re.compile(r"Reviewed commit:\**\s*`([0-9a-fA-F]{7,40})`")


def is_codex(user: dict | None) -> bool:
    user = user or {}
    return user.get("id") == CODEX_BOT_ID and user.get("type") == "Bot"


def names_head(sha: str, head: str) -> bool:
    return len(sha or "") >= 7 and head.lower().startswith(sha.lower())


def decide(pr: dict, comments: list, reviews: list) -> tuple[str, str, list]:
    """Return (state, description, warnings) for the PR's head commit."""
    head = pr["head"]["sha"]
    short = head[:7]
    warnings: list = []
    if (pr.get("user") or {}).get("login") == "dependabot[bot]":
        return "success", "Dependabot PR: Codex does not review dependency bumps", warnings

    markers, receipt_on_head = [], False
    for c in comments:
        if not is_codex(c.get("user")):
            continue
        body = c.get("body") or ""
        m = MARKER_RE.search(body)
        if m:
            try:
                review = json.loads(m.group(1)).get("code_review") or {}
            except ValueError as e:
                warnings.append(f"unreadable codex-review-state marker in comment {c.get('id')}: {e}")
                markers.append((c.get("updated_at") or c.get("created_at") or "", None))
                continue
            markers.append((c.get("updated_at") or c.get("created_at") or "", review))
        elif "codex-review-receipt" in body:
            r = RECEIPT_RE.search(body)
            if r and names_head(r.group(1), head):
                receipt_on_head = True
    review_on_head = any(is_codex(r.get("user")) and names_head(r.get("commit_id") or "", head)
                         for r in reviews)

    if pr.get("draft"):
        return "pending", "Draft: Codex reviews it once marked ready", warnings
    if markers:
        _, review = max(markers, key=lambda m: m[0])
        if review is None:
            return "pending", "Codex review state is unreadable: re-run after Codex updates it", warnings
        status, sha = review.get("status") or "none", review.get("commit_sha") or ""
        if status == "completed" and names_head(sha, head):
            return "success", f"Codex reviewed {short}", warnings
        if names_head(sha, head):
            return "pending", f"Codex review of {short} is {status}", warnings
        if sha:
            return "pending", f"Codex last reviewed {sha[:7]}, not {short}: comment @codex review", warnings
        return "pending", "Waiting for Codex to review this PR", warnings
    if receipt_on_head or review_on_head:
        return "success", f"Codex reviewed {short}", warnings
    return "pending", f"Waiting for a Codex review of {short}", warnings


def api(path: str):
    out = subprocess.run(["gh", "api", "--paginate", "--slurp", path], check=True,
                         capture_output=True, text=True).stdout
    pages = json.loads(out)
    if pages and isinstance(pages[0], list):
        return [item for page in pages for item in page]
    return pages[0]


def main() -> int:
    repo, number = os.environ["REPO"], os.environ["PR"]
    pr = api(f"repos/{repo}/pulls/{number}")
    if pr["state"] != "open":
        print(f"PR #{number} is {pr['state']}: nothing to do")
        return 0
    comments = api(f"repos/{repo}/issues/{number}/comments?per_page=100")
    reviews = api(f"repos/{repo}/pulls/{number}/reviews?per_page=100")
    state, desc, warnings = decide(pr, comments, reviews)
    for w in warnings:
        print(f"::warning::{w}")
    head = pr["head"]["sha"]
    subprocess.run(["gh", "api", "-X", "POST", f"repos/{repo}/statuses/{head}",
                    "-f", f"state={state}", "-f", "context=codex-gate",
                    "-f", f"description={desc[:140]}", "-f", f"target_url={pr['html_url']}"],
                   check=True, capture_output=True)
    print(f"{repo}#{number} {head[:7]}: {state} ({desc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
