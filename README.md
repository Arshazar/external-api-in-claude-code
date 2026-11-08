# External APIs in Claude Code

Configure Claude Code to use an external API or gateway on **macOS, Linux, and
Windows**. Supply your provider's base URL, credential, and model IDs. The tool
supports **Agent Router (AgentRouter)**, **OpenCode**, and other services that
expose an Anthropic-compatible endpoint.

Claude Code sends Anthropic Messages requests, including streaming and tool
calls. An OpenAI-only or other incompatible API needs a gateway that translates
these requests and responses. This tool configures Claude Code; it does not
translate API protocols or run a proxy. See Claude Code's
[gateway compatibility guide](https://code.claude.com/docs/en/llm-gateway-protocol).

## Setup

Requires **Python 3.9+**, Claude Code, and a credential for your provider. No
Python packages are needed. Close Claude Code before changing its settings.

### macOS and Linux

```bash
bash setup-external-api.sh --base-url https://gateway.example.com --model your-model-id
```

### Windows (PowerShell)

```powershell
.\setup-external-api.ps1 --base-url https://gateway.example.com --model your-model-id
```

If PowerShell blocks local scripts, use Python directly:

```powershell
py -3 .\setup_external_api.py --base-url https://gateway.example.com --model your-model-id
```

All entry points use the same implementation and accept identical options.
Setup prompts for your credential without displaying it. For unattended use,
set `EXTERNAL_API_KEY`; command-line `--key` values may be saved in shell
history or visible in process listings.

Use the provider's documented **Claude Code base URL**, leaving off
`/v1/messages`. Choose exact model IDs available to your account. `--model`
sets the startup model and all three model aliases; individual overrides let
you select different models for different tasks.

Restart Claude Code after setup. In an IDE, use **Developer: Reload Window**.
Run `/status` in Claude Code to check the endpoint and authentication.

## Provider examples

### Any compatible external API

```bash
# Bearer authentication (the default); prompts for the credential
bash setup-external-api.sh --base-url https://gateway.example.com --model your-model-id

# For a provider that requires an x-api-key header
bash setup-external-api.sh --base-url https://gateway.example.com --model your-model-id --auth api-key

# Preview settings without writing; credentials are redacted
bash setup-external-api.sh --base-url https://gateway.example.com --model your-model-id --dry-run

# Route background tasks to a separate model
bash setup-external-api.sh --base-url https://gateway.example.com --model main-model-id --haiku-model small-model-id
```

You can also set `EXTERNAL_API_BASE_URL` instead of passing `--base-url`.
Use HTTPS for remote providers. Local HTTP gateway addresses are supported. For a local gateway that ignores
authentication, supply a placeholder credential with `--key local`.
URLs containing embedded credentials, query parameters, or fragments are
rejected; supply credentials separately.

### Agent Router (AgentRouter)

Use the Claude Code base URL and model ID supplied by Agent Router with your
Agent Router credential:

```bash
bash setup-external-api.sh --base-url YOUR_AGENT_ROUTER_BASE_URL --model YOUR_AGENT_ROUTER_MODEL_ID
```

Replace both placeholders before running. The endpoint is configurable so you
can use the address for your deployment. The
[AgentRouter reference project](https://github.com/Arshazar/agentrouter-api-in-claude-code)
provided the original setup workflow. Use `--auth api-key` if your deployment
requires an `x-api-key` header instead of a bearer token.

### OpenCode

Built-in presets retain support for OpenCode Console and Go. If signed in to a
Claude account, run `/logout` before switching, as required by
[OpenCode's Claude Code guide](https://opencode.ai/docs/console/harnesses/claude-code/).

```bash
# OpenCode Console, using its documented Claude model defaults
bash setup-external-api.sh --provider console

# Console with a specific model available to your account
bash setup-external-api.sh --provider console --model YOUR_CONSOLE_MODEL_ID

# OpenCode Go with a model included in your plan
bash setup-external-api.sh --provider go --model YOUR_GO_MODEL_ID
```

Console uses `https://opencode.ai/inference/anthropic`. Go uses
`https://opencode.ai/inference/go/anthropic`. Both default to bearer-token
credentials. `OPENCODE_API_KEY` remains supported for these presets as a fallback
after `EXTERNAL_API_KEY`; it is never used implicitly for a custom endpoint.

Console defaults are `claude-opus-5-5`, `claude-sonnet-5-5`, and
`claude-haiku-5-5`; Go defaults all aliases to `minimax-m3`. Model availability
changes: choose IDs from the current
[Console model list](https://opencode.ai/docs/console/models/) or
[Go documentation](https://opencode.ai/docs/console/go/). OpenCode's guide
supports paid or Go models for Claude Code; check your account's access.

## Options

| Option | Behavior |
| --- | --- |
| `--provider custom\|console\|go` | Custom endpoint (default), OpenCode Console, or OpenCode Go |
| `--base-url URL` | API base URL; overrides a preset; custom mode also reads `EXTERNAL_API_BASE_URL` |
| `-k`, `--key KEY` | Credential; otherwise uses `EXTERNAL_API_KEY`, OpenCode-only fallback, then a hidden prompt |
| `--auth bearer\|api-key` | Bearer token (default) or `x-api-key` |
| `-m`, `--model ID` | Startup model and default for all three aliases |
| `--opus-model ID` | Override the `opus` alias |
| `--sonnet-model ID` | Override the `sonnet` alias; also the startup model unless `--model` is supplied |
| `--haiku-model ID` | Override the `haiku` alias and lightweight background model |
| `--settings PATH` | Configure another settings file |
| `--dry-run` | Preview managed settings with credentials redacted; write nothing |
| `--restore BACKUP` | Restore the entire settings file from a backup |
| `-h`, `--help` | Show help |

Custom mode requires `--base-url` (or `EXTERNAL_API_BASE_URL`) and either
`--model` or all three alias options. It never guesses your provider's model IDs
or reuses model mappings from the previous provider.

The entry points were renamed from `setup-opencode.*` and `setup_opencode.py`
to `setup-external-api.*` and `setup_external_api.py`. Update existing scripts
to use these names and specify `--provider console` or `--provider go` when
using the OpenCode presets.

## What changes

The tool merges an `env` block into the user settings file:

- macOS/Linux: `~/.claude/settings.json`
- Windows: `%USERPROFILE%\.claude\settings.json`
- With `CLAUDE_CONFIG_DIR`: `<CLAUDE_CONFIG_DIR>/settings.json`

For example, a custom provider with bearer authentication produces:

```json
{
  "env": {
    "ANTHROPIC_BASE_URL": "https://gateway.example.com",
    "ANTHROPIC_AUTH_TOKEN": "<your provider credential>",
    "ANTHROPIC_API_KEY": "",
    "CLAUDE_CODE_USE_BEDROCK": "",
    "CLAUDE_CODE_USE_VERTEX": "",
    "CLAUDE_CODE_USE_FOUNDRY": "",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "your-model-id",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "your-model-id",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "your-model-id",
    "ANTHROPIC_MODEL": "your-model-id",
    "ANTHROPIC_SMALL_FAST_MODEL": "your-model-id"
  }
}
```

`--auth api-key` fills `ANTHROPIC_API_KEY` and clears `ANTHROPIC_AUTH_TOKEN`.
Switching providers clears conflicting authentication and the Bedrock, Vertex,
and Foundry flags in this settings file. Other settings, including permissions,
hooks, and unrelated environment entries, are preserved.

Before changing an existing file, setup saves an exact backup alongside it and
prints its path. Writes use a temporary file and atomic replacement. Repeating
the same configuration makes no further changes. Invalid JSON or a non-object
`env` field stops setup without changing the file.

```bash
bash setup-external-api.sh --restore /path/to/settings.json.external-api-backup-EXAMPLE.json
```

Restore replaces the **complete file**, including edits made after the backup,
and backs up the current file first. Old `.opencode-backup-*.json` backups can
also be restored. Restore can recover malformed current settings. To undo an
initial setup with no previous settings file, remove the managed entries shown
above from its `env` block.

Settings and backups contain credentials. New files have owner-only permissions
on macOS/Linux; Windows files inherit the directory's ACLs. Keep them private.

## Troubleshooting

- **Authentication errors:** check your provider's credential and required
  authentication mode. For OpenCode, run `/logout` first if signed in to Claude.
- **404 or protocol errors:** use an Anthropic-compatible base URL. A raw
  OpenAI `/v1/chat/completions` endpoint needs a translating gateway.
- **Unknown model or access denied:** choose exact model IDs supported by your
  provider and account; check its quota and billing.
- **Wrong endpoint or model:** project, local, managed, IDE environment settings,
  and explicit model selections can override user settings. Inspect those
  sources and older Agent Router or OpenCode configuration.
- **WSL:** run setup inside WSL for its Linux installation, or the PowerShell
  entry point for native Windows Claude Code.

## Development and verification

```bash
python3 -m unittest discover -s tests -v
```

Tests use temporary settings files and never change your Claude configuration.
GitHub Actions runs the suite on macOS, Linux, and Windows with Python 3.9 and
3.13 and checks the platform launchers. Tests cover custom providers, both
credential headers, OpenCode presets, validation, redaction, backups, restore,
and idempotency. Live authentication requires your provider account.

Primary references checked on **2026-11-08**:

- [Claude Code: connecting to a gateway](https://code.claude.com/docs/en/llm-gateway-connect)
- [Claude Code: gateway compatibility](https://code.claude.com/docs/en/llm-gateway-protocol)
- [Claude Code: settings files](https://code.claude.com/docs/en/settings)
- [OpenCode: Claude Code integration](https://opencode.ai/docs/console/harnesses/claude-code/)
