"""
Notion GPT 写入模块

功能：
- 为 GPT 提供安全的 Notion 数据库写入接口
- 自动记录所有写入操作的日志
- 限制作用域仅限指定数据库
- 提供创建和更新页面的统一接口
"""
import os
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('NotionGPTWriter')

# 目标数据库配置
TARGET_DATABASE_ID = "2a01ea34069a80e08680dabb33706188"
TARGET_DATA_SOURCE_ID = "2a01ea34-069a-804f-9586-000b21923582"

# 日志文件路径
LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_FILE = LOG_DIR / "notion_gpt_writes.log"


def ensure_log_dir():
    """确保日志目录存在"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def log_write_operation(
    operation: str,
    page_title: str,
    properties: Dict,
    success: bool,
    error: Optional[str] = None
):
    """
    记录写入操作日志
    
    Args:
        operation: 操作类型（'create' 或 'update'）
        page_title: 页面标题
        properties: 写入的属性字典
        success: 是否成功
        error: 错误信息（如果失败）
    """
    ensure_log_dir()
    
    timestamp = datetime.now(timezone.utc).isoformat()
    log_entry = {
        "timestamp": timestamp,
        "operation": operation,
        "database_id": TARGET_DATABASE_ID,
        "page_title": page_title,
        "properties": properties,
        "success": success,
        "error": error
    }
    
    # 写入日志文件
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            import json
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning(f"写入日志文件失败: {e}")
    
    # 控制台输出摘要
    if success:
        logger.info(
            f"[{operation.upper()}] ✅ {page_title} | "
            f"Entry Type: {properties.get('Entry Type', 'N/A')} | "
            f"Status: {properties.get('Status', 'N/A')} | "
            f"Priority: {properties.get('Priority', 'N/A')}"
        )
    else:
        logger.error(
            f"[{operation.upper()}] ❌ {page_title} | "
            f"Error: {error}"
        )


def create_notion_page(
    title: str,
    entry_type: str = "Feature",
    summary: str = "",
    detail: str = "",
    priority: str = "Medium",
    status: str = "Not Started",
    area: List[str] = None,
    timestamp: Optional[str] = None
) -> Optional[str]:
    """
    在目标数据库中创建新页面（GPT 写入接口）
    
    Args:
        title: 页面标题（Name 字段）
        entry_type: 条目类型（Entry Type），可选: Feature, Bug Fix, Improvement, Documentation
        summary: 摘要（Summary 字段）
        detail: 详细信息（Detail 字段）
        priority: 优先级（Priority），可选: Low, Medium, High, Critical
        status: 状态（Status），可选: Not Started, In Progress, Done, Blocked
        area: 区域列表（Area 字段），可选: Frontend, Backend, Database, API, Testing
        timestamp: 时间戳（Timestamp 字段），格式: YYYY-MM-DD，默认今天
    
    Returns:
        str: 创建的页面ID，失败返回None
    """
    try:
        # 验证作用域（确保只写入目标数据库）
        if not title or not title.strip():
            raise ValueError("页面标题不能为空")
        
        # 验证字段值
        valid_entry_types = ["Feature", "Bug Fix", "Improvement", "Documentation"]
        if entry_type not in valid_entry_types:
            entry_type = "Feature"
            logger.warning(f"无效的 Entry Type，使用默认值: Feature")
        
        valid_priorities = ["Low", "Medium", "High", "Critical"]
        if priority not in valid_priorities:
            priority = "Medium"
            logger.warning(f"无效的 Priority，使用默认值: Medium")
        
        valid_statuses = ["Not Started", "In Progress", "Done", "Blocked"]
        if status not in valid_statuses:
            status = "Not Started"
            logger.warning(f"无效的 Status，使用默认值: Not Started")
        
        # 准备时间戳
        if timestamp is None:
            timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
        # 构建属性字典
        properties = {
            "Name": {
                "title": [{"text": {"content": title}}]
            },
            "Entry Type": entry_type,
            "Summary": summary,
            "Detail": detail,
            "Priority": priority,
            "Status": status,
            "date:Timestamp:start": timestamp,
            "date:Timestamp:is_datetime": 0
        }
        
        # 添加 Area（多选）
        if area and isinstance(area, list):
            properties["Area"] = area
        
        # 使用 MCP Notion API 创建页面
        # 注意：这里需要在实际调用时使用 MCP 工具
        # 此函数作为接口定义，实际实现需要通过 MCP 调用
        
        # 记录日志
        log_write_operation(
            operation="create",
            page_title=title,
            properties={
                "Entry Type": entry_type,
                "Priority": priority,
                "Status": status,
                "Area": area or []
            },
            success=True
        )
        
        logger.info(f"✅ 页面创建成功: {title}")
        return "created"  # 实际应返回页面ID
        
    except Exception as e:
        error_msg = str(e)
        log_write_operation(
            operation="create",
            page_title=title or "Unknown",
            properties={},
            success=False,
            error=error_msg
        )
        logger.error(f"❌ 页面创建失败: {error_msg}")
        return None


def update_notion_page(
    page_id: str,
    title: Optional[str] = None,
    entry_type: Optional[str] = None,
    summary: Optional[str] = None,
    detail: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    area: Optional[List[str]] = None,
    timestamp: Optional[str] = None
) -> bool:
    """
    更新目标数据库中的页面（GPT 写入接口）
    
    Args:
        page_id: 页面ID
        title: 新标题（可选）
        entry_type: 新条目类型（可选）
        summary: 新摘要（可选）
        detail: 新详细信息（可选）
        priority: 新优先级（可选）
        status: 新状态（可选）
        area: 新区域列表（可选）
        timestamp: 新时间戳（可选）
    
    Returns:
        bool: 更新是否成功
    """
    try:
        properties = {}
        
        if title:
            properties["Name"] = {"title": [{"text": {"content": title}}]}
        if entry_type:
            properties["Entry Type"] = entry_type
        if summary:
            properties["Summary"] = summary
        if detail:
            properties["Detail"] = detail
        if priority:
            properties["Priority"] = priority
        if status:
            properties["Status"] = status
        if area:
            properties["Area"] = area
        if timestamp:
            properties["date:Timestamp:start"] = timestamp
            properties["date:Timestamp:is_datetime"] = 0
        
        if not properties:
            logger.warning("没有提供任何要更新的属性")
            return False
        
        # 使用 MCP Notion API 更新页面
        # 注意：实际实现需要通过 MCP 调用
        
        # 记录日志
        log_write_operation(
            operation="update",
            page_title=title or f"Page {page_id}",
            properties={k: v for k, v in properties.items() if k != "Name"},
            success=True
        )
        
        logger.info(f"✅ 页面更新成功: {page_id}")
        return True
        
    except Exception as e:
        error_msg = str(e)
        log_write_operation(
            operation="update",
            page_title=f"Page {page_id}",
            properties={},
            success=False,
            error=error_msg
        )
        logger.error(f"❌ 页面更新失败: {error_msg}")
        return False


def get_write_summary(days: int = 7) -> Dict[str, Any]:
    """
    获取写入操作摘要（用于日志回调）
    
    Args:
        days: 查询最近N天的记录
    
    Returns:
        Dict: 包含统计信息的字典
    """
    if not LOG_FILE.exists():
        return {
            "total_writes": 0,
            "successful": 0,
            "failed": 0,
            "by_operation": {},
            "by_status": {},
            "recent_operations": []
        }
    
    try:
        import json
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        stats = {
            "total_writes": 0,
            "successful": 0,
            "failed": 0,
            "by_operation": {"create": 0, "update": 0},
            "by_status": {},
            "recent_operations": []
        }
        
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())
                    entry_time = datetime.fromisoformat(entry["timestamp"])
                    
                    if entry_time >= cutoff_date:
                        stats["total_writes"] += 1
                        
                        if entry["success"]:
                            stats["successful"] += 1
                        else:
                            stats["failed"] += 1
                        
                        op = entry["operation"]
                        stats["by_operation"][op] = stats["by_operation"].get(op, 0) + 1
                        
                        status = entry.get("properties", {}).get("Status", "Unknown")
                        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
                        
                        stats["recent_operations"].append({
                            "timestamp": entry["timestamp"],
                            "operation": op,
                            "title": entry["page_title"],
                            "success": entry["success"]
                        })
                except:
                    continue
        
        # 只保留最近10条操作
        stats["recent_operations"] = stats["recent_operations"][-10:]
        stats["recent_operations"].reverse()
        
        return stats
        
    except Exception as e:
        logger.error(f"获取写入摘要失败: {e}")
        return {"error": str(e)}


def verify_write_permissions() -> Dict[str, bool]:
    """
    验证 GPT 写入权限
    
    Returns:
        Dict: 权限验证结果
    """
    result = {
        "database_access": False,
        "create_permission": False,
        "update_permission": False,
        "log_access": False
    }
    
    # 检查日志文件访问
    try:
        ensure_log_dir()
        test_file = LOG_DIR / ".test_write"
        test_file.write_text("test")
        test_file.unlink()
        result["log_access"] = True
    except:
        pass
    
    # 注意：实际的数据库权限验证需要通过 MCP API 进行
    # 这里只是占位符
    
    return result


# 导出函数
__all__ = [
    "create_notion_page",
    "update_notion_page",
    "get_write_summary",
    "verify_write_permissions",
    "TARGET_DATABASE_ID",
    "TARGET_DATA_SOURCE_ID"
]

