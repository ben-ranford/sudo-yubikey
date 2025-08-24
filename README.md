# sudo-yubikey

YubiKey U2F authentication for sudo on macOS

A focused script to enable YubiKey U2F authentication for sudo commands on macOS. Designed with reliability and enterprise-readiness in mind.

## Features

- 🔐 **YubiKey U2F Authentication** - Use your YubiKey to authenticate sudo commands
- 🔄 **Automatic Dependency Installation** - Installs pam-u2f automatically (requires Homebrew)  
- 🛡️ **Graceful Fallback** - Falls back to password (or optionally, TouchID) when YubiKey not present
- 📱 **GUI Session Support** - Optional pam_reattach.so for GUI applications
- 🔄 **Idempotent** - Safe to run as many times as you feel you need to

*Note: YubiKey is always configured as primary by this utility - TouchID will only prompt if YubiKey fails/isn't present. If you want both (i.e. Yubi as primary and TouchID as secondary), install sudo-touchid first to activate TouchID, and **then** install sudo-yubikey. When sudo-touchid is detected, this script modifies the main `/etc/pam.d/sudo` file to place YubiKey above TouchID. This is necessary because sudo-touchid **always** uses the legacy approach of modifying the system sudo file directly. When sudo-touchid is not present, the script uses the cleaner and more modern `/etc/pam.d/sudo_local` approach for proper separation of concerns.*

## Quick Start

### One-Line Install (Recommended)

```bash
# Install YubiKey authentication, install system command, and register keys  
curl -fsSL https://raw.githubusercontent.com/ben-ranford/sudo-yubikey/main/sudo-yubikey.sh -o /tmp/sudo-yubikey.sh && chmod +x /tmp/sudo-yubikey.sh && /tmp/sudo-yubikey.sh && /tmp/sudo-yubikey.sh --install-daemon && sudo-yubikey --setup-keys
```

### Manual Install

```bash
# Clone the repository
git clone https://github.com/ben-ranford/sudo-yubikey.git
cd sudo-yubikey

# Install YubiKey U2F authentication
./sudo-yubikey.sh

# Register your YubiKey
./sudo-yubikey.sh --setup-keys

# Optional: Install system command and LaunchDaemon (recommended for TouchID users or macOS ≤13)
./sudo-yubikey.sh --install-daemon
```

**Prerequisites**: Homebrew is required.

### Options

```bash
# Basic installation
./sudo-yubikey.sh                  # Install YubiKey U2F authentication
./sudo-yubikey.sh --setup-keys     # Register YubiKey for current user
./sudo-yubikey.sh --disable        # Remove all configuration

# Advanced options
./sudo-yubikey.sh --with-reattach  # Include GUI session support
./sudo-yubikey.sh --require-key    # Require YubiKey (no graceful fallback)
./sudo-yubikey.sh --install-deps   # Install dependencies only
./sudo-yubikey.sh --install-daemon # Install system command & LaunchDaemon protection
```

## Authentication Flow

### YubiKey Only (Default)

```
sudo command → YubiKey U2F prompt → Password fallback
```

### With TouchID Fallback (if sudo-touchid installed)
```
sudo command → YubiKey U2F prompt → TouchID prompt → Password fallback
```

**LaunchDaemon Protection**: When TouchID is detected, the script recommends installing a LaunchDaemon (`--install-daemon`) that runs once at startup (after 60s delay) as root to maintain proper YubiKey → TouchID ordering, preventing sudo-touchid from reordering the configuration.

## Configuration Files

### macOS 14+ (Sonoma and later, provided no sudo-touchid)

- Configuration: `/etc/pam.d/sudo_local`
- YubiKey mappings: `/etc/u2f_mappings`

### macOS 13 and earlier (Or if sudo-touchid is installed)

- Configuration: `/etc/pam.d/sudo`
- YubiKey mappings: `/etc/u2f_mappings`

## Installation Process

The main script performs:

1. **Dependency Check**: Installs Homebrew and pam-u2f if needed
2. **YubiKey Configuration**: Creates YubiKey U2F PAM configuration
3. **Key Registration Reminder**: Prompts user to register YubiKey

<details>
<summary><strong>Troubleshooting</strong></summary>

### YubiKey Not Recognized

```bash
# Re-register YubiKey (use system command if installed, otherwise local script)
sudo-yubikey --setup-keys
# OR if not installed as system command:
./sudo-yubikey.sh --setup-keys
```

### Authentication Issues

```bash
# Reset configuration
sudo-yubikey --disable  # OR ./sudo-yubikey.sh --disable
sudo rm -f /etc/u2f_mappings

# Reinstall
sudo-yubikey            # OR ./sudo-yubikey.sh
sudo-yubikey --setup-keys
```

### Permission Issues

```bash
# Check PAM configuration
sudo cat /etc/pam.d/sudo_local  # macOS 14+
sudo cat /etc/pam.d/sudo        # macOS 13-

# Verify YubiKey mappings
sudo cat /etc/u2f_mappings
```

</details>

## Uninstallation

```bash
# Remove YubiKey configuration
sudo-yubikey --disable  # OR ./sudo-yubikey.sh --disable

# Optional: Remove LaunchDaemon (if installed)
sudo launchctl unload /Library/LaunchDaemons/com.sudo-yubikey.plist
sudo rm -f /Library/LaunchDaemons/com.sudo-yubikey.plist
sudo rm -f /usr/local/bin/sudo-yubikey

# Optional: Remove YubiKey mappings
sudo rm -f /etc/u2f_mappings

# Optional: Uninstall pam-u2f
brew uninstall pam-u2f
```

## Philosophy

This tool follows the following principles. If contributing, I'd appreciate it if you could also pay particular attention to these:

- **Primary Focus**: YubiKey U2F authentication with essential maintenance tools
- **Separation of Concerns**: TouchID is handled by separate tools
- **Idempotent Operations**: Safe to run multiple times
- **Fail-Fast Operation**: Quick error detection with comprehensive user feedback
- **Dependency Management**: Automatic installation of required components
- **Clean Code**: Readable, maintainable, and well-documented

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request
6. Have copilot do a first pass to find anything silly

## License

This project is licensed under the Eclipse Public License 2.0 (EPL-2.0).

## Acknowledgments

- [Arthur Ginzburg](https://github.com/artginzburg) for the original sudo-touchid script
- [Yubico](https://developers.yubico.com/pam-u2f/) for the pam-u2f module
