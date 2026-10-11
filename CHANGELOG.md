# Changelog

## 2.0.0

- Remove unmapped-user authentication bypass and misleading mandatory-key mode.
- Require explicit activation; normal invocation only shows help.
- Preserve native fallback and reject unknown authentication stacks.
- Remove automatic dependency installation, enrollment and boot rewriting.
- Add atomic writes, unique private backups, rollback and configuration locking.
- Require enrollment and explicit module trust checks before activation.
- Add fixture-based logic and failure tests with Linux/macOS CI.
