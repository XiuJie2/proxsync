"""
状态持久化模块 (State Database)
用于存储同步状态、VM配置历史、节点资源历史等
支持增量同步和变更检测
"""

import sqlite3
import json
import time
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from pathlib import Path
import threading


class StateDB:
    """SQLite 状态数据库管理"""

    def __init__(self, db_path: str = "/var/lib/pve-sync/state.db"):
        """
        初始化状态数据库

        Args:
            db_path: SQLite 数据库文件路径
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        """初始化数据库表结构"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS vm_config_history (
                    vm_id INTEGER,
                    cluster_name TEXT,
                    sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    config_hash TEXT NOT NULL,
                    memory INTEGER,
                    vcpus INTEGER,
                    tags_json TEXT,  -- JSON array
                    PRIMARY KEY (vm_id, cluster_name, sync_time)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS node_status_history (
                    node_name TEXT,
                    cluster_name TEXT,
                    sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    status TEXT NOT NULL,  -- online/offline
                    PRIMARY KEY (node_name, cluster_name, sync_time)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS node_resource_history (
                    node_name TEXT,
                    cluster_name TEXT,
                    sync_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    cpu_usage REAL,  -- 0-1
                    memory_total INTEGER,
                    memory_used INTEGER,
                    memory_percent REAL,
                    disk_total INTEGER,
                    disk_used INTEGER,
                    disk_percent REAL,
                    PRIMARY KEY (node_name, cluster_name, sync_time)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS sync_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cluster_name TEXT NOT NULL,
                    start_time TIMESTAMP NOT NULL,
                    end_time TIMESTAMP,
                    success_count INTEGER DEFAULT 0,
                    total_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'running'  -- running, success, failed
                )
            """)

            # 创建索引以提升查询性能
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vm_config_vm_id ON vm_config_history(vm_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_vm_config_cluster ON vm_config_history(cluster_name)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_node_status_time ON node_status_history(sync_time)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sync_log_cluster ON sync_log(cluster_name)")

            # Add columns introduced in later versions (safe to re-run on existing DBs)
            for col_def in ("node TEXT", "primary_ip TEXT", "vm_name TEXT"):
                try:
                    conn.execute(f"ALTER TABLE vm_config_history ADD COLUMN {col_def}")
                except Exception:
                    pass  # column already exists

            conn.commit()

    # ========== Sync State 管理 ==========

    def set_state(self, key: str, value: Any):
        """设置状态值"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO sync_state (key, value, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
                    (key, json.dumps(value) if not isinstance(value, str) else value)
                )
                conn.commit()

    def get_state(self, key: str, default: Any = None) -> Any:
        """获取状态值"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT value FROM sync_state WHERE key = ?",
                    (key,)
                )
                row = cursor.fetchone()
                if row:
                    try:
                        return json.loads(row[0])
                    except:
                        return row[0]
                return default

    def delete_state(self, key: str):
        """删除状态"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("DELETE FROM sync_state WHERE key = ?", (key,))
                conn.commit()

    # ========== VM 配置历史 ==========

    def save_vm_config_snapshot(self, vm_id: int, cluster_name: str, config_hash: str,
                                memory: int, vcpus: int, tags: List[str],
                                node: str = None, primary_ip: str = None,
                                vm_name: str = None):
        """保存 VM 配置快照"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO vm_config_history
                    (vm_id, cluster_name, config_hash, memory, vcpus, tags_json, node, primary_ip, vm_name)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vm_id,
                        cluster_name,
                        config_hash,
                        memory,
                        vcpus,
                        json.dumps(tags) if tags else "[]",
                        node,
                        primary_ip,
                        vm_name,
                    )
                )
                conn.commit()

    def get_last_vm_config(self, vm_id: int, cluster_name: str) -> Optional[Dict]:
        """获取 VM 上次配置"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT config_hash, memory, vcpus, tags_json, sync_time, node, primary_ip, vm_name
                    FROM vm_config_history
                    WHERE vm_id = ? AND cluster_name = ?
                    ORDER BY sync_time DESC LIMIT 1
                    """,
                    (vm_id, cluster_name)
                )
                row = cursor.fetchone()
                if row and row[4]:  # 确保 sync_time 存在
                    return {
                        'config_hash': row[0],
                        'memory': row[1],
                        'vcpus': row[2],
                        'tags': json.loads(row[3]) if row[3] else [],
                        'sync_time': row[4],
                        'node': row[5],
                        'primary_ip': row[6],
                        'vm_name': row[7],
                    }
                return None

    def get_known_vmids(self, cluster_name: str) -> Dict[int, Dict]:
        """返回此叢集最近一次快照的所有 vmid，用於偵測刪除的 VM。

        Returns:
            {vmid: {'vm_name': str, 'node': str}} — 每個 vmid 取最新的一筆。
        """
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT vm_id, vm_name, node
                    FROM vm_config_history
                    WHERE cluster_name = ?
                      AND (vm_id, sync_time) IN (
                          SELECT vm_id, MAX(sync_time)
                          FROM vm_config_history
                          WHERE cluster_name = ?
                          GROUP BY vm_id
                      )
                    """,
                    (cluster_name, cluster_name),
                )
                result = {}
                for row in cursor.fetchall():
                    result[row[0]] = {'vm_name': row[1], 'node': row[2]}
                return result

    def get_vm_config_changes(self, vm_id: int, cluster_name: str, since: datetime) -> List[Dict]:
        """获取指定时间后的 VM 配置变更"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT config_hash, memory, vcpus, tags_json, sync_time
                    FROM vm_config_history
                    WHERE vm_id = ? AND cluster_name = ? AND sync_time >= ?
                    ORDER BY sync_time ASC
                    """,
                    (vm_id, cluster_name, since.isoformat())
                )
                changes = []
                for row in cursor.fetchall():
                    changes.append({
                        'config_hash': row[0],
                        'memory': row[1],
                        'vcpus': row[2],
                        'tags': json.loads(row[3]) if row[3] else [],
                        'sync_time': row[4]
                    })
                return changes

    # ========== 节点状态历史 ==========

    def save_node_status(self, node_name: str, cluster_name: str, status: str):
        """保存节点状态"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO node_status_history (node_name, cluster_name, status)
                    VALUES (?, ?, ?)
                    """,
                    (node_name, cluster_name, status)
                )
                conn.commit()

    def get_node_last_status(self, node_name: str, cluster_name: str) -> Optional[str]:
        """获取节点上次状态"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT status FROM node_status_history
                    WHERE node_name = ? AND cluster_name = ?
                    ORDER BY sync_time DESC LIMIT 1
                    """,
                    (node_name, cluster_name)
                )
                row = cursor.fetchone()
                return row[0] if row else None

    # ========== 节点资源历史 ==========

    def save_node_resources(self, node_name: str, cluster_name: str,
                           cpu_usage: float, memory_total: int, memory_used: int,
                           disk_total: int, disk_used: int):
        """保存节点资源使用情况"""
        memory_percent = (memory_used / memory_total * 100) if memory_total > 0 else 0
        disk_percent = (disk_used / disk_total * 100) if disk_total > 0 else 0

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT INTO node_resource_history
                    (node_name, cluster_name, cpu_usage, memory_total, memory_used,
                     memory_percent, disk_total, disk_used, disk_percent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        node_name, cluster_name, cpu_usage, memory_total, memory_used,
                        memory_percent, disk_total, disk_used, disk_percent
                    )
                )
                conn.commit()

    def get_node_resource_history(self, node_name: str, cluster_name: str,
                                  hours: int = 24) -> List[Dict]:
        """获取节点资源历史（最近N小时）"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cutoff = datetime.now().timestamp() - (hours * 3600)
                cursor = conn.execute(
                    """
                    SELECT cpu_usage, memory_total, memory_used, memory_percent,
                           disk_total, disk_used, disk_percent, sync_time
                    FROM node_resource_history
                    WHERE node_name = ? AND cluster_name = ? AND
                          strftime('%s', sync_time) > ?
                    ORDER BY sync_time ASC
                    """,
                    (node_name, cluster_name, cutoff)
                )
                history = []
                for row in cursor.fetchall():
                    history.append({
                        'cpu_usage': row[0],
                        'memory_total': row[1],
                        'memory_used': row[2],
                        'memory_percent': row[3],
                        'disk_total': row[4],
                        'disk_used': row[5],
                        'disk_percent': row[6],
                        'sync_time': row[7]
                    })
                return history

    # ========== 同步日志 ==========

    def start_sync_log(self, cluster_name: str) -> int:
        """开始同步日志，返回 log_id"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    INSERT INTO sync_log (cluster_name, start_time, status)
                    VALUES (?, CURRENT_TIMESTAMP, 'running')
                    """,
                    (cluster_name,)
                )
                conn.commit()
                return cursor.lastrowid if cursor.lastrowid is not None else -1

    def update_sync_log(self, log_id: int, success_count: int, total_count: int,
                       status: str = 'success'):
        """更新同步日志"""
        error_count = total_count - success_count
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    UPDATE sync_log
                    SET end_time = CURRENT_TIMESTAMP,
                        success_count = ?,
                        total_count = ?,
                        error_count = ?,
                        status = ?
                    WHERE id = ?
                    """,
                    (success_count, total_count, error_count, status, log_id)
                )
                conn.commit()

    def get_recent_sync_logs(self, cluster_name: str, limit: int = 10) -> List[Dict]:
        """获取最近的同步日志"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT id, start_time, end_time, success_count, total_count,
                           error_count, status
                    FROM sync_log
                    WHERE cluster_name = ?
                    ORDER BY start_time DESC LIMIT ?
                    """,
                    (cluster_name, limit)
                )
                logs = []
                for row in cursor.fetchall():
                    logs.append({
                        'id': row[0],
                        'start_time': row[1],
                        'end_time': row[2],
                        'success_count': row[3],
                        'total_count': row[4],
                        'error_count': row[5],
                        'status': row[6]
                    })
                return logs

    # ========== 工具方法 ==========

    def cleanup_old_data(self, days: int = 90):
        """清理90天前的历史数据"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                # 清理旧的 VM 配置历史（保留最近90天）
                conn.execute(
                    """
                    DELETE FROM vm_config_history
                    WHERE datetime(sync_time) < datetime('now', '-? days')
                    """,
                    (days,)
                )

                # 清理旧的节点状态历史（保留最近90天）
                conn.execute(
                    """
                    DELETE FROM node_status_history
                    WHERE datetime(sync_time) < datetime('now', '-? days')
                    """,
                    (days,)
                )

                # 清理旧的节点资源历史（保留最近90天）
                conn.execute(
                    """
                    DELETE FROM node_resource_history
                    WHERE datetime(sync_time) < datetime('now', '-? days')
                    """,
                    (days,)
                )

                # 清理旧的同步日志（保留最近365天）
                conn.execute(
                    """
                    DELETE FROM sync_log
                    WHERE datetime(start_time) < datetime('now', '-365 days')
                    """
                )

                conn.commit()
                print(f"✓ 已清理 {days} 天前的历史数据")

    def get_database_stats(self) -> Dict[str, int]:
        """获取数据库统计信息"""
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                stats = {}
                tables = [
                    'sync_state', 'vm_config_history', 'node_status_history',
                    'node_resource_history', 'sync_log'
                ]
                for table in tables:
                    cursor = conn.execute(f"SELECT COUNT(*) FROM {table}")
                    stats[table] = cursor.fetchone()[0]
                return stats

    def rename_cluster(self, old_name: str, new_name: str) -> int:
        """Rename cluster_name across all tables — call when PveClusterConfig.name changes."""
        total = 0
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                for table in ("vm_config_history", "node_status_history",
                              "node_resource_history", "sync_log"):
                    cur = conn.execute(
                        f"UPDATE {table} SET cluster_name = ? WHERE cluster_name = ?",
                        (new_name, old_name),
                    )
                    total += cur.rowcount
                conn.commit()
        return total


# 便利函数
def compute_config_hash(vm_config: Dict[str, Any], tags: List[str], network_interfaces: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    计算 VM 配置哈希，用于变更检测

    包含: memory, vcpus, ostype, tags, network_interfaces
    """
    import hashlib

    # 提取网络接口关键信息（接口名称、MAC、bridge）
    net_config = {}
    if network_interfaces is not None:
        for iface in network_interfaces:
            iface_name = iface.get('name', '')
            if iface_name:
                net_config[iface_name] = {
                    'mac': iface.get('mac_address', '').lower(),
                    'bridge': iface.get('bridge', ''),
                    'gateway': iface.get('gateway', '')
                }

    # 提取关键字段
    key_fields = {
        'memory': vm_config.get('memory', 0),
        'vcpus': vm_config.get('vcpus', 0),
        'ostype': vm_config.get('ostype', ''),
        'cores': vm_config.get('cores', 1),
        'sockets': vm_config.get('sockets', 1),
        'description': vm_config.get('description', '')[:200],  # 限制长度
        'tags': sorted(tags),  # 排序以确保一致性
        'networks': net_config  # 添加网络接口配置
    }

    config_str = json.dumps(key_fields, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(config_str.encode()).hexdigest()[:16]


if __name__ == "__main__":
    # 测试代码
    db = StateDB("test_state.db")

    # 测试保存和查询
    db.set_state("test_key", {"value": 123, "name": "test"})
    print(db.get_state("test_key"))

    # 测试 VM 配置历史
    db.save_vm_config_snapshot(
        vm_id=100,
        cluster_name="default",
        config_hash="abc123def456",
        memory=4096,
        vcpus=2,
        tags=["prod", "web"]
    )
    print(db.get_last_vm_config(100, "default"))

    # 测试节点状态
    db.save_node_status("pve01", "default", "online")
    print(db.get_node_last_status("pve01", "default"))

    # 统计
    print(db.get_database_stats())
