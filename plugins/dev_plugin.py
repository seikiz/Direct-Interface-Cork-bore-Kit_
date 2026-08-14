# plugins/dev_plugin.py
import re
import json
import subprocess
import sys
from plugin_base import PluginBase

class DevPlugin(PluginBase):
    name = "程序员工具"
    version = "1.0"
    description = "代码格式化、解释、生成、高亮等工具"
    author = "seiki"
    enabled = True

    # 代码高亮标签映射（在 CTkTextbox 中使用）
    HIGHLIGHT_RULES = {
        "keyword": ["def", "class", "if", "elif", "else", "for", "while", "return", "import", "from", "try", "except", "finally", "with", "as", "lambda", "yield", "pass", "break", "continue", "raise", "True", "False", "None", "and", "or", "not"],
        "string": ['"', "'", '"""', "'''"],
        "comment": ["#", "//", "/*", "*/"],
        "function": r'[a-zA-Z_][a-zA-Z0-9_]*\s*\(',
        "number": r'\b[0-9]+\b',
    }

    def __init__(self, core):
        super().__init__(core)
        self.temp_code = None

    def on_command(self, command, args):
        if command == "code":
            return self.cmd_code(args)
        elif command == "format":
            return self.cmd_format(args)
        elif command == "explain":
            return self.cmd_explain(args)
        elif command == "highlight":
            return self.cmd_highlight(args)
        elif command == "langs":
            return self.cmd_langs()
        return None

    # ---------- 子命令 ----------
    def cmd_code(self, args):
        """生成代码（AI辅助）"""
        if not args:
            return "用法: /code <描述>", False
        # 注：直接返回提示，让用户把描述发给AI，或者标记为AI指令
        return f"[AI生成请求]\n请帮我生成以下功能对应的代码：{args}", True

    def cmd_format(self, args):
        """格式化代码"""
        if not args:
            return "用法: /format <代码> 或 /format python <代码>", False
        
        # 检测是否带语言参数
        parts = args.split(maxsplit=1)
        lang = "python"
        code = args
        if len(parts) == 2 and parts[0] in ["python", "javascript", "js", "json", "html", "css"]:
            lang = parts[0]
            code = parts[1]
        
        try:
            if lang == "python":
                import ast
                tree = ast.parse(code)
                formatted = ast.unparse(tree)
                return f"```python\n{formatted}\n```", True
            elif lang in ["json", "js"]:
                # 尝试格式化 JSON
                data = json.loads(code)
                formatted = json.dumps(data, ensure_ascii=False, indent=2)
                return f"```json\n{formatted}\n```", True
            else:
                # 简单缩进格式化
                lines = code.strip().split('\n')
                formatted = self._simple_format(lines)
                return f"```{lang}\n{formatted}\n```", True
        except Exception as e:
            return f"格式化失败: {e}", False

    def cmd_explain(self, args):
        """解释代码"""
        if not args:
            return "用法: /explain <代码>", False
        return f"[AI解释请求]\n请用简单的语言解释以下代码的功能和逻辑：\n\n```\n{args[:500]}\n```", True

    def cmd_highlight(self, args):
        """生成带高亮的代码块（返回纯文本标记）"""
        if not args:
            return "用法: /highlight python <代码>", False
        
        parts = args.split(maxsplit=1)
        lang = "python"
        code = args
        if len(parts) == 2 and parts[0] in ["python", "javascript", "js", "json", "html", "css", "sql", "java", "cpp"]:
            lang = parts[0]
            code = parts[1]
        
        highlighted = self._highlight_code(code, lang)
        return f"【{lang.upper()} 高亮】\n{highlighted}", False

    def cmd_langs(self):
        return "支持的语言: python, javascript, js, json, html, css, sql, java, cpp", False

    # ---------- 内部工具 ----------
    def _simple_format(self, lines):
        """简单的缩进修复"""
        result = []
        indent_level = 0
        for line in lines:
            stripped = line.strip()
            if not stripped:
                result.append("")
                continue
            # 检查闭括号减少缩进
            if stripped in ['}', ']', ')']:
                indent_level = max(0, indent_level - 1)
            result.append("    " * indent_level + stripped)
            # 检查开括号增加缩进
            if stripped.endswith('{') or stripped.endswith('[') or stripped.endswith('('):
                indent_level += 1
        return '\n'.join(result)

    def _highlight_code(self, code, lang):
        """模拟代码高亮（返回纯文本标记）"""
        # 简单实现：只做关键字高亮标记
        keywords = set(self.HIGHLIGHT_RULES.get("keyword", []))
        lines = code.split('\n')
        result = []
        for line in lines:
            words = line.split()
            new_words = []
            for w in words:
                if w in keywords:
                    new_words.append(f"*{w}*")
                else:
                    new_words.append(w)
            result.append(' '.join(new_words))
        return '\n'.join(result)