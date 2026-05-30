# pve-netbox-sync 项目代理指南

## 项目概述

pve-netbox-sync 是一个**生产级、全功能**的 Proxmox VE 到 NetBox 同步工具，支持：

### 核心同步功能
- ✅ 自动同步 PVE 节点、虚拟机、容器到 NetBox
- ✅ 网络接口、IP 地址、磁盘配置完整同步
- ✅ QEMU Guest Agent 集成（实时 IP 获取）
- ✅ Telegram 实时通知 + 详细日志

### 增强监控与检测（v2.0+）
- 🚨 **节点离线检测** - 节点失联立即告警
- 📊 **节点资源监控** - CPU/内存/磁盘使用率 + 阈值告警
- 🔄 **配置漂移检测** - 自动发现 VM 配置变更（memory/vcpus）
- 🏷️ **标签变更追踪** - 检测 PVE tags 的增删
- ⏱️ **增量同步** - 仅同步配置变更的 VM，性能提升 50%+
- 💾 **状态持久化** - SQLite 存储完整历史（90天自动清理）
- 🔧 **配置热重载** - 修改 config.yaml 无需重启
- 🌐 **多集群支持** - 配置驱动，单实例同步多 PVE 集群

### NetBox 插件模式
- 🔌 **完整插件** - GUI 按钮触发、REST API、Webhook 接收
- 📈 **仪表板** - 内置同步历史、状态查看
- 🔔 **Webhook 实时** - PVE 事件即时响应（VM 启停、迁移）
- 💾 **备份状态同步** - 将 PVE 备份信息同步到 NetBox custom field

## 代码库模式
- **成熟度等级**: Production (已部署、日志管理、错误通知、健康检查)
- **编码标准**: PEP 8、类型注解、结构化日志、可测试
- **架构模式**: 缓存优先、错误恢复、幂等操作、状态驱动

## 可用的实现技能（优先级排序）

1. **subagent-driven-development** - 并行任务分解（首选）
2. **systematic-debugging** - 系统化调试（复杂问题）
3. **verification-before-completion** - 完成前验证（重要）
4. **brainstorming** - 设计讨论（新功能/架构变更）
5. **test-driven-development** - 测试驱动开发（高质量交付）
6. **executing-plans** - 执行已批准的方案

## 工作流程

### 同步流程（增强版）
```
1. 加载配置 (config.yaml + 环境变量)
2. 连接 PVE API（3次重试）
3. 连接 NetBox API
4. 预加载所有 NetBox 对象到缓存（18个缓存字典）
5. 验证必需的自定义字段
6. 批量加载 PVE 数据（节点、VM、Pool）
7. 初始化状态数据库（SQLite）
8. 检查节点状态 → 发送离线告警（如有）
9. 获取节点资源 → 检查阈值 → 发送资源告警（如有）
10. 同步节点 → 创建设备/更新状态
11. 对于每个 VM：
    a. 检测标签变更
    b. 检测配置漂移（memory/vcpus）
    c. 判断是否需要同步（增量：哈希对比）
    d. 如果需要同步：创建/更新 VM + 接口 + IP + 磁盘
    e. 保存配置快照到状态数据库
12. 记录同步日志（成功/失败统计）
13. 发送增强总结通知（包含检测统计）
```

### 关键决策点
- **VM 名称冲突**: 如果同名 VM 已存在于不同集群，添加 `-{vmid}` 后缀
- **IP 冲突**: 记录错误并通知 Telegram，保持已有分配
- **角色来源**: 优先使用 PVE Pool → 默认 "Virtual Machine"/"Container"
- **设备定位**: 通过节点名在 NetBox 中查找现有设备（小写匹配）
- **增量策略**: 基于配置哈希（SHA256 of memory/vcpus/ostype/tags）
- **集群识别**: `name::cluster_id` 双重索引确保唯一性

### 错误处理策略
- **ConnectionError/ReadTimeout**: 最多重试 3 次，指数退避（5秒→10秒→20秒）
- **IP 冲突**: 记录详细日志，发送 Telegram 通知，继续处理下一个 VM
- **自定义字段缺失**: 提前检查，发送创建指引，中止同步
- **配置漂移冲突**: 自动清除冲突 VM 的 `vm_id`，保留当前
- **Agent 网络信息**: 仅在 VM 运行且为 QEMU 类型时获取，异常静默跳过

## 数据模型映射（扩展版）

### 基础映射
| PVE 实体 | NetBox 实体 | 映射字段 |
|---------|-------------|---------|
| Node | Device | name, status (active/offline) |
| VM (qemu/lxc) | Virtual Machine | name, vcpus, memory, status, platform |
| Network interface | vminterface | mac_address, name (netX) |
| Disk | virtual_disk | name, size (MB) |
| Pool | Role | name (vm_role=True) |
| Tag | Tag | name (自动创建) |
| Cluster | Cluster | name, site, type |

