# fix_card.py
import json
import os

def fix_card(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 尝试修复常见的 JSON 损坏模式
    # 移除不完整的 completion_tokens_details
    import re
    # 查找并移除损坏的 completion_tokens_details 部分
    pattern = r'"completion_tokens_details":\s*\{[^}]*$'
    content = re.sub(pattern, '"completion_tokens_details": {}', content, flags=re.MULTILINE)
    
    # 尝试解析
    try:
        data = json.loads(content)
        # 递归清理 metadata.usage
        def clean_usage(obj):
            if isinstance(obj, dict):
                if "metadata" in obj and isinstance(obj["metadata"], dict):
                    if "usage" in obj["metadata"] and isinstance(obj["metadata"]["usage"], dict):
                        # 只保留基本字段
                        usage = obj["metadata"]["usage"]
                        clean_usage_dict = {
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                            "total_tokens": usage.get("total_tokens", 0),
                        }
                        obj["metadata"]["usage"] = clean_usage_dict
                for key, value in obj.items():
                    clean_usage(value)
            elif isinstance(obj, list):
                for item in obj:
                    clean_usage(item)
            return obj
        
        data = clean_usage(data)
        
        # 保存修复后的文件
        backup = filepath + ".bak"
        os.rename(filepath, backup)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ 修复完成: {filepath}")
        print(f"📁 备份保存为: {backup}")
    except json.JSONDecodeError as e:
        print(f"❌ 修复失败: {e}")

if __name__ == "__main__":
    fix_card("猫娘萝莉_重构版.json")  # 改成你的文件名