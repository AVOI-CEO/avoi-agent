---
sidebar_position: 7
---

# Profile Commands Reference

This page covers all commands related to [Avoi profiles](../user-guide/profiles.md). For general CLI commands, see [CLI Commands Reference](./cli-commands.md).

## `avoi profile`

```bash
avoi profile <subcommand>
```

Top-level command for managing profiles. Running `avoi profile` without a subcommand shows help.

| Subcommand | Description |
|------------|-------------|
| `list` | List all profiles. |
| `use` | Set the active (default) profile. |
| `create` | Create a new profile. |
| `delete` | Delete a profile. |
| `show` | Show details about a profile. |
| `alias` | Regenerate the shell alias for a profile. |
| `rename` | Rename a profile. |
| `export` | Export a profile to a tar.gz archive. |
| `import` | Import a profile from a tar.gz archive. |

## `avoi profile list`

```bash
avoi profile list
```

Lists all profiles. The currently active profile is marked with `*`.

**Example:**

```bash
$ avoi profile list
  default
* work
  dev
  personal
```

No options.

## `avoi profile use`

```bash
avoi profile use <name>
```

Sets `<name>` as the active profile. All subsequent `avoi` commands (without `-p`) will use this profile.

| Argument | Description |
|----------|-------------|
| `<name>` | Profile name to activate. Use `default` to return to the base profile. |

**Example:**

```bash
avoi profile use work
avoi profile use default
```

## `avoi profile create`

```bash
avoi profile create <name> [options]
```

Creates a new profile.

| Argument / Option | Description |
|-------------------|-------------|
| `<name>` | Name for the new profile. Must be a valid directory name (alphanumeric, hyphens, underscores). |
| `--clone` | Copy `config.yaml`, `.env`, and `SOUL.md` from the current profile. |
| `--clone-all` | Copy everything (config, memories, skills, sessions, state) from the current profile. |
| `--clone-from <profile>` | Clone from a specific profile instead of the current one. Used with `--clone` or `--clone-all`. |

**Examples:**

```bash
# Blank profile — needs full setup
avoi profile create mybot

# Clone config only from current profile
avoi profile create work --clone

# Clone everything from current profile
avoi profile create backup --clone-all

# Clone config from a specific profile
avoi profile create work2 --clone --clone-from work
```

## `avoi profile delete`

```bash
avoi profile delete <name> [options]
```

Deletes a profile and removes its shell alias.

| Argument / Option | Description |
|-------------------|-------------|
| `<name>` | Profile to delete. |
| `--yes`, `-y` | Skip confirmation prompt. |

**Example:**

```bash
avoi profile delete mybot
avoi profile delete mybot --yes
```

:::warning
This permanently deletes the profile's entire directory including all config, memories, sessions, and skills. Cannot delete the currently active profile.
:::

## `avoi profile show`

```bash
avoi profile show <name>
```

Displays details about a profile including its home directory, configured model, gateway status, skills count, and configuration file status.

| Argument | Description |
|----------|-------------|
| `<name>` | Profile to inspect. |

**Example:**

```bash
$ avoi profile show work
Profile: work
Path:    ~/.avoi/profiles/work
Model:   anthropic/claude-sonnet-4 (anthropic)
Gateway: stopped
Skills:  12
.env:    exists
SOUL.md: exists
Alias:   ~/.local/bin/work
```

## `avoi profile alias`

```bash
avoi profile alias <name> [options]
```

Regenerates the shell alias script at `~/.local/bin/<name>`. Useful if the alias was accidentally deleted or if you need to update it after moving your Avoi installation.

| Argument / Option | Description |
|-------------------|-------------|
| `<name>` | Profile to create/update the alias for. |
| `--remove` | Remove the wrapper script instead of creating it. |
| `--name <alias>` | Custom alias name (default: profile name). |

**Example:**

```bash
avoi profile alias work
# Creates/updates ~/.local/bin/work

avoi profile alias work --name mywork
# Creates ~/.local/bin/mywork

avoi profile alias work --remove
# Removes the wrapper script
```

## `avoi profile rename`

```bash
avoi profile rename <old-name> <new-name>
```

Renames a profile. Updates the directory and shell alias.

| Argument | Description |
|----------|-------------|
| `<old-name>` | Current profile name. |
| `<new-name>` | New profile name. |

**Example:**

```bash
avoi profile rename mybot assistant
# ~/.avoi/profiles/mybot → ~/.avoi/profiles/assistant
# ~/.local/bin/mybot → ~/.local/bin/assistant
```

## `avoi profile export`

```bash
avoi profile export <name> [options]
```

Exports a profile as a compressed tar.gz archive.

| Argument / Option | Description |
|-------------------|-------------|
| `<name>` | Profile to export. |
| `-o`, `--output <path>` | Output file path (default: `<name>.tar.gz`). |

**Example:**

```bash
avoi profile export work
# Creates work.tar.gz in the current directory

avoi profile export work -o ./work-2026-03-29.tar.gz
```

## `avoi profile import`

```bash
avoi profile import <archive> [options]
```

Imports a profile from a tar.gz archive.

| Argument / Option | Description |
|-------------------|-------------|
| `<archive>` | Path to the tar.gz archive to import. |
| `--name <name>` | Name for the imported profile (default: inferred from archive). |

**Example:**

```bash
avoi profile import ./work-2026-03-29.tar.gz
# Infers profile name from the archive

avoi profile import ./work-2026-03-29.tar.gz --name work-restored
```

## `avoi -p` / `avoi --profile`

```bash
avoi -p <name> <command> [options]
avoi --profile <name> <command> [options]
```

Global flag to run any Avoi command under a specific profile without changing the sticky default. This overrides the active profile for the duration of the command.

| Option | Description |
|--------|-------------|
| `-p <name>`, `--profile <name>` | Profile to use for this command. |

**Examples:**

```bash
avoi -p work chat -q "Check the server status"
avoi --profile dev gateway start
avoi -p personal skills list
avoi -p work config edit
```

## `avoi completion`

```bash
avoi completion <shell>
```

Generates shell completion scripts. Includes completions for profile names and profile subcommands.

| Argument | Description |
|----------|-------------|
| `<shell>` | Shell to generate completions for: `bash` or `zsh`. |

**Examples:**

```bash
# Install completions
avoi completion bash >> ~/.bashrc
avoi completion zsh >> ~/.zshrc

# Reload shell
source ~/.bashrc
```

After installation, tab completion works for:
- `avoi profile <TAB>` — subcommands (list, use, create, etc.)
- `avoi profile use <TAB>` — profile names
- `avoi -p <TAB>` — profile names

## See also

- [Profiles User Guide](../user-guide/profiles.md)
- [CLI Commands Reference](./cli-commands.md)
- [FAQ — Profiles section](./faq.md#profiles)
