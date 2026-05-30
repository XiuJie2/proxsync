# PVE-NetBox 同步工具 - 扩展规划

## 📊 当前架构分析

### 核心类结构
```python
class OptimizedPVEToNetBoxSync:
    - __init__(): 初始化缓存、Telegram配置
    - connect_pve(): 连接PVE API (重试3次)
    - connect_netbox(): 连接NetBox API
    - load_all_netbox_objects(): 预加载所有NetBox对象到缓存
    - check_required_custom_fields(): 验证必要字段
    - load_pve_data(): 批量加载PVE节点、VM、Pool
    - sync_pve_nodes_to_netbox(): 同步节点 → 设备
    - sync_pve_virtual_machines(): 同步VM → VM + 接口 + IP + 磁盘
    - process_virtual_machine(): 单个VM处理逻辑
    - send_telegram_notification(): Telegram通知
```

### 现有缓存设计
- **NetBox缓存** (`nb_cache`): 18个缓存字典
  - `devices` - 设备名小写 → Device
  - `virtual_machines_by_serial` - VM ID → VM (主索引)
  - `virtual_machines_by_name` - "name::cluster_id" → VM (次索引)
  - `vm_interfaces`, `ip_addresses`, `tags`, `roles`, `clusters`, 等

- **PVE缓存** (`pve_cache`):
  - `nodes` - 节点列表
  - `vms_by_node` - 节点名 → VM列表
  - `pools` - Pool ID → Pool信息

### 关键发现
1. **无状态设计**: 每次运行都是fresh start，没有与上次同步状态的比较
2. **全量同步**: 所有VM都会处理，即使未变更
3. **单集群硬编码**: `get_or_create_cluster("Proxmox Cluster", ...)` 固定名称
4. **单次执行模式**: 无webhook，完全依赖cron轮询
5. **配置来源**: 仅环境变量，无配置文件热加载
6. **状态映射**: 节点状态只有 `online` → `active`, else → `offline`

---

## 🎯 扩展功能列表（优先级排序）

### P1 - 立即实现（高价值、低复杂度）

#### 1. ✅ 节点离线检测
**问题**: 节点离线只更新NetBox状态，无告警
**方案**: 在 `sync_pve_nodes_to_netbox` 中添加检测
```python
for node in self.pve_cache['nodes']:
    node_name = node['node']
    device = self.nb_cache['devices'].get(node_name.lower())
    
    # 新增：离线检测
    if node['status'] == 'offline':
        self.send_telegram_notification(
            f"🚨 <b>PVE節點離線</b>\n"
            f"🖥️ 節點: {node_name}\n"
            f"📅 時間: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"❌ 狀態: offline"
        )
    
    # 原有逻辑继续...
```
**影响**: 无，仅添加通知
**文件**: `sync.py` - modify `sync_pve_nodes_to_netbox()`

#### 2. ✅ 配置漂移检测
**问题**: 无法发现PVE配置变更（内存/CPU/标签）
**方案**: 存储上次VM配置，对比关键字段
**数据存储**: 在 NetBox custom_fields 中添加 `last_sync_config_hash`
**检测字段**: `memory`, `vcpus`, `tags`, `description`, `ostype`
**通知格式**:
```
🔄 <b>VM 配置漂移檢測</b>
名稱: vm01 (ID: 100)
• memory: 4096 → 8192 MB
• tags: ['prod'] → ['prod', 'webserver']
```
**影响**: 需要修改 `process_virtual_machine`，读取历史配置
**文件**: `sync.py` - modify `process_virtual_machine()`

---

### P2 - 短期实现（1-2周，中等复杂度）

#### 3. 🔄 增量同步
**问题**: 每次全量处理所有VM，浪费资源
**方案**: 使用 PVE 的 `qm status` 的 `modify_ts` 字段或 VM 的配置modify时间
**策略**:
- 在 `load_pve_data()` 中获取每个 VM 的 `modify_ts` (last modification timestamp)
- 查询 NetBox 存储的 `last_sync_timestamp` custom field
- 只处理 `modify_ts > last_sync_timestamp` 的 VM
**状态存储**: VM custom field `last_sync_timestamp` (格式: ISO 8601)
**注意**: 首次运行必须全量同步，设置标志 `force_full_sync=True` 如果无记录
**影响**: 修改 `sync_pve_virtual_machines()` 循环，添加时间过滤
**文件**: `sync.py` - modify `load_pve_data()` + `sync_pve_virtual_machines()`

