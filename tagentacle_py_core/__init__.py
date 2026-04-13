"""
Tagentacle Python Core SDK — Node, LifecycleNode, and package utilities.

This is the zero-dependency core of the Tagentacle Python SDK.
Provides:
  - Node: Lightweight bus client with publish/subscribe/service/call_service.
  - LifecycleNode: Full lifecycle-managed node for Agent development.
  - SchemaRegistry: Modular JSON Schema validation for topic payloads.
  - Package utilities: load_pkg_toml, discover_packages, find_workspace_root.
  - Inbox: Agent-local message buffer with per-topic attention levels (Q27).
"""

import asyncio
import json
import logging
import os
import uuid
from enum import Enum
from typing import Callable, Dict, Any, List, Optional

from tagentacle_py_core.schema import SchemaRegistry, SchemaValidationError
from tagentacle_py_core.inbox import Inbox, TopicMode


def _load_secrets_file(path: str) -> Dict[str, str]:
    """Load secrets from a TOML file. Returns dict of key-value pairs."""
    secrets = {}
    if not os.path.isfile(path):
        return secrets
    try:
        try:
            import tomllib
        except ImportError:
            try:
                import tomli as tomllib
            except ImportError:
                # Fallback: simple line parser for KEY = "VALUE" format
                with open(path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip('"').strip("'")
                            secrets[k] = v
                return secrets
        with open(path, "rb") as f:
            data = tomllib.load(f)
        for k, v in data.items():
            if isinstance(v, str):
                secrets[k] = v
    except Exception:
        pass
    return secrets


class Node:
    """Simple API: Lightweight node for general-purpose programs.

    Provides publish(), subscribe(), service(), call_service() for quick
    integration with the Tagentacle bus. No lifecycle management.
    """

    def __init__(self, node_id: str, *, validation_mode: str = "warn"):
        self.node_id = node_id
        self.logger = logging.getLogger(f"tagentacle.{node_id}")
        # Get Daemon URL (default tcp://127.0.0.1:19999)
        url = os.environ.get("TAGENTACLE_DAEMON_URL", "tcp://127.0.0.1:19999")
        if url.startswith("tcp://"):
            url = url[6:]
        self.host, port_str = url.split(":")
        self.port = int(port_str)

        self.reader = None
        self.writer = None
        self._connected = False
        # topic -> List[async-callbacks]
        self.subscribers: Dict[str, List[Callable]] = {}
        # service -> callback
        self.services: Dict[str, Callable] = {}
        # request_id -> Future
        self.pending_requests: Dict[str, asyncio.Future] = {}

        # Schema validation
        self._schema_registry = SchemaRegistry()
        self._validation_mode = validation_mode  # "strict" | "warn" | "off"

        # Auto-load secrets from TAGENTACLE_SECRETS_FILE if set
        self._secrets: Dict[str, str] = {}
        secrets_path = os.environ.get("TAGENTACLE_SECRETS_FILE", "")
        if secrets_path:
            self._secrets = _load_secrets_file(secrets_path)
            if self._secrets:
                self.logger.info(
                    f"Loaded {len(self._secrets)} secret(s) from {secrets_path}"
                )

    @property
    def secrets(self) -> Dict[str, str]:
        """Secrets loaded from TAGENTACLE_SECRETS_FILE."""
        return self._secrets

    @property
    def schema_registry(self) -> SchemaRegistry:
        """The node's schema registry for topic payload validation."""
        return self._schema_registry

    @property
    def validation_mode(self) -> str:
        """Current validation mode: 'strict', 'warn', or 'off'."""
        return self._validation_mode

    @validation_mode.setter
    def validation_mode(self, mode: str) -> None:
        if mode not in ("strict", "warn", "off"):
            raise ValueError(
                f"Invalid validation_mode '{mode}'. Must be 'strict', 'warn', or 'off'."
            )
        self._validation_mode = mode

    def load_schemas(self, workspace_root: Optional[str] = None) -> int:
        """Load topic schemas from workspace interface packages.

        Scans for ``tagentacle.toml`` files with ``[topics]`` sections and
        loads the referenced JSON Schema files.

        Args:
            workspace_root: Workspace root directory.  If ``None``, uses
                ``find_workspace_root()`` to auto-detect.

        Returns:
            Number of schemas loaded.
        """
        if workspace_root is None:
            workspace_root = find_workspace_root()
        if workspace_root is None:
            self.logger.debug("Cannot auto-detect workspace root for schema loading.")
            return 0
        return self._schema_registry.load_from_workspace(workspace_root)

    def _validate_payload(self, topic: str, payload: Any, direction: str) -> None:
        """Validate payload against topic schema according to validation mode."""
        if self._validation_mode == "off":
            return
        error = self._schema_registry.validate(topic, payload)
        if error is None:
            return
        msg = f"[{direction}] Topic '{topic}': {error}"
        if self._validation_mode == "strict":
            raise SchemaValidationError(topic, msg)
        else:  # warn
            self.logger.warning(f"Schema validation warning: {msg}")

    async def connect(self):
        """Connect to Tagentacle Daemon bus, send Register handshake, and register existing subscriptions and services."""
        self.logger.info(
            f"Connecting to Tagentacle Daemon at {self.host}:{self.port}..."
        )
        self.reader, self.writer = await asyncio.open_connection(
            self.host, self.port, limit=4 * 1024 * 1024
        )  # 4 MB buffer for large messages
        self._connected = True
        self.logger.info(f"Node '{self.node_id}' connected.")

        # Send Register handshake first
        await self._send_json({"op": "register", "node_id": self.node_id})

        # Batch register pre-defined subscriptions
        for topic in self.subscribers.keys():
            await self._register_subscription(topic)

        # Batch register pre-defined services
        for service in self.services.keys():
            await self._register_service(service)

    async def disconnect(self):
        """Gracefully disconnect from the Tagentacle Daemon."""
        self._connected = False
        if self.writer:
            try:
                self.writer.close()
                await self.writer.wait_closed()
            except Exception:
                pass
            self.writer = None
            self.reader = None
        self.logger.info(f"Node '{self.node_id}' disconnected.")

    def subscribe(self, topic: str):
        """Decorator: Subscribe to a specified Topic and register an async callback."""

        def decorator(func: Callable):
            if topic not in self.subscribers:
                self.subscribers[topic] = []
                # If already connected, register immediately (for dynamic subscription scenarios)
                if self._connected:
                    asyncio.create_task(self._register_subscription(topic))
            self.subscribers[topic].append(func)
            return func

        return decorator

    async def _register_subscription(self, topic: str):
        """Send subscription message to Daemon."""
        msg = {"op": "subscribe", "topic": topic, "node_id": self.node_id}
        await self._send_json(msg)

    async def publish(self, topic: str, payload: Any):
        """Publish message to a specified Topic.

        If a JSON Schema is registered for the topic and validation_mode
        is not 'off', the payload is validated before sending.
        """
        self._validate_payload(topic, payload, "publish")
        msg = {
            "op": "publish",
            "topic": topic,
            "sender": self.node_id,
            "payload": payload,
        }
        await self._send_json(msg)

    def service(self, service_name: str):
        """Decorator: Provide a specified Service and register an async callback."""

        def decorator(func: Callable):
            if service_name not in self.services:
                self.services[service_name] = func
                # If already connected, register immediately
                if self._connected:
                    asyncio.create_task(self._register_service(service_name))
            return func

        return decorator

    async def _register_service(self, service_name: str):
        """Send service advertisement message to Daemon."""
        msg = {
            "op": "advertise_service",
            "service": service_name,
            "node_id": self.node_id,
        }
        await self._send_json(msg)

    async def call_service(
        self, service_name: str, payload: Any, timeout: float = 30.0
    ):
        """Call service and wait for response with timeout."""
        request_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self.pending_requests[request_id] = future

        msg = {
            "op": "call_service",
            "service": service_name,
            "request_id": request_id,
            "payload": payload,
            "caller_id": self.node_id,
        }
        await self._send_json(msg)

        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except asyncio.TimeoutError:
            self.logger.error(
                f"Service call '{service_name}' timed out after {timeout}s"
            )
            raise
        finally:
            self.pending_requests.pop(request_id, None)

    async def _send_json(self, data: Dict):
        """Send a single line JSON (with newline)."""
        if self.writer and self._connected:
            line = json.dumps(data) + "\n"
            self.writer.write(line.encode())
            await self.writer.drain()

    async def spin(self):
        """Keep running and listen for all push messages from the bus."""
        if not self.reader:
            raise RuntimeError(
                "Node is not connected. Call await node.connect() first."
            )

        try:
            while self._connected and not self.reader.at_eof():
                line = await self.reader.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line.decode())
                    await self._dispatch(msg)
                except json.JSONDecodeError:
                    continue
        except asyncio.CancelledError:
            pass
        finally:
            await self.disconnect()

    async def _dispatch(self, msg: Dict):
        """Dispatch an inbound message to the appropriate handler."""
        op = msg.get("op")

        if op == "message":
            topic = msg.get("topic")
            if topic in self.subscribers:
                # Validate incoming payload before delivering to subscribers
                try:
                    self._validate_payload(topic, msg.get("payload"), "subscribe")
                except SchemaValidationError:
                    return  # strict mode — drop the message
                for callback in self.subscribers[topic]:
                    asyncio.create_task(callback(msg))

        elif op == "call_service":
            service_name = msg.get("service")
            if service_name in self.services:
                asyncio.create_task(self._handle_service_call(msg))

        elif op == "service_response":
            request_id = msg.get("request_id")
            if request_id in self.pending_requests:
                future = self.pending_requests[request_id]
                if not future.done():
                    future.set_result(msg.get("payload"))

        elif op == "ping":
            # Respond to Daemon heartbeat
            await self._send_json({"op": "pong", "node_id": self.node_id})

        elif op == "register_ack":
            self.logger.debug("Register acknowledged by Daemon.")

    async def _handle_service_call(self, msg: Dict):
        """Handle inbound service requests."""
        service_name = msg.get("service")
        request_id = msg.get("request_id")
        caller_id = msg.get("caller_id")
        payload = msg.get("payload")

        handler = self.services.get(service_name)
        if handler:
            try:
                # Call handler function (await if it is async)
                if asyncio.iscoroutinefunction(handler):
                    response_payload = await handler(payload)
                else:
                    response_payload = handler(payload)

                # Send back the response
                resp = {
                    "op": "service_response",
                    "service": service_name,
                    "request_id": request_id,
                    "payload": response_payload,
                    "caller_id": caller_id,
                }
                await self._send_json(resp)
            except Exception as e:
                self.logger.error(f"Error handling service {service_name}: {e}")
                # Send error response back to caller
                resp = {
                    "op": "service_response",
                    "service": service_name,
                    "request_id": request_id,
                    "payload": {"error": str(e)},
                    "caller_id": caller_id,
                }
                await self._send_json(resp)


