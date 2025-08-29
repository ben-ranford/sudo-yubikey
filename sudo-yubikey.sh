#!/bin/bash
set -euo pipefail

# sudo-yubikey - YubiKey U2F authentication for sudo
# Based on sudo-touchid by Arthur Ginzburg (https://github.com/artginzburg/sudo-touchid)
# Adapted and enhanced by Ben Ranford for YubiKey U2F authentication using pam_u2f.so
# Licensed under EPL-2.0 (Eclipse Public License 2.0)

VERSION=1.0.0
readable_name='[YubiKey U2F for sudo]'
executable_name='sudo-yubikey'

# PAM configuration
BREW_PREFIX=$(brew --prefix 2>/dev/null || echo /opt/homebrew)
PAM_REATTACH_PATH="$BREW_PREFIX/lib/pam/pam_reattach.so"
PAM_REATTACH="auth       optional       $BREW_PREFIX/lib/pam/pam_reattach.so"

# File paths  
SUDO_PATH='/etc/pam.d/sudo'
SUDO_LOCAL_PATH='/etc/pam.d/sudo_local'
LEGACY_PAM_FILE='/etc/pam.d/sudo_yubikey'
U2F_MAPPINGS='/etc/u2f_mappings'

usage() {
  cat <<EOF

  Usage: $executable_name [options]
    Running without options installs YubiKey U2F authentication for sudo.

  Setup Options:
    --setup-keys       Register YubiKey U2F keys for current user
    --install-deps     Install required dependencies (pam-u2f)
    --with-reattach    Include pam_reattach.so for GUI session support
    --require-key      Require YubiKey present (no graceful fallback)
    --install-daemon   Install LaunchDaemon to maintain configuration

  Management Options:
    -d,  --disable     Remove all YubiKey U2F configuration
    -v,  --version     Show version
    -h,  --help        Show this help

  Examples:
    $executable_name                # Install YubiKey U2F authentication
    $executable_name --setup-keys   # Register your YubiKey
    $executable_name --disable      # Remove configuration



EOF
}



# Utility functions

detect_os_version() {
  sw_vers -productVersion | cut -d. -f1
}



check_homebrew_installed() {
  command -v brew >/dev/null 2>&1
}

check_pamu2f_installed() {
  if command -v brew >/dev/null 2>&1; then
    brew list pam-u2f >/dev/null 2>&1
  else
    # Check if pam_u2f.so exists in common locations
    [[ -f /usr/lib/pam/pam_u2f.so ]] || [[ -f /opt/homebrew/lib/pam/pam_u2f.so ]] || [[ -f /usr/local/lib/pam/pam_u2f.so ]]
  fi
}

install_pamu2f() {
  echo "Installing pam-u2f..."
  if command -v brew >/dev/null 2>&1; then
    brew install pam-u2f
  else
    echo "Error: Homebrew not found. Cannot install pam-u2f."
    return 1
  fi
}

install_dependencies() {
  # Check for Homebrew
  if ! check_homebrew_installed; then
    echo "Error: Homebrew is required but not installed."
    echo "Install Homebrew first: https://brew.sh"
    return 1
  fi
  
  # Check and install pam-u2f
  if ! check_pamu2f_installed; then
    echo "pam-u2f not found. Installing pam-u2f..."
    if ! install_pamu2f; then
      echo "Error: Failed to install pam-u2f."
      return 1
    fi
    echo "pam-u2f installed successfully."
  fi
  
  # Verify pamu2fcfg is available after installation
  if ! command -v pamu2fcfg >/dev/null 2>&1; then
    echo "Warning: pamu2fcfg not found in PATH. You may need to restart your shell."
    echo "Try running: source ~/.zshrc (or source ~/.bash_profile)"
  fi
  
  return 0
}

find_pamu2f_path() {
  local pam_path="$BREW_PREFIX/lib/pam/pam_u2f.so"
  if [[ -f "$pam_path" ]]; then
    echo "$pam_path"
  else
    echo "pam_u2f.so"  # Fallback to system search
  fi
}


generate_u2f_auth_line() {
  local require_key="$1"
  local pam_u2f_path
  pam_u2f_path=$(find_pamu2f_path)
  
  if [[ "$require_key" == "true" ]]; then
    echo "auth       sufficient     $pam_u2f_path authfile=/etc/u2f_mappings cue"
  else
    echo "auth       sufficient     $pam_u2f_path authfile=/etc/u2f_mappings cue nouserok"
  fi
}

check_legacy_configuration() {
  [[ -f "$LEGACY_PAM_FILE" ]] || grep -q "pam_u2f.so" "$SUDO_PATH" 2>/dev/null
}