#### 4. 📊 节点资源监控
**问题**: 只知道节点在线/离线，无资源使用率
**方案**: 获取 PVE 节点资源指标
**API**: `self.pve_api.nodes(node_name).status.get()` 返回:
```json
{
  "node": "pve01",
  "status": "online",
  "uptime": 1234567,
  "memory": {
    "total": 33554432,
    "used": 26843546,
    "free": 6710896
  },
  "cpu": 0.45,
  "disk": [...]
}
```
**检测阈值**:
- 内存使用率 > 85% → WARNING
- CPU 使用率 > 90% → WARNING
- 存储空间 < 10% 剩余 → CRITICAL
**通知**: 在节点状态更新后发送
**影响**: 扩展 `sync_pve_nodes_to_netbox()`，添加资源指标获取
**文件**: `sync.py` - modify `sync_pve_nodes_to_netbox()`

#### 5. 🏷️ 标签变更追踪
**问题**: PVE tags 会覆盖 NetBox tags，但无变更历史
**方案**: 对比新旧标签集合，报告增删
**存储**: 在 `process_virtual_machine` 中记录旧标签 (`old_tags` custom field 或读取现有 tags)
**联动**: 与配置漂移检测合并通知
**影响**: 修改标签处理逻辑（line 956-977）
**文件**: `sync.py` - modify `process_virtual_machine()`

---

### P3 - 中期实现（1月+, 较高复杂度）

#### 6. 🌐 多集群支持
**问题**: 硬编码 "Proxmox Cluster"，无法同步多个集群
**方案**: 支持配置文件定义多个 PVE 端点
**配置结构** (YAML):
```yaml
clusters:
  - name: "Production"
    pve:
      host: "pve-prod-01.example.com"
      user: "root@pam"
      token: "token1"
      verify_ssl: false
    netbox:
      url: "https://netbox.example.com"
      token: "netbox-token"
    site: "Production DC"
    cluster_type: "Proxmox"

  - name: "Development"
    pve:
      host: "pve-dev-01.example.com"
      ...
```
**主循环变更**:
```python
def sync_multi_clusters(self, config_file: str):
    for cluster_config in config['clusters']:
        self.init_pve_api(cluster_config['pve'])
        self.init_netbox_api(cluster_config['netbox'])
        self.sync()  # 复用现有单集群逻辑
```
**影响**: 重构 `__init__`, `connect_pve`, `connect_netbox` 支持参数传入
**新文件**: `config.yaml` 示例, `multi_cluster_sync.py`
**文件**: 创建新 `multi_cluster_sync.py`, 修改现有 `sync.py` 可配置化

#### 7. 🔌 Webhook 触发模式
**问题**: 无法实时响应 PVE 事件，依赖cron延迟
**方案**: 创建独立 webhook receiver 服务
**技术栈**: FastAPI (异步、高性能)
**Webhook 端点**:
```
POST /webhook/pve/event
{
  "event": "vm-started",
  "node": "pve01",
  "vmid": 100,
  "vmname": "web01",
  "timestamp": "2025-03-30T15:30:00Z"
}
```
**处理逻辑**:
- 验证签名（如果 PVE 配置了 webhook 签名密钥）
- 队列化（Redis/Celery）异步处理，避免阻塞 webhook 响应
- 幂等性检查：基于 event ID 或 timestamp + node + vmid 组合去重
- 即时同步：只处理变更的单个 VM
**新文件**:
- `webhook_receiver.py` - FastAPI 应用
- `config_webhook.yaml` - webhook 配置
- `requirements-webhook.txt` - FastAPI, uvicorn, redis (可选)
**注意**: Webhook 模式与 cron 模式应可共存（互斥锁防止同时运行）

#### 8. 🔄 配置热重载
**问题**: 修改环境变量需要重启服务
**方案**: 使用配置文件 + watchdog 监控文件变更
**配置来源**: YAML 文件（优先级高于环境变量）
```python
class ConfigManager:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self.load()
        self.observer = watchdog.observers.Observer()
        self.observer.schedule(ConfigChangeHandler(self), config_path)
        self.observer.start()
    
    def reload(self):
        self.config = self.load()
        # 通知已连接的 API 对象更新凭据（如果需要）
```
**热重载支持的功能**:
- Telegram Bot token / Chat ID
- 告警阈值（内存85% → 90%）
- 启用/禁用特定检测（如禁用漂移检测）
- 多集群配置（添加新集群无需重启）
**影响**: 创建新模块 `config.py`, 修改 `sync.py` 读取配置对象
**文件**: `config.py`, 修改 `sync.py`, `__init__.py`

---

### P4 - 长期/特殊场景（低优先级）

