# Changelog — tagentacle-py-core

All notable changes to **tagentacle-py-core** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.0] - 2026-03-03

### Added
- **Register handshake**: `Node.connect()` now sends `{op: register, node_id}` as the first message after TCP connect. Daemon responds with `register_ack`.
- **Heartbeat response**: `Node._dispatch()` auto-responds to daemon `ping` with `{op: pong, node_id}`.
- **Register ack handling**: `Node._dispatch()` logs `register_ack` at debug level.

## [0.1.0] - 2026-02-26

### Added
- **`Node`** (Simple API): Lightweight bus client — `connect`, `disconnect`, `publish`, `subscribe`, `service`, `call_service`, `spin`.
- **`LifecycleNode`** (Node API): Full lifecycle-managed node — `on_configure` / `on_activate` / `on_deactivate` / `on_shutdown`, `bringup()` convenience method.
- **`LifecycleState`** enum: UNCONFIGURED → INACTIVE → ACTIVE → FINALIZED.
- **Secrets management**: Auto-load `secrets.toml` via `TAGENTACLE_SECRETS_FILE` env var.
- **Package utilities**: `load_pkg_toml()`, `discover_packages()`, `find_workspace_root()`.
- **Tagentacle pkg manifest**: `tagentacle.toml` with `type = "library"`.
- **Zero external dependencies**: Pure Python stdlib.

> Extracted from the monolithic `tagentacle-py` (python-sdk) repo as part of the
> 1-repo-1-pkg architecture migration.
