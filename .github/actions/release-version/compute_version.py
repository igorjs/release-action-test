#!/usr/bin/env python3
"""Compute the next semantic version from commits since the last matching tag.

Needs a real git checkout with full tag history (actions/checkout with fetch-depth: 0),
unlike release-publishable and release-title-check, which only need the GitHub API.
Git tags and commit history are the source of truth for "what shipped", and a shallow
checkout would silently see fewer commits and fewer tags without failing.

Classification per commit, from its Conventional Commits type:
  major: '!' after the type/scope, or a 'BREAKING CHANGE:' footer
  minor: feat
  patch: fix, perf
  none:  everything else (chore, docs, style, test, build, ci, refactor, unlabeled)

The highest bump across all commits since the last tag wins. No commit that qualifies
means no release: this script only computes what the next version would be, the
caller decides whether to use it.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

COMMIT_HEADER = re.compile(r"^([a-z]+)(\([^)]+\))?(!)?:")
BREAKING_FOOTER = re.compile(r"^BREAKING CHANGE:", re.MULTILINE)

MINOR_TYPES = {"feat"}
PATCH_TYPES = {"fix", "perf"}


def run(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def last_tag(tag_prefix: str) -> str | None:
    try:
        return run(["git", "describe", "--tags", "--abbrev=0", "--match", f"{tag_prefix}*"])
    except subprocess.CalledProcessError:
        return None


def commits_since(tag: str | None) -> list[str]:
    range_arg = f"{tag}..HEAD" if tag else "HEAD"
    log = run(["git", "log", range_arg, "--format=%B%x00"])
    return [c for c in log.split("\x00") if c.strip()]


def classify(commit_body: str) -> str:
    first_line = commit_body.strip().splitlines()[0] if commit_body.strip() else ""
    match = COMMIT_HEADER.match(first_line)
    if not match:
        return "none"

    commit_type, _scope, breaking_marker = match.groups()
    if breaking_marker == "!" or BREAKING_FOOTER.search(commit_body):
        return "major"
    if commit_type in MINOR_TYPES:
        return "minor"
    if commit_type in PATCH_TYPES:
        return "patch"
    return "none"


def highest_bump(bumps: list[str]) -> str:
    for level in ("major", "minor", "patch"):
        if level in bumps:
            return level
    return "none"


def next_version(current: tuple[int, int, int], bump: str) -> tuple[int, int, int]:
    major, minor, patch = current
    if bump == "major":
        return (major + 1, 0, 0)
    if bump == "minor":
        return (major, minor + 1, 0)
    if bump == "patch":
        return (major, minor, patch + 1)
    return current


def parse_version(tag: str | None, tag_prefix: str) -> tuple[int, int, int]:
    if not tag:
        return (0, 0, 0)
    bare = tag[len(tag_prefix):] if tag.startswith(tag_prefix) else tag
    parts = bare.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ValueError(f"tag '{tag}' is not major.minor.patch after stripping the prefix")
    return tuple(int(p) for p in parts)  # type: ignore[return-value]


def write_github_output(path: str, bump: str, version: tuple[int, int, int], tag_prefix: str) -> None:
    version_str = ".".join(str(p) for p in version)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(f"bump={bump}\n")
        handle.write(f"version={version_str}\n")
        handle.write(f"tag={tag_prefix}{version_str}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag-prefix", required=True)
    parser.add_argument("--github-output", required=True)
    args = parser.parse_args()

    tag = last_tag(args.tag_prefix)
    try:
        current = parse_version(tag, args.tag_prefix)
    except ValueError as error:
        print(str(error))
        return 1

    commits = commits_since(tag)
    bumps = [classify(c) for c in commits]
    bump = highest_bump(bumps)
    version = next_version(current, bump)

    print(f"Last tag: {tag or '(none)'}")
    print(f"Commits since: {len(commits)}")
    print(f"Bump: {bump}")
    print(f"Next version: {'.'.join(str(p) for p in version)}")

    write_github_output(args.github_output, bump, version, args.tag_prefix)
    return 0


if __name__ == "__main__":
    sys.exit(main())