#### 9. 💾 状态持久化（用于增量同步的基础）
**问题**: 目前无状态，无法知道上次同步时间
**方案**: 使用 SQLite（轻量，文件易管理）
**Schema**:
```sql
CREATE TABLE sync_state (
    key TEXT PRIMARY KEY,  -- 'last_sync_time', 'cluster_name', etc.
    value TEXT
);

CREATE TABLE vm_config_history (
    vm_id INTEGER,
    sync_time TIMESTAMP,
    config_hash TEXT,
    memory INTEGER,
    vcpus INTEGER,
    tags TEXT,  -- JSON array
    PRIMARY KEY (vm_id, sync_time)
);
```
**查询示例**:
```python
def get_last_sync_time(self, cluster_name: str) -> datetime:
    cursor.execute(
        "SELECT value FROM sync_state WHERE key=?",
        (f'last_sync_{cluster_name}',)
    )
```
**冲突处理**: 数据库文件锁（SQLite 自带锁），异常时重建
**文件**: `state_db.py` (SQLite 封装类)

#### 10. 📈 历史趋势与报表
**问题**: 只有实时通知，无历史数据分析
**方案**: 将每次同步结果存入数据库
**数据点**:
- 同步耗时
- 处理VM数量、成功/失败数
- 检测到的漂移事件数量
- 节点资源使用率快照
**报表**: 可选 Prometheus exporter 或简单 HTML 报表
**影响**: 需要完整的 state_db + 定时清理旧数据
**文件**: `state_db.py` (扩展), `reporting.py`

#### 11. 📋 VM 备份状态同步
**问题**: PVE 有备份状态，但未同步到 NetBox
**方案**: 添加 backup status 到 custom field 或 separate object
**API**: `pve_api.nodes(node).qemu(vmid).status.backup.get()`
**NetBox 表示**: 可作为 VM 的 `custom_fields.backup_last_success` (timestamp)
**检测**: 超过 N 天无成功备份 → 告警
**影响**: 扩展 `process_virtual_machine`，添加 backup 检查
**条件**: 需要 PVE 配置了 Backup 模式（vzdump）

#### 12. 🏗️ VM 硬件变更追踪
**问题**: CPU/内存/磁盘大小变更可能影响运维
**方案**: 详细漂移检测（除了配置，还包括 hardware）
**通知字段**:
- `vcpus`: 2 → 4
- `memory`: 4096 → 8192
- `disks`: 添加/删除/大小变更
**联动**: 与配置漂移合并，但升级为 CRITICAL（需管理员确认）
**影响**: 扩展 `process_vm_disks` 检测磁盘变更

---

## 📅 实施路线图

### Phase 1: 基础改进（Week 1-2）
- [x] **节点离线检测** - 15分钟
- [ ] **配置漂移检测** - 2小时 (需要 state_db 基础)
- [ ] **节点资源监控** - 1.5小时
- [ ] **标签变更追踪** - 1小时 (依赖漂移检测存储)

**Phase 1 总估时**: ~5 小时

### Phase 2: 架构升级（Week 3-4）
- [ ] **增量同步** - 4小时 (需要 state_db 完整设计)
- [ ] **配置热重载** - 3小时 ( watchdog + ConfigManager)
- [ ] **多集群支持** - 6小时 (重构+测试)

**Phase 2 总估时**: ~13 小时

### Phase 3: 高级功能（Month 2-3）
- [ ] **Webhook 实时触发** - 8小时 (FastAPI + 队列)
- [ ] **状态持久化 (SQLite)** - 5小时 (完整 schema + migration)
- [ ] **备份状态同步** - 2小时
- [ ] **历史报表** - 4小时

**Phase 3 总估时**: ~19 小时

---

## 🏗️ 文件结构（扩展后）

```
pve-sync/
├── sync.py                    # 主同步器（修改）
├── config.py                  # 【新增】配置管理器 + 热重载
├── state_db.py                # 【新增】SQLite 状态持久化
├── multi_cluster_sync.py      # 【新增】多集群编排
├── webhook_receiver.py        # 【新增】FastAPI webhook 服务
├── reporting.py               # 【新增】历史报表生成
├── requirements.txt
├── requirements-webhook.txt   # 【新增】FastAPI, uvicorn
├── config.yaml                # 【新增】主配置文件（多集群、阈值）
├── config.webhook.yaml        # 【新增】webhook 配置
├── pve_netbox_sync.sh         # 启动脚本（修改支持多集群）
├── env.sh                     # 环境变量示例（保留向后兼容）
└── docs/
    ├── AGENTS.md              # 代理指南（更新）
    ├── EXTENSION_PLAN.md      # 本文件
    └── WEBHOOK_API.md         # webhook API 文档（新增）
```

---

## 🔧 技术决策点

### Q1: 配置漂移的存储方案
**选项 A**: NetBox custom field `last_sync_config_hash` (SHA256)
- ✅ 无需额外数据库
- ❌ 无法存储完整历史，只能对比当前 vs 上次
- ✅ 快速实现

