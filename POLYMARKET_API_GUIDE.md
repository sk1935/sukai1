# 🔑 如何获取 Polymarket API Key

## 📍 获取步骤

### 方法 1: 开发者文档网站
1. **访问 Polymarket 开发者页面**:
   - 直接访问: `https://polymarket.com/developers`
   - 或者访问: `https://docs.polymarket.com` (如果有文档站点)

2. **注册/登录**:
   - 使用你的 Polymarket 账号登录
   - 如果没有账号，先注册

3. **创建 API Key**:
   - 在开发者控制台中找到 "API Keys" 或 "Authentication"
   - 点击 "Create New API Key"
   - 复制生成的 API Key

### 方法 2: 在 Polymarket 网站中查找
1. **登录 Polymarket**:
   - 访问 `https://polymarket.com`
   - 登录你的账号

2. **查找设置**:
   - 点击右上角头像/设置
   - 查找 "Developer"、"API" 或 "Settings" 选项
   - 查看是否有 API Key 相关选项

### 方法 3: 联系支持
如果找不到 API Key 选项：
- 通过 Polymarket 的 Discord 社区询问
- 发送邮件到 support@polymarket.com
- 查看他们的官方文档或 GitHub

## ⚠️ 注意事项

1. **API 可能不公开**: 
   - Polymarket 可能没有公开的 API Key 系统
   - 某些 API 可能需要特殊申请

2. **替代方案**:
   - 如果没有 API Key，系统仍然可以工作
   - 使用 AI 模型进行预测（不使用市场数据）
   - 直接从网站复制市场信息手动输入

3. **Rate Limits**:
   - 如果有 API Key，注意使用频率限制
   - 遵守 Polymarket 的服务条款

## 🔧 配置 API Key

获取 API Key 后，添加到 `.env` 文件：

```bash
POLYMARKET_API_KEY=你的_api_key_这里
```

然后重启 Bot。

## ❓ 如果找不到 API Key

如果确实找不到 API Key，不用担心：

1. **系统仍然可以工作**: Bot 会在没有市场数据时使用 AI 模型预测
2. **手动输入**: 可以从 Polymarket 网站复制市场概率手动使用
3. **等待后续更新**: Polymarket 可能会在未来开放 API





