"""Veeam Backup & Replication collection over WinRM.

Community Edition answers "License restrictions apply." on the REST API
endpoints for jobs, sessions and restore points, so the data is read by
running the Veeam PowerShell module on the VBR server instead:

* VBR 13's module only loads in PowerShell 7 (``pwsh``) while WinRM starts
  Windows PowerShell 5.1, so the script is run through ``pwsh -File``.
* The script is too long for a command line (8191 chars), so it is uploaded
  in chunks to a temp file first and removed afterwards.
* The result is returned as base64 of UTF-8 JSON so non-ASCII VM names
  survive the console code page.
"""

import base64
import html
import json
import logging
import re
import uuid
from datetime import datetime, timezone as dt_timezone

logger = logging.getLogger(__name__)

# Base64 chars per upload command — keeps each WinRM command well under the
# Windows command-line limit once PowerShell -EncodedCommand inflates it.
_UPLOAD_CHUNK = 2000
_OUTPUT_START = "<<<NBVEEAM"
_OUTPUT_END = "NBVEEAM>>>"

# Runs on the VBR server under pwsh. Times are emitted with the server's
# UTC offset: Veeam's own *Utc properties on Proxmox restore points are wrong.
COLLECT_SCRIPT = r'''
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$WarningPreference = "SilentlyContinue"
Import-Module Veeam.Backup.PowerShell
try { Connect-VBRServer -Server localhost } catch { }

function T($d) {
    if ($d -isnot [datetime]) { return $null }
    # Unfinished sessions report DateTime.MinValue / 1900-01-01.
    if ($d.Year -lt 2000) { return $null }
    return ([DateTimeOffset]$d).ToString("o")
}

$serverInfo = [ordered]@{ hostname = $env:COMPUTERNAME; version = $null; edition = $null; license = $null }
try { $serverInfo.version = "$((Get-VBRBackupServerInfo).Build)" } catch { }
try {
    $lic = Get-VBRInstalledLicense
    $serverInfo.edition = "$($lic.Edition)"
    $serverInfo.license = [ordered]@{
        edition  = "$($lic.Edition)"
        type     = "$($lic.Type)"
        status   = "$($lic.Status)"
        expires  = T $lic.ExpirationDate
        licensed = $lic.InstanceLicenseSummary.LicensedInstancesNumber
        used     = $lic.InstanceLicenseSummary.UsedInstancesNumber
    }
} catch { }

$repos = @(foreach ($r in @(Get-VBRBackupRepository)) {
    $total = $null; $free = $null
    try { $c = $r.GetContainer(); $total = $c.CachedTotalSpace.InBytes; $free = $c.CachedFreeSpace.InBytes } catch { }
    [ordered]@{ id = "$($r.Id)"; name = $r.Name; type = "$($r.Type)"; path = "$($r.FriendlyPath)"; total = $total; free = $free }
})

$jobs = @(foreach ($j in @(Get-VBRJob)) {
    $s = $null
    try { $s = $j.FindLastSession() } catch { }
    $tasks = @()
    if ($s) {
        try {
            $tasks = @(Get-VBRTaskSession -Session $s | ForEach-Object {
                [ordered]@{
                    object_id = "$($_.ObjectId)"
                    name      = $_.Name
                    status    = "$($_.Status)"
                    reason    = "$($_.Info.Reason)"
                    start     = T $_.Progress.StartTimeLocal
                    end       = T $_.Progress.StopTimeLocal
                }
            })
        } catch { }
    }
    [ordered]@{
        id         = "$($j.Id)"
        name       = $j.Name
        type       = "$($j.TypeToString)"
        enabled    = [bool]$j.IsScheduleEnabled
        session_id = if ($s) { "$($s.Id)" } else { $null }
        result     = if ($s) { "$($s.Result)" } else { $null }
        state      = if ($s) { "$($s.State)" } else { $null }
        start      = if ($s) { T $s.CreationTime } else { $null }
        end        = if ($s) { T $s.EndTime } else { $null }
        reason     = if ($s) { "$($s.Info.Reason)" } else { $null }
        tasks      = $tasks
    }
})

$points = @(foreach ($g in @(Get-VBRRestorePoint | Group-Object { "$($_.ObjectId)" })) {
    $rp = $g.Group | Sort-Object CreationTime -Descending | Select-Object -First 1
    $vmid = $null; $node = $null; $pveCluster = $null; $jobName = $null
    # Proxmox jobs keep one child backup per VM, so Get-VBRBackup does not
    # list them by the restore point's BackupId; ask the point for its job.
    try { $jobName = $rp.FindSourceJob().Name } catch { }
    if (-not $jobName) { try { $jobName = $rp.GetBackup().JobName } catch { } }
    try {
        # Proxmox restore points carry the PVE VM config (VMID, node) here.
        $md = ([xml]$rp.AuxDataRaw).SelectSingleNode("//InstanceMetadata")
        if ($md) {
            $cfg = ($md.GetAttribute("UserData") | ConvertFrom-Json).backup_config
            $node = $cfg.proxmox_node_name
            $pveCluster = $cfg.proxmox_cluster_id
            if ("$($cfg.vm_config.Id)" -match ':(\d+)$') { $vmid = [int]$Matches[1] }
        }
    } catch { }
    [ordered]@{
        object_id      = $g.Name
        name           = $rp.VmName
        time           = T $rp.CreationTime
        type           = "$($rp.Type)"
        consistent     = [bool]$rp.IsConsistent
        backup_name    = $jobName
        points         = $g.Count
        vmid           = $vmid
        node           = $node
        pve_cluster_id = $pveCluster
    }
})

$out = [ordered]@{ server = $serverInfo; repositories = $repos; jobs = $jobs; restore_points = $points } | ConvertTo-Json -Depth 8 -Compress
"<<<NBVEEAM" + [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($out)) + "NBVEEAM>>>"
'''


