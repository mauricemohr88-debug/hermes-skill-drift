# Security boundary

This is a read-only static review assistant, not a security scanner or sandbox. It does
not prove skill safety, compatibility, provenance or correctness. Scanned source and
skills are data: never imported or executed by the scanner. The native Hermes host itself
executes its normal trusted runtime and this plugin, as with any installed Python package.

Use a trusted Git executable and choose trusted repository revisions. The tool disables
Git hooks, external diffs, replacement objects and lazy object fetching for its reads.
Selected Markdown inputs refuse symlinks/special files and enforce file/count/size limits.
This does not defend against a hostile local process racing filesystem state, a malicious
Git executable, kernel compromise or resource exhaustion from arbitrarily adversarial
repositories. Only macOS and Linux are supported in this release.

Snapshots include selected skill text. Reports include excerpts and local paths. Files
are newly created with private permissions and never overwritten; keep them private and
redact before sharing. Hashes detect accidental content changes, not signed approval.

Please use GitHub's private vulnerability reporting on the repository's Security tab for
security-sensitive reports. For ordinary bugs, open an issue with a minimal sanitized
reproduction. Do not disclose secrets or private skill content in public issues.
