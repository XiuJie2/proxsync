"""
PVE Sync Plugin Template Tags
Django 模板标签：在 NetBox 其他页面中嵌入按钮
"""

from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

from ..models import PveBackupStatus

register = template.Library()


@register.simple_tag
def pve_sync_button(vm_id=None, cluster='default'):
    """
    渲染 PVE 同步按钮

    使用示例:
    {% pve_sync_button vm_id=100 %}
    {% pve_sync_button %}
    """
    # 构建 API 触发 URL
    url = reverse("plugins:pve_sync_plugin:trigger-sync")
    if vm_id:
        url += f'?vm_id={vm_id}'

    button_html = f"""
    <form action="{url}" method="post" style="display: inline;" onsubmit="return confirm('确定要触发 PVE 同步吗?');">
        <input type="hidden" name="csrfmiddlewaretoken" value="{{{{ csrf_token }}}}">
        <input type="hidden" name="cluster" value="{cluster}">
        <button type="submit" class="btn btn-primary btn-sm">
            🔄 同步 PVE
        </button>
    </form>
    """
    return mark_safe(button_html)


@register.simple_tag
def pve_backup_status(vm):
    """
    显示 VM 的 PVE 备份状态

    使用示例:
    {% pve_backup_status vm %}
    """
    try:
        backup = PveBackupStatus.objects.get(vm=vm)
        if backup.backup_age_days and backup.backup_age_days > 7:
            return mark_safe(
                f'<span class="badge text-bg-danger" title="最后备份: {backup.last_backup}">'
                f'备份过期 ({backup.backup_age_days}天)</span>'
            )
        elif backup.last_backup:
            return mark_safe(
                f'<span class="badge text-bg-success" title="最后备份: {backup.last_backup}">'
                f'备份正常</span>'
            )
    except PveBackupStatus.DoesNotExist:
        pass

    return mark_safe('<span class="badge text-bg-secondary">无备份记录</span>')


@register.inclusion_tag("pve_sync/inc/vm_sync_button.html")
def pve_sync_button_inline(vm, cluster='default'):
    """
    在 VM 详情页嵌入同步按钮

    使用示例:
    {% pve_sync_button_inline vm %}
    """
    can_sync = vm is not None
    api_url = (
        reverse("plugins:pve_sync_plugin:trigger-vm-sync", args=[vm.pk])
        if can_sync
        else ""
    )
    return {
        'vm': vm,
        'api_url': api_url,
        'cluster': cluster,
        'can_sync': can_sync,
    }
