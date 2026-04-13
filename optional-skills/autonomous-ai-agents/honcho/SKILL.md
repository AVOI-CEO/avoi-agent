---
name: honcho
description: Configure and use Honcho memory with Avoi -- cross-session user modeling, multi-profile peer isolation, observation config, and dialectic reasoning. Use when setting up Honcho, troubleshooting memory, managing profiles with Honcho peers, or tuning observation and recall settings.
version: 1.0.0
author: AVOI Agent
license: MIT
metadata:
  avoi:
    tags: [Honcho, Memory, Profiles, Observation, Dialectic, User-Modeling]
    homepage: https://docs.honcho.dev
    related_skills: [avoi-agent]
prerequisites:
  pip: [honcho-ai]
---

# Honcho Memory for Avoi

Honcho provides AI-native cross-session user modeling. It learns who the user is across conversations and gives every Avoi profile its own peer identity while sharing a unified view of the user.

## When to Use

- Setting up Honcho (cloud or self-hosted)
- Troubleshooting memory not working / peers not syncing
- Creating multi-profile setups where each agent has its own Honcho peer
- Tuning observation, recall, or write frequency settings
- Understanding what the 4 Honcho tools do and when to use them

## Setup

### Cloud (app.honcho.dev)

```bash
avoi honcho setup
# select "cloud", paste API key from https://app.honcho.dev
```

### Self-hosted

```bash
avoi honcho setup
# select "local", enter base URL (e.g. http://localhost:8000)
```

See: https://docs.honcho.dev/v3/guides/integrations/avoi#running-honcho-locally-with-avoi

### Verify

```bash
avoi honcho status    # shows resolved config, connection test, peer info
```

## Architecture

### Peers

Honcho models conversations as interactions between **peers**. Avoi creates two peers per session:

- **User peer** (`peerName`): represents the human. Honcho builds a user representation from observed messages.
- **AI peer** (`aiPeer`): represents this Avoi instance. Each profile gets its own AI peer so agents develop independent views.

### Observation

Each peer has two observation toggles that control what Honcho learns from:

| Toggle | What it does |
|--------|-------------|
| `observeMe` | Peer's own messages are observed (builds self-representation) |
| `observeOthers` | Other peers' messages are observed (builds cross-peer understanding) |

Default: all four toggles **on** (full bidirectional observation).

Configure per-peer in `honcho.json`:

```json
{
  "observation": {
    "user": { "observeMe": true, "observeOthers": true },
    "ai":   { "observeMe": true, "observeOthers": true }
  }
}
```

Or use the shorthand presets:

| Preset | User | AI | Use case |
|--------|------|----|----------|
| `"directional"` (default) | me:on, others:on | me:on, others:on | Multi-agent, full memory |
| `"unified"` | me:on, others:off | me:off, others:on | Single agent, user-only modeling |

Settings changed in the [Honcho dashboard](https://app.honcho.dev) are synced back on session init -- server-side config wins over local defaults.

### Sessions

Honcho sessions scope where messages and observations land. Strategy options:

| Strategy | Behavior |
|----------|----------|
| `per-directory` (default) | One session per working directory |
| `per-repo` | One session per git repository root |
| `per-session` | New Honcho session each Avoi run |
| `global` | Single session across all directories |

Manual override: `avoi honcho map my-project-name`

### Recall Modes

How the agent accesses Honcho memory:

| Mode | Auto-inject context? | Tools available? | Use case |
|------|---------------------|-----------------|----------|
| `hybrid` (default) | Yes | Yes | Agent decides when to use tools vs auto context |
| `context` | Yes | No (hidden) | Minimal token cost, no tool calls |
| `tools` | No | Yes | Agent controls all memory access explicitly |

## Multi-Profile Setup

Each Avoi profile gets its own Honcho AI peer while sharing the same workspace (user context). This means:

- All profiles see the same user representation
- Each profile builds its own AI identity and observations
- Conclusions written by one profile are visible to others via the shared workspace

### Create a profile with Honcho peer

```bash
avoi profile create coder --clone
# creates host block avoi.coder, AI peer "coder", inherits config from default
```

What `--clone` does for Honcho:
1. Creates a `avoi.coder` host block in `honcho.json`
2. Sets `aiPeer: "coder"` (the profile name)
3. Inherits `workspace`, `peerName`, `writeFrequency`, `recallMode`, etc. from default
4. Eagerly creates the peer in Honcho so it exists before first message

### Backfill existing profiles

```bash
avoi honcho sync    # creates host blocks for all profiles that don't have one yet
```

### Per-profile config

Override any setting in the host block:

```json
{
  "hosts": {
    "avoi.coder": {
      "aiPeer": "coder",
      "recallMode": "tools",
      "observation": {
        "user": { "observeMe": true, "observeOthers": false },
        "ai": { "observeMe": true, "observeOthers": true }
      }
    }
  }
}
```

## Tools

The agent has 4 Honcho tools (hidden in `context` recall mode):

### `honcho_profile`
Quick factual snapshot of the user -- name, role, preferences, patterns. No LLM call, minimal cost. Use at conversation start or for fast lookups.

### `honcho_search`
Semantic search over stored context. Returns raw excerpts ranked by relevance, no LLM synthesis. Default 800 tokens, max 2000. Use when you want specific past facts to reason over yourself.

### `honcho_context`
Natural language question answered by Honcho's dialectic reasoning (LLM call on Honcho's backend). Higher cost, higher quality. Can query about user (default) or the AI peer.