### 自定义字段（必需）
| 字段名 | 类型 | 描述 | 用途 |
|--------|------|------|------|
| `vm_id` | integer | Proxmox VM ID | 用作 serial，索引优化 |
| `qemu_agent` | boolean | QEMU Guest Agent 状态 | 判断是否获取实时 IP |
| `ha` | boolean | High Availability | 预留 |
| `replicated` | boolean | VM 是否复制 | 预留 |
| `machine_type` | text | 机器类型 (pc/q35) | 硬件信息 |
| `search_domain` | text | 搜索域名 | 网络配置 |

### 扩展字段（NetBox 插件）
| 字段/模型 | 类型 | 描述 |
|----------|------|------|
| `pve_backup.last_backup` | datetime | 最后备份时间 |
| `pve_backup.backup_size` | integer | 备份大小（字节）|
| `pve_backup.backup_status` | choice | 备份状态（success/failed）|

## 状态数据库 Schema

### 表结构
```sql
-- 同步状态（kv 存储）
sync_state (key TEXT PK, value TEXT, updated_at TIMESTAMP)

-- VM 配置历史（用于漂移检测和增量同步）
vm_config_history (
    vm_id INTEGER,
    cluster_name TEXT,
    sync_time TIMESTAMP,
    config_hash TEXT,  -- SHA256 前16位
    memory INTEGER,
    vcpus INTEGER,
    tags_json TEXT,  -- JSON array
    PK: (vm_id, cluster_name, sync_time)
)

-- 节点状态历史
node_status_history (
    node_name TEXT,
    cluster_name TEXT,
    sync_time TIMESTAMP,
    status TEXT,  -- online/offline
    PK: (node_name, cluster_name, sync_time)
)

-- 节点资源历史（用于趋势分析）
node_resource_history (
    node_name TEXT,
    cluster_name TEXT,
    sync_time TIMESTAMP,
    cpu_usage REAL,
    memory_total, memory_used, memory_percent,
    disk_total, disk_used, disk_percent
)

-- 同步日志（用于审计）
sync_log (
    id INTEGER PK,
    cluster_name TEXT,
    start_time, end_time,
    success_count, total_count, error_count,
    status TEXT  -- running/success/failed
)
```

## 配置系统

### 配置文件 (config.yaml)
```yaml
clusters:
  - name: "production"
    pve:
      host: "pve01.example.com"
      user: "root@pam"
      token: "token-name"
      secret: "token-secret"
      verify_ssl: false
    netbox:
      url: "https://netbox.example.com"
      token: "netbox-token"
    settings:
      cluster_name: "Production Cluster"
      site_name: "Main Datacenter"
      cluster_type: "Proxmox"

telegram:
  enabled: true
  bot_token: "123:ABC"
  chat_id: "-1001234567890"

monitoring:
  node_offline_alert: true
  config_drift_alert: true
  tag_change_alert: true
  resource_alert:
    enabled: true
    memory_threshold: 85  # %
    cpu_threshold: 90     # %
    disk_threshold: 10    # % free space

sync:
  incremental: true       # 增量同步
  force_full_sync: false  # 强制全量
  batch_size: 50         # 批量处理大小

state_db:
  path: /var/lib/pve-sync/state.db
  cleanup_days: 90

plugins:
  netbox_integration: true  # 作为 NetBox 插件运行
```

### 环境变量覆盖（优先级最高）
```bash
PVE_API_HOST=...
PVE_API_USER=...
PVE_API_TOKEN=...
PVE_API_SECRET=...
PVE_API_VERIFY_SSL=false
NB_API_URL=...
NB_API_TOKEN=...
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
WEBHOOK_SECRET=...  # Webhook 签名密钥
```

## 部署架构

### 模式 1: 独立运行（Cron）
```bash
# 安装依赖
pip install -r requirements.txt

# 配置
cp config.yaml.example config.yaml
# 编辑 config.yaml

# 测试运行
python sync.py

# Crontab
*/5 * * * * cd /opt/pve-sync && /usr/bin/python3 sync.py >> /var/log/pve-sync.log 2>&1
```

### 模式 2: NetBox 插件（推荐）
```bash
# 1. 复制插件到 NetBox
cp -r pve_sync_plugin /opt/netbox/plugins/

# 2. 在 NetBox UI 启用插件
#    Admin → Plugins → Enable "pve_sync_plugin"

# 3. 配置插件凭据
#    Admin → Plugins → PVE-NetBox Sync → Configuration

# 4. 运行迁移
cd /opt/netbox
python3 manage.py migrate pve_sync_plugin

# 5. 访问仪表板
#    URL: /plugins/pve-sync/
```

**插件功能**:
- 📊 Web 仪表板（查看同步历史、状态）
- 🔘 GUI 按钮（在 VM 详情页嵌入"同步"按钮）
- 📡 Webhook 接收器（PVE 事件即时触发）
- 🔌 REST API（触发同步、查询状态、备份管理）
- 🔔 集成通知（复用 Telegram 配置）

## 检测能力矩阵

