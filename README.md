# Proxmox Sync — NetBox Plugin

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![NetBox 4.5+](https://img.shields.io/badge/NetBox-4.5%2B-green.svg)](https://netbox.dev/)
[![Proxmox VE](https://img.shields.io/badge/Proxmox-VE%20%2B%20PBS-orange.svg)](https://www.proxmox.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

將 **Proxmox Virtual Environment (PVE)** 與 **Proxmox Backup Server (PBS)** 的資產資料同步到 **NetBox** 的原生插件。支援多叢集、多 PBS 伺服器、Webhook 事件驅動同步，並透過 Telegram 發送通知。

---

## 功能特色

### Proxmox VE 同步
- 將 PVE 節點同步為 NetBox **Device**（含 CPU、記憶體、網路介面、IP）
- 將 VM / Container 同步為 NetBox **Virtual Machine**（狀態、規格、磁碟、標籤）
- 支援多個 PVE 叢集，每個叢集獨立設定連線與 NetBox 對應關係
- QEMU Guest Agent 整合，從執行中 VM 取得實際 IP 位址
- 配置漂移偵測：自動發現 VM 的記憶體/CPU 設定變更

### Proxmox Backup Server 同步
- 將 PBS 主機同步為 NetBox **Device**（含版本、規格、網路介面）
- 從 PBS API 讀取所有 Datastore 的備份快照記錄
- 自動更新 NetBox 中對應 VM 的 **Backup Status**（最後備份時間、大小、狀態）
- 支援多台 PBS 伺服器，每台獨立設定

### Web UI 管理
- **Dashboard**：同步統計、PVE 叢集狀態、PBS 伺服器狀態、Webhook URL 一鍵複製
- **PVE Clusters**：在 Web GUI 新增/編輯/刪除 PVE 叢集連線設定
- **PBS Servers**：在 Web GUI 新增/編輯/刪除 PBS 伺服器連線設定
- **Sync Jobs**：完整的同步歷史記錄，含狀態、執行時間、VM 統計
- **Webhook Events**：查看所有收到的 Webhook 事件及處理狀態
- **Backup Status**：每台 VM 的備份狀態一覽
- **Settings**：在 Web GUI 設定 NetBox API、Telegram 通知、Webhook 密鑰等

### 事件驅動
- 內建 Webhook 接收端點，接收 PVE 事件（VM 啟動/停止/遷移/備份完成）
- 接收到事件後自動觸發對應同步任務
- HMAC 簽名驗證（可選）

### 通知
- Telegram Bot 整合，同步成功/失敗/異常時發送通知
- 支援群組頻道（Chat ID 使用負號格式，如 `-1002581073501`）

---

## 系統需求

| 元件 | 版本需求 |
|---|---|
| Python | 3.12+ |
| NetBox | 4.5 – 4.6.x |
| Proxmox VE | 6.0+ |
| Proxmox Backup Server | 2.x（可選） |
| Redis | 任意版本（NetBox RQ Worker 需要） |

---

## 安裝

### 1. 安裝插件

```bash
# 在 NetBox venv 中安裝
/opt/netbox/venv/bin/pip install -e /opt/netbox-pve-sync
```

### 2. 啟用插件

在 NetBox 的 `configuration.py` 中加入：

```python
PLUGINS = [
    "pve_sync_plugin",
]

PLUGINS_CONFIG = {
    "pve_sync_plugin": {
        # NetBox API 連線（也可在 Web UI Settings 頁面設定）
        "netbox_url": "http://localhost:8001",
        "netbox_token": "your-netbox-api-token",
    },
}
```

### 3. 建立資料表

```bash
cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py migrate pve_sync_plugin
/opt/netbox/venv/bin/python manage.py collectstatic --no-input
```

### 4. 重啟服務

```bash
sudo systemctl restart netbox netbox-rq
```

---

## 設定

所有設定均可在 Web UI 完成，無需修改設定檔。

### 基本設定

前往 `Plugins → Proxmox Sync → Settings`：

| 欄位 | 說明 |
|---|---|
| NetBox URL | NetBox API 位址（如 `http://localhost:8001`） |
| NetBox Token | NetBox API Token |
| Telegram Bot Token | Telegram 機器人 Token（可選） |
| Telegram Chat ID | 通知目標頻道/群組 ID（群組須為負數，如 `-1002581073501`） |
| Webhook Secret | Webhook HMAC 簽名密鑰（可選，留空則不驗證） |
| Default Site | 預設對應的 NetBox Site 名稱 |
| Default Cluster Type | 預設叢集類型名稱 |
| State DB Path | 狀態資料庫路徑（預設 `/var/lib/netbox/pve-sync-state.db`） |

### 新增 PVE 叢集

前往 `Plugins → Proxmox Sync → PVE Clusters → Add`：

| 欄位 | 說明 |
|---|---|
| Name | 叢集識別名稱（同步任務會以此名稱區分） |
| PVE Host | PVE API URL，如 `https://pve01:8006` |
| PVE User | API 使用者，如 `root@pam` |
| PVE Token | API Token 名稱 |
| PVE Secret | API Token 密鑰 |
| NetBox Site | 對應的 NetBox Site |
| NetBox Cluster | 對應的 NetBox Cluster |
| Enabled | 是否啟用此叢集同步 |

### 新增 PBS 伺服器

前往 `Plugins → Proxmox Sync → PBS Servers → Add`：

| 欄位 | 說明 |
|---|---|
| Name | 伺服器識別名稱 |
| PBS Host | PBS API URL，如 `https://pbs01:8007` |
| PBS Token Name | API Token，如 `root@pam!apitoken` |
| PBS Token Secret | Token 密鑰 |
| PBS Node Name | PBS 節點名稱 |
| NetBox Site | 對應的 NetBox Site |
| Enabled | 是否啟用 |

---

## 使用方式

### 手動觸發同步

**PVE 同步**：Dashboard 頁面右上角選擇叢集後點擊「Sync Now」

**PBS 同步**：Dashboard 頁面 PBS Servers 表格中點擊各伺服器的 `⟳` 按鈕，或進入 PBS 伺服器詳情頁點擊「Sync This PBS Server Now」

**VM 頁面同步**：在 NetBox Virtual Machine 詳情頁頂部點擊「Proxmox Sync」按鈕，觸發該 VM 所屬叢集的同步

### Management Command

```bash
cd /opt/netbox/netbox

# 同步指定叢集
/opt/netbox/venv/bin/python manage.py pve_sync --cluster production

# 等待完成並取得結果
/opt/netbox/venv/bin/python manage.py pve_sync --cluster production --wait --timeout 300
```

### Webhook 接收

Webhook 端點（無需認證，支援 HMAC 驗證）：

```
POST /plugins/pve-sync/webhook/
```

請求格式：
```json
{
  "event": "vm-started",
  "node": "pve01",
  "vmid": 100,
  "vmname": "web-server-01"
}
```

支援的事件類型：`vm-started`、`vm-stopped`、`vm-migrated`、`backup-done`、`backup-failed`、`configuration-change`

若設定了 `webhook_secret`，需在 Header 加入：
```
X-PVE-Signature: <hmac-sha256-hex>
```

### REST API

```bash
# 觸發同步
POST /api/plugins/pve-sync/jobs/trigger/

# 查詢同步任務
GET /api/plugins/pve-sync/jobs/

# 查詢 PVE 叢集設定
GET /api/plugins/pve-sync/clusters/

# 查詢備份狀態
GET /api/plugins/pve-sync/backup-status/
```

---

## 資料對應

### PVE → NetBox

| PVE | NetBox | 備註 |
|---|---|---|
| 節點 | dcim.Device | 節點名稱為設備名稱 |
| 節點狀態 `online` | `active` | 其他狀態對應 `offline` |
| 節點網路介面 | dcim.Interface + ipam.IPAddress | 含 MAC 與 IP |
| VM / CT | virtualization.VirtualMachine | |
| `status: running` | `active` | |
| `status: stopped` | `offline` | |
| `vcpus` | vcpus | |
| `memory` | memory_mb | |
| `ostype` | platform | 自動建立 |
| PVE tags | NetBox Tags | |
| 網路介面 MAC | VMInterface | |
| QEMU Agent IP | IPAddress | 僅執行中 VM |

### PBS → NetBox

| PBS | NetBox | 備註 |
|---|---|---|
| PBS 節點 | dcim.Device | 含 CPU、記憶體、磁碟資訊 |
| 備份快照 | PveBackupStatus.last_backup | 取各 VM 最新快照 |
| 快照大小 | PveBackupStatus.backup_size | bytes |
| 備份狀態 | `success`（≤7天）/ `failed`（>7天） | |

---

## PBS 備份狀態比對邏輯

PBS 同步完成後，系統會將備份記錄寫回 NetBox VM 的 Backup Status。比對順序：

1. 找到 `PveBackupStatus.pve_backup_id` 符合 `vm/{vmid}` 的記錄
2. 找到 `VirtualMachine.custom_field_data.pve_vmid == vmid` 的記錄

若兩者都找不到（PBS vmid 無法對應 NetBox VM），則跳過並記錄 debug log。

---

## 專案結構

```
pve_sync_plugin/
├── __init__.py          # PluginConfig（PveSyncPluginConfig）
├── models.py            # 資料模型
│   ├── PveSyncJob       # 同步任務記錄
│   ├── PveWebhookEvent  # Webhook 事件記錄
│   ├── PveClusterConfig # PVE 叢集連線設定
│   ├── PbsServerConfig  # PBS 伺服器連線設定
│   ├── PveBackupStatus  # VM 備份狀態
│   └── PvePluginSettings# 插件全域設定（單例）
├── views.py             # UI views
├── urls.py              # URL 路由
├── forms.py             # 表單
├── tables.py            # 列表表格
├── filtersets.py        # 篩選
├── navigation.py        # 側欄選單
├── tasks.py             # RQ 背景任務
│   ├── run_sync_job()         # PVE 同步
│   ├── run_pbs_sync_job()     # PBS 同步
│   ├── process_webhook_event()# Webhook 處理
│   ├── _fetch_pbs_snapshots() # 從 PBS API 取備份清單
│   └── _apply_pbs_backup_status() # 寫入 Backup Status
├── signals.py           # VM 建立時自動建立 PveBackupStatus
├── template_content.py  # VM 詳情頁注入「Proxmox Sync」按鈕
├── utils.py             # get_plugin_config()（DB → config → env 優先級）
├── sync/
│   ├── engine.py        # PVE 同步引擎（OptimizedPVEToNetBoxSync）
│   └── config_bridge.py # 將 DB 設定轉換為 engine 所需的 YAML 格式
├── migrations/          # 資料庫 Migration
├── templates/pve_sync/  # Django 模板
└── api/                 # REST API（序列化、ViewSet、路由）

pbs215_sync.py           # PBS 同步腳本（由 tasks.run_pbs_sync_job 呼叫）
```

---

## 設定優先級

`get_plugin_config(key)` 依以下順序取值：

1. **Web UI Settings**（`PvePluginSettings` 資料表，有快取）
2. **`PLUGINS_CONFIG["pve_sync_plugin"]`**（`configuration.py`）
3. **環境變數**（`NB_API_URL`、`NB_API_TOKEN`、`TELEGRAM_BOT_TOKEN` 等）
4. **預設值**

---

## 常見問題

**Q：同步失敗，提示「No enabled PVE cluster config found」**

前往 `Plugins → Proxmox Sync → PVE Clusters → Add` 新增叢集設定，確認 `Enabled` 已勾選。

**Q：Telegram 通知未收到**

1. 確認 Chat ID 格式正確（群組/頻道須為負數，如 `-1002581073501`）
2. 確認 Bot 已加入目標群組/頻道
3. 在 Settings 頁面更新 Chat ID 後儲存

**Q：Webhook 回應 500 錯誤**

確認 NetBox 版本為 4.5+，且 `netbox-rq` 服務正在執行：
```bash
systemctl status netbox-rq
```

**Q：PBS 備份狀態沒有更新到 NetBox VM**

PBS 備份記錄需透過 `pve_vmid` custom field 或已有的 `pve_backup_id` 與 NetBox VM 比對。若 VM 尚未設定 `pve_vmid` custom field，可在 NetBox 建立 Integer 類型的 `pve_vmid` custom field，並在 PVE 同步時填入。

**Q：`/var/lib/netbox/` 目錄不存在**

```bash
mkdir -p /var/lib/netbox
chown netbox:netbox /var/lib/netbox
```

---

## 開發

```bash
# 複製專案
git clone https://github.com/XiuJie2/netbox-pve-sync.git
cd netbox-pve-sync

# 安裝至 NetBox venv（開發模式）
/opt/netbox/venv/bin/pip install -e .

# 套用 migration
cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py migrate pve_sync_plugin

# 重啟
systemctl restart netbox netbox-rq
```

---

## 授權

MIT License

---

## 致謝

- [Proxmox](https://www.proxmox.com/) — 優秀的虛擬化與備份平台
- [NetBox](https://netbox.dev/) — 強大的網路基礎設施管理系統
- [pynetbox](https://github.com/netbox-community/pynetbox) — Python NetBox API 客戶端
- [proxmoxer](https://github.com/proxmoxer/proxmoxer) — Proxmox API 封裝