migrate_legacy_configuration() {
  echo "Migrating from legacy YubiKey U2F configuration..."
  
  # Remove legacy PAM file if it exists
  if [[ -f "$LEGACY_PAM_FILE" ]]; then
    sudo rm -f "$LEGACY_PAM_FILE"
    echo "Removed legacy PAM file: $LEGACY_PAM_FILE"
  fi
  
  # Remove U2F and pam_reattach from /etc/pam.d/sudo if present
  if grep -q "pam_u2f.so\|pam_reattach.so" "$SUDO_PATH" 2>/dev/null; then
    sudo cp "$SUDO_PATH" "$SUDO_PATH.bak"
    sudo sed -i '.bak' '/pam_u2f\.so/d' "$SUDO_PATH"
    sudo sed -i '.bak' '/pam_reattach\.so/d' "$SUDO_PATH"
    echo "Removed YubiKey U2F configuration from $SUDO_PATH (backup saved as $SUDO_PATH.bak)"
  fi
  
  echo "Legacy configuration removed successfully."
}

detect_touchid() {
  # Check both sudo and sudo_local for TouchID on all macOS versions
  if grep -q "pam_tid.so" "$SUDO_PATH" 2>/dev/null; then
    return 0
  fi
  
  if [[ -f "$SUDO_LOCAL_PATH" ]] && grep -q "pam_tid.so" "$SUDO_LOCAL_PATH" 2>/dev/null; then
    return 0
  fi
  
  return 1
}



sudo_yubikey_pamlocal_install() {
  local include_reattach="$1"
  local require_key="$2"
  
  echo "Installing YubiKey U2F configuration for macOS 14+"
  
  # Detect sudo-touchid and modify main sudo file for proper priority
  if detect_touchid; then
    echo "🔍 sudo-touchid detected - placing YubiKey above TouchID in main sudo file"
    
    local u2f_line
    u2f_line=$(generate_u2f_auth_line "$require_key")
    
    # Create backup and modify main sudo file
    sudo cp "$SUDO_PATH" "$SUDO_PATH.bak"
    
    local temp_file
    temp_file=$(mktemp)
    
    # Remove existing YubiKey lines, preserve everything else
    grep -v -E "^auth.*pam_u2f|^# YubiKey U2F" "$SUDO_PATH" > "$temp_file"
    
    # Insert YubiKey above TouchID
    {
      head -1 "$temp_file"  # First comment line
      echo "# YubiKey U2F authentication (primary)"
      [[ "$include_reattach" == "true" ]] && echo "$PAM_REATTACH"
      echo "$u2f_line"
      tail -n +2 "$temp_file"  # Rest of the file
    } | sudo tee "$SUDO_PATH" >/dev/null
    
    rm -f "$temp_file"
    
    echo "Modified $SUDO_PATH (backup at $SUDO_PATH.bak)"
    echo "🔗 Authentication flow: YubiKey (primary) → TouchID (fallback) → Password"
    echo "$readable_name enabled successfully for macOS 14+."
    echo ""
    echo "💡 Consider running: sudo-yubikey --install-daemon"
    echo "   This protects your configuration from system updates and other tools"
    return 0
  fi
  
  # Use sudo_local when no TouchID detected
  local u2f_line
  u2f_line=$(generate_u2f_auth_line "$require_key")
  
  local pam_lines=()
  [[ "$include_reattach" == "true" ]] && pam_lines+=("$PAM_REATTACH")
  pam_lines+=("# YubiKey U2F authentication (primary)")
  pam_lines+=("$u2f_line")
  
  # Remove any existing YubiKey lines and prepend new ones
  if [[ -f "$SUDO_LOCAL_PATH" ]]; then
    local existing_content
    existing_content=$(grep -v "pam_u2f.so\|# YubiKey U2F" "$SUDO_LOCAL_PATH" 2>/dev/null || true)
    {
      printf '%s\n' "${pam_lines[@]}"
      [[ -n "$existing_content" ]] && echo "$existing_content"
    } | sudo tee "$SUDO_LOCAL_PATH" >/dev/null
  else
    printf '%s\n' "${pam_lines[@]}" | sudo tee "$SUDO_LOCAL_PATH" >/dev/null
    sudo chmod 644 "$SUDO_LOCAL_PATH"
  fi
  
  echo "Created $SUDO_LOCAL_PATH"
  echo "$readable_name enabled successfully for macOS 14+."
  
  return 0
}

