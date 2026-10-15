"""Unit tests for the Veeam collection and alerting logic (no NetBox needed)."""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Shaped like the output of veeam.COLLECT_SCRIPT on a VBR 13 server.
SAMPLE = {
    "server": {
        "hostname": "VBR01",
        "version": "13.0.1.1071",
        "edition": "Community",
        "license": {"edition": "Community", "type": "Evaluation", "status": "Valid",
                    "expires": None, "licensed": 10.0, "used": 10.0},
    },
    "repositories": [
        {"id": "r1", "name": "nfs-repo", "type": "Nfs", "path": "nfs41://nas:/backup",
         "total": 1000, "free": 50},
        {"id": "r2", "name": "local", "type": "WinLocal", "path": "F:\\Backup",
         "total": 1000, "free": 900},
    ],
    "jobs": [
        {
            "id": "job-1", "name": "Daily PVE", "type": "Proxmox Backup", "enabled": True,
            "session_id": "s1", "result": "Success", "state": "Stopped",
            "start": "2026-10-14T03:00:11.2303480+08:00", "end": "2026-10-14T03:26:06.6652740+08:00",
            "reason": "",
            "tasks": [
                {"object_id": "o1", "name": "vm-a", "status": "Success", "reason": "",
                 "start": "2026-10-14T03:13:55.4378290+08:00", "end": "2026-10-14T03:16:21.7945400+08:00"},
                {"object_id": "o2", "name": "vm-b", "status": "Warning", "reason": "Low space",
                 "start": "2026-10-14T03:14:00+08:00", "end": "2026-10-14T03:18:00+08:00"},
            ],
        },
    ],
    "restore_points": [
        {"object_id": "o1", "name": "vm-a", "time": "2026-10-14T03:13:52.0000000+08:00",
         "type": "Increment", "consistent": True, "backup_name": "vm-a Backup", "points": 19,
         "vmid": 138, "node": "pve01", "pve_cluster_id": "c1"},
        {"object_id": "o3", "name": "vm-c", "time": "2026-10-01T03:00:00+08:00",
         "type": "Full", "consistent": True, "backup_name": "vm-c Backup", "points": 3,
         "vmid": 200, "node": "pve02", "pve_cluster_id": "c1"},
    ],
}


class FakeServer:
    name = "vbr<01>"
    winrm_url = "http://vbr01:5985/wsman"
    username = "u"
    password = "p"
    winrm_verify_ssl = False


@pytest.fixture
def env(monkeypatch):
    """Load veeam.py with a stub plugin package and a recording Telegram sender."""
    sent = []
    thresholds = {
        "veeam_job_not_run_hours": 26,
        "veeam_repo_free_percent": 10,
    }
    state = {"telegram": True}

    package = types.ModuleType("pve_sync_plugin")
    package.__path__ = [str(PROJECT_ROOT / "pve_sync_plugin")]
    utils = types.ModuleType("pve_sync_plugin.utils")
    utils.get_threshold = lambda key: thresholds[key]

    def send_backup_alert(text):
        sent.append(text)
        return state["telegram"]

    utils.send_backup_alert = send_backup_alert
    monkeypatch.setitem(sys.modules, "pve_sync_plugin", package)
    monkeypatch.setitem(sys.modules, "pve_sync_plugin.utils", utils)

    spec = importlib.util.spec_from_file_location(
        "pve_sync_plugin.veeam", PROJECT_ROOT / "pve_sync_plugin" / "veeam.py"
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "pve_sync_plugin.veeam", module)
    spec.loader.exec_module(module)
    return types.SimpleNamespace(veeam=module, sent=sent, thresholds=thresholds, state=state)


def test_parse_time_keeps_server_offset_and_seven_digit_fractions(env):
    parsed = env.veeam.parse_time("2026-10-14T03:00:11.2303480+08:00")
    assert parsed.utcoffset() == timedelta(hours=8)
    assert parsed.astimezone(timezone.utc) == datetime(2026, 10, 13, 19, 0, 11, 230348, tzinfo=timezone.utc)
    assert env.veeam.parse_time(None) is None
    assert env.veeam.parse_time("garbage") is None


@pytest.mark.parametrize(
    ("value", "state", "expected"),
    [
        ("Success", "Stopped", "success"),
        ("Warning", None, "warning"),
        ("Failed", None, "failed"),
        ("InProgress", None, "running"),
        ("None", "Working", "running"),
        ("None", "Stopped", "unknown"),
        (None, None, "unknown"),
    ],
)
def test_normalize_result(env, value, state, expected):
    assert env.veeam.normalize_result(value, state) == expected


