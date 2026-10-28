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
- A marker that does not parse, or has fields of the wrong type, never counts
  as success, and is reported, not skipped.
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
UNREADABLE = "Codex review state is unreadable: re-run after Codex updates it"


def is_codex(user):
    user = user or {}
    return user.get("id") == CODEX_BOT_ID and user.get("type") == "Bot"


def names_head(sha, head):
    if not isinstance(sha, str) or len(sha) < 7:
        return False
    return head.lower().startswith(sha.lower())


def when(item):
    return item.get("updated_at") or item.get("created_at") or ""


def parse_marker(body):
    """Return (review, problem). review is None when the marker is unusable."""
    m = MARKER_RE.search(body)
    if not m:
        return None, "marker does not parse"
    try:
        data = json.loads(m.group(1))
    except ValueError as e:
        return None, f"marker is not JSON: {e}"
    review = data.get("code_review") if isinstance(data, dict) else None
    if not isinstance(review, dict):
        return None, "marker has no code_review object"
    status = review.get("status")
    sha = review.get("commit_sha")
    if not isinstance(status, str):
        return None, "marker status is not a string"
    if sha is not None and not isinstance(sha, str):
        return None, "marker commit_sha is not a string"
    return {"status": status, "commit_sha": sha or ""}, None


def receipt_names_head(body, head):
    r = RECEIPT_RE.search(body)
    return bool(r) and names_head(r.group(1), head)


def collect(comments, reviews, head):
    """Return (markers, legacy_on_head, warnings) from Codex comments/reviews."""
    markers = []
    legacy = False
    warnings = []
    for c in comments:
        if not is_codex(c.get("user")):
            continue
        body = c.get("body") or ""
        if "codex-review-state" in body:
            review, problem = parse_marker(body)
            if problem:
                warnings.append(f"comment {c.get('id')}: {problem}")
            markers.append((when(c), review))
        elif "codex-review-receipt" in body:
            legacy = legacy or receipt_names_head(body, head)
    for r in reviews:
        if is_codex(r.get("user")) and names_head(r.get("commit_id"), head):
            legacy = True
    return markers, legacy, warnings


def from_marker(review, head):
    short = head[:7]
    if review is None:
        return "pending", UNREADABLE
    status = review["status"]
    sha = review["commit_sha"]
    if names_head(sha, head) and status == "completed":
        return "success", f"Codex reviewed {short}"
    if names_head(sha, head):
        return "pending", f"Codex review of {short} is {status}"
    if sha:
        hint = "comment @codex review"
        return "pending", f"Codex last reviewed {sha[:7]}, not {short}: {hint}"
    return "pending", "Waiting for Codex to review this PR"


def decide(pr, comments, reviews):
    """Return (state, description, warnings) for the PR's head commit."""
    head = pr["head"]["sha"]
    if (pr.get("user") or {}).get("login") == "dependabot[bot]":
        return "success", "Dependabot PR: Codex skips dependency bumps", []
    markers, legacy, warnings = collect(comments, reviews, head)
    if pr.get("draft"):
        return "pending", "Draft: Codex reviews it once marked ready", warnings
    if markers:
        newest = max(markers, key=lambda m: m[0])[1]
        state, desc = from_marker(newest, head)
        return state, desc, warnings
    if legacy:
        return "success", f"Codex reviewed {head[:7]}", warnings
    return "pending", f"Waiting for a Codex review of {head[:7]}", warnings


def api(path):
    args = ["gh", "api", "--paginate", "--slurp", path]
    out = subprocess.run(args, check=True, capture_output=True, text=True)
    pages = json.loads(out.stdout)
    if pages and isinstance(pages[0], list):
        return [item for page in pages for item in page]
    return pages[0]


def post_status(repo, head, state, desc, url):
    args = ["gh", "api", "-X", "POST", f"repos/{repo}/statuses/{head}"]
    args += ["-f", f"state={state}", "-f", "context=codex-gate"]
    args += ["-f", f"description={desc[:140]}", "-f", f"target_url={url}"]
    subprocess.run(args, check=True, capture_output=True)


def main():
    repo = os.environ["REPO"]
    number = os.environ["PR"]
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
    post_status(repo, head, state, desc, pr["html_url"])
    print(f"{repo}#{number} {head[:7]}: {state} ({desc})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
