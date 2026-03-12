# tagentacle-py-core — CI/CD & Development Instructions

## Project Overview

- **Language**: Python ≥ 3.10
- **Build**: `hatchling` (PEP 517)
- **Package**: `tagentacle_py_core` — Node, LifecycleNode, SchemaRegistry, package utilities
- **Version**: Tracked in `pyproject.toml` — must match latest `CHANGELOG.md` release
- **Optional deps**: `jsonschema>=4.0` (for schema validation, install via `[validation]` extra)
- **Tests**: `pytest` (currently no tests — adding them is a priority)

## CI Pipeline

The GitHub Actions workflow (`.github/workflows/ci.yml`) runs on every push and PR:

### Jobs

1. **lint** — `ruff check .` (fast Python linter, replaces flake8/isort/pyflakes)
2. **format** — `ruff format --check .` (formatting consistency)
3. **test** — `pytest` (unit tests)
4. **build** — `pip install .` (verify package builds cleanly)

### Adding Tests

Create `tests/` directory at repo root:

```
tests/
├── test_node.py
├── test_lifecycle.py
├── test_schema.py
└── conftest.py
```

Example test:

```python
import pytest
from tagentacle_py_core import Node

@pytest.mark.asyncio
async def test_node_creation():
    node = Node("test_node")
    assert node.node_id == "test_node"
```

Use `pytest-asyncio` for async tests (most Node operations are async).

### Release Process

1. Update `CHANGELOG.md` with new version section
2. Update `version` in `pyproject.toml` to match
3. Commit: `chore: bump version to X.Y.Z`
4. Tag: `git tag vX.Y.Z`
5. Push: `git push && git push --tags`

## Commit Convention

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new feature (e.g., new Node method)
- `fix:` — bug fix
- `docs:` — documentation only
- `refactor:` — code change that neither fixes a bug nor adds a feature
- `chore:` — tooling, CI, version bumps
- `ci:` — CI configuration changes

## Architecture Notes

- `Node` is the base communication primitive — pub/sub + service RPC over TCP JSON Lines
- `LifecycleNode` adds state machine (unconfigured → inactive → active → finalized)
- `SchemaRegistry` loads JSON Schemas from workspace `tagentacle.toml` files
- Validation modes per-node: `strict` (raise) / `warn` (log) / `off`
- Zero mandatory dependencies — `jsonschema` is optional
- This package has NO dependency on MCP — MCP integration is in `tagentacle-py-mcp`
