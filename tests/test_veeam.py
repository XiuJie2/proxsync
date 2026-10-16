"""Unit tests for the Veeam collection and alerting logic (no NetBox needed)."""

from __future__ import annotations

import ast
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


def _real_utils_functions(namespace, *names):
    """Run the named definitions from utils.py (which needs Django to import)
    inside ``namespace``, so the stub uses the real job-period logic."""
    tree = ast.parse((PROJECT_ROOT / "pve_sync_plugin" / "utils.py").read_text())
    wanted = [
        node for node in tree.body
        if getattr(node, "name", None) in names
        or (isinstance(node, ast.Assign) and any(getattr(t, "id", None) in names for t in node.targets))
    ]
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "utils.py", "exec"), namespace)


@pytest.fixture
def env(monkeypatch):
    """Load veeam.py with a stub plugin package and a recording Telegram sender."""
    sent = []
    thresholds = {
        "backup_overdue_days_veeam": 7,
        "veeam_job_not_run_hours": 26,
        "veeam_repo_free_percent": 10,
    }
    state = {"telegram": True}

    package = types.ModuleType("pve_sync_plugin")
    package.__path__ = [str(PROJECT_ROOT / "pve_sync_plugin")]
    utils = types.ModuleType("pve_sync_plugin.utils")
    utils.get_threshold = lambda key: thresholds[key]
    _real_utils_functions(
        utils.__dict__, "VEEAM_JOB_PERIODS", "veeam_job_period_days", "veeam_overdue_days", "veeam_not_run_hours"
    )

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


def test_summarize_jobs_counts(env):
    job = env.veeam.summarize_jobs(SAMPLE)[0]
    assert job["result"] == "success"
    assert job["task_counts"]["success"] == 1 and job["task_counts"]["warning"] == 1
    assert job["failed_tasks"] == [{"name": "vm-b", "status": "warning", "reason": "Low space"}]
    assert job["member_count"] is None


def _with_members(result="Success", tasks=None, log=(), retry=False):
    data = copy.deepcopy(SAMPLE)
    job = data["jobs"][0]
    job.update(result=result, retry=retry, log=list(log))
    if tasks is not None:
        job["tasks"] = tasks
    job["members"] = [{"object_id": "o1", "name": "vm-a"}, {"object_id": "o9", "name": "c1:383"}]
    return data


def test_members_mark_in_job_and_leftover_restore_points(env):
    records = env.veeam.build_vm_records(_with_members())
    assert records["o1"]["in_job"] is True
    # Restore points of a job that no longer has the VM.
    assert records["o3"]["in_job"] is False
    # A member without a task in a successful session is left alone.
    assert records["o9"]["result"] == "unknown" and records["o9"]["job_name"] == "Daily PVE"


def test_member_skipped_by_failed_session_is_failed_with_its_log_line(env):
    log = [{"status": "EWarning", "title": "There are no resources to process"},
           {"status": "EFailed", "title": "Failed to find the VM c1:383"}]
    records = env.veeam.build_vm_records(_with_members(result="Failed", tasks=[], log=log))
    assert records["o9"]["result"] == "failed"
    assert records["o9"]["reason"] == "Failed to find the VM c1:383"
    # vm-a is not named: the session's first failure line is used.
    assert records["o1"]["result"] == "failed" and records["o1"]["job_name"] == "Daily PVE"


def test_retry_or_running_session_does_not_fail_missing_members(env):
    for data in (_with_members(result="Failed", tasks=[], retry=True), _with_members(result="None", tasks=[])):
        data["jobs"][0]["state"] = "Working" if not data["jobs"][0]["retry"] else "Stopped"
        records = env.veeam.build_vm_records(data)
        assert records["o9"]["result"] == "unknown"


def test_unreadable_members_leave_in_job_unknown(env):
    records = env.veeam.build_vm_records(SAMPLE)
    assert {rec["in_job"] for rec in records.values()} == {None}


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


def test_mark_jobs_not_run_sends_nothing(env):
    data = copy.deepcopy(SAMPLE)
    data["jobs"][0]["start"] = "2020-01-01T00:00:00+00:00"
    summary = env.veeam.summarize_jobs(data)
    env.veeam.mark_jobs_not_run(summary)
    assert summary[0]["not_run"] is True
    assert env.sent == []


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


def test_job_period_follows_job_name(env):
    utils = sys.modules["pve_sync_plugin.utils"]
    assert utils.veeam_job_period_days("Everyday") == 1
    assert utils.veeam_job_period_days("Backup Job everyDay") == 1
    assert utils.veeam_job_period_days("Every Month") == 31
    assert utils.veeam_job_period_days("Backup Job 1") is None
    assert [utils.veeam_overdue_days(n) for n in ("Everyday", "Everymonth", "Backup Job 1")] == [1, 31, 7]
    env.thresholds["backup_overdue_days_veeam"] = 0
    assert utils.veeam_overdue_days("Everyday") == 0


def test_monthly_job_not_run_after_a_month(env):
    now = datetime.now(timezone.utc)
    job = {"name": "Everymonth", "enabled": True, "result": "success"}
    assert env.veeam._job_not_run({**job, "start": (now - timedelta(days=20)).isoformat()}, now) is False
    assert env.veeam._job_not_run({**job, "start": (now - timedelta(days=33)).isoformat()}, now) is True
    assert env.veeam._job_not_run({**job, "name": "Everyday", "start": (now - timedelta(days=2)).isoformat()}, now) is True