# --- Lifecycle Node (Node API) ---


class LifecycleState(Enum):
    """Node lifecycle states, inspired by ROS 2 managed nodes."""

    UNCONFIGURED = "unconfigured"
    INACTIVE = "inactive"
    ACTIVE = "active"
    FINALIZED = "finalized"


class LifecycleNode(Node):
    """Node API: Full lifecycle-managed node for Agent development.

    Extends Node with lifecycle hooks (on_configure, on_activate,
    on_deactivate, on_shutdown) and Bringup config injection support.
    Suitable for CLI-launched nodes accepting centralized configuration.

    Lifecycle: UNCONFIGURED -> configure() -> INACTIVE -> activate() -> ACTIVE
                                                       <- deactivate() <-
               INACTIVE/ACTIVE -> shutdown() -> FINALIZED
    """

    def __init__(self, node_id: str, *, validation_mode: str = "warn"):
        super().__init__(node_id, validation_mode=validation_mode)
        self._state = LifecycleState.UNCONFIGURED
        self._config: Dict[str, Any] = {}
        # Merge secrets into config for lifecycle access
        if self._secrets:
            self._config["secrets"] = dict(self._secrets)

    @property
    def state(self) -> LifecycleState:
        """Current lifecycle state."""
        return self._state

    @property
    def config(self) -> Dict[str, Any]:
        """Configuration injected during configure phase."""
        return self._config

    async def _publish_lifecycle_event(self, prev_state: str, new_state: str):
        """Best-effort publish lifecycle transition to /tagentacle/node_events."""
        if not self._connected:
            return
        try:
            await self.publish(
                "/tagentacle/node_events",
                {
                    "event": "lifecycle_transition",
                    "node_id": self.node_id,
                    "prev_state": prev_state,
                    "state": new_state,
                },
            )
        except Exception:
            pass  # best-effort: never break state transitions

    async def configure(self, config: Optional[Dict[str, Any]] = None):
        """Transition: UNCONFIGURED -> INACTIVE. Calls on_configure()."""
        if self._state != LifecycleState.UNCONFIGURED:
            raise RuntimeError(f"Cannot configure from state {self._state.value}")

        self._config = config or {}
        self.logger.info(f"[{self.node_id}] Configuring...")

        services_before = set(self.services.keys())
        subs_before = set(self.subscribers.keys())

        try:
            result = self.on_configure(self._config)
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            self.logger.error(f"[{self.node_id}] on_configure() failed: {e}")
            raise

        # Register any new services/subscriptions added during on_configure
        if self._connected:
            for svc in set(self.services.keys()) - services_before:
                await self._register_service(svc)
            for topic in set(self.subscribers.keys()) - subs_before:
                await self._register_subscription(topic)

        self._state = LifecycleState.INACTIVE
        self.logger.info(f"[{self.node_id}] State -> INACTIVE")
        await self._publish_lifecycle_event("unconfigured", "inactive")

    async def activate(self):
        """Transition: INACTIVE -> ACTIVE. Calls on_activate()."""
        if self._state != LifecycleState.INACTIVE:
            raise RuntimeError(f"Cannot activate from state {self._state.value}")

        self.logger.info(f"[{self.node_id}] Activating...")

        services_before = set(self.services.keys())
        subs_before = set(self.subscribers.keys())

        try:
            result = self.on_activate()
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            self.logger.error(f"[{self.node_id}] on_activate() failed: {e}")
            raise

        # Register any new services/subscriptions added during on_activate
        if self._connected:
            for svc in set(self.services.keys()) - services_before:
                await self._register_service(svc)
            for topic in set(self.subscribers.keys()) - subs_before:
                await self._register_subscription(topic)

        self._state = LifecycleState.ACTIVE
        self.logger.info(f"[{self.node_id}] State -> ACTIVE")
        await self._publish_lifecycle_event("inactive", "active")

    async def deactivate(self):
        """Transition: ACTIVE -> INACTIVE. Calls on_deactivate()."""
        if self._state != LifecycleState.ACTIVE:
            raise RuntimeError(f"Cannot deactivate from state {self._state.value}")

        self.logger.info(f"[{self.node_id}] Deactivating...")

        try:
            result = self.on_deactivate()
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            self.logger.error(f"[{self.node_id}] on_deactivate() failed: {e}")
            raise

        self._state = LifecycleState.INACTIVE
        self.logger.info(f"[{self.node_id}] State -> INACTIVE")
        await self._publish_lifecycle_event("active", "inactive")

    async def shutdown(self):
        """Transition: any -> FINALIZED. Calls on_shutdown()."""
        self.logger.info(f"[{self.node_id}] Shutting down...")

        try:
            result = self.on_shutdown()
            if asyncio.iscoroutine(result):
                await result
        except Exception as e:
            self.logger.error(f"[{self.node_id}] on_shutdown() failed: {e}")

        prev_state = self._state.value
        self._state = LifecycleState.FINALIZED
        await self._publish_lifecycle_event(prev_state, "finalized")
        await self.disconnect()
        self.logger.info(f"[{self.node_id}] State -> FINALIZED")

    async def bringup(self, config: Optional[Dict[str, Any]] = None):
        """Convenience: connect + configure + activate in one call.

        Also auto-loads topic schemas from workspace interface packages.

        Typical usage for CLI-launched nodes:
            node = MyAgent("agent_1")
            await node.bringup({"api_key": "sk-...", "tools": ["search"]})
            await node.spin()
        """
        # Apply validation_mode from config if provided
        cfg = config or {}
        if "validation_mode" in cfg:
            self.validation_mode = cfg["validation_mode"]

        await self.connect()

        # Auto-load schemas from workspace (best-effort, never fails bringup)
        try:
            ws = cfg.get("workspace_root") or find_workspace_root()
            if ws:
                self.load_schemas(ws)
        except Exception as e:
            self.logger.debug(f"Schema auto-load skipped: {e}")

        await self.configure(config)
        await self.activate()

    # --- Override these in subclasses ---

    def on_configure(self, config: Dict[str, Any]):
        """Called during UNCONFIGURED -> INACTIVE transition.

        Use this to initialize resources, load API keys from config,
        set up tool allow-lists, etc. Can be async.
        """
        pass

    def on_activate(self):
        """Called during INACTIVE -> ACTIVE transition.

        Use this to register subscriptions, start background tasks, etc.
        Can be async.
        """
        pass

    def on_deactivate(self):
        """Called during ACTIVE -> INACTIVE transition.

        Use this to pause processing, unsubscribe from topics, etc.
        Can be async.
        """
        pass

    def on_shutdown(self):
        """Called during any -> FINALIZED transition.

        Use this for cleanup: close file handles, save state, etc.
        Can be async.
        """
        pass


