# Notion 数据库属性设置指南

## 📋 问题说明

当前 Notion 数据库中只有标题列，其他字段无法写入，因为缺少对应的属性列。

**重要**：Notion API 不支持通过代码创建数据库属性，需要在 Notion 界面中手动创建。

---

## 🚀 快速设置步骤（推荐）

### 方法一：通过表格视图快速添加（最简单）

1. **打开数据库**
   - 访问：https://www.notion.so/29f1ea34069a80ab95bcc8e2bd34af3f

2. **在表格顶部添加属性**
   - 在表格的列标题区域，点击 **"+ Add a property"** 按钮
   - 依次创建以下属性（点击一个创建一个）：

   | 属性名称 | 属性类型 | 说明 |
   |---------|---------|------|
   | `Outcome Name` | **Text** | 选项名称 |
   | `AI Prediction (%)` | **Number** | AI 预测概率 |
   | `Market Prediction (%)` | **Number** | 市场价格概率 |
   | `Diff (AI - Market)` | **Number** | AI 与市场差值 |
   | `Sum (ΣAI)` | **Number** | AI 预测总和 |
   | `Category` | **Text** | 事件类别 |
   | `Models Used` | **Text** | 使用的模型 |
   | `Summary (AI reasoning)` | **Text** | AI 推理摘要 |
   | `Rules Summary` | **Text** | 规则摘要 |
   | `Timestamp` | **Date** | 时间戳 |
   | `Run ID` | **Text** | 运行 ID |

3. **重命名 Title 列（可选）**
   - 如果 Title 列的名称不是 "Event Name"
   - 点击 Title 列，选择 "Rename"，改为 `Event Name`

---

## 📝 详细步骤说明

### 步骤 1：打开数据库属性设置

1. 在数据库页面，点击右上角的 **"⋯"** (三个点) 菜单
2. 选择 **"Properties"**（属性）

### 步骤 2：添加第一个属性（示例：Outcome Name）

1. 点击 **"+ Add a property"** 按钮
2. 在弹出窗口中：
   - **属性名称**：输入 `Outcome Name`（注意大小写和空格）
   - **属性类型**：选择 **Text**
   - 点击 **"Add"** 或按回车

### 步骤 3：重复添加其他属性

按照上面的表格，依次添加所有 11 个属性。

**重要提示**：
- ⚠️ **属性名称必须完全一致**（包括大小写、空格、特殊字符）
- ⚠️ **属性类型必须正确**（Text/Number/Date）
- ✅ 创建顺序不重要
- ✅ 可以先创建几个，保存后继续创建

---

## ✅ 验证设置

创建完所有属性后，运行验证脚本：

```bash
source venv/bin/activate
python setup_notion_properties.py
```

如果看到 "✅ 所有必需的属性都已存在！"，说明设置成功。

---

## 🎯 属性清单（复制粘贴版）

创建时可以复制以下列表：

```
Outcome Name - Text
AI Prediction (%) - Number
Market Prediction (%) - Number
Diff (AI - Market) - Number
Sum (ΣAI) - Number
Category - Text
Models Used - Text
Summary (AI reasoning) - Text
Rules Summary - Text
Timestamp - Date
Run ID - Text
```

---

## 🔍 常见问题

### Q: 创建属性后还是没有数据？
A: 检查属性名称是否完全一致（包括括号、空格）

### Q: 如何批量创建？
A: Notion 不支持批量创建，需要逐个创建

### Q: 属性类型选错了怎么办？
A: 可以删除后重新创建，或者使用 Notion 的 "Change type" 功能

### Q: 可以不创建某些属性吗？
A: 可以，代码会跳过不存在的属性，但建议创建全部以获得完整数据

---

## 📞 需要帮助？

如果遇到问题，可以：
1. 查看 Notion 官方文档
2. 运行 `python setup_notion_properties.py` 检查当前状态
3. 查看日志文件中的错误信息

---

**创建完成后，Bot 的下一次预测就会自动写入所有字段到 Notion！** 🎉