**选项 B**: SQLite state_db 存储每次同步的配置快照
- ✅ 完整历史，可做趋势分析
- ❌ 需要额外维护数据库
- ✅ 便于后续报表功能

**推荐**: **A → B 演进**。先实现 A 快速上线，再迁移到 B 用于报表。

### Q2: 增量同步的时间戳来源
**选项 A**: PVE VM 的 `modify_ts` (来自 `/nodes/{node}/qemu/{vmid}/status` 或 config)
- ✅ 官方字段，准确反映配置变更
- ❌ 需要额外 API 调用（已预加载的部分 VM 有 config，但没有 modify_ts）

**选项 B**: 本地存储上次同步时所有 VM 的 memory/vcpus/tags 哈希，对比变化
- ✅ 无需 PVE 新 API，完全本地计算
- ❌ 需要完整加载所有 VM 配置（已有部分预加载）
- ✅ 更通用，可检测任何字段

**推荐**: **选项 B**。使用配置哈希（`hash(config)`），在本地 state_db 存储。

### Q3: 多集群 vs 单集群可配置化
**选项 A**: 完全重构为多集群，去除单集群硬编码
- ✅ 架构清晰，扩展性强
- ❌ 破坏现有部署，需要迁移

**选项 B**: 保持现有单集群逻辑，抽取 `SingleClusterSync` 类，`MultiClusterSync` 包装多个实例
- ✅ 向后兼容，现有部署无需改动
- ✅ 逐步迁移，单集群仍可用原脚本
- ✅ 代码复用率最高

**推荐**: **选项 B**。保持 `OptimizedPVEToNetBoxSync` 不变，创建 `MultiClusterOrchestrator`。

### Q4: Webhook 是否需要独立服务？
**选项 A**: 集成到同步器，同一个进程既处理 webhook 又执行定时 sync
- ✅ 部署简单（一个服务）
- ❌ webhook 阻塞会影响 sync 定时执行
- ❌ 需要复杂的线程/异步管理

**选项 B**: 完全独立服务 `webhook_receiver.py`，接收后写入 Redis Queue，同步器从队列消费
- ✅ 职责分离，高可用
- ✅ 可独立伸缩（webhook 接收可集群化）
- ✅ 即使 webhook 挂掉，cron 仍能工作（双保险）
- ❌ 需要 Redis (外部依赖)

**推荐**: **选项 B**。解耦，生产环境更稳健。

---

## 🚀 立即开始的准备

### 前置条件
1. ✅ 创建 `state_db.py` (SQLite 封装)
   - 表: `sync_state (key, value, updated_at)`
   - 表: `vm_config_history (vm_id, cluster_name, sync_time, config_hash, memory, vcpus, tags_json)`

2. ✅ 创建 `config.py`
   - 读取 `config.yaml` (支持环境变量覆盖)
   - `class Config` 持有所有配置项
   - `watchdog` 监控文件变更，触发 `config.reload()`

3. ✅ 准备 `config.yaml` 结构
   ```yaml
   clusters:
     - name: "default"
       pve:
         host: "${PVE_API_HOST}"
         user: "${PVE_API_USER}"
         token: "${PVE_API_TOKEN}"
         secret: "${PVE_API_SECRET}"
         verify_ssl: false
       netbox:
         url: "${NB_API_URL}"
         token: "${NB_API_TOKEN}"
       settings:
         cluster_name: "Proxmox Cluster"
         site_name: "Main Datacenter"
         cluster_type: "Proxmox"
   
   telegram:
     enabled: true
     bot_token: "${TELEGRAM_BOT_TOKEN}"
     chat_id: "${TELEGRAM_CHAT_ID}"
   
   monitoring:
     node_offline_alert: true
     config_drift_alert: true
     resource_alert:
       enabled: true
       memory_threshold: 85
       cpu_threshold: 90
       disk_threshold: 10
   
   sync:
     incremental: true  # 默认启用增量
     force_full_sync: false
   ```

---

## 📝 需要我立即开始实现的模块

根据你最关心的优先级，我可以：

1. **立即**: 节点离线检测（15分钟）
2. **快速**: 节点资源监控（1.5小时）
3. **基础架构**: state_db.py + config.py（3小时）
4. **核心功能**: 配置漂移检测（2小时，依赖 state_db）
5. **完整重构**: 配置热重载 + 多集群支持（9小时）

**请告诉我**: 你想从哪里开始？我建议按顺序实施：

```
1 → 3 → 2 → 4 → 5 ...
```

这样可以逐步构建基础设施，每个阶段都可独立验证。

---

*文档生成时间: 2025-03-30 | 基于 sync.py v1.0 分析*
