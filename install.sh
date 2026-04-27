#!/bin/bash
# ============================================================
#   ssh-bot-Robexia Installer v1.0
#   https://github.com/Hajiyor/ssh-bot-Robexia
# ============================================================

set -e

# ─── Colors ────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ─── Config ────────────────────────────────────────────────
BOT_NAME="ssh-bot-Robexia"
VERSION="v1.0"
REPO="https://github.com/Hajiyor/ssh-bot-Robexia"
INSTALL_DIR="/opt/ssh-bot-robexia"
SERVICE_NAME="ssh-bot-robexia"
ENV_FILE="$INSTALL_DIR/.env"
PYTHON_MIN="3.9"

# ─── Banner ────────────────────────────────────────────────
print_banner() {
    clear
    echo -e "${CYAN}${BOLD}"
    echo "  ╔══════════════════════════════════════════╗"
    echo "  ║         ssh-bot-Robexia  $VERSION           ║"
    echo "  ║     Telegram SSH/SFTP Bot by Robexia     ║"
    echo "  ╚══════════════════════════════════════════╝"
    echo -e "${NC}"
    echo -e "  ${BLUE}GitHub:${NC} $REPO"
    echo ""
}

# ─── Menu ──────────────────────────────────────────────────
print_menu() {
    echo -e "${BOLD}  Please choose an option:${NC}"
    echo ""
    echo -e "  ${GREEN}[1]${NC} Install bot"
    echo -e "  ${YELLOW}[2]${NC} Uninstall bot"
    echo -e "  ${BLUE}[3]${NC} Update bot"
    echo -e "  ${RED}[0]${NC} Exit"
    echo ""
    echo -ne "  ${BOLD}Enter your choice: ${NC}"
}

# ─── Helpers ───────────────────────────────────────────────
log_info()    { echo -e "  ${GREEN}[INFO]${NC}  $1"; }
log_warn()    { echo -e "  ${YELLOW}[WARN]${NC}  $1"; }
log_error()   { echo -e "  ${RED}[ERROR]${NC} $1"; }
log_step()    { echo -e "\n  ${CYAN}${BOLD}>> $1${NC}"; }
log_success() { echo -e "  ${GREEN}${BOLD}✓ $1${NC}"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root."
        log_error "Try: sudo bash install.sh"
        exit 1
    fi
}

check_python() {
    log_step "Checking Python version..."
    if ! command -v python3 &>/dev/null; then
        log_error "Python3 not found. Installing..."
        apt-get update -qq && apt-get install -y python3 python3-pip python3-venv
    else
        # مطمئن بشیم python3-venv نصبه
        python3 -m venv --help &>/dev/null || apt-get install -y -qq python3-venv
    fi
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    log_info "Python version: $PY_VER"
    if python3 -c "import sys; exit(0 if sys.version_info >= (3,9) else 1)"; then
        log_success "Python version OK"
    else
        log_error "Python 3.9+ is required. Found: $PY_VER"
        exit 1
    fi
}

check_service_exists() {
    systemctl list-unit-files | grep -q "^${SERVICE_NAME}.service" 2>/dev/null
}

