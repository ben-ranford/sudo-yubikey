# Security model

This utility configures an alternative sudo authentication method with native
fallback. It is not a mandatory hardware factor. Successful key authentication
can skip Touch ID/password authentication, and sudo timestamp caching can skip
PAM entirely. Missing mappings never intentionally authenticate a user.

Configuration changes require administrator privilege and a retained recovery
shell. PAM files and mappings must be root-controlled. The module's executable
code and all dependent libraries must be trusted in sudo's root context.
User-managed Homebrew modules need explicit `--trust-homebrew-module` acceptance;
that option deliberately relaxes the module trust boundary, not PAM file checks.

The tool accepts only recognized native macOS 14+ authentication layouts. It
rejects custom factors to avoid accidentally bypassing them. Backups support
recovery from errors, but do not replace a tested recovery procedure. Atomic
replacement protects individual files, not a multi-file transaction across power
loss. Locks coordinate this tool's invocations, not unrelated root processes.

The automated suite validates configuration and failure logic. Hardware behavior,
macOS PAM runtime semantics and complete dynamic-library provenance require
administrator validation. Do not deploy without evaluating those limits.

Never commit mapping files, authentication credentials, PINs or private logs.
