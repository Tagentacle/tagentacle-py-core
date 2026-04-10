# Tagentacle Python Core SDK

> **The ROS of AI Agents** — Zero-dependency core library for the Tagentacle message bus.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

`tagentacle-py-core` is the foundational library pkg of the Tagentacle Python SDK. It provides:

- **`Node`** — Lightweight bus client with `publish()`, `subscribe()`, `service()`, `call_service()`, `spin()`.
- **`LifecycleNode`** — Full lifecycle-managed node for Agent development (ROS 2 managed node pattern).
- **Package utilities** — `load_pkg_toml()`, `discover_packages()`, `find_workspace_root()`.

**Zero external dependencies** — pure Python stdlib (`asyncio`, `json`, `logging`).

## Install

```bash
pip install tagentacle-py-core
```

Or in a uv project:

```bash
uv add tagentacle-py-core
```

## Quick Start

```python
import asyncio
from tagentacle_py_core import Node

async def main():
    node = Node("my_node")
    await node.connect()

    @node.subscribe("/chat/global")
    async def on_message(msg):
        print(f"[{msg['sender']}] {msg['payload']}")

    await node.publish("/chat/global", {"text": "Hello!"})
    await node.spin()

asyncio.run(main())
```

## API

### `Node` (Simple API)

| Method | Description |
|--------|-------------|
| `connect()` | Connect to Tagentacle Daemon |
| `disconnect()` | Gracefully disconnect |
| `publish(topic, payload)` | Publish message to a Topic |
| `subscribe(topic)` | Decorator: register Topic callback |
| `service(name)` | Decorator: register Service handler |
| `call_service(name, payload, timeout)` | RPC-style service call |
| `spin()` | Main loop — dispatch messages |

### `LifecycleNode` (Node API)

Extends `Node` with lifecycle hooks, inspired by ROS 2 managed nodes.

```
UNCONFIGURED → configure() → INACTIVE → activate() → ACTIVE
                                       ← deactivate() ←
INACTIVE/ACTIVE → shutdown() → FINALIZED
```

| Method | Description |
|--------|-------------|
| `configure(config)` | Inject config, call `on_configure()` |
| `activate()` | Transition to ACTIVE, call `on_activate()` |
| `deactivate()` | Transition to INACTIVE, call `on_deactivate()` |
| `shutdown()` | Finalize and disconnect, call `on_shutdown()` |
| `bringup(config)` | Convenience: connect + configure + activate |

## Tagentacle Pkg

This is a Tagentacle **library pkg** (`type = "library"` in `tagentacle.toml`).
Other pkgs declare dependency on it via `[dependencies] tagentacle = ["tagentacle_py_core"]`.

## Package Naming Convention

Tagentacle borrows the multi-layer naming pattern from **ROS 2**, adapted for the Python/pip ecosystem:

| Layer | Convention | Example | ROS 2 Analogy |
|-------|-----------|---------|---------------|
| **Repo directory** | `kebab-case` | `tagentacle-py-core/` | ROS 2 uses `snake_case`; we follow GitHub convention |
| **`tagentacle.toml` name** | `snake_case` | `tagentacle_py_core` | `package.xml` `<name>` |
| **Python module dir** | `snake_case` (= toml name) | `tagentacle_py_core/` | `import turtlesim` |
| **`pyproject.toml` name** (pip) | `kebab-case` | `tagentacle-py-core` | `ros-jazzy-turtlesim` (apt) |

**Golden rules:**

1. **`tagentacle.toml` name = Python module directory = import name.**  
   If `name = "example_agent"`, the module lives in `example_agent/` and you write `import example_agent`.

2. **`-` ↔ `_` mapping** between pip name and import name (same as pip convention and ROS 2 apt↔pkg mapping).  
   `pip install example-agent` → `import example_agent`.

3. **Repo directory** uses kebab-case for GitHub URL readability.  
   The repo `example-agent/` contains the package `example_agent`.

## License

MIT
