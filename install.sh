#!/bin/bash
# chess-self-coach installer
# Usage: curl -fsSL https://raw.githubusercontent.com/Bobain/chess-self-coach/main/install.sh | bash
set -euo pipefail

PACKAGE="chess-self-coach"

# --- OS detection ---

detect_platform() {
  OS="$(uname -s)"
  case "$OS" in
    Darwin) PLATFORM="macos" ;;
    Linux)  PLATFORM="linux" ;;
    *)      echo "❌ Unsupported OS: $OS (macOS and Debian/Ubuntu supported)" && exit 1 ;;
  esac
}

# --- Detection helpers ---

check_homebrew()  { command -v brew &>/dev/null; }
check_uv()        { command -v uv &>/dev/null; }
check_stockfish() { command -v stockfish &>/dev/null; }
check_package()   { uv tool list 2>/dev/null | grep -q "$PACKAGE"; }

# --- Prompt helper (works with curl | bash) ---

prompt_user() {
  local prompt="$1" default="${2:-y}"
  if [ ! -t 0 ] && [ ! -e /dev/tty ]; then
    return 0  # non-interactive (CI): proceed silently
  fi
  local answer
  printf "%s " "$prompt" >&2
  read -r answer < /dev/tty
  answer="${answer:-$default}"
  case "$answer" in
    [Yy]*) return 0 ;;
    *)     return 1 ;;
  esac
}

# --- Dependency summary + consent ---

show_dependency_summary() {
  local needs_install=0

  echo "Dependencies:"

  # Homebrew (macOS only)
  if [ "$PLATFORM" = "macos" ]; then
    if check_homebrew; then
      echo "  ✓ Homebrew — already installed"
    else
      echo "  ⬇ Homebrew (macOS package manager) — will be installed"
      needs_install=1
    fi
  fi

  # uv
  if check_uv; then
    echo "  ✓ uv $(uv --version 2>/dev/null || echo '') — already installed"
  else
    echo "  ⬇ uv (Python tool manager) — will be installed"
    needs_install=1
  fi

  # Stockfish
  if check_stockfish; then
    echo "  ✓ Stockfish — already installed"
  else
    case "$PLATFORM" in
      macos) echo "  ⬇ Stockfish (chess engine, via Homebrew) — will be installed" ;;
      linux) echo "  ⬇ Stockfish (chess engine, via apt) — will be installed" ;;
    esac
    needs_install=1
  fi

  # Syzygy tables
  local syzygy_dir="$HOME/.local/share/syzygy"
  if [ -d "$syzygy_dir" ] && ls "$syzygy_dir"/*.rtbw &>/dev/null 2>&1; then
    echo "  ✓ Syzygy endgame tables — already installed"
  else
    echo "  ⬇ Syzygy endgame tables (3-5 pieces, ~1 GB) — will be downloaded"
    needs_install=1
  fi

  # chess-self-coach
  if check_uv && check_package; then
    echo "  ✓ $PACKAGE — already installed (will check for upgrade)"
  else
    echo "  ⬇ $PACKAGE — will be installed"
    needs_install=1
  fi

  echo ""

  if [ "$needs_install" -eq 0 ]; then
    return 0
  fi

  if ! prompt_user "Proceed with installation? [Y/n]" "y"; then
    echo ""
    if ! prompt_user "⚠️  Without these dependencies, $PACKAGE cannot run. Are you sure you want to cancel? [y/N]" "n"; then
      echo ""
      echo "Continuing installation..."
      return 0
    fi
    echo ""
    echo "Installation cancelled."
    exit 0
  fi
  echo ""
}

# --- Install functions ---

install_homebrew() {
  if check_homebrew; then
    echo "  ✓ Homebrew already installed"
    return
  fi
  echo "  Installing Homebrew..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  echo "  ✓ Homebrew installed"
}

install_uv() {
  if check_uv; then
    echo "  ✓ uv already installed ($(uv --version 2>/dev/null || echo ''))"
    return
  fi
  echo "  Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
  echo "  ✓ uv installed"
}

install_stockfish() {
  if check_stockfish; then
    echo "  ✓ Stockfish already installed ($(stockfish --help 2>&1 | head -1 || echo 'found'))"
    return
  fi

  echo "  Installing Stockfish..."
  case "$PLATFORM" in
    macos)
      brew install stockfish
      ;;
    linux)
      if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq && sudo apt-get install -y stockfish
      else
        echo "  ❌ apt-get not found. Install Stockfish manually:"
        echo "     https://stockfishchess.org/download/"
        exit 1
      fi
      ;;
  esac
  echo "  ✓ Stockfish installed"
}

install_package() {
  if check_uv && check_package; then
    echo "  Upgrading $PACKAGE..."
    uv tool upgrade "$PACKAGE"
  else
    echo "  Installing $PACKAGE from PyPI..."
    uv tool install "$PACKAGE" --python 3.12
  fi
  echo "  ✓ $PACKAGE ready"
}

install_syzygy() {
  local syzygy_dir="$HOME/.local/share/syzygy"
  if [ -d "$syzygy_dir" ] && ls "$syzygy_dir"/*.rtbw &>/dev/null; then
    echo "  ✓ Syzygy tables already installed at $syzygy_dir"
    return
  fi

  if ! command -v wget &>/dev/null; then
    echo "  ⚠ wget not found — skipping Syzygy download"
    echo "    Install wget and run: chess-self-coach syzygy download"
    return
  fi

  echo "  Downloading 3-5 piece tables (~1 GB) to $syzygy_dir..."
  mkdir -p "$syzygy_dir"
  wget -q -c -r -np -nH --cut-dirs=2 -e robots=off -A "*.rtbw,*.rtbz" \
      -P "$syzygy_dir" http://tablebase.sesse.net/syzygy/3-4-5/ || {
    echo "  ⚠ Syzygy download failed (analysis will still work via API fallback)"
    return
  }
  echo "  ✓ Syzygy endgame tables installed"
}

# --- Main ---

main() {
  echo ""
  echo "♟️  chess-self-coach installer"
  echo "─────────────────────────────"
  echo ""

  detect_platform
  echo "Platform: $PLATFORM ($(uname -m))"
  echo ""

  show_dependency_summary

  # Compute total steps
  local total=4
  if [ "$PLATFORM" = "macos" ] && ! check_homebrew; then
    total=5
  fi

  local step=0

  # Homebrew (macOS only, if missing)
  if [ "$PLATFORM" = "macos" ] && ! check_homebrew; then
    step=$((step + 1))
    echo "Step $step/$total: Homebrew"
    install_homebrew
    echo ""
  fi

  # uv
  step=$((step + 1))
  echo "Step $step/$total: uv"
  install_uv
  echo ""

  # Stockfish
  step=$((step + 1))
  echo "Step $step/$total: Stockfish"
  install_stockfish
  echo ""

  # Syzygy endgame tables
  step=$((step + 1))
  echo "Step $step/$total: Syzygy endgame tables"
  install_syzygy
  echo ""

  # chess-self-coach
  step=$((step + 1))
  echo "Step $step/$total: $PACKAGE"
  install_package
  echo ""

  echo "─────────────────────────────"
  echo "✓ Installation complete!"
  echo ""
  echo "Run the setup wizard:"
  echo "  chess-self-coach setup"
  echo ""
  echo "Update later with:"
  echo "  chess-self-coach update"
  echo ""
}

main "$@"
