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
    EVERY_6H = "every_6h", "Every 6 hours"
    DAILY = "daily", "Daily"
    WEEKLY = "weekly", "Weekly"
