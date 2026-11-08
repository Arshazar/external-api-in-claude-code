#!/usr/bin/env python3
"""Configure Claude Code for an external Anthropic-compatible API or gateway."""

import argparse
import copy
import getpass
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


OPENCODE_BASE_URLS = {
    "console": "https://opencode.ai/inference/anthropic",
    "go": "https://opencode.ai/inference/go/anthropic",
}
OPENCODE_DEFAULT_MODELS = {
    "opus": "claude-opus-5-5",
    "sonnet": "claude-sonnet-5-5",
    "haiku": "claude-haiku-5-5",
}


def settings_path():
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    return (Path(config_dir).expanduser() if config_dir else Path.home() / ".claude") / "settings.json"


def parse_settings(raw):
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Settings must be valid UTF-8 JSON; the file was not changed.") from exc
    if not isinstance(data, dict) or not isinstance(data.get("env", {}), dict):
        raise ValueError("Settings and its env field must be JSON objects; the file was not changed.")
    return data


def validate_base_url(value):
    try:
        parsed = urlsplit(value)
        _ = parsed.port  # Validate the optional port.
    except ValueError as exc:
        raise ValueError("Base URL must be a valid HTTP(S) URL.") from exc
    if (parsed.scheme not in ("http", "https") or not parsed.hostname
            or parsed.username is not None or parsed.password is not None
            or parsed.query or parsed.fragment or "?" in value or "#" in value
            or any(c.isspace() or ord(c) < 32 for c in value)):
        raise ValueError("Base URL must be HTTP(S), without credentials, query, fragment, or whitespace.")
    return value.rstrip("/")


def configure(data, key, provider="custom", model=None, *, base_url=None, auth="bearer", **aliases):
    endpoint = base_url or OPENCODE_BASE_URLS.get(provider)
    if not endpoint:
        raise ValueError("Supply --base-url (or EXTERNAL_API_BASE_URL) for a custom provider.")
    endpoint = validate_base_url(endpoint)
    if provider == "custom" and not model and not all(aliases.get(alias) for alias in OPENCODE_DEFAULT_MODELS):
        raise ValueError("Supply --model or all three model aliases for a custom provider.")
    result = copy.deepcopy(data)
    env = result.setdefault("env", {})
    env.update({
        "ANTHROPIC_BASE_URL": endpoint,
        "ANTHROPIC_AUTH_TOKEN": key if auth == "bearer" else "",
        "ANTHROPIC_API_KEY": key if auth == "api-key" else "",
        "CLAUDE_CODE_USE_BEDROCK": "",
        "CLAUDE_CODE_USE_VERTEX": "",
        "CLAUDE_CODE_USE_FOUNDRY": "",
    })
    defaults = OPENCODE_DEFAULT_MODELS if provider == "console" else dict.fromkeys(OPENCODE_DEFAULT_MODELS, "minimax-m3" if provider == "go" else None)
    for alias, default in defaults.items():
        env["ANTHROPIC_DEFAULT_" + alias.upper() + "_MODEL"] = aliases.get(alias) or model or default
    env["ANTHROPIC_MODEL"] = model or env["ANTHROPIC_DEFAULT_SONNET_MODEL"]
    # Older Claude Code releases use this variable for lightweight tasks.
    env["ANTHROPIC_SMALL_FAST_MODEL"] = env["ANTHROPIC_DEFAULT_HAIKU_MODEL"]
    return result


