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


def test_ui_model_detail_routes_match_model_absolute_urls() -> None:
    urls = _read_text("pve_sync_plugin/urls.py")
    models = _read_text("pve_sync_plugin/models.py")

    expected_route_names = (
        "pvesyncjob",
        "pvewebhookevent",
        "pveclusterconfig",
        "pvebackupstatus",
    )

    for route_name in expected_route_names:
        assert f'name="{route_name}"' in urls
        assert f"plugins:pve_sync_plugin:{route_name}" in models


def test_vm_button_template_tag_uses_registered_ui_route() -> None:
    tags = _read_text("pve_sync_plugin/templatetags/pve_sync_tags.py")
    urls = _read_text("pve_sync_plugin/urls.py")

    assert "api-trigger" not in tags
    assert "pve_sync/inc/vm_sync_button.html" in tags
    assert 'name="trigger-vm-sync"' in urls


def test_tests_do_not_need_project_root_path_mutation() -> None:
    source = _read_text("test_network_sync.py")

    assert "sys.path.insert" not in source
