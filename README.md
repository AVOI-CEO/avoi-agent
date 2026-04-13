<p align="center">
  <img src="assets/banner.png" alt="AVOI Agent" width="100%">
</p>

# AVOI Agent ◈

<p align="center">
  <a href="https://docs.avoi.in/docs/"><img src="https://img.shields.io/badge/Docs-avoi--agent.avoi.in-FFD700?style=for-the-badge" alt="Documentation"></a>
  <a href="https://discord.gg/AVOI-CEO"><img src="https://img.shields.io/badge/Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Discord"></a>
  <a href="https://github.com/AVOI-CEO/avoi-agent/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License: MIT"></a>
  <a href="https://avoi.in"><img src="https://img.shields.io/badge/Built%20by-AVOI%20AI-blueviolet?style=for-the-badge" alt="Built by AVOI AI"></a>
</p>

**The self-improving AI agent built by [AVOI AI](https://avoi.in).** It's the only agent with a built-in learning loop — it creates skills from experience, improves them during use, nudges itself to persist knowledge, searches its own past conversations, and builds a deepening model of who you are across sessions. Run it on a $5 VPS, a GPU cluster, or serverless infrastructure that costs nearly nothing when idle. It's not tied to your laptop — talk to it from Telegram while it works on a cloud VM.

Use any model you want — [AVOI Portal](https://portal.avoi.in), [OpenRouter](https://openrouter.ai) (200+ models), [z.ai/GLM](https://z.ai), [Kimi/Moonshot](https://platform.moonshot.ai), [MiniMax](https://www.minimax.io), OpenAI, or your own endpoint. Switch with `avoi model` — no code changes, no lock-in.

<table>
<tr><td><b>A real terminal interface</b></td><td>Full TUI with multiline editing, slash-command autocomplete, conversation history, interrupt-and-redirect, and streaming tool output.</td></tr>
<tr><td><b>Lives where you do</b></td><td>Telegram, Discord, Slack, WhatsApp, Signal, and CLI — all from a single gateway process. Voice memo transcription, cross-platform conversation continuity.</td></tr>
<tr><td><b>A closed learning loop</b></td><td>Agent-curated memory with periodic nudges. Autonomous skill creation after complex tasks. Skills self-improve during use. FTS5 session search with LLM summarization for cross-session recall. <a href="https://github.com/plastic-labs/honcho">Honcho</a> dialectic user modeling. Compatible with the <a href="https://agentskills.io">agentskills.io</a> open standard.</td></tr>
<tr><td><b>Scheduled automations</b></td><td>Built-in cron scheduler with delivery to any platform. Daily reports, nightly backups, weekly audits — all in natural language, running unattended.</td></tr>
<tr><td><b>Delegates and parallelizes</b></td><td>Spawn isolated subagents for parallel workstreams. Write Python scripts that call tools via RPC, collapsing multi-step pipelines into zero-context-cost turns.</td></tr>
<tr><td><b>Runs anywhere, not just your laptop</b></td><td>Six terminal backends — local, Docker, SSH, Daytona, Singularity, and Modal. Daytona and Modal offer serverless persistence — your agent's environment hibernates when idle and wakes on demand, costing nearly nothing between sessions. Run it on a $5 VPS or a GPU cluster.</td></tr>
<tr><td><b>Research-ready</b></td><td>Batch trajectory generation, Atropos RL environments, trajectory compression for training the next generation of tool-calling models.</td></tr>
</table>

---

## Quick Install

```bash
curl -fsSL https://raw.githubusercontent.com/AVOI-CEO/avoi-agent/main/scripts/install.sh | bash
```

Works on Linux, macOS, WSL2, and Android via Termux. The installer handles the platform-specific setup for you.

> **Android / Termux:** The tested manual path is documented in the [Termux guide](https://docs.avoi.in/docs/getting-started/termux). On Termux, Avoi installs a curated `.[termux]` extra because the full `.[all]` extra currently pulls Android-incompatible voice dependencies.
>
> **Windows:** Native Windows is not supported. Please install [WSL2](https://learn.microsoft.com/en-us/windows/wsl/install) and run the command above.

After installation:

```bash
source ~/.bashrc    # reload shell (or: source ~/.zshrc)
avoi              # start chatting!
```

---

## Getting Started

```bash
avoi              # Interactive CLI — start a conversation
avoi model        # Choose your LLM provider and model
avoi tools        # Configure which tools are enabled
avoi config set   # Set individual config values
avoi gateway      # Start the messaging gateway (Telegram, Discord, etc.)
avoi setup        # Run the full setup wizard (configures everything at once)
avoi update       # Update to the latest version
avoi doctor       # Diagnose any issues
```

📖 **[Full documentation →](https://docs.avoi.in/docs/)**

## CLI vs Messaging Quick Reference

Avoi has two entry points: start the terminal UI with `avoi`, or run the gateway and talk to it from Telegram, Discord, Slack, WhatsApp, Signal, or Email. Once you're in a conversation, many slash commands are shared across both interfaces.

| Action | CLI | Messaging platforms |
|---------|-----|---------------------|
| Start chatting | `avoi` | Run `avoi gateway setup` + `avoi gateway start`, then send the bot a message |
| Start fresh conversation | `/new` or `/reset` | `/new` or `/reset` |
| Change model | `/model [provider:model]` | `/model [provider:model]` |
| Set a personality | `/personality [name]` | `/personality [name]` |
| Retry or undo the last turn | `/retry`, `/undo` | `/retry`, `/undo` |
| Compress context / check usage | `/compress`, `/usage`, `/insights [--days N]` | `/compress`, `/usage`, `/insights [days]` |
| Browse skills | `/skills` or `/<skill-name>` | `/skills` or `/<skill-name>` |
| Interrupt current work | `Ctrl+C` or send a new message | `/stop` or send a new message |
| Platform-specific status | `/platforms` | `/status`, `/sethome` |

For the full command lists, see the [CLI guide](https://docs.avoi.in/docs/user-guide/cli) and the [Messaging Gateway guide](https://docs.avoi.in/docs/user-guide/messaging).

---

## Documentation

All documentation lives at **[docs.avoi.in/docs](https://docs.avoi.in/docs/)**:

| Section | What's Covered |
|---------|---------------|
| [Quickstart](https://docs.avoi.in/docs/getting-started/quickstart) | Install → setup → first conversation in 2 minutes |
| [CLI Usage](https://docs.avoi.in/docs/user-guide/cli) | Commands, keybindings, personalities, sessions |
| [Configuration](https://docs.avoi.in/docs/user-guide/configuration) | Config file, providers, models, all options |
| [Messaging Gateway](https://docs.avoi.in/docs/user-guide/messaging) | Telegram, Discord, Slack, WhatsApp, Signal, Home Assistant |
| [Security](https://docs.avoi.in/docs/user-guide/security) | Command approval, DM pairing, container isolation |
| [Tools & Toolsets](https://docs.avoi.in/docs/user-guide/features/tools) | 40+ tools, toolset system, terminal backends |
| [Skills System](https://docs.avoi.in/docs/user-guide/features/skills) | Procedural memory, Skills Hub, creating skills |
| [Memory](https://docs.avoi.in/docs/user-guide/features/memory) | Persistent memory, user profiles, best practices |
| [MCP Integration](https://docs.avoi.in/docs/user-guide/features/mcp) | Connect any MCP server for extended capabilities |
| [Cron Scheduling](https://docs.avoi.in/docs/user-guide/features/cron) | Scheduled tasks with platform delivery |
| [Context Files](https://docs.avoi.in/docs/user-guide/features/context-files) | Project context that shapes every conversation |
| [Architecture](https://docs.avoi.in/docs/developer-guide/architecture) | Project structure, agent loop, key classes |
| [Contributing](https://docs.avoi.in/docs/developer-guide/contributing) | Development setup, PR process, code style |
| [CLI Reference](https://docs.avoi.in/docs/reference/cli-commands) | All commands and flags |
| [Environment Variables](https://docs.avoi.in/docs/reference/environment-variables) | Complete env var reference |

---

## Contributing

We welcome contributions! See the [Contributing Guide](https://docs.avoi.in/docs/developer-guide/contributing) for development setup, code style, and PR process.

Quick start for contributors:

```bash
git clone https://github.com/AVOI-CEO/avoi-agent.git
cd avoi-agent
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv venv --python 3.11
source venv/bin/activate
uv pip install -e ".[all,dev]"
python -m pytest tests/ -q
```

> **RL Training (optional):** To work on the RL/Tinker-Atropos integration:
> ```bash
> git submodule update --init tinker-atropos
> uv pip install -e "./tinker-atropos"
> ```

---

## Community

- 💬 [Discord](https://discord.gg/AVOI-CEO)
- 📚 [Skills Hub](https://agentskills.io)
- 🐛 [Issues](https://github.com/AVOI-CEO/avoi-agent/issues)
- 💡 [Discussions](https://github.com/AVOI-CEO/avoi-agent/discussions)

---

## License

MIT — see [LICENSE](LICENSE).

Built by [AVOI AI](https://avoi.in).
