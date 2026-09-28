#!/usr/bin/env python3
"""PreToolUse fence for unattended R&D runs (scripts/rnd/run.sh).

A no-op unless AIRA_AUTONOMOUS=1, so interactive sessions are untouched. When on, the agent
may read anything, write only inside its worktree (AIRA_RND_ROOT) and the report folder
(AIRA_RND_OUT), run read-only database queries, and read logs. Anything that could reach
customers, production or git history is denied: push, commit, deploys, infra CLIs, writes
through MCP, a local backend (its scheduler would message real leads), paid evals on a
client's key.
"""
import json
import os
import re
import sys

# A command in command position: start of line, or after ; & | ( or $( or `.
CMD = (
    r"(?:^|[;&|(`]\s*|\$\(\s*|\bxargs\s+|\bsh\s+-c\s+['\"]?)"
    r"(?:(?:npx|bunx|pnpm\s+dlx|yarn\s+dlx|env)\s+(?:-\S+\s+)*)?"  # npx vercel, env X=1 render
)
BASH_DENY = [
    (r"\bgit\s+(push|commit|merge|rebase|reset|revert|cherry-pick|tag|clean|am|apply|stash)\b", "git history/remote changes"),
    (r"\bgit\s+(checkout|switch)\s+(-b|-B|-c|-C)\b", "creating branches"),
    (CMD + r"gh\s+(?!(issue|pr|run)\s+(list|view|status)\b)", "GitHub writes (only gh issue/pr/run list|view allowed)"),
    (CMD + r"(vercel|render|supabase|psql|flyctl|heroku|terraform|kubectl)\b", "infrastructure CLIs"),
    (r"\bcurl\b.*(-X\s*(POST|PUT|PATCH|DELETE)|--data|\s-d\s|--form|\s-F\s)", "HTTP writes"),
    (r"\b(uvicorn|gunicorn)\b|\bapp\.main\b", "a local backend (its scheduler would message real leads)"),
    (r"\brm\s+-[a-zA-Z]*[rR]", "recursive deletes"),
    (CMD + r"(sudo|launchctl|crontab|osascript|security|pmset)\b", "system changes"),
    (r"(^|[\s/'\"])\.env(\s|$|['\"]|\.(?!example))|\.test-account\.json|\.aira-rnd/env", "reading secrets"),
]
EVAL_RE = re.compile(r"-m\s+evals\.")

READ_MCP = [
    r"^mcp__render__(list_\w+|get_\w+)$",
    r"^mcp__(claude_ai_)?[Ss]upabase__(list_tables|list_migrations|list_extensions|get_advisors|query_logs|search_docs|get_project_url)$",
]
SQL_TOOL = re.compile(r"^mcp__(claude_ai_)?[Ss]upabase__execute_sql$")
SQL_WRITE = re.compile(
    r"\b(insert|update|delete|merge|upsert|drop|alter|create|truncate|grant|revoke|copy|call|do|vacuum|"
    r"refresh|lock|comment|security|reindex|cluster|listen|notify|pg_\w*file\w*|lo_import|set\s+role)\b"
)
DENY_SKILLS = re.compile(r"(^|-)(ship|land-and-deploy|setup-deploy)$")
FILE_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def deny(reason: str) -> None:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": f"R&D fence: {reason}",
    }}))
    sys.exit(0)


def no_objection() -> None:
    """The fence only ever denies; everything else follows the session's normal rules."""
    print("{}")
    sys.exit(0)


def inside(path: str, roots: list[str]) -> bool:
    real = os.path.realpath(os.path.expanduser(path))
    return any(real == r or real.startswith(r + os.sep) for r in roots)


def read_only_sql(sql: str) -> bool:
    text = re.sub(r"--[^\n]*|/\*.*?\*/", " ", sql or "", flags=re.S).strip().lower()
    if ";" in text.rstrip(";"):
        return False  # one statement only
    return bool(re.match(r"^(select|with|explain|show)\b", text)) and not SQL_WRITE.search(text)


def main() -> None:
    if os.environ.get("AIRA_AUTONOMOUS") != "1":
        print("{}")
        return
    data = json.load(sys.stdin)
    tool = data.get("tool_name") or ""
    args = data.get("tool_input") or {}
    roots = [os.path.realpath(os.environ[k]) for k in ("AIRA_RND_ROOT", "AIRA_RND_OUT") if os.environ.get(k)]

    if tool == "Bash":
        cmd = args.get("command") or ""
        for pattern, why in BASH_DENY:
            if re.search(pattern, cmd, flags=re.M):
                deny(f"blocked {why}: {cmd[:120]}")
        if EVAL_RE.search(cmd) and "--test-key-tenant" not in cmd:
            deny("evals only with a test key tenant (--test-key-tenant)")
    elif tool in FILE_TOOLS:
        path = args.get("file_path") or args.get("notebook_path") or ""
        if not roots or not inside(path, roots):
            deny(f"writes are allowed only in the R&D worktree and report folder, not {path}")
    elif tool == "Skill":
        if DENY_SKILLS.search(args.get("skill") or ""):
            deny("ship/deploy skills are for a person only")
    elif tool.startswith("mcp__"):
        if SQL_TOOL.match(tool):
            if not read_only_sql(args.get("query") or ""):
                deny("only a single read-only SELECT/WITH/EXPLAIN query is allowed")
        elif not any(re.match(p, tool) for p in READ_MCP):
            deny(f"{tool} is not on the read-only tool list")
    no_objection()


if __name__ == "__main__":
    main()
