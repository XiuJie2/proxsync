# 發布新版本到 PyPI

## 步驟

1. 修改 `pyproject.toml` 裡的版本號

   ```toml
   version = "2.1.0"
   ```

2. Commit 版本號變更

   ```bash
   git add pyproject.toml
   git commit -m "chore: bump version to 2.1.0"
   ```

3. 打包

   ```bash
   rm -rf dist/
   /opt/netbox/venv/bin/python -m build
   ```

4. 上傳到 PyPI

   ```bash
   /opt/netbox/venv/bin/python -m twine upload dist/* --username __token__ --password <your-api-token>
   ```

5. 確認發布結果

   https://pypi.org/project/proxsync/
