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
    service_catalog: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an ordered repo execution plan for a Linear-triggered task."""
    if default_owner is None:
        default_owner = _DEFAULT_REPO_OWNER
    label_repo_mapping = label_repo_mapping or {}
    service_catalog = service_catalog or {}
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

    for catalog_entry in _infer_catalog_entries(
        comment_body=comment_body,
        issue=issue,
        service_catalog=service_catalog,
        default_owner=default_owner,
    ):
        _append_plan_entry(
            entries,
            repo=catalog_entry["repo"],
            source=catalog_entry["source"],
            reason=catalog_entry["reason"],
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


def _infer_catalog_entries(
    *,
    comment_body: str,
    issue: Mapping[str, Any],
    service_catalog: Mapping[str, Any],
    default_owner: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    if not service_catalog:
        return entries

    label_names = {label.lower() for label in _linear_label_names(issue)}
    context_text = _issue_context_text(comment_body, issue)

    for repo_entry in _iter_catalog_repo_entries(service_catalog, default_owner):
        label_matches = sorted(label_names & repo_entry["linear_labels"])
        for label_name in label_matches:
            _append_catalog_entry(
                entries,
                repo=repo_entry["repo"],
                source="service_catalog_label",
                reason=f"service catalog label {label_name}",
            )
            break

        if any(_text_contains_phrase(context_text, alias) for alias in repo_entry["aliases"]):
            _append_catalog_entry(
                entries,
                repo=repo_entry["repo"],
                source="service_catalog_text",
                reason=f"service catalog alias {repo_entry['name']}",
            )

    for group_entry in _iter_catalog_group_entries(service_catalog, default_owner):
        if any(_text_contains_phrase(context_text, alias) for alias in group_entry["aliases"]):
            for repo in group_entry["repos"]:
                _append_catalog_entry(
                    entries,
                    repo=repo,
                    source="service_catalog_group",
                    reason=f"service catalog group {group_entry['name']}",
                )

    return entries


def _iter_catalog_repo_entries(
    service_catalog: Mapping[str, Any], default_owner: str
) -> list[dict[str, Any]]:
    raw_entries: list[Any] = []
    for key in ("repos", "services"):
        value = service_catalog.get(key)
        if isinstance(value, list):
            raw_entries.extend(value)

    entries: list[dict[str, Any]] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, Mapping):
            continue

        repo = _coerce_catalog_repo(raw_entry.get("repo"), default_owner)
        if not repo:
            owner = raw_entry.get("owner")
            name = raw_entry.get("name")
            if owner and name:
                repo = _normalize_repo({"owner": str(owner), "name": str(name)})
        if not repo:
            continue

        name = str(raw_entry.get("name") or repo["name"]).strip()
        aliases = _catalog_terms(
            raw_entry.get("aliases"),
            raw_entry.get("keywords"),
            raw_entry.get("domains"),
            [name, repo["name"]],
        )
        labels = _catalog_terms(raw_entry.get("linear_labels"), raw_entry.get("labels"))
        entries.append(
            {
                "repo": repo,
                "name": name,
                "aliases": aliases,
                "linear_labels": {label.lower() for label in labels},
            }
        )
    return entries


def _iter_catalog_group_entries(
    service_catalog: Mapping[str, Any], default_owner: str
) -> list[dict[str, Any]]:
    raw_groups = service_catalog.get("groups")
    if not isinstance(raw_groups, list):
        return []

    groups: list[dict[str, Any]] = []
    for raw_group in raw_groups:
        if not isinstance(raw_group, Mapping):
            continue
        raw_repos = raw_group.get("repos")
        if not isinstance(raw_repos, list):
            continue
        repos = [
            repo
            for repo in (_coerce_catalog_repo(raw_repo, default_owner) for raw_repo in raw_repos)
            if repo
        ]
        if not repos:
            continue
        name = str(raw_group.get("name") or "").strip()
        aliases = _catalog_terms(raw_group.get("aliases"), raw_group.get("keywords"), [name])
        groups.append({"name": name or "unnamed", "aliases": aliases, "repos": repos})
    return groups


def _issue_context_text(comment_body: str, issue: Mapping[str, Any]) -> str:
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
    return "\n".join(text_parts)


def _catalog_terms(*values: Any) -> list[str]:
    terms: list[str] = []
    for value in values:
        if isinstance(value, str):
            _append_term_once(terms, value)
        elif isinstance(value, list | tuple | set):
            for item in value:
                if isinstance(item, str):
                    _append_term_once(terms, item)
    return terms


def _append_term_once(terms: list[str], value: str) -> None:
    term = value.strip().lower()
    if term and term not in terms:
        terms.append(term)


def _text_contains_phrase(text: str, phrase: str) -> bool:
    phrase = phrase.strip().lower()
    if not phrase:
        return False
    escaped = re.escape(phrase).replace(r"\ ", r"[\s_-]+")
    return re.search(rf"(?<![a-z0-9]){escaped}(?![a-z0-9])", text.lower()) is not None


def _coerce_catalog_repo(value: Any, default_owner: str) -> dict[str, str] | None:
    if isinstance(value, Mapping):
        return _normalize_repo(
            {"owner": str(value.get("owner") or ""), "name": str(value.get("name") or "")}
        )
    if isinstance(value, str):
        repo_value = value.strip()
        if not repo_value:
            return None
        if "/" in repo_value:
            owner, name = repo_value.split("/", 1)
        else:
            owner, name = default_owner, repo_value
        return _normalize_repo({"owner": owner, "name": name})
    return None


def _append_catalog_entry(
    entries: list[dict[str, Any]], *, repo: dict[str, str], source: str, reason: str
) -> None:
    if any(_repo_key(entry["repo"]) == _repo_key(repo) for entry in entries):
        return
    entries.append({"repo": repo, "source": source, "reason": reason})


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