# Provide simplified exports
__all__ = [
    "Node",
    "LifecycleNode",
    "LifecycleState",
    "SchemaRegistry",
    "SchemaValidationError",
    "Inbox",
    "TopicMode",
    "load_pkg_toml",
    "discover_packages",
    "find_workspace_root",
]


# --- Bringup Utilities ---


def load_pkg_toml(pkg_dir: str) -> Dict[str, Any]:
    """Load and parse a tagentacle.toml from a package directory.

    Returns a dict with sections as nested dicts:
        {"package": {"name": "...", "version": "..."}, "entry_points": {...}, ...}
    """
    toml_path = os.path.join(pkg_dir, "tagentacle.toml")
    if not os.path.isfile(toml_path):
        raise FileNotFoundError(f"No tagentacle.toml in {pkg_dir}")

    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib
        except ImportError:
            # Fallback: simple section + key=value parser
            return _parse_toml_fallback(toml_path)

    with open(toml_path, "rb") as f:
        return tomllib.load(f)


def _parse_toml_fallback(path: str) -> Dict[str, Any]:
    """Minimal TOML parser for environments without tomllib/tomli."""
    result: Dict[str, Any] = {}
    section = ""
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1]
                if section not in result:
                    result[section] = {}
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                # Try to parse arrays
                if v.startswith("[") and v.endswith("]"):
                    inner = v[1:-1]
                    v = [
                        x.strip().strip('"').strip("'")
                        for x in inner.split(",")
                        if x.strip()
                    ]
                if section:
                    result.setdefault(section, {})[k] = v
                else:
                    result[k] = v
    return result