# ─── Install ───────────────────────────────────────────────
do_install() {
    log_step "Starting installation of $BOT_NAME $VERSION"

    if check_service_exists; then
        log_warn "Bot is already installed!"
        echo -ne "  Do you want to reinstall? (y/N): "
        read -r confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            log_info "Installation cancelled."
            return
        fi
        systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    fi

    check_root
    check_python

    # ─── Get bot token ──────────────────────────────────────
    log_step "Bot Configuration"
    echo ""
    echo -e "  ${BOLD}Step 1/2: Bot Token${NC}"
    echo -e "  Get your token from ${CYAN}@BotFather${NC} on Telegram."
    echo ""
    while true; do
        echo -ne "  Enter bot token: "
        read -r BOT_TOKEN
        BOT_TOKEN=$(echo "$BOT_TOKEN" | tr -d ' ')
        if [[ "$BOT_TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]{35,}$ ]]; then
            log_success "Token format looks valid."
            break
        else
            log_error "Invalid token format. Example: 123456789:ABCdef..."
        fi
    done

    # ─── Get admin ID ───────────────────────────────────────
    echo ""
    echo -e "  ${BOLD}Step 2/2: Admin Telegram ID${NC}"
    echo -e "  Get your numeric ID from ${CYAN}@userinfobot${NC} on Telegram."
    echo ""
    while true; do
        echo -ne "  Enter your Telegram numeric ID: "
        read -r ADMIN_ID
        ADMIN_ID=$(echo "$ADMIN_ID" | tr -d ' ')
        if [[ "$ADMIN_ID" =~ ^[0-9]{5,15}$ ]]; then
            log_success "Admin ID: $ADMIN_ID"
            break
        else
            log_error "Invalid ID. Must be a numeric value (e.g. 123456789)."
        fi
    done

    # ─── Download bot ───────────────────────────────────────
    log_step "Downloading bot files..."

    apt-get update -qq
    apt-get install -y -qq git curl python3-venv python3-pip

    if [[ -d "$INSTALL_DIR/.git" ]]; then
        log_info "Updating existing files..."
        cd "$INSTALL_DIR" && git pull origin main
    else
        rm -rf "$INSTALL_DIR"
        git clone --depth=1 "$REPO.git" "$INSTALL_DIR" 2>/dev/null || {
            # اگر git clone شکست خورد، از curl دانلود کنیم
            log_warn "Git clone failed. Trying direct download..."
            mkdir -p "$INSTALL_DIR"
            cd "$INSTALL_DIR"
            curl -sSL "$REPO/archive/refs/heads/main.tar.gz" | tar xz --strip-components=1
        }
    fi
    log_success "Files downloaded."

    # ─── Create virtualenv ──────────────────────────────────
    log_step "Setting up Python virtual environment..."
    cd "$INSTALL_DIR"

    # نصب python3-venv بر اساس نسخه پایتون
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
    log_info "Installing python3-venv..."
    apt-get install -y -qq "python3.${PY_MINOR}-venv" 2>/dev/null || \
        apt-get install -y -qq python3-venv 2>/dev/null || \
        apt-get install -y "python3-venv" || true

    # ساخت venv
    rm -rf venv
    if ! python3 -m venv venv; then
        log_error "Failed to create virtual environment!"
        log_error "Try manually: apt install python3.${PY_MINOR}-venv"
        exit 1
    fi
    log_success "Virtual environment created."
    ./venv/bin/pip install --upgrade pip -q
    ./venv/bin/pip install -r requirements.txt -q
    log_success "Dependencies installed."

    # ─── Create .env file ───────────────────────────────────
    log_step "Creating configuration file..."
    mkdir -p "$INSTALL_DIR/data"
    cat > "$ENV_FILE" << EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_IDS=$ADMIN_ID
LOG_LEVEL=INFO
EOF
    chmod 600 "$ENV_FILE"
    log_success "Configuration saved to $ENV_FILE"

    # ─── Create systemd service ─────────────────────────────
    log_step "Creating systemd service..."
    cat > "/etc/systemd/system/${SERVICE_NAME}.service" << EOF
[Unit]
Description=ssh-bot-Robexia Telegram SSH Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$INSTALL_DIR/venv/bin/python bot.py
Restart=always
RestartSec=10
StandardOutput=append:$INSTALL_DIR/data/bot.log
StandardError=append:$INSTALL_DIR/data/bot.log

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl start "$SERVICE_NAME"

    # ─── Verify ─────────────────────────────────────────────
    sleep 3
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        echo ""
        echo -e "  ${GREEN}${BOLD}╔══════════════════════════════════════════╗${NC}"
        echo -e "  ${GREEN}${BOLD}║       ✅ Bot installed successfully!     ║${NC}"
        echo -e "  ${GREEN}${BOLD}╚══════════════════════════════════════════╝${NC}"
        echo ""
        echo -e "  ${BOLD}Install directory:${NC} $INSTALL_DIR"
        echo -e "  ${BOLD}Log file:${NC}         $INSTALL_DIR/data/bot.log"
        echo -e "  ${BOLD}Config file:${NC}      $ENV_FILE"
        echo ""
        echo -e "  ${BOLD}Useful commands:${NC}"
        echo -e "  ${CYAN}systemctl status $SERVICE_NAME${NC}   — Check status"
        echo -e "  ${CYAN}systemctl restart $SERVICE_NAME${NC}  — Restart bot"
        echo -e "  ${CYAN}systemctl stop $SERVICE_NAME${NC}     — Stop bot"
        echo -e "  ${CYAN}tail -f $INSTALL_DIR/data/bot.log${NC} — View logs"
        echo ""
        echo -e "  Start a chat with your bot on Telegram and send /start"
        echo ""
    else
        log_error "Bot failed to start! Check logs:"
        echo -e "  ${CYAN}tail -50 $INSTALL_DIR/data/bot.log${NC}"
        exit 1
    fi
}

# ─── Uninstall ─────────────────────────────────────────────
do_uninstall() {
    log_step "Uninstalling $BOT_NAME..."

    if ! check_service_exists; then
        log_warn "Bot is not installed."
        return
    fi

    echo -ne "  ${RED}${BOLD}Are you sure you want to uninstall? (y/N): ${NC}"
    read -r confirm
    if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
        log_info "Uninstall cancelled."
        return
    fi

    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
    systemctl daemon-reload

    echo -ne "  Delete bot files in $INSTALL_DIR? (y/N): "
    read -r del_files
    if [[ "$del_files" == "y" || "$del_files" == "Y" ]]; then
        rm -rf "$INSTALL_DIR"
        log_success "Bot files deleted."
    else
        log_info "Bot files kept at $INSTALL_DIR"
    fi

    log_success "Bot uninstalled successfully."
}

# ─── Update ────────────────────────────────────────────────
do_update() {
    log_step "Updating $BOT_NAME..."

    if [[ ! -d "$INSTALL_DIR" ]]; then
        log_error "Bot is not installed. Please install first (option 1)."
        return
    fi

    # بکاپ از .env
    cp "$ENV_FILE" /tmp/robexia_env_backup 2>/dev/null || true

    log_info "Stopping bot..."
    systemctl stop "$SERVICE_NAME" 2>/dev/null || true

    log_info "Downloading latest version..."
    cd "$INSTALL_DIR"
    if [[ -d ".git" ]]; then
        git pull origin main
    else
        curl -sSL "$REPO/archive/refs/heads/main.tar.gz" | tar xz --strip-components=1
    fi

    # بازیابی .env
    if [[ -f /tmp/robexia_env_backup ]]; then
        cp /tmp/robexia_env_backup "$ENV_FILE"
        chmod 600 "$ENV_FILE"
        rm -f /tmp/robexia_env_backup
    fi

    log_info "Updating dependencies..."
    ./venv/bin/pip install -r requirements.txt -q

    log_info "Starting bot..."
    systemctl start "$SERVICE_NAME"

    sleep 3
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        log_success "Bot updated and running!"
        NEW_VER=$(grep -r "v[0-9]\+\.[0-9]\+" "$INSTALL_DIR/bot.py" 2>/dev/null | head -1 | grep -oP 'v\d+\.\d+' | head -1)
        [[ -n "$NEW_VER" ]] && log_info "Version: $NEW_VER"
    else
        log_error "Bot failed to start after update! Check logs:"
        echo -e "  ${CYAN}tail -50 $INSTALL_DIR/data/bot.log${NC}"
    fi
}

# ─── Main ──────────────────────────────────────────────────
main() {
    print_banner

    # اگر argument داده شده بود مستقیم اجرا کن
    case "$1" in
        install)   do_install;   exit 0 ;;
        uninstall) do_uninstall; exit 0 ;;
        update)    do_update;    exit 0 ;;
    esac

    # منوی تعاملی
    while true; do
        print_menu
        read -r choice
        echo ""
        case "$choice" in
            1) do_install   ;;
            2) do_uninstall ;;
            3) do_update    ;;
            0)
                echo -e "  ${BOLD}Goodbye!${NC}"
                echo ""
                exit 0
                ;;
            *)
                log_error "Invalid option. Please enter 0, 1, 2, or 3."
                ;;
        esac
        echo ""
        echo -ne "  Press Enter to return to menu..."
        read -r
        print_banner
    done
}

main "$@"
