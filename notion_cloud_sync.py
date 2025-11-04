from flask import Flask, request, jsonify
from notion_client import Client
import os

NOTION_TOKEN = "ntn_U82242454027zGX0MnNU1fUCKIqyNxL9ww2OszvPLRudaP"
DATABASE_ID = "2a01ea34069a80e08680dabb33706188"

notion = Client(auth=NOTION_TOKEN)
app = Flask(__name__)

@app.route('/notion_sync', methods=['POST'])
def notion_sync():
    data = request.get_json()
    module = data.get('module', '未命名模块')
    status = data.get('status', 'Unknown')

    try:
        notion.pages.create(
            parent={"database_id": DATABASE_ID},
            properties={
                "模块名": {"title": [{"text": {"content": module}}]},
                "状态": {"rich_text": [{"text": {"content": status}}]},
            },
        )
        return jsonify({"success": True, "message": f"✅ 已写入 Notion：{module} ({status})"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
