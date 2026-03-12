"""
Smoke test for tagentacle-py-core package.

Verifies the package is importable and exports expected symbols.
"""


def test_import_node():
    """Core Node class should be importable."""
    from tagentacle_py_core import Node

    assert Node is not None


def test_import_lifecycle_node():
    """LifecycleNode should be importable."""
    from tagentacle_py_core import LifecycleNode

    assert LifecycleNode is not None


def test_node_creation():
    """Node can be instantiated with a node_id."""
    from tagentacle_py_core import Node

    node = Node("test_node")
    assert node.node_id == "test_node"