sudo_yubikey_legacy_install() {
  local include_reattach="$1"
  local require_key="$2"
  
  echo "Installing YubiKey U2F configuration for macOS ≤13"
  
  local touchid_detected=false
  if detect_touchid; then
    touchid_detected=true
    echo "🔍 sudo-touchid detected - YubiKey will be configured as primary"
  fi
  
  local u2f_line
  u2f_line=$(generate_u2f_auth_line "$require_key")
  
  # Create backup and modify main sudo file
  sudo cp "$SUDO_PATH" "$SUDO_PATH.bak"
  
  local temp_file
  temp_file=$(mktemp)
  
  # Remove existing YubiKey/reattach, preserve everything else including TouchID
  tail -n +2 "$SUDO_PATH" | grep -v -E "^auth.*(pam_u2f|pam_reattach)" > "$temp_file"
  
  # Add YubiKey at top, preserving TouchID if it exists  
  {
    head -1 "$SUDO_PATH"  # Keep first comment line
    echo "# YubiKey U2F authentication (primary)"
    [[ "$include_reattach" == "true" ]] && echo "$PAM_REATTACH"
    echo "$u2f_line"
    cat "$temp_file"
  } | sudo tee "$SUDO_PATH.new" >/dev/null && sudo mv "$SUDO_PATH.new" "$SUDO_PATH"
  
  rm -f "$temp_file"
  
  echo "Created a backup file at $SUDO_PATH.bak"
  
  if [[ "$touchid_detected" == "true" ]]; then
    echo "🔗 Authentication flow: YubiKey (primary) → TouchID (fallback) → Password"
  fi
  
  echo "$readable_name enabled successfully."
  echo ""
  echo "💡 Consider running: sudo-yubikey --install-daemon"
  echo "   This protects your configuration from system updates and other tools"
  
  return 0
}

check_reattach_available() {
  [[ -f "$PAM_REATTACH_PATH" ]]
}

install_launch_daemon() {
  local plist_path="/Library/LaunchDaemons/com.sudo-yubikey.plist"
  local safe_script_path="/usr/local/bin/sudo-yubikey"
  local current_script
  current_script="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/sudo-yubikey.sh"
  
  # Ensure destination directory exists
  local dest_dir
  dest_dir="$(dirname "$safe_script_path")"
  if [[ ! -d "$dest_dir" ]]; then
    echo "Creating directory $dest_dir..."
    if ! sudo mkdir -p "$dest_dir"; then
      echo "Error: Failed to create directory $dest_dir"
      return 1
    fi
    echo "Directory $dest_dir created successfully."
  fi
  
  # Copy script to safe location
  echo "Installing script to $safe_script_path..."
  sudo cp "$current_script" "$safe_script_path"
  sudo chmod 755 "$safe_script_path"
  
  local plist_content="<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
    <key>Label</key>
    <string>com.sudo-yubikey</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>sleep 60 && $safe_script_path</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/var/log/sudo-yubikey.out</string>
    <key>StandardErrorPath</key>
    <string>/var/log/sudo-yubikey.err</string>
    <key>UserName</key>
    <string>root</string>
</dict>
</plist>"

  echo "$plist_content" | sudo tee "$plist_path" >/dev/null
  sudo launchctl load "$plist_path"
  echo "Script copied to $safe_script_path"
  echo "LaunchDaemon installed at $plist_path (runs once at startup after 60s delay)"
}

setup_u2f_keys() {
  echo "Setting up U2F keys for user: $(whoami)"
  echo
  
  # Install dependencies if not present
  echo "Checking dependencies..."
  if ! install_dependencies; then
    echo "Error: Failed to install required dependencies."
    return 1
  fi
  
  # Check if pamu2fcfg is available
  if ! command -v pamu2fcfg >/dev/null 2>&1; then
    echo "Error: pamu2fcfg not found even after dependency installation."
    echo "You may need to restart your shell and try again."
    return 1
  fi
  
  # Check if U2F mappings file exists
  if [[ ! -f "$U2F_MAPPINGS" ]]; then
    echo "Creating U2F mappings file..."
    sudo touch "$U2F_MAPPINGS"
    sudo chmod 644 "$U2F_MAPPINGS"
  fi
  
  echo "Please insert your YubiKey and press any key when ready..."
  read -r -n 1 -s
  echo
  
  echo "Touch your YubiKey when it blinks..."
  local u2f_output
  if u2f_output=$(pamu2fcfg -u"$(whoami)" 2>/dev/null) && [[ -n "$u2f_output" ]]; then
    # Remove existing entry for this user if it exists
    sudo sed -i ".bak" "/^$(whoami):/d" "$U2F_MAPPINGS"
    
    # Add the new entry
    echo "$u2f_output" | sudo tee -a "$U2F_MAPPINGS" >/dev/null
    
    echo "U2F key registration successful!"
    echo "Entry added to $U2F_MAPPINGS"
  else
    echo "Error: Failed to register U2F key. Make sure your YubiKey supports U2F."
    return 1
  fi
}



