# Notion GPT 写入模式配置指南

## 📋 配置概览

**目标数据库ID:** `2a01ea34069a80e08680dabb33706188`  
**数据源ID:** `2a01ea34-069a-804f-9586-000b21923582`  
**数据库名称:** 软件优化

## ✅ 已启用的功能

### 1. 创建与更新页面
- ✅ **创建权限**: 已启用
- ✅ **更新权限**: 已启用
- ✅ **作用域限制**: 仅限目标数据库

### 2. 日志回调
- ✅ **日志文件**: `logs/notion_gpt_writes.log`
- ✅ **控制台输出**: 每次写入显示摘要
- ✅ **统计摘要**: 支持查询最近N天的写入记录

### 3. 安全限制
- ✅ **作用域验证**: 仅允许写入指定数据库
- ✅ **字段验证**: 自动验证字段值的有效性
- ✅ **错误处理**: 所有异常被捕获并记录

## 🔧 使用方法

### Python 代码示例

```python
from src.services.notion_gpt_writer import (
    create_notion_page,
    update_notion_page,
    get_write_summary,
    verify_write_permissions
)

# 1. 创建新页面
page_id = create_notion_page(
    title="优化新闻抓取模块性能",
    entry_type="Improvement",
    summary="优化了并发抓取逻辑，提升了50%的处理速度",
    detail="详细内容...",
    priority="High",
    status="In Progress",
    area=["Backend", "API"]
)

# 2. 更新页面
update_notion_page(
    page_id=page_id,
    status="Done",
    summary="已完成性能优化"
)

# 3. 查看写入摘要
summary = get_write_summary(days=7)
print(f"最近7天写入: {summary['total_writes']} 次")
print(f"成功: {summary['successful']} 次")
print(f"失败: {summary['failed']} 次")
```

### MCP Notion API 直接调用

```python
from mcp_Notion import notion_create_pages, notion_update_page

# 创建页面
notion_create_pages(
    parent={"data_source_id": "2a01ea34-069a-804f-9586-000b21923582"},
    pages=[{
        "properties": {
            "Name": {"title": [{"text": {"content": "标题"}}]},
            "Entry Type": "Feature",
            "Summary": "摘要",
            "Priority": "High",
            "Status": "Not Started",
            "Area": ["Backend"]
        }
    }]
)

# 更新页面
notion_update_page(
    page_id="页面ID",
    command="update_properties",
    properties={
        "Status": "Done"
    }
)
```

## 📊 字段说明

### Entry Type（条目类型）
- `Feature` - 新功能
- `Bug Fix` - Bug修复
- `Improvement` - 改进优化
- `Documentation` - 文档更新

### Priority（优先级）
- `Low` - 低优先级
- `Medium` - 中等优先级
- `High` - 高优先级
- `Critical` - 紧急

### Status（状态）
- `Not Started` - 未开始
- `In Progress` - 进行中
- `Done` - 已完成
- `Blocked` - 已阻塞

### Area（区域）
- `Frontend` - 前端
- `Backend` - 后端
- `Database` - 数据库
- `API` - API接口
- `Testing` - 测试

## 📝 日志格式

每次写入操作会记录到 `logs/notion_gpt_writes.log`，格式：

```json
{
  "timestamp": "2025-01-27T10:30:00Z",
  "operation": "create",
  "database_id": "2a01ea34069a80e08680dabb33706188",
  "page_title": "页面标题",
  "properties": {
    "Entry Type": "Feature",
    "Priority": "High",
    "Status": "In Progress"
  },
  "success": true,
  "error": null
}
```

## 🔍 查看写入记录

```python
from src.services.notion_gpt_writer import get_write_summary

# 获取最近7天的写入摘要
summary = get_write_summary(days=7)

print("📊 写入统计:")
print(f"  总写入次数: {summary['total_writes']}")
print(f"  成功: {summary['successful']}")
print(f"  失败: {summary['failed']}")
print(f"  创建操作: {summary['by_operation']['create']}")
print(f"  更新操作: {summary['by_operation']['update']}")

print("\n📋 最近操作:")
for op in summary['recent_operations']:
    status = "✅" if op['success'] else "❌"
    print(f"  {status} [{op['operation']}] {op['title']}")
```

## ⚠️ 注意事项

1. **作用域限制**: 所有写入操作仅限于数据库 `2a01ea34069a80e08680dabb33706188`
2. **字段验证**: 无效的字段值会被自动替换为默认值
3. **错误处理**: 所有错误都会被记录，不会中断程序执行
4. **日志大小**: 日志文件会持续增长，建议定期清理旧记录

## 🔐 权限配置

GPT 写入权限通过 Notion Integration 配置：

1. **Notion Integration 设置**:
   - 确保 Integration 有目标数据库的访问权限
   - 确保有 "Update content" 权限
   - 确保有 "Insert content" 权限

2. **数据库权限**:
   - 在 Notion 中，将 Integration 添加到数据库的 "People & Groups"
   - 授予 "Full access" 或 "Can edit" 权限

## ✅ 验证状态

使用以下代码验证权限：

```python
from src.services.notion_gpt_writer import verify_write_permissions

permissions = verify_write_permissions()
print(f"数据库访问: {permissions['database_access']}")
print(f"创建权限: {permissions['create_permission']}")
print(f"更新权限: {permissions['update_permission']}")
print(f"日志访问: {permissions['log_access']}")
```

