#!/usr/bin/env python3
"""
自动创建 Notion 数据库属性（尝试通过 API）

注意：Notion API 可能不支持创建属性，此脚本会尝试，如果失败则提供手动步骤。
"""
import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
load_dotenv()

try:
    from notion_client import Client
    
    notion_token = os.getenv("NOTION_TOKEN")
    database_id = os.getenv("NOTION_DB_ID")
    
    if not notion_token or not database_id:
        print("❌ 请先配置 NOTION_TOKEN 和 NOTION_DB_ID")
        sys.exit(1)
    
    client = Client(auth=notion_token)
    
    print("=" * 70)
    print("🔧 自动创建 Notion 数据库属性")
    print("=" * 70)
    print()
    
    # 获取当前数据库
    try:
        database = client.databases.retrieve(database_id=database_id)
        existing_props = database.get("properties", {})
        existing_prop_names = set(existing_props.keys())
        
        print(f"📊 当前属性数量: {len(existing_props)}")
        print()
        
        # 需要创建的属性
        properties_to_add = {
            "Outcome Name": {"rich_text": {}},
            "AI Prediction (%)": {"number": {}},
            "Market Prediction (%)": {"number": {}},
            "Diff (AI - Market)": {"number": {}},
            "Sum (ΣAI)": {"number": {}},
            "Category": {"rich_text": {}},
            "Models Used": {"rich_text": {}},
            "Summary (AI reasoning)": {"rich_text": {}},
            "Rules Summary": {"rich_text": {}},
            "Timestamp": {"date": {}},
            "Run ID": {"rich_text": {}}
        }
        
        # 检查 Event Name（Title 列）
        if "Event Name" not in existing_prop_names:
            # 尝试重命名 Title 列
            title_prop = None
            for prop_name, prop_info in existing_props.items():
                if prop_info.get("type") == "title":
                    title_prop = prop_name
                    break
            
            if title_prop:
                print(f"💡 检测到 Title 列: '{title_prop}'，建议重命名为 'Event Name'")
                print("   （需要在 Notion 界面手动重命名）")
                print()
        
        # 过滤出需要添加的属性
        props_to_create = {
            name: prop_def 
            for name, prop_def in properties_to_add.items() 
            if name not in existing_prop_names
        }
        
        if not props_to_create:
            print("✅ 所有属性都已存在！")
            sys.exit(0)
        
        print(f"📝 准备创建 {len(props_to_create)} 个属性...")
        print()
        
        # 尝试通过 API 更新数据库
        success_count = 0
        failed_props = []
        
        # 注意：Notion API 可能不支持批量添加属性
        # 我们尝试一次添加一个
        new_properties = existing_props.copy()
        
        for prop_name, prop_def in props_to_create.items():
            try:
                # 尝试添加属性到字典中
                new_properties[prop_name] = prop_def
                print(f"  ✅ 准备添加: {prop_name} ({list(prop_def.keys())[0]})")
                success_count += 1
            except Exception as e:
                print(f"  ❌ 失败: {prop_name} - {e}")
                failed_props.append(prop_name)
        
        # 尝试更新数据库
        if success_count > 0:
            print()
            print("🔄 尝试通过 API 更新数据库...")
            try:
                # Notion API 的 databases.update 方法
                updated_database = client.databases.update(
                    database_id=database_id,
                    properties=new_properties
                )
                
                print("✅ 成功！数据库已更新")
                print(f"   新属性数量: {len(updated_database.get('properties', {}))}")
                print()
                print("💡 请前往 Notion 查看结果：")
                print(f"   https://www.notion.so/{database_id}")
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ API 更新失败: {error_msg}")
                print()
                
                if "does not support" in error_msg.lower() or "not allowed" in error_msg.lower():
                    print("=" * 70)
                    print("⚠️  Notion API 不支持通过代码创建属性")
                    print("=" * 70)
                    print()
                    print("需要在 Notion 界面中手动创建以下属性：")
                    print()
                    
                    for prop_name, prop_def in props_to_create.items():
                        prop_type = list(prop_def.keys())[0]
                        type_map = {
                            "rich_text": "Text（文本）",
                            "number": "Number（数字）",
                            "date": "Date（日期）"
                        }
                        print(f"• {prop_name} - {type_map.get(prop_type, prop_type)}")
                    
                    print()
                    print("📝 手动创建步骤：")
                    print("1. 打开数据库：")
                    print(f"   https://www.notion.so/{database_id}")
                    print()
                    print("2. 在表格顶部，点击 '+ Add a property'")
                    print()
                    print("3. 依次创建上述属性，确保名称和类型完全一致")
                    print()
                    
                else:
                    print("💡 可能原因：")
                    print("   - Integration 没有数据库编辑权限")
                    print("   - 数据库属性限制")
                    print("   - API 版本不支持")
                    
        else:
            print("❌ 没有可以添加的属性")
            
    except Exception as e:
        print(f"❌ 操作失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
except ImportError:
    print("❌ notion-client 未安装")
    print("💡 请运行: pip install notion-client")

