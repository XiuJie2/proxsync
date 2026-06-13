from __future__ import annotations

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read_text(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_core_sync_modules_are_packaged_with_plugin() -> None:
    pyproject = _read_text("pyproject.toml")

    assert 'py-modules = ["config", "state_db", "sync"]' in pyproject


def test_plugin_engine_does_not_mutate_python_path() -> None:
    tree = ast.parse(_read_text("pve_sync_plugin/sync/engine.py"))

    sys_path_mutations = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr in {"insert", "append"}
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "path"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "sys"
    ]

    assert sys_path_mutations == []


def test_webhook_api_route_matches_documented_public_path() -> None:
    api_urls = _read_text("pve_sync_plugin/api/urls.py")
    plugin_views = _read_text("pve_sync_plugin/views.py")

    assert 'path("webhook/", plugin_views.webhook_receiver, name="webhook")' in api_urls
    assert "POST /api/plugins/pve-sync/webhook/" in plugin_views


def test_tests_do_not_need_project_root_path_mutation() -> None:
    source = _read_text("test_network_sync.py")

    assert "sys.path.insert" not in source
