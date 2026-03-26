"""Git operations service — subprocess wrapper for clone, commit, push, ls-remote.

All operations use HTTPS + PAT authentication. PATs are embedded in the clone URL
and never written to disk config files or logged.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from pathlib import Path

import structlog

logger = structlog.get_logger(__name__)

_PAT_URL_RE = re.compile(r"(https?://)([^@]+)@")


def _redact_url(url: str) -> str:
    return _PAT_URL_RE.sub(r"\1***@", url)


def _build_auth_url(url: str, token: str) -> str:
    if "://" not in url:
        url = "https://" + url
    return url.replace("https://", f"https://{token}@")


def _run_git(
    args: list[str],
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    full_env = {**os.environ, **(env or {})}
    full_env["GIT_TERMINAL_PROMPT"] = "0"
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=full_env,
    )
    return result


def ls_remote(url: str, token: str) -> bool:
    auth_url = _build_auth_url(url, token)
    result = _run_git(["ls-remote", "--exit-code", auth_url], timeout=30)
    if result.returncode != 0:
        logger.warning(
            "git_ls_remote_failed",
            url=_redact_url(auth_url),
            stderr=result.stderr.strip(),
        )
        return False
    logger.info("git_ls_remote_success", url=_redact_url(auth_url))
    return True


def clone_repo(url: str, token: str, branch: str, dest: str | Path) -> bool:
    auth_url = _build_auth_url(url, token)
    result = _run_git(
        ["clone", "--branch", branch, "--single-branch", "--depth=1", auth_url, str(dest)],
        timeout=120,
    )
    if result.returncode != 0:
        if "not found" in result.stderr or "Could not find remote branch" in result.stderr:
            result = _run_git(["clone", auth_url, str(dest)], timeout=120)
            if result.returncode != 0:
                logger.error(
                    "git_clone_failed",
                    url=_redact_url(auth_url),
                    stderr=result.stderr.strip(),
                )
                raise RuntimeError(f"Git clone failed: {result.stderr.strip()}")
            _run_git(["checkout", "-b", branch], cwd=str(dest))
        else:
            logger.error(
                "git_clone_failed",
                url=_redact_url(auth_url),
                stderr=result.stderr.strip(),
            )
            raise RuntimeError(f"Git clone failed: {result.stderr.strip()}")
    logger.info("git_clone_success", url=_redact_url(auth_url), branch=branch)
    return True


def clone_or_init(url: str, token: str, branch: str, dest: str | Path) -> None:
    auth_url = _build_auth_url(url, token)
    result = _run_git(
        ["clone", "--branch", branch, "--single-branch", auth_url, str(dest)],
        timeout=120,
    )
    if result.returncode != 0:
        os.makedirs(dest, exist_ok=True)
        _run_git(["init"], cwd=str(dest))
        _run_git(["checkout", "-b", branch], cwd=str(dest))
        _run_git(["remote", "add", "origin", auth_url], cwd=str(dest))
        logger.info("git_init_new_repo", url=_redact_url(auth_url), branch=branch)
    else:
        logger.info("git_clone_success", url=_redact_url(auth_url), branch=branch)


def commit_and_push(
    repo_dir: str | Path,
    message: str,
    url: str,
    token: str,
    branch: str,
) -> tuple[str, int]:
    _run_git(["config", "user.email", "export@mcpworks.io"], cwd=str(repo_dir))
    _run_git(["config", "user.name", "MCPWorks Export"], cwd=str(repo_dir))

    _run_git(["add", "-A"], cwd=str(repo_dir))

    status = _run_git(["status", "--porcelain"], cwd=str(repo_dir))
    files_changed = len([l for l in status.stdout.strip().split("\n") if l.strip()])
    if files_changed == 0:
        logger.info("git_no_changes", message="Nothing to commit")
        head = _run_git(["rev-parse", "HEAD"], cwd=str(repo_dir))
        return head.stdout.strip(), 0

    result = _run_git(["commit", "-m", message], cwd=str(repo_dir))
    if result.returncode != 0:
        raise RuntimeError(f"Git commit failed: {result.stderr.strip()}")

    sha_result = _run_git(["rev-parse", "HEAD"], cwd=str(repo_dir))
    sha = sha_result.stdout.strip()

    auth_url = _build_auth_url(url, token)
    _run_git(["remote", "set-url", "origin", auth_url], cwd=str(repo_dir))

    push_result = _run_git(["push", "-u", "origin", branch], cwd=str(repo_dir), timeout=120)
    if push_result.returncode != 0:
        raise RuntimeError(f"Git push failed: {push_result.stderr.strip()}")

    logger.info(
        "git_push_success",
        url=_redact_url(auth_url),
        branch=branch,
        sha=sha[:12],
        files_changed=files_changed,
    )
    return sha, files_changed


def create_temp_dir() -> tempfile.TemporaryDirectory[str]:
    return tempfile.TemporaryDirectory(prefix="mcpworks-export-")
