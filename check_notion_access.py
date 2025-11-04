#!/usr/bin/env python3
"""
检查 Notion Integration 访问权限和数据库状态
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
    
    print("=" * 70)
    print("🔐 Notion Integration 权限检查")
    print("=" * 70)
    print()
    
    if not notion_token:
        print("❌ NOTION_TOKEN 未设置")
        sys.exit(1)
    
    if not database_id:
        print("❌ NOTION_DB_ID 未设置")
        sys.exit(1)
    
    print(f"✅ Token: {notion_token[:20]}...")
    print(f"✅ Database ID: {database_id}")
    print()
    
    client = Client(auth=notion_token)
    
    # 1. 测试能否访问数据库
    print("=" * 70)
    print("📋 测试 1: 数据库访问权限")
    print("=" * 70)
    print()
    
    try:
        database = client.databases.retrieve(database_id=database_id)
        print("✅ 可以访问数据库")
        
        db_title = database.get("title", [{}])
        title_text = db_title[0].get("plain_text", "Unknown") if db_title else "Unknown"
        print(f"   数据库标题: {title_text}")
        
        # 检查 Title 列的名称
        properties = database.get("properties", {})
        title_prop_name = None
        for prop_name, prop_info in properties.items():
            if prop_info.get("type") == "title":
                title_prop_name = prop_name
                break
        
        if title_prop_name:
            print(f"   Title 列名称: \"{title_prop_name}\"")
            if title_prop_name != "Event Name":
                print(f"   ⚠️  注意：Title 列名称是 \"{title_prop_name}\"，不是 \"Event Name\"")
                print(f"   代码中使用 \"Event Name\"，可能需要重命名 Title 列")
        else:
            print("   ⚠️  未找到 Title 列")
        
        print(f"   总属性数: {len(properties)}")
        print()
        
    except Exception as e:
        print(f"❌ 无法访问数据库: {type(e).__name__}: {e}")
        print()
        if "unauthorized" in str(e).lower() or "401" in str(e):
            print("💡 可能原因：Token 无效或已过期")
        elif "not found" in str(e).lower() or "404" in str(e):
            print("💡 可能原因：Database ID 不正确")
        elif "forbidden" in str(e).lower() or "403" in str(e):
            print("💡 可能原因：Integration 没有该数据库的访问权限")
            print("   解决方案：")
            print("   1. 在 Notion 中打开数据库")
            print("   2. 点击右上角 '...' → 'Connections'")
            print("   3. 确保你的 Integration 已连接")
        sys.exit(1)
    
    # 2. 列出所有属性
    print("=" * 70)
    print("📋 测试 2: 列出所有属性")
    print("=" * 70)
    print()
    
    properties = database.get("properties", {})
    
    if not properties:
        print("❌ 数据库中没有属性（只有默认的 Title 列）")
        print()
        print("可能的原因：")
        print("1. 属性确实尚未创建")
        print("2. 属性在某个视图中被隐藏（但 API 应该仍能看到）")
        print("3. 创建属性的数据库不是当前这个数据库")
        print()
        print("💡 请确认：")
        print(f"   - 你创建属性的数据库 ID 是: {database_id}")
        print(f"   - 数据库链接: https://www.notion.so/{database_id}")
        print()
    else:
        print(f"✅ 找到 {len(properties)} 个属性：")
        print()
        for prop_name, prop_info in properties.items():
            prop_type = prop_info.get("type", "unknown")
            print(f"   • \"{prop_name}\" ({prop_type})")
        print()
    
    # 3. 测试写入权限
    print("=" * 70)
    print("📋 测试 3: 写入权限测试")
    print("=" * 70)
    print()
    
    try:
        # 使用 Title 列（一定存在）创建测试页面
        title_prop_name = None
        for prop_name, prop_info in properties.items():
            if prop_info.get("type") == "title":
                title_prop_name = prop_name
                break
        
        if title_prop_name:
            test_props = {
                title_prop_name: {
                    "title": [{"text": {"content": "测试权限 - 可删除"}}]
                }
            }
            
            test_page = client.pages.create(
                parent={"database_id": database_id},
                properties=test_props
            )
            print("✅ 可以写入数据库")
            print(f"   测试页面 ID: {test_page.get('id', '')[:8]}...")
            
            # 删除测试页面
            try:
                client.pages.update(
                    page_id=test_page['id'],
                    archived=True
                )
                print("   ✅ 测试页面已删除")
            except:
                print("   ⚠️  无法删除测试页面（可以手动删除）")
            
        else:
            print("⚠️  无法测试写入（未找到 Title 列）")
            
    except Exception as e:
        error_msg = str(e)
        print(f"❌ 无法写入数据库: {error_msg}")
        print()
        if "forbidden" in error_msg.lower() or "403" in error_msg:
            print("💡 权限问题：Integration 没有写入权限")
            print("   解决方案：")
            print("   1. 在 Notion 中打开数据库")
            print("   2. 点击右上角 '...' → 'Connections'")
            print("   3. 确保你的 Integration 有 'Can edit' 权限")
        elif "not a property" in error_msg.lower():
            print("💡 属性问题：使用的属性不存在")
        
    # 4. 检查代码中使用的属性名称
    print()
    print("=" * 70)
    print("📋 测试 4: 代码中的属性名称检查")
    print("=" * 70)
    print()
    
    code_properties = [
        "Event Name",
        "Outcome Name",
        "AI Prediction (%)",
        "Market Prediction (%)",
        "Diff (AI - Market)",
        "Sum (ΣAI)",
        "Category",
        "Models Used",
        "Summary (AI reasoning)",
        "Rules Summary",
        "Timestamp",
        "Run ID"
    ]
    
    print("代码中使用的属性名称：")
    for prop in code_properties:
        if prop in properties:
            print(f"   ✅ \"{prop}\" - 存在")
        else:
            print(f"   ❌ \"{prop}\" - 不存在")
    print()
    
    # 5. 总结和建议
    print("=" * 70)
    print("💡 总结和建议")
    print("=" * 70)
    print()
    
    if not properties or len(properties) <= 1:  # 只有 Title
        print("🔴 问题确认：数据库中缺少必要的属性")
        print()
        print("请执行以下步骤：")
        print(f"1. 打开数据库: https://www.notion.so/{database_id}")
        print("2. 在表格顶部，点击 '+ Add a property'")
        print("3. 创建以下属性（注意名称必须完全一致）：")
        print()
        for prop in code_properties[1:]:  # 跳过 Event Name（Title）
            print(f"   • {prop}")
        print()
        print("⚠️  重要提示：")
        print("   - 属性名称必须与代码中完全一致（包括大小写、空格、括号）")
        print("   - Event Name 通常是 Title 列，如果名称不同需要重命名")
        print("   - 创建后可能需要等待几秒钟 API 才能看到新属性")
        
except ImportError:
    print("❌ notion-client 未安装")
    print("💡 请运行: pip install notion-client")
except Exception as e:
    print(f"❌ 检查失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

