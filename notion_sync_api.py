"""
Notion 同步 API 服务

功能：
- 提供 Flask API 端点，用于将模块状态同步到 Notion
- 支持写入模块名称、优先级、状态和备注
- 用于模块激活状态检测和监控

使用方法：
1. 启动服务：python notion_sync_api.py
2. POST 请求：curl -X POST http://localhost:5001/notion_sync -H "Content-Type: application/json" -d '{"module": "event_manager", "priority": "High", "status": "Active", "notes": "模块已激活"}'
"""
from flask import Flask, request, jsonify
from notion_client import Client
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

# --- 配置区 ---
# 优先从环境变量读取，如果不存在则使用硬编码值（用于测试）
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "ntn_U82242454027zGX0MnNU1fUCKIqyNxL9ww2OszvPLRudaP")
DATABASE_ID = os.getenv("NOTION_DB_ID", "2a01ea34069a80e08680dabb33706188")

try:
    notion = Client(auth=NOTION_TOKEN)
    print(f"✅ Notion 客户端已初始化（数据库 ID: {DATABASE_ID[:8]}...）")
except Exception as e:
    print(f"⚠️ Notion 客户端初始化失败: {e}")
    notion = None

app = Flask(__name__)


def write_to_notion(module, priority="Medium", status="In Progress", notes=""):
    """
    写入模块状态到 Notion 数据库
    
    Args:
        module: 模块名称
        priority: 优先级 ("Low", "Medium", "High")
        status: 状态 ("Not Started", "In Progress", "Done", "Active", "Inactive")
        notes: 备注信息
    """
    if notion is None:
        raise Exception("Notion 客户端未初始化")
    
    try:
        notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties={
                "Name": {"title": [{"text": {"content": module}}]},
                "Priority": {"select": {"name": priority}},
                "Status": {"select": {"name": status}},
                "Notes": {"rich_text": [{"text": {"content": notes}}]},
                "Updated": {"date": {"start": datetime.datetime.utcnow().isoformat()}}
            }
        )
        print(f"✅ 已写入 Notion：{module} ({status})")
    except Exception as e:
        print(f"❌ 写入 Notion 失败: {e}")
        raise


@app.route("/notion_sync", methods=["POST"])
def sync_to_notion():
    """
    Notion 同步 API 端点
    
    请求格式:
    {
        "module": "event_manager",
        "priority": "Medium",
        "status": "In Progress",
        "notes": "模块已激活，调用链完整"
    }
    """
    if notion is None:
        return jsonify({
            "success": False,
            "error": "Notion 客户端未初始化"
        }), 500
    
    data = request.get_json()
    
    if not data:
        return jsonify({
            "success": False,
            "error": "请求体不能为空"
        }), 400
    
    module = data.get("module", "未指定模块")
    priority = data.get("priority", "Medium")
    status = data.get("status", "In Progress")
    notes = data.get("notes", "")
    
    try:
        write_to_notion(module, priority, status, notes)
        return jsonify({
            "success": True,
            "message": f"✅ 已写入 Notion：{module} ({status})"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@app.route("/health", methods=["GET"])
def health_check():
    """健康检查端点"""
    return jsonify({
        "status": "healthy",
        "notion_initialized": notion is not None,
        "database_id": DATABASE_ID[:8] + "..." if DATABASE_ID else "未配置"
    })


@app.route("/", methods=["GET"])
def index():
    """API 信息端点"""
    return jsonify({
        "service": "Notion Sync API",
        "version": "1.0.0",
        "endpoints": {
            "POST /notion_sync": "同步模块状态到 Notion",
            "GET /health": "健康检查",
            "GET /": "API 信息"
        },
        "usage": {
            "method": "POST",
            "url": "/notion_sync",
            "content_type": "application/json",
            "body": {
                "module": "string (required)",
                "priority": "string (optional, default: 'Medium')",
                "status": "string (optional, default: 'In Progress')",
                "notes": "string (optional, default: '')"
            }
        }
    })


if __name__ == "__main__":
    port = int(os.getenv("NOTION_SYNC_PORT", 5001))
    print(f"\n{'='*60}")
    print(f"🚀 Notion 同步 API 服务启动")
    print(f"{'='*60}")
    print(f"📡 端口: {port}")
    print(f"📊 数据库 ID: {DATABASE_ID[:8]}...")
    print(f"🔗 API 端点:")
    print(f"   POST http://localhost:{port}/notion_sync")
    print(f"   GET  http://localhost:{port}/health")
    print(f"   GET  http://localhost:{port}/")
    print(f"{'='*60}\n")
    
    app.run(host="0.0.0.0", port=port, debug=False)

