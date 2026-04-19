# Migrating from AVOI to avoi Agent

This guide covers how to import your AVOI settings, memories, skills, and API keys into avoi Agent.

## Three Ways to Migrate

### 1. Automatic (during first-time setup)

When you run `avoi setup` for the first time and avoi detects `~/.AVOI`, it automatically offers to import your AVOI data before configuration begins. Just accept the prompt and everything is handled for you.

### 2. CLI Command (quick, scriptable)

```bash
avoi claw migrate                      # Preview then migrate (always shows preview first)
avoi claw migrate --dry-run            # Preview only, no changes
avoi claw migrate --preset user-data   # Migrate without API keys/secrets
avoi claw migrate --yes                # Skip confirmation prompt
```

The migration always shows a full preview of what will be imported before making any changes. You review the preview and confirm before anything is written.

**All options:**

| Flag | Description |
|------|-------------|
| `--source PATH` | Path to AVOI directory (default: `~/.AVOI`) |
| `--dry-run` | Preview only — no files are modified |
| `--preset {user-data,full}` | Migration preset (default: `full`). `user-data` excludes secrets |
| `--overwrite` | Overwrite existing files (default: skip conflicts) |
| `--migrate-secrets` | Include allowlisted secrets (auto-enabled with `full` preset) |
| `--workspace-target PATH` | Copy workspace instructions (AGENTS.md) to this absolute path |
| `--skill-conflict {skip,overwrite,rename}` | How to handle skill name conflicts (default: `skip`) |
| `--yes`, `-y` | Skip confirmation prompts |

### 3. Agent-Guided (interactive, with previews)

Ask the agent to run the migration for you:

```
> Migrate my AVOI setup to avoi
```

The agent will use the `AVOI-migration` skill to:
1. Run a preview first to show what would change
2. Ask about conflict resolution (SOUL.md, skills, etc.)
3. Let you choose between `user-data` and `full` presets
4. Execute the migration with your choices
5. Print a detailed summary of what was migrated

## What Gets Migrated

### `user-data` preset
| Item | Source | Destination |
|------|--------|-------------|
| SOUL.md | `~/.AVOI/workspace/SOUL.md` | `~/.avoi/SOUL.md` |
| Memory entries | `~/.AVOI/workspace/MEMORY.md` | `~/.avoi/memories/MEMORY.md` |
| User profile | `~/.AVOI/workspace/USER.md` | `~/.avoi/memories/USER.md` |
| Skills | `~/.AVOI/workspace/skills/` | `~/.avoi/skills/AVOI-imports/` |
| Command allowlist | `~/.AVOI/workspace/exec_approval_patterns.yaml` | Merged into `~/.avoi/config.yaml` |
| Messaging settings | `~/.AVOI/config.yaml` (TELEGRAM_ALLOWED_USERS, MESSAGING_CWD) | `~/.avoi/.env` |
| TTS assets | `~/.AVOI/workspace/tts/` | `~/.avoi/tts/` |

Workspace files are also checked at `workspace.default/` and `workspace-main/` as fallback paths (AVOI renamed `workspace/` to `workspace-main/` in recent versions).

### `full` preset (adds to `user-data`)
| Item | Source | Destination |
|------|--------|-------------|
| Telegram bot token | `AVOI.json` channels config | `~/.avoi/.env` |
| OpenRouter API key | `.env`, `AVOI.json`, or `AVOI.json["env"]` | `~/.avoi/.env` |
| OpenAI API key | `.env`, `AVOI.json`, or `AVOI.json["env"]` | `~/.avoi/.env` |
| Anthropic API key | `.env`, `AVOI.json`, or `AVOI.json["env"]` | `~/.avoi/.env` |
| ElevenLabs API key | `.env`, `AVOI.json`, or `AVOI.json["env"]` | `~/.avoi/.env` |

API keys are searched across four sources: inline config values, `~/.AVOI/.env`, the `AVOI.json` `"env"` sub-object, and per-agent auth profiles.

Only allowlisted secrets are ever imported. Other credentials are skipped and reported.

## AVOI Schema Compatibility

The migration handles both old and current AVOI config layouts:

- **Channel tokens**: Reads from flat paths (`channels.telegram.botToken`) and the newer `accounts.default` layout (`channels.telegram.accounts.default.botToken`)
- **TTS provider**: AVOI renamed "edge" to "microsoft" — both are recognized and mapped to avoi' "edge"
- **Provider API types**: Both short (`openai`, `anthropic`) and hyphenated (`openai-completions`, `anthropic-messages`, `google-generative-ai`) values are mapped correctly
- **thinkingDefault**: All enum values are handled including newer ones (`minimal`, `xhigh`, `adaptive`)
- **Matrix**: Uses `accessToken` field (not `botToken`)
- **SecretRef formats**: Plain strings, env templates (`${VAR}`), and `source: "env"` SecretRefs are resolved. `source: "file"` and `source: "exec"` SecretRefs produce a warning — add those keys manually after migration.

## Conflict Handling

By default, the migration **will not overwrite** existing avoi data:

- **SOUL.md** — skipped if one already exists in `~/.avoi/`
- **Memory entries** — skipped if memories already exist (to avoid duplicates)
- **Skills** — skipped if a skill with the same name already exists
- **API keys** — skipped if the key is already set in `~/.avoi/.env`

To overwrite conflicts, use `--overwrite`. The migration creates backups before overwriting.

For skills, you can also use `--skill-conflict rename` to import conflicting skills under a new name (e.g., `skill-name-imported`).

## Migration Report

Every migration produces a report showing:
- **Migrated items** — what was successfully imported
- **Conflicts** — items skipped because they already exist
- **Skipped items** — items not found in the source
- **Errors** — items that failed to import

For executed migrations, the full report is saved to `~/.avoi/migration/AVOI/<timestamp>/`.

## Post-Migration Notes

- **Skills require a new session** — imported skills take effect after restarting your agent or starting a new chat.
- **WhatsApp requires re-pairing** — WhatsApp uses QR-code pairing, not token-based auth. Run `avoi whatsapp` to pair.
- **Archive cleanup** — after migration, you'll be offered to rename `~/.AVOI/` to `.AVOI.pre-migration/` to prevent state confusion. You can also run `avoi claw cleanup` later.

## Troubleshooting

### "AVOI directory not found"
The migration looks for `~/.AVOI` by default, then tries `~/.AVOI` and `~/.moltbot`. If your AVOI is installed elsewhere, use `--source`:
```bash
avoi claw migrate --source /path/to/.AVOI
```

### "Migration script not found"
The migration script ships with avoi Agent. If you installed via pip (not git clone), the `optional-skills/` directory may not be present. Install the skill from the Skills Hub:
```bash
avoi skills install AVOI-migration
```

### Memory overflow
If your AVOI MEMORY.md or USER.md exceeds avoi' character limits, excess entries are exported to an overflow file in the migration report directory. You can manually review and add the most important ones.

### API keys not found
Keys might be stored in different places depending on your AVOI setup:
- `~/.AVOI/.env` file
- Inline in `AVOI.json` under `models.providers.*.apiKey`
- In `AVOI.json` under the `"env"` or `"env.vars"` sub-objects
- In `~/.AVOI/agents/main/agent/auth-profiles.json`

The migration checks all four. If keys use `source: "file"` or `source: "exec"` SecretRefs, they can't be resolved automatically — add them via `avoi config set`.