def test_build_vm_records_merges_restore_points_and_tasks(env):
    records = env.veeam.build_vm_records(SAMPLE)

    assert set(records) == {"o1", "o2", "o3"}
    a = records["o1"]
    assert (a["vmid"], a["node"], a["job_name"], a["result"]) == (138, "pve01", "Daily PVE", "success")
    assert a["restore_point"].astimezone(timezone.utc).hour == 19
    # Task without restore point: known from the session only.
    assert records["o2"]["result"] == "warning" and records["o2"]["reason"] == "Low space"
    assert records["o2"]["restore_point"] is None
    # Restore point without a task in the last session keeps its backup name.
    assert records["o3"]["result"] == "unknown" and records["o3"]["job_name"] == "vm-c Backup"


def test_build_vm_records_prefers_most_recent_job_run(env):
    data = copy.deepcopy(SAMPLE)
    older = copy.deepcopy(data["jobs"][0])
    older.update(id="job-0", name="Weekly PVE", start="2026-10-01T03:00:00+08:00")
    for task in older["tasks"]:
        task.update(status="Failed", start="2026-10-01T03:10:00+08:00")
    data["jobs"].append(older)

    records = env.veeam.build_vm_records(data)
    assert records["o1"]["job_name"] == "Daily PVE"
    assert records["o1"]["result"] == "success"


def test_summarize_jobs_counts_and_carries_notified_only_for_same_session(env):
    summary = env.veeam.summarize_jobs(SAMPLE)
    job = summary[0]
    assert job["result"] == "success"
    assert job["task_counts"]["success"] == 1 and job["task_counts"]["warning"] == 1
    assert job["failed_tasks"] == [{"name": "vm-b", "status": "warning", "reason": "Low space"}]

    job["notified"] = True
    assert env.veeam.summarize_jobs(SAMPLE, previous=summary)[0]["notified"] is True
    new_session = copy.deepcopy(SAMPLE)
    new_session["jobs"][0]["session_id"] = "s2"
    assert env.veeam.summarize_jobs(new_session, previous=summary)[0]["notified"] is False


def _failed_sample():
    data = copy.deepcopy(SAMPLE)
    data["jobs"][0].update(result="Failed", session_id="s-failed", start=datetime.now(timezone.utc).isoformat())
    data["jobs"][0]["tasks"][0].update(status="Failed", reason="Cannot connect <pve> & retry")
    return data


def test_failed_job_alerts_once_and_escapes_html(env):
    summary = env.veeam.summarize_jobs(_failed_sample())
    assert env.veeam.notify_job_alerts(FakeServer(), summary) == 1
    assert len(env.sent) == 1
    assert "vbr&lt;01&gt;" in env.sent[0]
    assert "Cannot connect &lt;pve&gt; &amp; retry" in env.sent[0]

    again = env.veeam.summarize_jobs(_failed_sample(), previous=summary)
    assert env.veeam.notify_job_alerts(FakeServer(), again) == 0
    assert len(env.sent) == 1


def test_failed_send_is_retried_but_unconfigured_telegram_is_not(env):
    env.state["telegram"] = False  # Telegram rejected the message
    summary = env.veeam.summarize_jobs(_failed_sample())
    env.veeam.notify_job_alerts(FakeServer(), summary)
    assert summary[0]["notified"] is False

    env.state["telegram"] = None  # Telegram not configured
    env.veeam.notify_job_alerts(FakeServer(), summary)
    assert summary[0]["notified"] is True


def test_job_not_run_detection(env):
    now = datetime.now(timezone.utc)
    job = {"enabled": True, "result": "success", "start": (now - timedelta(hours=30)).isoformat()}
    assert env.veeam._job_not_run(job, now) is True
    assert env.veeam._job_not_run({**job, "start": (now - timedelta(hours=2)).isoformat()}, now) is False
    assert env.veeam._job_not_run({**job, "enabled": False}, now) is False
    assert env.veeam._job_not_run({**job, "result": "running"}, now) is False
    assert env.veeam._job_not_run({**job, "start": None}, now) is True
    env.thresholds["veeam_job_not_run_hours"] = 0
    assert env.veeam._job_not_run(job, now) is False


