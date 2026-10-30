#!/usr/bin/env python3
"""Decide whether a push changed anything that should trigger a release.

Resolves the changed paths from the GitHub compare API (base_sha..head_sha), the same
approach platform/.baseline's prcheck-diff/resolve_diff.py uses for pull requests, so
this needs no deep checkout either.

A path is ignored when it matches a glob in the config file's "ignore" list (fnmatch,
the same matching minimatch's prototype used). Prints should_release=true/false on its
last line for the composite action's shell step to read, and exits 1 only when the
compare call itself fails: a missing or empty config is not an error, it just means
nothing is ignored.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PAGE_SIZE = 100
MAX_PAGES = 30

DEFAULT_IGNORE = ["**/*.md", ".github/**", "docs/**"]


def _get(url: str, token: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "release-publishable",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read())


def fetch_changed_paths(repository: str, base: str, head: str, token: str, api_url: str) -> list[str]:
    paths: list[str] = []
    for page in range(1, MAX_PAGES + 1):
        url = f"{api_url}/repos/{repository}/compare/{base}...{head}?per_page={PAGE_SIZE}&page={page}"
        batch = _get(url, token).get("files") or []
        paths.extend(entry["filename"] for entry in batch if entry.get("filename"))
        if len(batch) < PAGE_SIZE:
            break
    return paths


def load_ignore_globs(config_path: str) -> list[str]:
    path = Path(config_path)
    if not path.is_file():
        return DEFAULT_IGNORE
    data = json.loads(path.read_text())
    globs = data.get("ignore")
    if not isinstance(globs, list) or not globs:
        return DEFAULT_IGNORE
    return globs


def is_ignored(path: str, globs: list[str]) -> bool:
    """fnmatch has no '**' semantics of its own: '*' already crosses '/' for it, so a
    literal '/' in the pattern still has to be present in the path. A leading '**/' is
    meant to match zero directories as well as one or more, so try the glob both with
    and without that prefix."""
    for glob in globs:
        if fnmatch.fnmatch(path, glob):
            return True
        if glob.startswith("**/") and fnmatch.fnmatch(path, glob[3:]):
            return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--ignore-config", required=True)
    args = parser.parse_args()

    repository = os.environ.get("GITHUB_REPOSITORY", "")
    token = os.environ.get("GITHUB_TOKEN", "")
    api_url = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")

    try:
        paths = fetch_changed_paths(repository, args.base, args.head, token, api_url)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError) as error:
        print(f"could not resolve the diff: {error}")
        return 1

    globs = load_ignore_globs(args.ignore_config)
    publishable_paths = [p for p in paths if not is_ignored(p, globs)]

    print(f"Changed paths: {len(paths)}")
    for path in paths:
        tag = "ignored" if is_ignored(path, globs) else "publishable"
        print(f"  {tag}: {path}")

    should_release = len(publishable_paths) > 0
    print(f"should_release={str(should_release).lower()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
