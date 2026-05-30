# 浏览器自动化技能对比

## 1. playwright - 独立会话模式

### 特点
- **无状态**：每次调用都是全新的浏览器会话
- **即用即走**：操作完成后浏览器自动关闭
- **简单直接**：适合单次操作任务

### 典型工作流
```
1. browser_navigate → 打开页面
2. browser_snapshot → 获取页面结构
3. browser_click → 点击元素
4. browser_take_screenshot → 截图
5. browser_close → 关闭浏览器（可选，会自动清理）
```

### 使用示例

**单步操作：**
```typescript
// 导航并截图
skill_mcp(mcp_name="playwright", tool_name="browser_navigate", arguments={url: "https://example.com"})
skill_mcp(mcp_name="playwright", tool_name="browser_take_screenshot", arguments={filename: "example.png"})
skill_mcp(mcp_name="playwright", tool_name="browser_close", arguments={})
```

**多个操作：**
```typescript
// 每次都是全新的浏览器
skill_mcp(..., browser_navigate, {url: "https://a.com"})
skill_mcp(..., browser_close, {})
skill_mcp(..., browser_navigate, {url: "https://b.com"})
```

### 适用场景
- 单页面截图
- 快速验证某个页面
- 不需要保持登录状态的任务
- 独立的 API 测试

### 工具列表（playwright MCP）
- `browser_navigate` - 导航到URL
- `browser_snapshot` - 获取ARIA快照
- `browser_click` - 点击元素
- `browser_type` - 输入文本
- `browser_fill_form` - 填充表单
- `browser_take_screenshot` - 截图
- `browser_console_messages` - 获取控制台日志
- `browser_network_requests` - 获取网络请求
- `browser_evaluate` - 执行JS代码
- `browser_handle_dialog` - 处理弹窗
- `browser_file_upload` - 文件上传
- `browser_wait_for` - 等待元素/文本
- `browser_press_key` - 按键操作
- `browser_select_option` - 选择下拉选项
- `browser_drag` - 拖拽操作
- `browser_hover` - 悬停
- `browser_tabs` - 标签页管理
- `browser_run_code` - 运行Playwright代码片段
- `browser_install` - 安装浏览器
- `browser_resize` - 调整窗口大小
- `browser_navigate_back` - 返回上一页

---

## 2. dev-browser - 持久化会话模式

### 特点
- **状态持久化**：页面在脚本结束后仍保持打开
- **命名页面**：可以为页面创建有意义的名称
- **多次连接**：多个脚本可以连接到同一个浏览器会话
- **适合复杂工作流**：多步骤任务，需要保持登录、表单数据等

### 典型工作流

**启动服务器**（独立进程）
```bash
# 独立模式（默认）
cd skills/dev-browser && npm i && ./server.sh &

# 或扩展模式（连接到用户Chrome）
cd skills/dev-browser && npm i && npm run start-extension &
```

**编写脚本**（客户端）
```typescript
// 1. 连接到服务器
import { connect } from "@/client.js";
const client = await connect();

// 2. 获取或创建命名页面
const page = await client.page("login", { viewport: { width: 1920, height: 1080 } });

// 3. 执行操作
await page.goto("https://example.com/login");
await page.type("[ref=e1]", "username");
await page.type("[ref=e2]", "password");
await page.click("[ref=e3]");

// 4. 断开连接（页面保持打开）
await client.disconnect();
```

**再次连接**（在另一个脚本中）
```typescript
const client = await connect();
const page = await client.page("checkout"); // 连接到已存在的checkout页面

// 这里的页面状态和之前完全一样，包括登录状态、表单数据等
const items = await page.textContent(".cart-items");
console.log(items);

await client.disconnect();
```

### 使用方式

**方式一：内联脚本（推荐用于快速测试）**
```bash
cd skills/dev-browser && npx tsx <<'EOF'
import { connect, waitForPageLoad } from "@/client.js";

const client = await connect();
const page = await client.page("test");

await page.goto("https://example.com");
await waitForPageLoad(page);
console.log(await page.title());

await client.disconnect();
EOF
```

**方式二：编写脚本文件**
```typescript
// demo.ts
import { connect } from "@/client.js";

const client = await connect();
const checkout = await client.page("checkout");

await checkout.goto("https://example.com/cart");
// ... 更多操作

await client.disconnect();
```

### 适用场景
- 多步骤工作流（登录 → 浏览 → 结账）
- 需要保持登录状态的任务
- 复杂的表单填充和验证
- 页面元素变化监控
- 数据抓取（需要多次交互）

### 关键API
- `connect()` - 连接到服务器
- `client.page(name, options?)` - 获取/创建命名页面
- `client.list()` - 列出所有命名页面
- `client.close(name)` - 关闭指定页面
- `client.disconnect()` - 断开连接（页面保留）
- `client.getAISnapshot(name)` - 获取ARIA快照
- `client.selectSnapshotRef(name, ref)` - 通过ref获取元素
- `page.goto(url)` - 导航
- `page.screenshot(path)` - 截图
- `page.waitForSelector(selector)` - 等待元素
- `page.evaluate(fn)` - 在页面内执行JS

---

## 对比总结

| 特性 | playwright | dev-browser |
|------|------------|-------------|
| **状态持久化** | ❌ 每次全新 | ✅ 页面保持打开 |
| **命名页面** | ❌ 无 | ✅ 支持 |
| **多脚本协作** | ❌ 不可能 | ✅ 可以连接到同一页面 |
| **会话复用** | ❌ 需要重新登录等 | ✅ 保持登录状态 |
| **适用场景** | 单步操作、快速测试 | 多步骤工作流 |
| **服务器依赖** | 内置MCP服务器 | 需要额外启动server.js |
| **复杂度** | 简单 | 稍复杂（需要管理连接） |
| **资源消耗** | 每次创建/销毁 | 长期占用资源 |

---

## 选择建议

**使用 playwright 当：**
- 只需要截图或获取页面信息
- 任务不超过3-5步
- 不需要保持任何状态
- 想要最简单直接的方式

**使用 dev-browser 当：**
- 需要多步骤交互
- 必须保持登录状态
- 前一步的结果影响后一步
- 需要在不同脚本间共享页面状态
- 复杂的数据抓取任务

---

## 补充说明

### ARIA快照 vs 截图
- **playwright**: `browser_snapshot` 返回YAML格式的DOM结构
- **dev-browser**: `client.getAISnapshot()` + `client.selectSnapshotRef()` 提供类似功能

### 截图后缀
- **playwright**: `browser_take_screenshot` 保存到指定文件
- **dev-browser**: `page.screenshot({path})` 指定路径

### 错误恢复
- **playwright**: 失败后需要重新开始
- **dev-browser**: 可以连接到失败的页面继续调试
