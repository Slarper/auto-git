#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "python-dotenv>=1.1",
#   "httpx>=0.28",
# ]
# ///

"""git-sync-main.py — auto-commit with AI-generated message, pull, push."""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import httpx

load_dotenv()

# --- config from .env ---
AI_PROVIDER = os.getenv("AI_PROVIDER", "openrouter")
AI_MODEL = os.getenv("AI_MODEL", "deepseek/deepseek-v4-flash")
AI_API_KEY = os.getenv("AI_API_KEY", "")
GITHUB_PAT = os.getenv("GITHUB_PAT", "")
GIT_REMOTE = os.getenv("GIT_REMOTE", "origin")

PROVIDER_BASE = {
    "openrouter": "https://openrouter.ai",
}


def _git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True, check=check)
    return r.stdout.strip()


def _stage_all():
    _git("add", "-A")


def _get_diff() -> str | None:
    d = _git("diff", "--cached", check=False)
    if not d:
        d = _git("diff", check=False)
    return d or None


def _generate_message(diff: str) -> str:
    base = PROVIDER_BASE.get(AI_PROVIDER, AI_PROVIDER)
    url = f"{base.rstrip('/')}/api/v1/chat/completions"

    payload = {
        "model": AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You write concise git commit messages from a diff. "
                    "First line ≤72 characters, blank line, then optional body. "
                    "Output ONLY the commit message."
                ),
            },
            {"role": "user", "content": f"Commit message for:\n\n{diff}"},
        ],
        "max_tokens": 200,
        "temperature": 0.3,
    }

    resp = httpx.post(
        url,
        headers={
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"]["content"]
    if content is None or not content.strip():
        msg = "AI response content is empty. Check your model or API key."
        print(f"FATAL: {msg}", file=sys.stderr)
        sys.exit(1)
    return content.strip()


def commit() -> bool:
    _stage_all()
    diff = _get_diff()
    if not diff:
        print("Nothing to commit.", file=sys.stderr)
        return False

    print("Generating AI commit message ...")
    msg = _generate_message(diff)
    print(msg)
    _git("commit", "-m", msg)
    print("Committed.")
    return True


def _authed_remote_url() -> str | None:
    url = _git("remote", "get-url", GIT_REMOTE, check=False)
    if not url:
        return None
    if url.startswith("https://") and GITHUB_PAT:
        return url.replace("https://", f"https://{GITHUB_PAT}@", 1)
    return url


def _current_branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD")


def pull():
    print("Pulling & merging ...")
    _git("pull", GIT_REMOTE, _current_branch())
    print("Pull done.")


def push():
    print("Pushing ...")
    _git("push", GIT_REMOTE, _current_branch())
    print("Push done.")


def main():
    if not AI_API_KEY:
        print("FATAL: AI_API_KEY not set in .env", file=sys.stderr)
        sys.exit(1)

    os.chdir(_git("rev-parse", "--show-toplevel"))

    authed = _authed_remote_url()
    original = None
    if authed:
        original = _git("remote", "get-url", GIT_REMOTE)
        _git("remote", "set-url", GIT_REMOTE, authed)
    try:
        commit()
        pull()
        push()
    finally:
        if original:
            _git("remote", "set-url", GIT_REMOTE, original)


if __name__ == "__main__":
    main()