| 检测类型 | 触发条件 | 通知方式 | 数据存储 | 级别 |
|---------|---------|---------|---------|------|
| 节点离线 | `status != 'online'` | Telegram + 日志 | ✅ 历史 | CRITICAL |
| 内存超标 | `memory_percent > 85%` | Telegram | ✅ 历史 | WARNING |
| CPU 超标 | `cpu_usage > 90%` | Telegram | ✅ 历史 | WARNING |
| 磁盘空间 | `free_percent < 10%` | Telegram | ✅ 历史 | CRITICAL |
| VM 标签变更 | tags 增删 | Telegram + 日志 | ✅ 历史 | INFO |
| VM 配置漂移 | memory/vcpus 变化 | Telegram + 日志 | ✅ 历史 | WARNING |
| IP 地址冲突 | 主 IP 被占用 | Telegram + 日志 | ✅ 历史 | ERROR |
| VM 意外状态 | 标签期望 vs 实际 | Telegram | ❌ 仅通知 | WARNING |
| 备份过期 | `last_backup > 7天` | 仪表板标记 | ✅ 状态 | WARNING |

## 性能特性

- **预加载优化**: 所有 NetBox 对象一次性加载，循环内 O(1) 查找
- **增量同步**: 配置哈希对比，仅处理变更 VM（1000 VM → 50 变更 = 95% 减少）
- **批量处理**: PVE 查询批量获取，避免 N+1 问题
- **内存缓存**: 18 个索引字典，峰值内存 ~100MB（1000 VM）
- **并发安全**: SQLite 行级锁，支持多进程同时读取
- **超时控制**: API 30秒超时，防止死锁

## 扩展建议

### 已实现功能（v2.0）
- ✅ 增量同步（仅更新变更的 VM）
- ✅ 节点资源监控（CPU/Memory/Disk）
- ✅ 配置漂移检测（memory/vcpus）
- ✅ 标签变更追踪
- ✅ 状态持久化（SQLite）
- ✅ 配置热重载（watchdog）
- ✅ 多集群支持（配置驱动）
- ✅ Webhook 接收（NetBox 插件）
- ✅ 备份状态同步（NetBox 插件）

### 未来改进（可选）
1. 支持更多 PVE 属性同步（HA 状态、备份详情、快照）
2. 添加 Prometheus 指标导出
3. 实现多租户隔离（不同 NetBox 站点）
4. 添加变更回滚能力（配置历史版本化）
5. 实现配置 diff 可视化（Web UI）
6. 支持 NetBox → PVE 反向同步（标签同步）

## API 参考（NetBox 插件）

### REST 端点

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/plugins/pve-sync/trigger/` | 触发同步 | 认证用户 |
| GET | `/api/plugins/pve-sync/status/{job_id}/` | 查询任务状态 | 认证用户 |
| GET | `/api/plugins/pve-sync/jobs/` | 列出最近任务 | 认证用户 |
| GET | `/api/plugins/pve-sync/backup-status/` | 备份状态列表 | 认证用户 |
| POST | `/api/plugins/pve-sync/backup-status/{vm_id}/` | 更新备份状态 | 认证用户 |
| POST | `/api/plugins/pve-sync/webhook/` | 接收 PVE Webhook | 公开（签名验证） |

### Webhook 事件类型
- `vm-started` - VM 启动
- `vm-stopped` - VM 停止
- `vm-migrated` - VM 迁移
- `node-online` - 节点上线
- `node-offline` - 节点离线
- `backup-done` - 备份完成
- `backup-failed` - 备份失败
- `configuration-change` - 配置变更

## 故障排除

### 常见问题
1. **自定义字段缺失** → 检查 NetBox → Extensions → Custom Fields，确认 6 个字段存在
2. **设备未找到** → 确保 PVE 节点名与 NetBox Device 名称一致（不区分大小写）
3. **IP 冲突错误** → "Cannot reassign IP while designated as primary" → 手动解除主 IP 关系
4. **增量同步不生效** → 首次运行总是全量，检查 `state.db` 是否存在
5. **配置文件不生效** → 检查 YAML 语法，查看日志中的配置加载信息
6. **插件未显示** → 确认 `plugin.py` 的 `name` 与目录名一致，重启 NetBox 服务
7. **Webhook 403** → 验证 `WEBHOOK_SECRET` 配置和签名头 `X-PVE-Signature`

### 调试命令
```bash
# 查看状态数据库
sqlite3 /var/lib/pve-sync/state.db "SELECT * FROM sync_log ORDER BY start_time DESC LIMIT 10;"

# 检查配置加载
python -c "from config import get_config; c=get_config(); print(c.get('telegram.enabled'))"

# 测试 PVE 连接
python -c "from proxmoxer import ProxmoxAPI; pve=ProxmoxAPI('host','user','token','secret'); print(pve.nodes.get())"

# 查看最近同步
tail -f /var/log/pve-sync/sync_*.log
```

## 相关资源
- [NetBox 文档](https://netbox.readthedocs.io/)
- [Proxmox API 参考](https://pve.proxmox.com/pve-docs/api/)
- [pynetbox 文档](https://pynetbox.readthedocs.io/)
- [Django 插件开发](https://docs.djangoproject.com/en/stable/ref/plugins/)

---

*本文档由 Sisyphus AI 分析生成，最后更新: 2025-03-30 | 版本: 2.0*