### `honcho_conclude`
Write a persistent fact about the user. Conclusions build the user's profile over time. Use when the user states a preference, corrects you, or shares something to remember.

## Config Reference

Config file: `$AVOI_HOME/honcho.json` (profile-local) or `~/.honcho/config.json` (global).

### Key settings

| Key | Default | Description |
|-----|---------|-------------|
| `apiKey` | -- | API key ([get one](https://app.honcho.dev)) |
| `baseUrl` | -- | Base URL for self-hosted Honcho |
| `peerName` | -- | User peer identity |
| `aiPeer` | host key | AI peer identity |
| `workspace` | host key | Shared workspace ID |
| `recallMode` | `hybrid` | `hybrid`, `context`, or `tools` |
| `observation` | all on | Per-peer `observeMe`/`observeOthers` booleans |
| `writeFrequency` | `async` | `async`, `turn`, `session`, or integer N |
| `sessionStrategy` | `per-directory` | `per-directory`, `per-repo`, `per-session`, `global` |
| `dialecticReasoningLevel` | `low` | `minimal`, `low`, `medium`, `high`, `max` |
| `dialecticDynamic` | `true` | Auto-bump reasoning by query length. `false` = fixed level |
| `messageMaxChars` | `25000` | Max chars per message (chunked if exceeded) |
| `dialecticMaxInputChars` | `10000` | Max chars for dialectic query input |

### Cost-awareness (advanced, root config only)

| Key | Default | Description |
|-----|---------|-------------|
| `injectionFrequency` | `every-turn` | `every-turn` or `first-turn` |
| `contextCadence` | `1` | Min turns between context API calls |
| `dialecticCadence` | `1` | Min turns between dialectic API calls |

## Troubleshooting

### "Honcho not configured"
Run `avoi honcho setup`. Ensure `memory.provider: honcho` is in `~/.avoi/config.yaml`.

### Memory not persisting across sessions
Check `avoi honcho status` -- verify `saveMessages: true` and `writeFrequency` isn't `session` (which only writes on exit).

### Profile not getting its own peer
Use `--clone` when creating: `avoi profile create <name> --clone`. For existing profiles: `avoi honcho sync`.

### Observation changes in dashboard not reflected
Observation config is synced from the server on each session init. Start a new session after changing settings in the Honcho UI.

### Messages truncated
Messages over `messageMaxChars` (default 25k) are automatically chunked with `[continued]` markers. If you're hitting this often, check if tool results or skill content is inflating message size.

## CLI Commands

| Command | Description |
|---------|-------------|
| `avoi honcho setup` | Interactive setup wizard (cloud/local, identity, observation, recall, sessions) |
| `avoi honcho status` | Show resolved config, connection test, peer info for active profile |
| `avoi honcho enable` | Enable Honcho for the active profile (creates host block if needed) |
| `avoi honcho disable` | Disable Honcho for the active profile |
| `avoi honcho peer` | Show or update peer names (`--user <name>`, `--ai <name>`, `--reasoning <level>`) |
| `avoi honcho peers` | Show peer identities across all profiles |
| `avoi honcho mode` | Show or set recall mode (`hybrid`, `context`, `tools`) |
| `avoi honcho tokens` | Show or set token budgets (`--context <N>`, `--dialectic <N>`) |
| `avoi honcho sessions` | List known directory-to-session-name mappings |
| `avoi honcho map <name>` | Map current working directory to a Honcho session name |
| `avoi honcho identity` | Seed AI peer identity or show both peer representations |
| `avoi honcho sync` | Create host blocks for all Avoi profiles that don't have one yet |
| `avoi honcho migrate` | Step-by-step migration guide from native memory to Avoi + Honcho |
| `avoi memory setup` | Generic memory provider picker (selecting "honcho" runs the same wizard) |
| `avoi memory status` | Show active memory provider and config |
| `avoi memory off` | Disable external memory provider |