def test_job_not_run_alert_sent_once(env):
    data = copy.deepcopy(SAMPLE)
    data["jobs"][0]["start"] = "2020-01-01T00:00:00+00:00"
    summary = env.veeam.summarize_jobs(data)
    env.veeam.notify_job_alerts(FakeServer(), summary)
    assert summary[0]["not_run"] is True
    assert len([t for t in env.sent if "未依排程執行" in t]) == 1

    again = env.veeam.summarize_jobs(data, previous=summary)
    env.veeam.notify_job_alerts(FakeServer(), again)
    assert len([t for t in env.sent if "未依排程執行" in t]) == 1


def test_repository_alert_once_and_rearms_after_recovery(env):
    info = env.veeam.summarize_server_info(SAMPLE)
    assert info["license"]["used"] == 10.0
    repo = info["repositories"][0]
    assert (repo["free_percent"], repo["used_percent"]) == (5.0, 95.0)

    assert env.veeam.notify_repository_alerts(FakeServer(), info) == 1
    assert info["repositories"][0]["low"] is True and info["repositories"][1]["low"] is False
    assert "nfs-repo" in env.sent[0]

    info2 = env.veeam.summarize_server_info(SAMPLE, previous=info)
    assert env.veeam.notify_repository_alerts(FakeServer(), info2) == 0

    recovered = copy.deepcopy(SAMPLE)
    recovered["repositories"][0]["free"] = 500
    info3 = env.veeam.summarize_server_info(recovered, previous=info2)
    env.veeam.notify_repository_alerts(FakeServer(), info3)
    assert info3["repositories"][0]["alerted"] is False

    info4 = env.veeam.summarize_server_info(SAMPLE, previous=info3)
    assert env.veeam.notify_repository_alerts(FakeServer(), info4) == 1


def test_collect_decodes_output_and_normalizes_single_items(env, monkeypatch):
    data = copy.deepcopy(SAMPLE)
    # ConvertTo-Json emits a lone element as an object instead of a list.
    data["jobs"] = data["jobs"][0]
    data["jobs"]["tasks"] = data["jobs"]["tasks"][0]
    data["restore_points"] = data["restore_points"][0]
    payload = base64.b64encode(json.dumps(data, ensure_ascii=False).encode()).decode()
    stdout = f"noise\n<<<NBVEEAM{payload}NBVEEAM>>>\n"

    client = env.veeam.VeeamWinRMClient(FakeServer())
    monkeypatch.setattr(client, "run_pwsh", lambda script: (stdout, "", 0))
    result = client.collect()
    assert isinstance(result["jobs"], list) and isinstance(result["jobs"][0]["tasks"], list)
    assert isinstance(result["restore_points"], list)


def test_collect_reports_powershell_error(env, monkeypatch):
    stderr = (
        '#< CLIXML\r\n<Objs Version="1.1.0.1"><S S="Error">Import-Module : not found_x000D__x000A_</S>'
        '<S S="Error">At line:1 &lt;x&gt;_x000D__x000A_</S></Objs>'
    )
    client = env.veeam.VeeamWinRMClient(FakeServer())
    monkeypatch.setattr(client, "run_pwsh", lambda script: ("", stderr, 1))
    with pytest.raises(env.veeam.VeeamError, match=r"Import-Module : not found\nAt line:1 <x>"):
        client.collect()


@pytest.fixture
def fields_module():
    if importlib.util.find_spec("django") is None or importlib.util.find_spec("cryptography") is None:
        pytest.skip("django/cryptography not installed")
    from django.conf import settings

    if not settings.configured:
        settings.configure(SECRET_KEY="test-secret-key")
    spec = importlib.util.spec_from_file_location("fields_under_test", PROJECT_ROOT / "pve_sync_plugin" / "fields.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_mask_secrets(fields_module):
    data = {"name": "x", "password": "secret", "token": ""}
    assert fields_module.mask_secrets(data, ["password", "token"]) == {
        "name": "x", "password": "********", "token": "",
    }


def test_secret_encryption_round_trip(fields_module, monkeypatch):
    stored = fields_module.encrypt_secret("NTUB^secret")
    assert stored.startswith("enc:") and "NTUB" not in stored
    assert fields_module.encrypt_secret(stored) == stored  # never double-encrypted
    assert fields_module.decrypt_secret(stored) == "NTUB^secret"
    assert fields_module.decrypt_secret("legacy-plaintext") == "legacy-plaintext"
    assert fields_module.encrypt_secret("") == ""

    from django.conf import settings

    monkeypatch.setattr(settings, "SECRET_KEY", "another-key")
    assert fields_module.decrypt_secret(stored) == ""
