# Tagentacle Python Core SDK

> **The ROS of AI Agents** — 零依赖 Tagentacle 消息总线核心库。

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

`tagentacle-py-core` 是 Tagentacle Python SDK 的基础库 pkg，提供：

- **`Node`** — 轻量级总线客户端：`publish()`、`subscribe()`、`service()`、`call_service()`、`spin()`。
- **`LifecycleNode`** — 完整生命周期管理节点，适用于 Agent 开发（ROS 2 托管节点模式）。
- **包管理工具** — `load_pkg_toml()`、`discover_packages()`、`find_workspace_root()`。

**零外部依赖** — 纯 Python 标准库（`asyncio`、`json`、`logging`）。

## 安装

```bash
pip install tagentacle-py-core
```

或在 uv 项目中：

```bash
uv add tagentacle-py-core
```

## 快速开始

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

### `Node`（简单 API）

| 方法 | 说明 |
|------|------|
| `connect()` | 连接到 Tagentacle Daemon |
| `disconnect()` | 优雅断开连接 |
| `publish(topic, payload)` | 发布消息到 Topic |
| `subscribe(topic)` | 装饰器：注册 Topic 回调 |
| `service(name)` | 装饰器：注册 Service 处理器 |
| `call_service(name, payload, timeout)` | RPC 风格的服务调用 |
| `spin()` | 主循环——分发消息 |

### `LifecycleNode`（生命周期 API）

继承 `Node`，添加生命周期钩子，灵感来自 ROS 2 托管节点。

```
UNCONFIGURED → configure() → INACTIVE → activate() → ACTIVE
                                       ← deactivate() ←
INACTIVE/ACTIVE → shutdown() → FINALIZED
```

| 方法 | 说明 |
|------|------|
| `configure(config)` | 注入配置，调用 `on_configure()` |
| `activate()` | 转为 ACTIVE 状态，调用 `on_activate()` |
| `deactivate()` | 转为 INACTIVE 状态，调用 `on_deactivate()` |
| `shutdown()` | 终结并断开连接，调用 `on_shutdown()` |
| `bringup(config)` | 便捷方法：connect + configure + activate |

## Tagentacle Pkg

这是一个 Tagentacle **library pkg**（`tagentacle.toml` 中 `type = "library"`）。
其他 pkg 通过 `[dependencies] tagentacle = ["tagentacle_py_core"]` 声明依赖。

## 包命名规范

Tagentacle 借鉴了 **ROS 2** 的多层命名模式，并适配 Python/pip 生态：

| 层级 | 约定 | 示例 | ROS 2 类比 |
|------|------|------|------------|
| **Repo 目录** | `kebab-case` | `tagentacle-py-core/` | ROS 2 用 `snake_case`；我们遵循 GitHub 惯例 |
| **`tagentacle.toml` name** | `snake_case` | `tagentacle_py_core` | `package.xml` `<name>` |
| **Python module 目录** | `snake_case`（= toml name） | `tagentacle_py_core/` | `import turtlesim` |
| **`pyproject.toml` name**（pip） | `kebab-case` | `tagentacle-py-core` | `ros-jazzy-turtlesim`（apt） |

**黄金法则：**

1. **`tagentacle.toml` name = Python module 目录 = import 名。**  
   若 `name = "example_agent"`，则模块位于 `example_agent/`，代码中写 `import example_agent`。

2. **`-` ↔ `_` 映射**：pip 包名与 import 名之间的转换（同 pip 惯例 & ROS 2 apt↔pkg 映射）。  
   `pip install example-agent` → `import example_agent`。

3. **Repo 目录**使用 kebab-case 以提高 GitHub URL 可读性。  
   仓库 `example-agent/` 包含包 `example_agent`。

## 许可证

MIT
