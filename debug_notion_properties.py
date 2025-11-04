#!/usr/bin/env python3
"""
详细诊断 Notion 数据库属性问题
"""
import sys
import os
import json
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
    print("🔍 Notion 数据库属性详细诊断")
    print("=" * 70)
    print()
    
    try:
        database = client.databases.retrieve(database_id=database_id)
        
        print(f"📊 数据库 ID: {database_id}")
        db_title = database.get("title", [{}])
        title_text = db_title[0].get("plain_text", "Unknown") if db_title else "Unknown"
        print(f"📝 数据库标题: {title_text}")
        print()
        
        # 获取所有属性（包括隐藏的）
        all_properties = database.get("properties", {})
        
        print("=" * 70)
        print("📋 数据库中的所有属性（原始数据）")
        print("=" * 70)
        print()
        
        if not all_properties:
            print("❌ 未检测到任何属性（除了默认的 Title 列）")
            print()
            print("可能原因：")
            print("1. 属性尚未创建")
            print("2. Integration 没有读取权限")
            print("3. 属性在其他视图中被隐藏")
            print()
        else:
            print(f"✅ 检测到 {len(all_properties)} 个属性：")
            print()
            
            for prop_name, prop_info in all_properties.items():
                prop_type = prop_info.get("type", "unknown")
                print(f"属性名: \"{prop_name}\"")
                print(f"  类型: {prop_type}")
                
                # 显示原始 JSON（用于调试）
                print(f"  原始数据: {json.dumps(prop_info, indent=2, ensure_ascii=False)[:200]}...")
                print()
        
        # 代码中使用的属性名称
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
        
        print("=" * 70)
        print("🔍 属性名称匹配检查")
        print("=" * 70)
        print()
        print("代码中使用的属性名称 vs 数据库中的实际属性：")
        print()
        
        missing_props = []
        found_props = []
        similar_props = []
        
        for code_prop in code_properties:
            if code_prop in all_properties:
                found_props.append(code_prop)
                print(f"✅ 匹配: \"{code_prop}\"")
            else:
                # 检查是否有相似的名称
                similar = [p for p in all_properties.keys() 
                          if p.lower().replace(' ', '') == code_prop.lower().replace(' ', '')]
                
                if similar:
                    similar_props.append((code_prop, similar[0]))
                    print(f"⚠️  相似但不匹配:")
                    print(f"   代码中: \"{code_prop}\"")
                    print(f"   数据库中: \"{similar[0]}\"")
                    print(f"   (可能是大小写或空格问题)")
                else:
                    missing_props.append(code_prop)
                    print(f"❌ 缺失: \"{code_prop}\"")
            print()
        
        print("=" * 70)
        print("📊 匹配统计")
        print("=" * 70)
        print(f"✅ 完全匹配: {len(found_props)}/{len(code_properties)}")
        print(f"⚠️  相似但不匹配: {len(similar_props)}")
        print(f"❌ 完全缺失: {len(missing_props)}")
        print()
        
        if similar_props:
            print("=" * 70)
            print("⚠️  发现名称相似但不完全匹配的属性")
            print("=" * 70)
            print()
            print("建议修复方法：")
            for code_name, db_name in similar_props:
                print(f"1. 在 Notion 中将 \"{db_name}\" 重命名为 \"{code_name}\"")
            print()
        
        if missing_props:
            print("=" * 70)
            print("❌ 完全缺失的属性")
            print("=" * 70)
            print()
            for prop in missing_props:
                print(f"  - {prop}")
            print()
            print("请在 Notion 中创建这些属性")
            print()
        
        # 测试写入一个属性，看实际错误
        print("=" * 70)
        print("🧪 测试写入（诊断模式）")
        print("=" * 70)
        print()
        
        test_props = {}
        if found_props:
            # 尝试使用一个已存在的属性
            test_prop_name = found_props[0]
            if all_properties[test_prop_name].get("type") == "rich_text":
                test_props[test_prop_name] = {
                    "rich_text": [{"text": {"content": "测试"}}]
                }
                print(f"尝试写入属性: {test_prop_name}")
            elif all_properties[test_prop_name].get("type") == "number":
                test_props[test_prop_name] = {"number": 1.0}
                print(f"尝试写入属性: {test_prop_name}")
        
        if test_props:
            try:
                # 尝试创建一条测试记录
                test_page = client.pages.create(
                    parent={"database_id": database_id},
                    properties=test_props
                )
                print(f"✅ 测试写入成功！")
                print(f"   页面 ID: {test_page.get('id', '')[:8]}...")
                print()
                print("💡 说明：至少有一个属性可以正常写入")
                
                # 删除测试页面
                try:
                    client.pages.update(
                        page_id=test_page['id'],
                        archived=True
                    )
                    print("   测试页面已删除")
                except:
                    pass
                
            except Exception as e:
                error_msg = str(e)
                print(f"❌ 测试写入失败: {error_msg}")
                print()
                
                # 分析错误
                if "not a property" in error_msg.lower():
                    print("💡 问题分析：")
                    print("   属性名称不匹配，请检查：")
                    print("   1. 属性名称是否完全一致（包括大小写、空格、特殊字符）")
                    print("   2. 是否在正确的数据库中")
                    print("   3. Integration 是否有该数据库的访问权限")
                elif "permission" in error_msg.lower() or "forbidden" in error_msg.lower():
                    print("💡 问题分析：")
                    print("   权限不足，请检查 Integration 是否有写入权限")
                else:
                    print(f"💡 其他错误: {type(e).__name__}")
        else:
            print("⚠️  没有可测试的属性（所有属性都缺失）")
            
    except Exception as e:
        print(f"❌ 诊断失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        
except ImportError:
    print("❌ notion-client 未安装")
    print("💡 请运行: pip install notion-client")

