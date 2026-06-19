# netbox-pve-sync

[![Version](https://img.shields.io/badge/version-2.1.0-blue.svg)](https://github.com/XiuJie2/netbox-pve-sync)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![NetBox 4.5–4.6](https://img.shields.io/badge/NetBox-4.5%20–%204.6-green.svg)](https://netbox.dev/)
[![Proxmox VE](https://img.shields.io/badge/Proxmox-VE%20%2B%20PBS-orange.svg)](https://www.proxmox.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

將 **Proxmox Virtual Environment (PVE)** 與 **Proxmox Backup Server (PBS)** 的資產資料自動同步到 **NetBox** 的原生插件。支援多叢集、多 PBS 伺服器、排程同步、Webhook 事件驅動，以及 Telegram 通知。

---

## 功能特色

### Proxmox VE 同步

- 節點 → NetBox **Device**（CPU、記憶體、網路介面、Primary IP）
- VM / CT → NetBox **Virtual Machine**（狀態、規格、磁碟、標籤）
- QEMU Guest Agent 整合，從執行中 VM 取得實際 IP 位址
- 配置漂移偵測：自動發現 VM 的 CPU / 記憶體設定變更
- 增量同步：透過 SQLite state_db 追蹤變更，避免全量更新

### 多叢集支援

- 每個 PVE 叢集獨立設定連線、NetBox Site、Cluster、Cluster Type
- VM serial key 以 `vmid::cluster_id` 為複合鍵，正確處理跨叢集 vmid 重複的情況
- 節點名稱衝突時（不同叢集有同名節點）自動加上叢集名稱後綴

### Proxmox Backup Server 同步

- PBS 主機 → NetBox **Device**（版本、規格、網路介面）
- 讀取所有 Datastore 備份快照，更新對應 VM 的 **Backup Status**（最後備份時間、大小）
- 支援多台 PBS 伺服器，每台獨立設定

### 排程自動同步

- 每個 PVE 叢集和 PBS 伺服器均可設定同步週期：`hourly`、`every_3h`、`every_6h`、`daily`、`weekly`
- 由系統 cron 每 15 分鐘執行 `run_scheduled_syncs` management command，自動觸發到期的同步
- 同步中時不重複觸發（避免排隊堆積）

### 事件驅動（Webhook）

- 內建 Webhook 接收端點，接收 PVE 事件（VM 啟動/停止/遷移/備份完成）
- 接收到事件後自動觸發對應同步任務
- HMAC-SHA256 簽名驗證（可選）

### Web UI 管理

- **Dashboard**：PVE 叢集狀態、PBS 伺服器狀態、同步統計、Webhook URL 一鍵複製
- **PVE Clusters**：新增／編輯／刪除 PVE 叢集連線設定
- **PBS Servers**：新增／編輯／刪除 PBS 伺服器連線設定
- **Sync Jobs**：完整同步歷史，含狀態、執行時間、VM 統計
- **Webhook Events**：查看所有收到的 Webhook 事件及處理狀態
- **Backup Status**：每台 VM 的備份狀態一覽
- **Settings**：NetBox API、Telegram 通知、Webhook 密鑰等設定

### 通知

- Telegram Bot 整合，同步成功／失敗／異常時傳送通知
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
        # 也可在 Web UI Settings 頁面設定，此處為預設值
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

### 5. 設定排程自動同步（推薦）

在 root crontab 加入以下排程，每 15 分鐘檢查一次是否有到期的同步任務：

```bash
sudo crontab -e
```

加入：

```
*/15 * * * * cd /opt/netbox/netbox && /opt/netbox/venv/bin/python manage.py run_scheduled_syncs >> /var/log/netbox-pve-scheduled-sync.log 2>&1
```

> 設定好 cron 後，只需在 Web UI 各叢集設定中選擇同步週期，系統即會自動執行。

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
| Telegram Chat ID | 通知目標頻道／群組 ID（群組須為負數，如 `-1002581073501`） |
| Webhook Secret | Webhook HMAC 簽名密鑰（可選，留空則不驗證） |
| Default Site | 預設對應的 NetBox Site 名稱 |
| Default Cluster Type | 預設叢集類型名稱 |
| State DB Path | 狀態資料庫路徑（預設 `/var/lib/netbox/pve-sync-state.db`） |

### 新增 PVE 叢集

前往 `Plugins → Proxmox Sync → PVE Clusters → Add`：

| 欄位 | 說明 |
|---|---|
| Name | 叢集識別名稱（用於日誌、排程識別） |
| PVE Host | PVE API URL，如 `https://pve01:8006` |
| PVE User | API 使用者，如 `root@pam` |
| PVE Token | API Token 名稱 |
| PVE Secret | API Token 密鑰 |
| NetBox Site | 對應的 NetBox Site |
| NetBox Cluster Type | 叢集類型（預設 `Proxmox`） |
| NetBox Cluster | 對應的 NetBox Cluster 名稱 |
| Sync Schedule | 自動同步週期（`Disabled`／`Hourly`／`Every 3 hours` 等） |
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
| Sync Schedule | 自動同步週期 |
| Enabled | 是否啟用 |

---

## 使用方式

### 手動觸發同步

**PVE 同步**：Dashboard 頁面右上角選擇叢集後點擊「Sync Now」

**PBS 同步**：Dashboard 頁面 PBS Servers 區塊點擊各伺服器的 `⟳` 按鈕，或進入 PBS 伺服器詳情頁點擊「Sync This PBS Server Now」

**VM 頁面同步**：在 NetBox Virtual Machine 詳情頁頂部點擊「Proxmox Sync」按鈕，觸發該 VM 所屬叢集的同步

### Management Command

```bash
cd /opt/netbox/netbox

# 同步指定叢集
/opt/netbox/venv/bin/python manage.py pve_sync --cluster production

# 等待完成並取得結果
/opt/netbox/venv/bin/python manage.py pve_sync --cluster production --wait --timeout 300

# 檢查哪些叢集即將觸發（不實際執行）
/opt/netbox/venv/bin/python manage.py run_scheduled_syncs --dry-run

# 手動執行所有到期的排程同步
/opt/netbox/venv/bin/python manage.py run_scheduled_syncs
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
| 節點 | dcim.Device | 節點名稱為設備名稱；跨叢集同名時自動加上叢集後綴 |
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

## 專案結構

```
netbox-pve-sync/
├── pve_sync_plugin/
│   ├── __init__.py               # PluginConfig（v2.1.0）
│   ├── models.py                 # PveSyncJob / PveClusterConfig / PbsServerConfig
│   │                             # PveBackupStatus / PvePluginSettings / PveWebhookEvent
│   ├── views.py                  # Web UI views
│   ├── urls.py                   # URL 路由
│   ├── forms.py                  # 表單
│   ├── tables.py                 # 列表表格
│   ├── filtersets.py             # 篩選
│   ├── navigation.py             # 側欄選單
│   ├── choices.py                # Enum（同步狀態、排程週期）
│   ├── tasks.py                  # RQ 背景任務（PVE / PBS 同步、Webhook 處理）
│   ├── signals.py                # VM 建立時自動建立 PveBackupStatus
│   ├── template_content.py       # VM 詳情頁注入「Proxmox Sync」按鈕
│   ├── utils.py                  # get_plugin_config()（DB → config → env 優先級）
│   ├── view_helpers.py           # has_active_sync_job() 等共用 helper
│   ├── sync/
│   │   ├── engine.py             # PVE 同步引擎（OptimizedPVEToNetBoxSync）
│   │   └── config_bridge.py      # DB 設定 → 同步引擎所需的 config dict
│   ├── management/commands/
│   │   ├── pve_sync.py           # manage.py pve_sync
│   │   └── run_scheduled_syncs.py# manage.py run_scheduled_syncs（排程驅動）
│   ├── migrations/               # 資料庫 Migration
│   ├── templates/pve_sync/       # Django 模板
│   └── api/                      # REST API（序列化、ViewSet、路由）
│
├── sync.py                       # PVE 同步引擎核心
├── pbs215_sync.py                # PBS 同步腳本
├── state_db.py                   # SQLite 增量同步狀態管理
├── config.py                     # 設定讀取（env / YAML）
├── pyproject.toml
└── requirements.txt
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

**Q：排程同步設定好後沒有自動執行**

確認 cron 是否已設定：

```bash
sudo crontab -l | grep run_scheduled_syncs
```

若沒有輸出，請按照「安裝 → 步驟 5」加入 cron 排程。另可手動執行確認邏輯：

```bash
cd /opt/netbox/netbox
/opt/netbox/venv/bin/python manage.py run_scheduled_syncs --dry-run
```

**Q：同步失敗，提示「No enabled PVE cluster config found」**

前往 `Plugins → Proxmox Sync → PVE Clusters → Add` 新增叢集設定，確認 `Enabled` 已勾選。

**Q：PBS 伺服器顯示同步成功，但 NetBox 裝置清單看不到設備**

確認 PBS Host 與 PBS Node Name 設定正確，且插件可連線至 PBS API（`https://pbs-host:8007`）。若連線失敗，同步任務會記錄為失敗狀態。可至 `Sync Jobs` 查看詳細錯誤訊息。

**Q：兩個叢集有相同的 vmid，同步後 VM 資料互相覆蓋**

v2.1.0 已修正此問題，VM 以 `vmid::cluster_id` 為複合鍵區分，不同叢集的相同 vmid 會正確同步為獨立的 NetBox VM。若你正在使用舊版，請升級至 v2.1.0。

**Q：兩個叢集有相同名稱的節點（如都叫 `pve`），裝置名稱衝突**

v2.1.0 已修正：同一 Site 下節點名稱衝突時，會自動改為 `{node}-{cluster_name}` 後綴格式（如 `pve-智楊老師`）。

**Q：Telegram 通知未收到**

1. 確認 Chat ID 格式正確（群組／頻道須為負數，如 `-1002581073501`）
2. 確認 Bot 已加入目標群組／頻道
3. 在 Settings 頁面更新 Chat ID 後儲存

**Q：Webhook 回應 500 錯誤**

確認 NetBox 版本為 4.5+，且 `netbox-rq` 服務正在執行：

```bash
systemctl status netbox-rq
```

**Q：PBS 備份狀態沒有更新到 NetBox VM**

PBS 備份記錄需透過 `pve_vmid` custom field 與 NetBox VM 比對。若 VM 尚未設定 `pve_vmid`，可在 NetBox 建立 Integer 類型的 `pve_vmid` custom field，並執行一次 PVE 同步填入數值。

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
