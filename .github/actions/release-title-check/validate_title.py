#!/usr/bin/env python3
"""Validate a pull request title against Conventional Commits, strictly.

Deliberately stricter than compute_version.py's commit classification: that script
treats an unrecognised type as "no release" rather than an error, because it reads a
merged history it cannot change. This script decides whether a PR is even allowed to
merge, so an unrecognised type, a missing colon, or a trailing period is a failure,
not a shrug.

Exits 0 on a valid title, 1 with a reason on stdout otherwise.
"""

from __future__ import annotations

import argparse
import re
import sys

TITLE_PATTERN = re.compile(r"^([a-z]+)(\([^)]+\))?(!)?: (.+)$")


def validate(title: str, known_types: set[str]) -> str | None:
    """Return a failure reason, or None when the title is valid."""
    title = title.strip()
    if not title:
        return "the title is empty"
    if title.endswith("."):
        return "the title ends with a period"

    match = TITLE_PATTERN.match(title)
    if not match:
        return "the title has no 'type: subject' or 'type(scope): subject' shape"

    commit_type, _scope, _breaking, subject = match.groups()
    if commit_type not in known_types:
        return f"'{commit_type}' is not a known type (expected one of: {', '.join(sorted(known_types))})"

    if subject != subject.strip():
        return "the subject has leading or trailing whitespace"
    if subject.isupper() and len(subject) > 1:
        return "the subject is all caps"

    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--title", required=True)
    parser.add_argument("--known-types", required=True)
    args = parser.parse_args()

    known_types = {t.strip() for t in args.known_types.split(",") if t.strip()}
    reason = validate(args.title, known_types)

    if reason is None:
        print(f"'{args.title}' is a valid Conventional Commits title.")
        return 0

    print(f"'{args.title}' is not a valid Conventional Commits title: {reason}.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
