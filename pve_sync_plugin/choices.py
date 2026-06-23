"""Enumerated choices for PVE Sync plugin models."""

from django.db import models


class SyncJobStatusChoices(models.TextChoices):
    STATUS_PENDING = "pending", "Pending"
    STATUS_RUNNING = "running", "Running"
    STATUS_SUCCESS = "success", "Success"
    STATUS_FAILED = "failed", "Failed"
    STATUS_PARTIAL = "partial", "Partial Success"


class SyncJobTriggerChoices(models.TextChoices):
    TRIGGER_MANUAL = "manual", "Manual"
    TRIGGER_SCHEDULED = "scheduled", "Scheduled"
    TRIGGER_WEBHOOK = "webhook", "Webhook"
    TRIGGER_API = "api", "API Call"


class WebhookEventChoices(models.TextChoices):
    VM_STARTED = "vm-started", "VM Started"
    VM_STOPPED = "vm-stopped", "VM Stopped"
    VM_MIGRATED = "vm-migrated", "VM Migrated"
    NODE_ONLINE = "node-online", "Node Online"
    NODE_OFFLINE = "node-offline", "Node Offline"
    BACKUP_DONE = "backup-done", "Backup Completed"
    BACKUP_FAILED = "backup-failed", "Backup Failed"
    CONFIG_CHANGE = "configuration-change", "Configuration Change"


class BackupStatusChoices(models.TextChoices):
    STATUS_SUCCESS = "success", "Success"
    STATUS_FAILED = "failed", "Failed"
    STATUS_RUNNING = "running", "Running"
    STATUS_UNKNOWN = "unknown", "Unknown"


class SyncScheduleChoices(models.TextChoices):
    DISABLED = "disabled", "Disabled"
    HOURLY = "hourly", "Hourly"
    EVERY_3H = "every_3h", "Every 3 hours"
    EVERY_6H = "every_6h", "Every 6 hours"
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"


class VmTaskTypeChoices(models.TextChoices):
    CREATE   = "qmcreate",   "建立 VM"
    DESTROY  = "qmdestroy",  "刪除 VM"
    CLONE    = "qmclone",    "Clone VM"
    MIGRATE  = "qmmigrate",  "遷移 VM"
    RESTORE  = "qmrestore",  "還原 VM"
    BACKUP   = "vzdump",     "備份 VM"
    START    = "qmstart",    "開機"
    STOP     = "qmstop",     "強制關機"
    SHUTDOWN = "qmshutdown", "正常關機"
    REBOOT   = "qmreboot",   "重新開機"


class DriftTypeChoices(models.TextChoices):
    HARDWARE = "hardware", "硬體配置變更"
    MIGRATION = "migration", "VM 遷移"
    IP_CHANGE = "ip_change", "IP 位址變更"
    TAG_CHANGE = "tag_change", "標籤變更"
    VM_CREATED = "vm_created", "VM 新增"
    VM_DELETED = "vm_deleted", "VM 刪除"
    VM_RENAMED = "vm_renamed", "VM 更名"
    DISK_CHANGE = "disk_change", "磁碟配置變更"
    DESCRIPTION_CHANGE = "description_change", "描述變更"
