"""
Tagentacle Schema Registry — modular JSON Schema validation for bus messages.

Discovers JSON Schema definitions from interface packages (any package with
``[topics]`` in its ``tagentacle.toml``) and validates Topic payloads at the
SDK level — both on publish and on subscribe (before the callback fires).

Requires the ``jsonschema`` package for full validation::

    pip install tagentacle-py-core[validation]

If ``jsonschema`` is not installed validation is silently skipped (a one-time
warning is logged).

Usage::

    from tagentacle_py_core.schema import SchemaRegistry

    registry = SchemaRegistry()
    registry.load_from_workspace("/path/to/workspace")

    # Validate a payload
    error = registry.validate("/mcp/directory", payload_dict)
    if error:
        print(error)

Integration with Node is automatic — see ``Node.__init__`` and
``Node.load_schemas()``.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tagentacle.schema")

# ---------------------------------------------------------------------------
# Optional jsonschema import
# ---------------------------------------------------------------------------

try:
    import jsonschema as _jsonschema
    from jsonschema import Draft7Validator  # noqa: F401
    from jsonschema import ValidationError as _ValidationError  # noqa: F401

    _HAS_JSONSCHEMA = True
except ImportError:
    _jsonschema = None  # type: ignore[assignment]
    _HAS_JSONSCHEMA = False

_warned_no_jsonschema = False


def _warn_no_jsonschema() -> None:
    """Emit a one-time warning when jsonschema is missing."""
    global _warned_no_jsonschema
    if not _warned_no_jsonschema:
        logger.warning(
            "jsonschema package not installed — schema validation is disabled. "
            "Install with: pip install tagentacle-py-core[validation]"
        )
        _warned_no_jsonschema = True


# ---------------------------------------------------------------------------
# Validation mode
# ---------------------------------------------------------------------------

VALID_MODES = ("strict", "warn", "off")


class SchemaValidationError(Exception):
    """Raised in strict mode when a payload fails schema validation."""

    def __init__(self, topic: str, message: str):
        self.topic = topic
        self.validation_message = message
        super().__init__(f"[{topic}] {message}")


# ---------------------------------------------------------------------------
# Schema Registry
# ---------------------------------------------------------------------------


class SchemaRegistry:
    """Discovers JSON Schemas from workspace packages and validates payloads.

    Schemas are keyed by **topic name** (e.g. ``/mcp/directory``).

    Discovery flow:
      1. Scan workspace for ``tagentacle.toml`` files.
      2. Parse ``[topics.<topic>]`` sections.
      3. If a section has ``schema = "msg/Foo.json"``, load the JSON Schema
         file relative to the package directory.
      4. Register the schema for that topic.

    This works with *any* package that declares ``[topics]`` — not limited
    to ``type = "interface"`` packages, though that is the convention.
    """

    def __init__(self) -> None:
        self._schemas: Dict[str, dict] = {}  # topic -> raw schema dict
        self._validators: Dict[
            str, Any
        ] = {}  # topic -> Draft7Validator (if jsonschema available)

    # -- Registration --

    def register(self, topic: str, schema: dict) -> None:
        """Manually register a JSON Schema for a topic.

        Args:
            topic: Topic name (e.g. ``/mcp/directory``).
            schema: Raw JSON Schema dict.
        """
        self._schemas[topic] = schema
        if _HAS_JSONSCHEMA:
            # Pre-compile validator for speed
            self._validators[topic] = Draft7Validator(schema)
        logger.debug(f"Schema registered for topic '{topic}'")

    def register_from_file(self, topic: str, schema_path: str) -> None:
        """Load a JSON Schema file and register it for a topic.

        Args:
            topic: Topic name.
            schema_path: Absolute or relative path to a ``.json`` schema file.
        """
        with open(schema_path, "r", encoding="utf-8") as f:
            schema = json.load(f)
        self.register(topic, schema)

    # -- Discovery --

    def load_from_workspace(self, workspace_root: str) -> int:
        """Scan workspace for interface packages and load their topic schemas.

        Walks directories looking for ``tagentacle.toml`` files with
        ``[topics]`` sections.  For each topic with a ``schema`` key,
        loads the referenced JSON Schema file.

        Args:
            workspace_root: Absolute path to the workspace root.

        Returns:
            Number of schemas loaded.
        """
        loaded = 0
        workspace_root = os.path.abspath(workspace_root)
        skip_dirs = {
            ".venv",
            "__pycache__",
            "target",
            "node_modules",
            "install",
            ".git",
            "build",
            "dist",
        }

        def _scan(directory: str, depth: int) -> None:
            nonlocal loaded
            if depth > 5:
                return
            toml_path = os.path.join(directory, "tagentacle.toml")
            if os.path.isfile(toml_path):
                loaded += self._load_from_toml(directory, toml_path)
                return  # Don't recurse into packages

            try:
                for entry in os.scandir(directory):
                    if (
                        entry.is_dir()
                        and entry.name not in skip_dirs
                        and not entry.name.startswith(".")
                    ):
                        _scan(entry.path, depth + 1)
            except PermissionError:
                pass

        _scan(workspace_root, 0)
        if loaded:
            logger.info(
                f"Loaded {loaded} topic schema(s) from workspace '{workspace_root}'"
            )
        return loaded

    def _load_from_toml(self, pkg_dir: str, toml_path: str) -> int:
        """Parse a single tagentacle.toml and register any topic schemas."""
        try:
            try:
                import tomllib
            except ImportError:
                try:
                    import tomli as tomllib  # type: ignore[no-redef]
                except ImportError:
                    return self._load_from_toml_fallback(pkg_dir, toml_path)

            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
        except Exception as e:
            logger.debug(f"Failed to parse {toml_path}: {e}")
            return 0

        return self._register_topics_from_dict(pkg_dir, data)

    def _load_from_toml_fallback(self, pkg_dir: str, toml_path: str) -> int:
        """Minimal fallback parser for [topics."xxx"] sections."""
        # This is rough — only handles the simple case:
        #   [topics."/foo/bar"]
        #   schema = "msg/Foo.json"
        loaded = 0
        current_topic = None
        schema_value = None

        with open(toml_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Match [topics."/some/topic"]
                if line.startswith("[topics."):
                    stripped = line[len("[topics.") :]
                    stripped = stripped.rstrip("]").strip().strip('"').strip("'")
                    current_topic = stripped
                    schema_value = None
                elif current_topic and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k == "schema":
                        schema_value = v
                        schema_abs = os.path.join(pkg_dir, schema_value)
                        if os.path.isfile(schema_abs):
                            try:
                                self.register_from_file(current_topic, schema_abs)
                                loaded += 1
                            except Exception as e:
                                logger.warning(
                                    f"Failed to load schema '{schema_abs}' "
                                    f"for topic '{current_topic}': {e}"
                                )
                        current_topic = None
                elif line.startswith("["):
                    current_topic = None
        return loaded

    def _register_topics_from_dict(self, pkg_dir: str, data: dict) -> int:
        """Extract [topics] from a parsed TOML dict and register schemas."""
        topics = data.get("topics", {})
        if not isinstance(topics, dict):
            return 0

        loaded = 0
        for topic, topic_meta in topics.items():
            if not isinstance(topic_meta, dict):
                continue
            schema_rel = topic_meta.get("schema")
            if not schema_rel:
                continue

            schema_abs = os.path.join(pkg_dir, schema_rel)
            if not os.path.isfile(schema_abs):
                logger.warning(
                    f"Schema file '{schema_abs}' not found "
                    f"for topic '{topic}' (declared in {pkg_dir}/tagentacle.toml)"
                )
                continue

            try:
                self.register_from_file(topic, schema_abs)
                loaded += 1
            except Exception as e:
                logger.warning(
                    f"Failed to load schema '{schema_abs}' for topic '{topic}': {e}"
                )
        return loaded

    # -- Validation --

    def validate(self, topic: str, payload: Any) -> Optional[str]:
        """Validate a payload against the schema for a topic.

        Args:
            topic: Topic name.
            payload: The message payload (dict, list, scalar, etc.).

        Returns:
            An error message string if validation fails, or ``None`` if
            the payload is valid (or no schema is registered for this topic).
        """
        if topic not in self._schemas:
            return None  # No schema → always valid

        if not _HAS_JSONSCHEMA:
            _warn_no_jsonschema()
            return None  # Can't validate without jsonschema

        validator = self._validators.get(topic)
        if validator is None:
            return None

        errors = list(validator.iter_errors(payload))
        if not errors:
            return None

        # Return the first (most relevant) error
        err = errors[0]
        path = (
            ".".join(str(p) for p in err.absolute_path)
            if err.absolute_path
            else "(root)"
        )
        return f"{err.message} (at {path})"

    def validate_or_raise(
        self, topic: str, payload: Any, *, direction: str = "publish"
    ) -> None:
        """Validate and raise ``SchemaValidationError`` on failure.

        Args:
            topic: Topic name.
            payload: The message payload.
            direction: ``"publish"`` or ``"subscribe"`` — included in error
                message for diagnostics.

        Raises:
            SchemaValidationError: If the payload fails validation.
        """
        error = self.validate(topic, payload)
        if error:
            raise SchemaValidationError(
                topic,
                f"Schema validation failed on {direction}: {error}",
            )

    # -- Queries --

    def has_schema(self, topic: str) -> bool:
        """Check whether a schema is registered for a topic."""
        return topic in self._schemas

    def get_schema(self, topic: str) -> Optional[dict]:
        """Return the raw JSON Schema dict for a topic, or ``None``."""
        return self._schemas.get(topic)

    def topics(self) -> List[str]:
        """Return all topics that have schemas registered."""
        return list(self._schemas.keys())

    def __len__(self) -> int:
        return len(self._schemas)

    def __repr__(self) -> str:
        return f"SchemaRegistry({len(self._schemas)} topic(s))"