def discover_packages(root: str, max_depth: int = 5) -> List[Dict[str, Any]]:
    """Discover all Tagentacle packages under a root directory.

    Returns a list of dicts with keys: name, path, has_pyproject, has_venv.
    """
    packages = []
    root = os.path.abspath(root)
    _skip_dirs = {".venv", "__pycache__", "target", "node_modules", "install", ".git"}

    def _scan(directory: str, depth: int):
        if depth > max_depth:
            return
        toml = os.path.join(directory, "tagentacle.toml")
        if os.path.isfile(toml):
            info = load_pkg_toml(directory)
            pkg_name = info.get("package", {}).get("name", os.path.basename(directory))
            packages.append(
                {
                    "name": pkg_name,
                    "path": directory,
                    "has_pyproject": os.path.isfile(
                        os.path.join(directory, "pyproject.toml")
                    ),
                    "has_venv": os.path.isdir(os.path.join(directory, ".venv")),
                }
            )
            return  # Don't recurse into packages

        try:
            for entry in os.scandir(directory):
                if (
                    entry.is_dir()
                    and entry.name not in _skip_dirs
                    and not entry.name.startswith(".")
                ):
                    _scan(entry.path, depth + 1)
        except PermissionError:
            pass

    _scan(root, 0)
    return packages


def find_workspace_root(start: str = ".") -> Optional[str]:
    """Walk up from `start` to find the workspace root.

    The workspace root is the directory containing both `tagentacle/`
    (Rust daemon) and `tagentacle-py/` (Python SDK), or a directory
    with an `install/` folder generated by `tagentacle setup dep --all`.
    """
    directory = os.path.abspath(start)
    for _ in range(10):
        if os.path.isdir(os.path.join(directory, "tagentacle")) and os.path.isdir(
            os.path.join(directory, "tagentacle-py")
        ):
            return directory
        if os.path.isdir(os.path.join(directory, "install")):
            return directory
        parent = os.path.dirname(directory)
        if parent == directory:
            break
        directory = parent
    return None
