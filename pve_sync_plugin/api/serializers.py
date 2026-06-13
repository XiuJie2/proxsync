"""API serializers for PVE Sync plugin models."""

from rest_framework import serializers

from netbox.api.serializers import NetBoxModelSerializer

from pve_sync_plugin.models import (
    PveBackupStatus,
    PveClusterConfig,
    PvePluginSettings,
    PveSyncJob,
    PveWebhookEvent,
)


class PveSyncJobSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:pve_sync_plugin-api:pvesyncjob-detail",
    )
    duration = serializers.FloatField(read_only=True)
    success_rate = serializers.FloatField(read_only=True)

    class Meta:
        model = PveSyncJob
        fields = [
            "id",
            "url",
            "display",
            "cluster_name",
            "status",
            "trigger",
            "start_time",
            "end_time",
            "duration",
            "total_vms",
            "success_vms",
            "failed_vms",
            "success_rate",
            "nodes_offline",
            "config_drifts",
            "tag_changes",
            "resource_alerts",
            "details",
            "triggered_by",
            "created",
            "last_updated",
        ]


class PveWebhookEventSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:pve_sync_plugin-api:pvewebhookevent-detail",
    )

    class Meta:
        model = PveWebhookEvent
        fields = [
            "id",
            "url",
            "display",
            "event_type",
            "node",
            "vmid",
            "vm_name",
            "raw_data",
            "processed",
            "processed_at",
            "processing_error",
            "sync_job",
            "received_at",
            "created",
            "last_updated",
        ]


class PveClusterConfigSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:pve_sync_plugin-api:pveclusterconfig-detail",
    )

    class Meta:
        model = PveClusterConfig
        fields = [
            "id",
            "url",
            "display",
            "name",
            "description",
            "pve_host",
            "pve_user",
            "pve_token",
            "pve_secret",
            "pve_verify_ssl",
            "netbox_site",
            "netbox_cluster_type",
            "netbox_cluster",
            "enabled",
            "sync_schedule",
            "last_sync",
            "last_sync_status",
            "created",
            "last_updated",
        ]
        # Never expose credentials in API responses
        extra_kwargs = {
            "pve_token": {"write_only": True},
            "pve_secret": {"write_only": True},
        }


class PveBackupStatusSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:pve_sync_plugin-api:pvebackupstatus-detail",
    )
    backup_age_days = serializers.IntegerField(read_only=True)
    is_stale = serializers.BooleanField(read_only=True)

    class Meta:
        model = PveBackupStatus
        fields = [
            "id",
            "url",
            "display",
            "vm",
            "last_backup",
            "backup_size",
            "backup_status",
            "backup_path",
            "next_backup",
            "pve_backup_id",
            "backup_age_days",
            "is_stale",
            "created",
            "last_updated",
        ]


class PvePluginSettingsSerializer(NetBoxModelSerializer):
    url = serializers.HyperlinkedIdentityField(
        view_name="plugins-api:pve_sync_plugin-api:pvepluginsettings-detail",
    )

    class Meta:
        model = PvePluginSettings
        fields = [
            "id",
            "url",
            "pve_api_host",
            "pve_api_user",
            "pve_api_verify_ssl",
            "netbox_url",
            "default_cluster_name",
            "default_netbox_cluster",
            "default_site",
            "default_cluster_type",
            "default_node_role",
            "default_node_type",
            "state_db_path",
            "enable_backup_sync",
        ]
        # Never expose secrets via API
