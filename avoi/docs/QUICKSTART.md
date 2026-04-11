# AVOI Quick Start Guide

## Prerequisites

- **Linux**, **macOS**, **Windows**, or **WSL2**
- Python 3.11+
- Git
- An LLM API key (OpenRouter recommended for access to 200+ models)

## Step 1: Clone & Install

```bash
git clone git@github.com:avoi-ai/avoi-agent.git
cd avoi-agent
pip install -e ".[all]"
```

## Step 2: Configure

```bash
avoi setup
```

This launches an interactive wizard. You'll need:
- Your LLM provider API key
- (Optional) Telegram/Discord/Slack tokens for messaging

## Step 3: Start

```bash
avoi
```

You're now in a conversation with your AVOI agent. Try:
- "Search the web for the latest AI news"
- "Create a Python script that..."
- "Schedule a daily report at 9 AM"

## Step 4: Connect Messaging (Optional)

```bash
avoi gateway setup
avoi gateway start
```

Now talk to your agent from Telegram, Discord, or Slack.

## Updating

```bash
cd ~/avoi-agent
git pull origin avoi/main
pip install -e ".[all]"
```
