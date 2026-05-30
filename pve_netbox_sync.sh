#!/bin/bash

# 設定環境變數
export NB_API_URL="https://localhost"
export NB_API_TOKEN="a52c44a47fbfa168f1b38b2eb7dac2b71a6bfe03"

export PVE_API_HOST="172.17.202.195"
#export PVE_API_USER="root@pam"
export PVE_API_USER="netbox@pve"
export PVE_API_TOKEN="netbox"
#export PVE_API_SECRET="c1ce2567-bb0a-4c70-86a1-856443976592"
export PVE_API_SECRET="e0db5a73-4ab2-47a3-aa2e-c4f5c461bbb2"
export PVE_API_VERIFY_SSL="false"
export NB_CLUSTER_ID="2"

export TELEGRAM_BOT_TOKEN="7968501743:AAFQizgHMHTDYtUpWrMvs_TzGAbBoS-EVTo"
export TELEGRAM_CHAT_ID="-1003496396467"
SCRIPT_DIR="/opt/pve-sync"
LOG_DIR="/home/birc/logs/netbox-pve-sync"
LOG_FILE="$LOG_DIR/sync_$(date +'%Y%m%d_%H%M%S').log"
ERROR_LOG="$LOG_DIR/error.log"

# 創建日誌目錄
mkdir -p $LOG_DIR

# 開始執行
echo "========== 開始同步 $(date) ==========" >> $LOG_FILE

cd $SCRIPT_DIR

# 執行同步腳本
/opt/pve-sync/venv/bin/python /opt/pve-sync/sync.py >> $LOG_FILE 2>&1

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "同步完成，退出碼: $EXIT_CODE" >> $LOG_FILE
else
    echo "同步失敗，退出碼: $EXIT_CODE" >> $LOG_FILE
    echo "$(date): 同步失敗，退出碼: $EXIT_CODE" >> $ERROR_LOG
    # 可以添加郵件通知或其他告警機制
fi

echo "========== 同步結束 $(date) ==========" >> $LOG_FILE

# 刪除超過30天的日誌
find $LOG_DIR -name "sync_*.log" -mtime +7 -delete

exit $EXIT_CODE
