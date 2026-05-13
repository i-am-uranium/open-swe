"""Utilities for extracting repository configuration from text."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

_DEFAULT_REPO_OWNER = os.environ.get("DEFAULT_REPO_OWNER", "langchain-ai")


def extract_repo_from_text(text: str, default_owner: str | None = None) -> dict[str, str] | None:
    """Extract owner/name repo config from text containing repo: syntax or GitHub URLs.

    Checks for explicit ``repo:owner/name`` or ``repo owner/name`` first, then
    falls back to GitHub URL extraction.

    Returns:
        A dict with ``owner`` and ``name`` keys, or ``None`` if no repo found.
    """
    if default_owner is None:
        default_owner = _DEFAULT_REPO_OWNER
    owner: str | None = None
    name: str | None = None

    if "repo:" in text or "repo " in text:
        match = re.search(r"repo[: ]([a-zA-Z0-9_.\-/]+)", text)
        if match:
            value = match.group(1).rstrip("/")
            if "/" in value:
                owner, name = value.split("/", 1)
            else:
                owner = default_owner
                name = value

    if not owner or not name:
        github_match = re.search(r"github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)", text)
        if github_match:
            owner, name = github_match.group(1).split("/", 1)

    if owner and name:
        return {"owner": owner, "name": name}
    return None


def extract_repos_from_text(text: str, default_owner: str | None = None) -> list[dict[str, str]]:
    """Extract all repo configs from explicit repo syntax and GitHub URLs."""
    if default_owner is None:
        default_owner = _DEFAULT_REPO_OWNER

    repos: list[dict[str, str]] = []

    for match in re.finditer(r"repo[: ]([a-zA-Z0-9_.\-/]+)", text):
        value = match.group(1).rstrip("/.,)")
        if "/" in value:
            owner, name = value.split("/", 1)
        else:
            owner, name = default_owner, value
        _append_repo_once(repos, {"owner": owner, "name": name})

    for owner, name in re.findall(r"github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+)", text):
        _append_repo_once(repos, {"owner": owner, "name": name})

    return repos


def build_linear_repo_plan(
    *,
    comment_body: str,
    issue: Mapping[str, Any],
    fallback_repo: dict[str, str],
    default_owner: str | None = None,
    label_repo_mapping: Mapping[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build an ordered repo execution plan for a Linear-triggered task."""
    if default_owner is None:
        default_owner = _DEFAULT_REPO_OWNER
    label_repo_mapping = label_repo_mapping or {}
    entries: list[dict[str, Any]] = []

    text_parts = [
        comment_body,
        str(issue.get("title") or ""),
        str(issue.get("description") or ""),
    ]
    comments = issue.get("comments")
    if isinstance(comments, Mapping):
        for comment in comments.get("nodes") or []:
            if isinstance(comment, Mapping):
                text_parts.append(str(comment.get("body") or ""))

    for repo in extract_repos_from_text("\n".join(text_parts), default_owner=default_owner):
        _append_plan_entry(
            entries,
            repo=repo,
            source="explicit",
            reason="mentioned in Linear context",
        )

    for label_name in _linear_label_names(issue):
        mapped_repo = label_repo_mapping.get(label_name.lower())
        if mapped_repo:
            _append_plan_entry(
                entries,
                repo=mapped_repo,
                source="linear_label",
                reason=f"Linear label {label_name}",
            )

    if not entries:
        _append_plan_entry(
            entries,
            repo=fallback_repo,
            source="fallback",
            reason="team/project/default mapping",
        )

    for index, entry in enumerate(entries):
        entry["execution_order"] = index

    return {
        "mode": "multi_repo" if len(entries) > 1 else "single_repo",
        "repos": entries,
    }


def _linear_label_names(issue: Mapping[str, Any]) -> list[str]:
    labels = issue.get("labels")
    if not isinstance(labels, Mapping):
        return []
    names: list[str] = []
    for label in labels.get("nodes") or []:
        if isinstance(label, Mapping):
            name = str(label.get("name") or "").strip()
            if name:
                names.append(name)
    return names


def _append_plan_entry(
    entries: list[dict[str, Any]], *, repo: dict[str, str], source: str, reason: str
) -> None:
    normalized = _normalize_repo(repo)
    if not normalized:
        return
    if any(_repo_key(entry["repo"]) == _repo_key(normalized) for entry in entries):
        return
    entries.append({"repo": normalized, "source": source, "reason": reason})


def _append_repo_once(repos: list[dict[str, str]], repo: dict[str, str]) -> None:
    normalized = _normalize_repo(repo)
    if not normalized:
        return
    if any(_repo_key(existing) == _repo_key(normalized) for existing in repos):
        return
    repos.append(normalized)


def _normalize_repo(repo: Mapping[str, str]) -> dict[str, str] | None:
    owner = str(repo.get("owner") or "").strip().strip("/")
    name = str(repo.get("name") or "").strip().strip("/")
    if not owner or not name:
        return None
    return {"owner": owner, "name": name}


def _repo_key(repo: Mapping[str, str]) -> str:
    return f"{repo.get('owner', '').lower()}/{repo.get('name', '').lower()}"
