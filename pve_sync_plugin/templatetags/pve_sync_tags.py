"""
PVE Sync Plugin Template Tags
Django 模板标签：在 NetBox 其他页面中嵌入按钮
"""

from django import template
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
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
    from django.http import HttpRequest
    from django.contrib.auth.models import User
    
    # 构建 API 触发 URL
    url = reverse('pve_sync_plugin:api-trigger')
    if vm_id:
        url += f'?vm_id={vm_id}'
    
    # 检查权限
    # 实际实现需要根据用户权限判断是否显示
    button_html = f"""
    <form action="{url}" method="post" style="display: inline;" onsubmit="return confirm('确定要触发 PVE 同步吗?');">
        <input type="hidden" name="csrfmiddlewaretoken" value="{{{{ csrf_token }}}}">
        <input type="hidden" name="cluster" value="{cluster}">
        <button type="submit" class="btn btn-primary btn-sm">
            🔄 同步 PVE
        </button>
    </form>
    """
    return button_html


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
            return f'<span class="badge badge-danger" title="最后备份: {backup.last_backup}">备份过期 ({backup.backup_age_days}天)</span>'
        elif backup.last_backup:
            return f'<span class="badge badge-success" title="最后备份: {backup.last_backup}">备份正常</span>'
    except PveBackupStatus.DoesNotExist:
        pass
    
    return '<span class="badge badge-secondary">无备份记录</span>'


@register.inclusion_tag('pve_sync/vm_button.html')
def pve_sync_button_inline(vm, cluster='default'):
    """
    在 VM 详情页嵌入同步按钮
    
    使用示例:
    {% pve_sync_button_inline vm %}
    """
    api_url = reverse('pve_sync_plugin:api-trigger')
    can_sync = vm is not None
    return {
        'vm': vm,
        'api_url': api_url,
        'cluster': cluster,
        'can_sync': can_sync,
    }
