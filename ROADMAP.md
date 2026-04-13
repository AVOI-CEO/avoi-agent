# AVOI Agent Development Roadmap

## Vision
AVOI Agent is an autonomous AI agent platform -- independently developed, zero upstream dependencies.
A finished product that users trust and pay for. Not a fork. Not a wrapper. Its own thing.

## Current State (v0.8.0)
- Independently developed autonomous AI agent platform
- Hot pink Lain-inspired theme (skin engine)
- Provider system: zai, openrouter, anthropic, openai, minimax, deepseek, etc.
- Tool system: browser, terminal, file ops, delegation, cron, memory, skills
- Skill system: 50+ built-in skills
- CLI TUI with skins, banner art, spinners

## Development Council Goals (Autonomous Cron Jobs)

### 1. CORE ENGINE IMPROVEMENTS
- [ ] Diff-based file editing (inspired by claw-code) -- token-efficient targeted edits
- [ ] Plan-then-execute architecture (inspired by oh-my-openagent) -- separate planning from execution
- [ ] Observer/safety layer (inspired by oh-my-openagent) -- validate agent actions before execution
- [ ] Permission/sandbox system (inspired by claw-code) -- fine-grained control over dangerous ops
- [ ] Cost tracking dashboard (inspired by claw-code) -- real-time API cost awareness
- [ ] Smart context window management (inspired by claw-code) -- summarization for large codebases
- [ ] Plugin/extension system (inspired by oh-my-openagent) -- community-extensible capabilities
- [ ] Multi-LLM adapter abstraction (inspired by oh-my-openagent) -- seamless provider switching
- [ ] Router-based tool dispatch (inspired by oh-my-openagent) -- intelligent tool selection

### 2. MCP SERVER INTEGRATION
- [ ] AVOI as an MCP server (inspired by tanbiralam & codeaashu claude-code)
- [ ] Code analysis tools (structure parsing, dependency graphs)
- [ ] Multi-language sandboxed execution (Python, Node.js, Bash)
- [ ] Git operations as MCP tools
- [ ] Web fetching as MCP tool
- [ ] Project-level analysis (tech stack detection, dependency audit)

### 3. PRODUCT POLISH
- [ ] Onboarding wizard (first-run setup with API key configuration)
- [ ] Configuration UI (TUI-based settings panel)
- [ ] Session management (list, resume, export sessions)
- [ ] Usage analytics dashboard (tokens, costs, model usage)
- [ ] Auto-update system
- [ ] Error recovery (crash reports, auto-retry, graceful degradation)

### 4. DOCUMENTATION & WEBSITE
- [ ] Complete docs site (docs.avoi.in)
- [ ] Getting started guide
- [ ] API reference
- [ ] Skill authoring guide
- [ ] Architecture overview
- [ ] Changelog management
- [ ] Landing page improvements

### 5. COMMUNITY & GROWTH
- [ ] GitHub Issues management (bug triage, feature requests)
- [ ] CONTRIBUTING.md guide
- [ ] Beta tester outreach program
- [ ] Discord/community setup
- [ ] Release notes automation
- [ ] Social media presence (Twitter/X)

### 6. QUALITY & TESTING
- [ ] Comprehensive test suite
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Automated regression testing
- [ ] Performance benchmarks
- [ ] Security audit
- [ ] Code quality metrics

## Priority Order
1. Core engine improvements (diff editing, plan-execute, observer)
2. MCP server integration
3. Onboarding & polish
4. Documentation
5. Testing & CI/CD
6. Community & growth