class VeeamError(Exception):
    pass


def _encode_ps(script):
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _clixml_errors(stderr):
    """Pull readable error lines out of PowerShell's CLIXML stderr stream."""
    if "#< CLIXML" not in stderr:
        return stderr.strip()
    lines = re.findall(r'<S S="Error">(.*?)</S>', stderr, re.S)
    text = "".join(lines).replace("_x000D__x000A_", "\n").replace("_x000A_", "\n")
    for entity, char in (("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'"), ("&amp;", "&")):
        text = text.replace(entity, char)
    return text.strip()


class VeeamWinRMClient:
    def __init__(self, server, timeout=600):
        self.server = server
        self.timeout = timeout

    def _protocol(self):
        try:
            import winrm
        except ImportError as exc:
            raise VeeamError("pywinrm 未安裝（需要 pywinrm>=0.5）") from exc
        session = winrm.Session(
            self.server.winrm_url,
            auth=(self.server.username, self.server.password),
            transport="ntlm",
            server_cert_validation="validate" if self.server.winrm_verify_ssl else "ignore",
            read_timeout_sec=self.timeout + 30,
            operation_timeout_sec=self.timeout,
        )
        return session.protocol

    @staticmethod
    def _run(protocol, shell_id, script):
        command_id = protocol.run_command(
            shell_id, "powershell", ["-NoProfile", "-NonInteractive", "-EncodedCommand", _encode_ps(script)]
        )
        try:
            stdout, stderr, rc = protocol.get_command_output(shell_id, command_id)
        finally:
            protocol.cleanup_command(shell_id, command_id)
        return stdout.decode("utf-8", "replace"), stderr.decode("utf-8", "replace"), rc

    def run_pwsh(self, script):
        """Run ``script`` under pwsh on the server; return (stdout, stderr, rc)."""
        protocol = self._protocol()
        try:
            shell_id = protocol.open_shell()
        except Exception as exc:
            raise VeeamError(f"無法透過 WinRM 連線 {self.server.winrm_url}: {exc}") from exc

        path = rf"$env:TEMP\nbveeam_{uuid.uuid4().hex}"
        payload = base64.b64encode(script.encode("utf-8")).decode("ascii")
        try:
            self._run(protocol, shell_id, f'Set-Content -Path "{path}.b64" -Value "" -NoNewline')
            for i in range(0, len(payload), _UPLOAD_CHUNK):
                _, err, rc = self._run(
                    protocol, shell_id,
                    f'Add-Content -Path "{path}.b64" -Value "{payload[i:i + _UPLOAD_CHUNK]}" -NoNewline',
                )
                if rc != 0:
                    raise VeeamError(f"上傳腳本失敗: {_clixml_errors(err)}")
            return self._run(protocol, shell_id, (
                f'$ErrorActionPreference = "Stop"; '
                f'[IO.File]::WriteAllBytes("{path}.ps1", [Convert]::FromBase64String((Get-Content "{path}.b64" -Raw).Trim())); '
                f'$pwsh = (Get-Command pwsh -ErrorAction SilentlyContinue).Source; '
                f'if (-not $pwsh) {{ $pwsh = "$env:ProgramFiles\\PowerShell\\7\\pwsh.exe" }}; '
                f'try {{ & $pwsh -NoProfile -NonInteractive -File "{path}.ps1"; exit $LASTEXITCODE }} '
                f'finally {{ Remove-Item "{path}.ps1", "{path}.b64" -ErrorAction SilentlyContinue }}'
            ))
        finally:
            try:
                protocol.close_shell(shell_id)
            except Exception:
                pass

    def collect(self):
        """Return {'server': {...}, 'jobs': [...], 'restore_points': [...]}."""
        stdout, stderr, rc = self.run_pwsh(COLLECT_SCRIPT)
        match = re.search(re.escape(_OUTPUT_START) + r"(.*?)" + re.escape(_OUTPUT_END), stdout, re.S)
        if rc != 0 or not match:
            detail = _clixml_errors(stderr) or stdout.strip()[-500:] or f"exit code {rc}"
            raise VeeamError(f"Veeam PowerShell 執行失敗: {detail[:1000]}")
        data = json.loads(base64.b64decode(match.group(1)).decode("utf-8"))
        # ConvertTo-Json turns single-element arrays into objects when nested.
        for key in ("jobs", "restore_points", "repositories"):
            data[key] = _as_list(data.get(key))
        for job in data["jobs"]:
            job["tasks"] = _as_list(job.get("tasks"))
        return data


