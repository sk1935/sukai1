#!/usr/bin/env python3
"""
Notion 数据库属性检查和设置工具

此脚本将：
1. 检查 Notion 数据库中现有的属性
2. 列出缺失的属性
3. 提供详细的创建步骤
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

try:
    from notion_client import Client
    import json
    
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DB_ID")
    
    if not notion_token or not database_id:
        print("❌ 请先配置 NOTION_TOKEN 和 NOTION_DB_ID")
        sys.exit(1)
    
    client = Client(auth=notion_token)
    
    print("=" * 70)
    print("📋 Notion 数据库属性检查工具")
    print("=" * 70)
    print()
    
    # 获取数据库信息
    try:
        database = client.databases.retrieve(database_id=database_id)
        db_title = database.get("title", [{}])
        title_text = db_title[0].get("plain_text", "Unknown") if db_title else "Unknown"
        
        print(f"📊 数据库标题: {title_text}")
        print(f"📝 数据库 ID: {database_id}")
        print()
        
        # 获取现有属性
        existing_props = database.get("properties", {})
        
        print("=" * 70)
        print("✅ 现有属性列表")
        print("=" * 70)
        if existing_props:
            for prop_name, prop_info in existing_props.items():
                prop_type = prop_info.get("type", "unknown")
                prop_id = prop_info.get("id", "")
                print(f"  ✅ {prop_name}")
                print(f"     类型: {prop_type}")
                print(f"     ID: {prop_id[:8]}...")
                print()
        else:
            print("  (无属性，只有默认的 Title 列)")
            print()
        
        # 必需的属性列表
        required_props = {
            "Event Name": {
                "type": "title",
                "description": "事件名称（主标题列，通常已存在）"
            },
            "Outcome Name": {
                "type": "rich_text",
                "description": "选项名称"
            },
            "AI Prediction (%)": {
                "type": "number",
                "description": "AI 预测概率（百分比）"
            },
            "Market Prediction (%)": {
                "type": "number",
                "description": "市场价格概率（百分比）"
            },
            "Diff (AI - Market)": {
                "type": "number",
                "description": "AI 与市场预测差值"
            },
            "Sum (ΣAI)": {
                "type": "number",
                "description": "AI 预测总和（多选项事件）"
            },
            "Category": {
                "type": "rich_text",
                "description": "事件类别"
            },
            "Models Used": {
                "type": "rich_text",
                "description": "使用的模型列表"
            },
            "Summary (AI reasoning)": {
                "type": "rich_text",
                "description": "AI 推理摘要"
            },
            "Rules Summary": {
                "type": "rich_text",
                "description": "市场规则摘要"
            },
            "Timestamp": {
                "type": "date",
                "description": "预测时间戳（UTC）"
            },
            "Run ID": {
                "type": "rich_text",
                "description": "运行 ID（UUID）"
            }
        }
        
        existing_prop_names = set(existing_props.keys())
        missing_props = []
        
        print("=" * 70)
        print("❌ 缺失的属性列表")
        print("=" * 70)
        for prop_name, prop_info in required_props.items():
            if prop_name not in existing_prop_names:
                missing_props.append((prop_name, prop_info))
                print(f"  ❌ {prop_name}")
                print(f"     类型: {prop_info['type']}")
                print(f"     说明: {prop_info['description']}")
                print()
        
        if not missing_props:
            print("  ✅ 所有必需的属性都已存在！")
            print()
        else:
            print("=" * 70)
            print("📝 创建步骤（请按照以下步骤在 Notion 中手动创建）")
            print("=" * 70)
            print()
            print("⚠️  注意：Notion API 不支持通过代码创建数据库属性")
            print("   需要您在 Notion 界面中手动添加以下属性。")
            print()
            
            for i, (prop_name, prop_info) in enumerate(missing_props, 1):
                print(f"步骤 {i}: 创建属性 '{prop_name}'")
                print("  • 在 Notion 数据库中，点击右上角的 '...' 菜单")
                print("  • 选择 'Properties'（属性）")
                print("  • 点击 '+' 添加新属性")
                print(f"  • 属性名称: {prop_name}")
                
                prop_type = prop_info['type']
                if prop_type == "rich_text":
                    print("  • 属性类型: Text（文本）")
                elif prop_type == "number":
                    print("  • 属性类型: Number（数字）")
                elif prop_type == "date":
                    print("  • 属性类型: Date（日期）")
                elif prop_type == "title":
                    print("  • 属性类型: Title（标题）- 通常已存在")
                
                print(f"  • 说明: {prop_info['description']}")
                print()
            
            print("=" * 70)
            print("💡 快速创建方法")
            print("=" * 70)
            print()
            print("1. 打开数据库：")
            print(f"   https://www.notion.so/{database_id}")
            print()
            print("2. 在表格顶部，点击 '+ Add a property'")
            print()
            print("3. 依次创建以下属性（按顺序）：")
            for prop_name, prop_info in missing_props:
                print(f"   - {prop_name} ({prop_info['type']})")
            print()
            print("4. 创建完成后，重新运行此脚本验证")
            print()
            print("=" * 70)
            
    except Exception as e:
        print(f"❌ 获取数据库信息失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
except ImportError:
    print("❌ notion-client 未安装")
    print("💡 请运行: pip install notion-client")