def atomic_write(path, raw):
    """Replace a file only after its complete replacement has been written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".external-api-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def backup(path, raw):
    fd, filename = tempfile.mkstemp(prefix=path.name + ".external-api-backup-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        os.unlink(filename)
        raise
    return Path(filename)


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("-k", "--key", help="Provider credential (prefer the hidden prompt or EXTERNAL_API_KEY)")
    result.add_argument("--base-url", help="Your provider's Anthropic-compatible base URL; otherwise EXTERNAL_API_BASE_URL or an interactive prompt")
    result.add_argument("--auth", choices=("bearer", "api-key"), default="bearer", help="Bearer token (default) or x-api-key header")
    result.add_argument("-m", "--model", help="Use this exact model ID for every model alias and the default")
    result.add_argument("--opus-model", dest="opus", help="Override the opus alias")
    result.add_argument("--sonnet-model", dest="sonnet", help="Override the sonnet alias")
    result.add_argument("--haiku-model", dest="haiku", help="Override the haiku/background alias")
    result.add_argument("--provider", choices=("custom", "console", "go"), default="custom", help="Custom endpoint (default), OpenCode Console, or OpenCode Go")
    result.add_argument("--settings", type=Path, help="Target settings.json (default: CLAUDE_CONFIG_DIR or ~/.claude)")
    result.add_argument("--dry-run", action="store_true", help="Preview managed values with credentials redacted; write nothing")
    result.add_argument("--restore", type=Path, metavar="BACKUP", help="Restore a complete settings backup, backing up current settings first")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        path = (args.settings or settings_path()).expanduser().resolve()
        original = path.read_bytes() if path.exists() else None
        if args.restore:
            if args.restore.expanduser().resolve() == path:
                raise ValueError("The restore source must differ from the settings file.")
            desired = args.restore.expanduser().read_bytes()
            parse_settings(desired)
            if args.dry_run:
                print("Would restore complete settings from {} to {} (no files written).".format(args.restore, path))
                return 0
        else:
            data = parse_settings(original) if original is not None else {}
            base_url = args.base_url or (os.environ.get("EXTERNAL_API_BASE_URL") if args.provider == "custom" else None)
            if args.provider == "custom":
                if not base_url and sys.stdin.isatty():
                    base_url = input("Your API base URL (omit /v1/messages): ").strip()
                if not base_url:
                    raise ValueError("Supply --base-url (or EXTERNAL_API_BASE_URL) when running non-interactively.")
                # Reject invalid endpoints before asking for a model or credential.
                base_url = validate_base_url(base_url)
                if not args.model and not all((args.opus, args.sonnet, args.haiku)) and sys.stdin.isatty():
                    args.model = input("Your API model ID (used for unspecified aliases): ").strip()
            options = dict(base_url=base_url, auth=args.auth, opus=args.opus, sonnet=args.sonnet, haiku=args.haiku)
            # Validate the endpoint and model mappings before requesting credentials.
            configure({}, "", args.provider, args.model, **options)
            key = args.key if args.key is not None else os.environ.get("EXTERNAL_API_KEY")
            if key is None and args.provider in OPENCODE_BASE_URLS:
                key = os.environ.get("OPENCODE_API_KEY")
            if key is None:
                if not sys.stdin.isatty():
                    raise ValueError("Supply EXTERNAL_API_KEY or --key when running non-interactively (OPENCODE_API_KEY also works for console/go).")
                key = getpass.getpass("External API key (hidden): ")
            if not key or any(char.isspace() for char in key) or not key.isascii():
                raise ValueError("API key must be nonempty ASCII without whitespace.")
            for model in (args.model, args.opus, args.sonnet, args.haiku):
                if model is not None and (not model or any(c.isspace() for c in model)):
                    raise ValueError("Use exact model IDs without whitespace.")
            updated = configure(data, key, args.provider, args.model, **options)
            desired = (json.dumps(updated, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
            if args.dry_run:
                # Preview only the entries we manage; unrelated settings may hold other secrets.
                preview = configure({}, "<redacted>", args.provider, args.model, **options)
                print("Would configure {} (no files written):".format(path))
                print(json.dumps(preview, indent=2))
                return 0
        if desired == original:
            print("Settings already match: {}".format(path))
            return 0
        if original is not None:
            print("Backup: {}".format(backup(path, original)))
        atomic_write(path, desired)
        print("{}: {}".format("Restored settings" if args.restore else "Configured external API", path))
        if not args.restore:
            print("Follow your provider's login instructions; OpenCode requires /logout if signed in to Claude.")
            print("Restart Claude Code or reload your IDE, then use /status to verify the base URL and token.")
        return 0
    except (OSError, ValueError, EOFError) as exc:
        print("Error: {}".format(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