def _as_list(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def parse_time(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        logger.debug("Veeam: cannot parse time %r", value)
        return None


_RESULT_MAP = {
    "success": "success",
    "warning": "warning",
    "failed": "failed",
    "inprogress": "running",
    "pending": "running",
    "working": "running",
    "starting": "running",
    "stopping": "running",
}


def normalize_result(value, state=None):
    """Map Veeam session/task Result/Status values to VeeamResultChoices."""
    if state and str(state).lower() in ("starting", "working", "stopping", "resuming", "postprocessing"):
        return "running"
    return _RESULT_MAP.get(str(value or "").lower(), "unknown")


# ---------------------------------------------------------------------------
# NetBox mapping
# ---------------------------------------------------------------------------

def build_vm_records(data):
    """Merge restore points and last-session tasks into one record per Veeam object.

    Returns {object_id: {name, vmid, node, job_name, result, run_start, run_end,
    reason, restore_point, restore_point_type, consistent}}.
    """
    records = {}
    for rp in data.get("restore_points", []):
        oid = rp.get("object_id")
        if not oid:
            continue
        records[oid] = {
            "name": rp.get("name") or "",
            "vmid": rp.get("vmid"),
            "node": rp.get("node") or "",
            "job_name": rp.get("backup_name") or "",
            "result": "unknown",
            "run_start": None,
            "run_end": None,
            "reason": "",
            "restore_point": parse_time(rp.get("time")),
            "restore_point_type": rp.get("type") or "",
            "consistent": rp.get("consistent"),
        }

    for job in data.get("jobs", []):
        for task in job.get("tasks", []):
            oid = task.get("object_id")
            if not oid:
                continue
            start = parse_time(task.get("start")) or parse_time(job.get("start"))
            rec = records.setdefault(oid, {
                "name": task.get("name") or "",
                "vmid": None,
                "node": "",
                "job_name": "",
                "result": "unknown",
                "run_start": None,
                "run_end": None,
                "reason": "",
                "restore_point": None,
                "restore_point_type": "",
                "consistent": None,
            })
            # A VM can sit in several jobs — keep the most recent run.
            if rec["run_start"] and start and start <= rec["run_start"]:
                continue
            rec.update({
                "job_name": job.get("name") or rec["job_name"],
                "result": normalize_result(task.get("status")),
                "run_start": start,
                "run_end": parse_time(task.get("end")),
                "reason": (task.get("reason") or "").strip(),
            })
    return records


def match_vm(name, vmid, node):
    """Find the NetBox VM for a Veeam object.

    Returns (vm, candidates). ``vm`` is None when nothing or more than one VM
    matches; ``candidates`` lists the VMs that were considered.
    """
    from virtualization.models import VirtualMachine

    qs = VirtualMachine.objects.select_related("device", "cluster")
    if vmid is not None:
        # The PVE sync stores the VMID in serial; VMIDs repeat across clusters.
        candidates = list(qs.filter(serial=str(vmid)))
        if not candidates:
            candidates = list(qs.filter(custom_field_data__vm_id=int(vmid)))
    else:
        candidates = list(qs.filter(name__iexact=name)) if name else []
    if len(candidates) == 1:
        return candidates[0], candidates
    if not candidates:
        return None, candidates

    narrowed = candidates
    if node:
        # Node devices get "-<cluster>" appended when the plain name is taken.
        by_node = [
            c for c in narrowed
            if c.device and (c.device.name == node or c.device.name.startswith(f"{node}-"))
        ]
        if by_node:
            narrowed = by_node
    if len(narrowed) > 1 and name:
        names = {name.lower(), f"{name}-{vmid}".lower()}
        by_name = [c for c in narrowed if c.name.lower() in names]
        if by_name:
            narrowed = by_name
    if len(narrowed) == 1:
        return narrowed[0], candidates
    return None, candidates


def apply_veeam_backup_status(server, data):
    """Write the collected data into VeeamBackupStatus rows for ``server``.

    Returns a dict of counters for the sync job details.
    """
    from .models import VeeamBackupStatus

    records = build_vm_records(data)
    keep_vm_ids = set()
    written = {}  # vm pk -> restore point written this run
    updated = 0
    unmatched = []
    ambiguous = []

    for oid, rec in records.items():
        vm, candidates = match_vm(rec["name"], rec["vmid"], rec["node"])
        if vm is None:
            label = rec["name"] + (f" (VMID {rec['vmid']})" if rec["vmid"] is not None else "")
            if candidates:
                keep_vm_ids.update(c.pk for c in candidates)
                ambiguous.append(f"{label} → NetBox: {', '.join(sorted(c.name for c in candidates))}")
            else:
                unmatched.append(label)
            continue

        keep_vm_ids.add(vm.pk)
        # One VM can show up as several Veeam objects (e.g. re-added to a job);
        # the newest restore point wins.
        if vm.pk in written and (
            rec["restore_point"] is None
            or (written[vm.pk] is not None and rec["restore_point"] <= written[vm.pk])
        ):
            continue
        written[vm.pk] = rec["restore_point"]
        status, _ = VeeamBackupStatus.objects.get_or_create(vm=vm, server=server)
        status.veeam_object_id = oid
        status.job_name = rec["job_name"][:200]
        status.last_result = rec["result"]
        status.last_run_start = rec["run_start"]
        status.last_run_end = rec["run_end"]
        status.last_run_reason = rec["reason"]
        status.last_restore_point = rec["restore_point"]
        status.restore_point_type = rec["restore_point_type"][:50]
        status.restore_point_consistent = rec["consistent"]
        status.save()
        updated += 1

    removed, _ = VeeamBackupStatus.objects.filter(server=server).exclude(vm_id__in=keep_vm_ids).delete()
    return {
        "veeam_objects": len(records),
        "backup_updated": updated,
        "backup_removed": removed,
        "backup_unmatched": unmatched,
        "backup_ambiguous": ambiguous,
    }


def summarize_jobs(data, previous=None):
    """Build the job summary stored on VeeamServerConfig.job_summary.

    ``notified`` carries over for a session that was already reported so a
    failed run is announced once, not on every sync.
    """
    prev_by_id = {j.get("id"): j for j in previous or []}
    summary = []
    for job in data.get("jobs", []):
        counts = {"success": 0, "warning": 0, "failed": 0, "running": 0, "unknown": 0}
        for task in job.get("tasks", []):
            counts[normalize_result(task.get("status"))] += 1
        prev = prev_by_id.get(job.get("id")) or {}
        summary.append({
            "id": job.get("id"),
            "name": job.get("name"),
            "type": job.get("type"),
            "enabled": job.get("enabled"),
            "session_id": job.get("session_id"),
            "result": normalize_result(job.get("result"), job.get("state")) if job.get("session_id") else "unknown",
            "start": job.get("start"),
            "end": job.get("end"),
            "reason": (job.get("reason") or "").strip(),
            "task_counts": counts,
            "failed_tasks": [
                {"name": t.get("name"), "status": normalize_result(t.get("status")), "reason": (t.get("reason") or "").strip()}
                for t in job.get("tasks", [])
                if normalize_result(t.get("status")) in ("failed", "warning")
            ],
            "notified": bool(prev.get("notified")) and prev.get("session_id") == job.get("session_id"),
            "not_run_notified": bool(prev.get("not_run_notified")) and prev.get("session_id") == job.get("session_id"),
        })
    return summary


def _job_not_run(job, now=None):
    """True when an enabled job has not started within the configured hours."""
    from .utils import get_threshold

    hours = get_threshold("veeam_job_not_run_hours")
    if not hours or not job.get("enabled") or job.get("result") == "running":
        return False
    start = parse_time(job.get("start"))
    if start is None:
        return True
    return ((now or datetime.now(dt_timezone.utc)) - start).total_seconds() > hours * 3600


def notify_job_alerts(server, summary):
    """Send Telegram alerts for failed/warning job sessions and for enabled jobs
    that stopped running. Each condition is reported once per session.

    Marks reported entries in ``summary`` (mutated in place); also sets each
    job's ``not_run`` flag for display. Returns the number of alerts sent.
    """
    from .utils import get_threshold, send_backup_alert

    sent = 0
    server_name = html.escape(server.name)
    for job in summary:
        job_name = html.escape(job["name"] or "")
        job["not_run"] = _job_not_run(job)

        if job["not_run"] and not job.get("not_run_notified"):
            last = (job.get("start") or "")[:16].replace("T", " ") or "從未執行"
            text = "\n".join([
                "⏰ <b>Veeam 備份任務未依排程執行</b>",
                "",
                f"🗄️ 伺服器: {server_name}",
                f"📋 任務: <b>{job_name}</b>",
                f"📅 最後一次執行: {last}",
                f"⚠️ 已超過 {get_threshold('veeam_job_not_run_hours')} 小時沒有執行，請確認排程與 Veeam 服務。",
            ])
            result = send_backup_alert(text)
            if result is not False:
                job["not_run_notified"] = True
                sent += bool(result)

        if job["result"] not in ("failed", "warning") or job["notified"]:
            continue
        icon = "❌" if job["result"] == "failed" else "⚠️"
        lines = [
            f"{icon} <b>Veeam 備份任務{'失敗' if job['result'] == 'failed' else '警告'}</b>",
            "",
            f"🗄️ 伺服器: {server_name}",
            f"📋 任務: <b>{job_name}</b>",
            f"📅 執行時間: {(job.get('start') or '?')[:19].replace('T', ' ')}",
        ]
        if job.get("reason"):
            lines.append(f"💬 {html.escape(job['reason'][:300])}")
        if job["failed_tasks"]:
            lines.append("")
            for task in job["failed_tasks"][:10]:
                mark = "❌" if task["status"] == "failed" else "⚠️"
                reason = f" — {html.escape(task['reason'][:150])}" if task["reason"] else ""
                lines.append(f"{mark} {html.escape(task['name'] or '')}{reason}")
            if len(job["failed_tasks"]) > 10:
                lines.append(f"… 還有 {len(job['failed_tasks']) - 10} 台")
        result = send_backup_alert("\n".join(lines))
        if result is not False:
            job["notified"] = True
            sent += bool(result)
    return sent


def summarize_server_info(data, previous=None):
    """Build VeeamServerConfig.server_info: server, license and repositories.

    A repository's ``alerted`` flag carries over while it stays low on space.
    """
    info = dict(data.get("server") or {})
    prev_repos = {r.get("id"): r for r in (previous or {}).get("repositories") or []}
    repos = []
    for repo in data.get("repositories", []):
        total, free = repo.get("total"), repo.get("free")
        percent = round(free * 100 / total, 1) if total and free is not None else None
        repos.append({
            "id": repo.get("id"),
            "name": repo.get("name"),
            "type": repo.get("type"),
            "path": repo.get("path"),
            "total": total,
            "free": free,
            "free_percent": percent,
            "used_percent": round(100 - percent, 1) if percent is not None else None,
            "alerted": bool(prev_repos.get(repo.get("id"), {}).get("alerted")),
        })
    info["repositories"] = repos
    return info


def notify_repository_alerts(server, server_info):
    """Alert once when a repository's free space drops below the threshold;
    re-arm when it recovers. Mutates ``server_info``. Returns alerts sent."""
    from .utils import get_threshold, send_backup_alert

    threshold = get_threshold("veeam_repo_free_percent")
    sent = 0
    for repo in server_info.get("repositories", []):
        percent = repo.get("free_percent")
        low = bool(threshold) and percent is not None and percent < threshold
        repo["low"] = low
        if not low:
            repo["alerted"] = False
            continue
        if repo["alerted"]:
            continue
        text = "\n".join([
            "💾 <b>Veeam Repository 空間不足</b>",
            "",
            f"🗄️ 伺服器: {html.escape(server.name)}",
            f"📦 Repository: <b>{html.escape(repo['name'] or '')}</b>",
            f"📁 {html.escape(repo.get('path') or '')}",
            f"📊 剩餘 {_format_bytes(repo['free'])} / {_format_bytes(repo['total'])}（{percent}%，低於 {threshold}%）",
        ])
        result = send_backup_alert(text)
        if result is not False:
            repo["alerted"] = True
            sent += bool(result)
    return sent


def _format_bytes(value):
    if value is None:
        return "?"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
