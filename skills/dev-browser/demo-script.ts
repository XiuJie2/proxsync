import { connect, waitForPageLoad } from "@/client.js";

const client = await connect();
const page = await client.page("demo", { viewport: { width: 1280, height: 720 } });

console.log("导航到 example.com...");
await page.goto("https://example.com");
await waitForPageLoad(page);

console.log("页面标题:", await page.title());
console.log("当前URL:", page.url());

// 获取 ARIA 快照
const snapshot = await client.getAISnapshot("demo");
console.log("\n=== ARIA 快照 ===");
console.log(snapshot);

// 截屏
await page.screenshot({ path: "demo-page.png" });
console.log("\n截图已保存: demo-page.png");

// 获取页面文本
const bodyText = await page.textContent("body");
console.log("\n=== 页面正文预览 ===");
console.log(bodyText.slice(0, 200) + "...");

await client.disconnect();
console.log("\n连接已关闭，页面状态保留在服务器上");