sudo_yubikey_install() {
  local include_reattach="$1"
  local require_key="$2"
  local major_version
  major_version=$(detect_os_version)
  
  # Install dependencies if not present
  echo "Checking dependencies..."
  install_dependencies
  echo "Dependencies verified."
  
  # Handle legacy migration inline (only if TouchID not present)
  if check_legacy_configuration && ! detect_touchid; then
    echo "Legacy YubiKey U2F configuration detected. Migrating..."
    migrate_legacy_configuration
  fi
  
  # Check if already installed
  local target_file
  if [[ "$major_version" -ge 14 ]]; then
    target_file="$SUDO_LOCAL_PATH"
  else
    target_file="$SUDO_PATH"
  fi
  
  if [[ -f "$target_file" ]] && grep -q "pam_u2f.so" "$target_file" 2>/dev/null; then
    echo "$readable_name appears to be already installed."
    return 0
  fi
  
  # Check for pam_reattach if requested
  if [[ "$include_reattach" == "true" ]] && ! check_reattach_available; then
    echo "Warning: pam_reattach.so not found. Install with: brew install pam-reattach"
    echo "Continuing without pam_reattach..."
    include_reattach="false"
  fi
  
  if [[ "$major_version" -ge 14 ]]; then
    sudo_yubikey_pamlocal_install "$include_reattach" "$require_key"
  else
    sudo_yubikey_legacy_install "$include_reattach" "$require_key"
  fi
  
  echo "Note: If this is your first run, you need to setup your U2F keys with: sudo-yubikey --setup-keys"
}

sudo_yubikey_disable() {
  # Check what configurations exist
  if [[ ! -f "$SUDO_LOCAL_PATH" ]] && [[ ! -f "$LEGACY_PAM_FILE" ]] && ! grep -q "pam_u2f.so" "$SUDO_PATH" 2>/dev/null; then
    echo "$readable_name seems to be already disabled"
    return 0
  fi
  
  echo "Removing YubiKey U2F configuration..."
  read -p "Continue? (y/N): " -r response || true
  if [[ ! "${response:-}" =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 1
  fi
  
  # Remove sudo_local file (macOS 14+)
  [[ -f "$SUDO_LOCAL_PATH" ]] && sudo rm -f "$SUDO_LOCAL_PATH" && echo "Removed $SUDO_LOCAL_PATH"
  
  # Remove legacy PAM file
  [[ -f "$LEGACY_PAM_FILE" ]] && sudo rm -f "$LEGACY_PAM_FILE" && echo "Removed $LEGACY_PAM_FILE"
  
  # Remove from main sudo file
  if grep -q "pam_u2f.so\|pam_reattach.so" "$SUDO_PATH" 2>/dev/null; then
    sudo cp "$SUDO_PATH" "$SUDO_PATH.bak"
    sudo sed -i '' '/pam_u2f\.so/d; /pam_reattach\.so/d' "$SUDO_PATH"
    echo "Removed YubiKey U2F from $SUDO_PATH (backup: $SUDO_PATH.bak)"
  fi
  
  echo "$readable_name disabled. U2F mappings in $U2F_MAPPINGS preserved."
}

sudo_yubikey() {
  local include_reattach="false"
  local action="install"
  local require_key="false"
  
  while [[ $# -gt 0 ]]; do
    case "$1" in
    -v | --version)
      echo "v$VERSION"
      return 0
      ;;
    -d | --disable)
      action="disable"
      shift
      ;;
    --with-reattach)
      include_reattach="true"
      shift
      ;;
    --setup-keys)
      action="setup-keys"
      shift
      ;;
    --install-deps)
      action="install-deps"
      shift
      ;;
    --require-key)
      require_key="true"
      shift
      ;;
    --install-daemon)
      action="install-daemon"
      shift
      ;;
    -h | --help)
      usage
      return 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      return 1
      ;;
    esac
  done
  
  case "$action" in
  install)
    sudo_yubikey_install "$include_reattach" "$require_key"
    ;;
  disable)
    sudo_yubikey_disable
    ;;
  setup-keys)
    setup_u2f_keys
    ;;
  install-deps)
    install_dependencies
    ;;
  install-daemon)
    install_launch_daemon
    ;;
  esac
}

sudo_yubikey "$@"
