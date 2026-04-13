#!/usr/bin/env bash
# ── AVOI Agent Installer ──────────────────────────────────────────────
# Usage: curl -fsSL https://avoi.in/install.sh | bash
set -euo pipefail

BOLD='\033[1m'
CYAN='\033[36m'
GREEN='\033[32m'
RED='\033[31m'
NC='\033[0m'

REPO="https://github.com/AVOI-CEO/avoi-agent.git"
INSTALL_DIR="$HOME/avoi-agent"
BRANCH="avoi/main"

print_banner() {
    echo -e "${CYAN}"
    echo "___ _    _____ ___"
    echo "   /   | |  / / _ \\\\_ _|"
    echo "  / /| | | / / / / | |"
    echo " / ___ | |/ / /_/ /| |"
    echo "/_/  |_|___/\\____/|___|"
    echo -e "${NC}"
    echo -e "  ${BOLD}AVOI Agent${NC} — Autonomous AI Agent Platform"
    echo ""
}

die() {
    echo -e "${RED}Error: $1${NC}" >&2
    exit 1
}

check_deps() {
    local missing=()
    command -v git &>/dev/null || missing+=("git")
    command -v python3 &>/dev/null || missing+=("python3")

    if [ ${#missing[@]} -gt 0 ]; then
        die "Missing dependencies: ${missing[*]}. Install them first."
    fi

    # Check Python version >= 3.10
    py_ver=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    py_major=$(echo "$py_ver" | cut -d. -f1)
    py_minor=$(echo "$py_ver" | cut -d. -f2)
    if [ "$py_major" -lt 3 ] || { [ "$py_major" -eq 3 ] && [ "$py_minor" -lt 10 ]; }; then
        die "Python 3.10+ required (found $py_ver)"
    fi
}

clone_repo() {
    if [ -d "$INSTALL_DIR/.git" ]; then
        echo -e "  ${GREEN}✓${NC} Existing install found at $INSTALL_DIR, pulling updates..."
        cd "$INSTALL_DIR"
        git fetch origin "$BRANCH" || die "Failed to fetch updates"
        git reset --hard "origin/$BRANCH" || die "Failed to update"
    else
        echo -e "  ${CYAN}→${NC} Cloning AVOI Agent..."
        git clone -b "$BRANCH" --depth 1 "$REPO" "$INSTALL_DIR" || die "Failed to clone repository"
        cd "$INSTALL_DIR"
    fi
}

setup_venv() {
    echo -e "  ${CYAN}→${NC} Setting up virtual environment..."
    python3 -m venv venv || die "Failed to create virtual environment"
    source venv/bin/activate || die "Failed to activate virtual environment"
}

install_deps() {
    echo -e "  ${CYAN}→${NC} Installing AVOI Agent..."
    pip install -e . --quiet 2>&1 || die "Failed to install dependencies"
}

setup_command() {
    # Create ~/.local/bin/avoi wrapper
    mkdir -p "$HOME/.local/bin"

    cat > "$HOME/.local/bin/avoi" << 'WRAPPER'
#!/usr/bin/env bash
source "$HOME/avoi-agent/venv/bin/activate"
exec python -m avoi_cli.main "$@"
WRAPPER
    chmod +x "$HOME/.local/bin/avoi"

    # Add ~/.local/bin to PATH if not already there
    if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
        echo -e "  ${CYAN}→${NC} Adding ~/.local/bin to PATH..."
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.zshrc" 2>/dev/null || true
        export PATH="$HOME/.local/bin:$PATH"
    fi
}

# ── Main ──────────────────────────────────────────────────────────────
print_banner
check_deps
clone_repo
setup_venv
install_deps
setup_command

echo ""
echo -e "${GREEN}╭──────────────────────────────────────────────────────╮${NC}"
echo -e "${GREEN}│${NC}  ${BOLD}AVOI Agent installed successfully!${NC}                  ${GREEN}│${NC}"
echo -e "${GREEN}╰──────────────────────────────────────────────────────╯${NC}"
echo ""
echo "  Next steps:"
echo "    1. Restart your terminal (or run: source ~/.bashrc)"
echo "    2. Configure your API key:"
echo "       avoi setup"
echo "    3. Start chatting:"
echo "       avoi"
echo ""
echo "  One-line setup with GLM key:"
echo "       avoi config set model z-ai/glm-5.1"
echo "       echo 'GLM_API_KEY=your_key' >> ~/.avoi/.env"
echo ""
