# plugins/math_plugin.py
import math
import random
from plugin_base import PluginBase

class MathPlugin(PluginBase):
    name = "数学运算"
    version = "1.0"
    description = "计算、方程求解、统计等工具"
    author = "seiki"
    enabled = True

    def on_command(self, command, args):
        if command == "calc":
            return self.cmd_calc(args)
        elif command == "solve":
            return self.cmd_solve(args)
        elif command == "stats":
            return self.cmd_stats(args)
        elif command == "rand":
            return self.cmd_rand(args)
        elif command == "prime":
            return self.cmd_prime(args)
        return None

    # ---------- 子命令 ----------
    def cmd_calc(self, args):
        """表达式计算"""
        if not args:
            return "用法: /calc <表达式>", False
        
        # 安全评估
        try:
            # 只允许安全的函数
            safe_dict = {
                'abs': abs, 'round': round, 'sum': sum,
                'pow': pow, 'max': max, 'min': min,
                'math': math,
            }
            # 允许访问 math 模块
            result = eval(args, {"__builtins__": {}}, safe_dict)
            return f"{args} = {result}", False
        except Exception as e:
            return f"计算错误: {e}", False

    def cmd_solve(self, args):
        """解方程（返回AI辅助）"""
        if not args:
            return "用法: /solve <方程描述>", False
        return f"[AI求解请求]\n请解以下方程：{args}\n请给出步骤和答案", True

    def cmd_stats(self, args):
        """统计计算"""
        if not args:
            return "用法: /stats <数字1> <数字2> ... 或 /stats <用逗号分隔的数字>", False
        
        # 解析数字列表
        nums = []
        for part in args.replace(',', ' ').split():
            try:
                nums.append(float(part))
            except:
                pass
        
        if len(nums) < 2:
            return "至少需要2个数字", False
        
        n = len(nums)
        total = sum(nums)
        mean = total / n
        variance = sum((x - mean) ** 2 for x in nums) / n
        std_dev = math.sqrt(variance)
        sorted_nums = sorted(nums)
        median = sorted_nums[n//2] if n % 2 else (sorted_nums[n//2-1] + sorted_nums[n//2]) / 2
        
        result = f"""📊 统计结果 (共 {n} 个数):
总和: {total}
平均值: {mean:.4f}
中位数: {median:.4f}
标准差: {std_dev:.4f}
最小值: {min(nums)}
最大值: {max(nums)}"""
        return result, False

    def cmd_rand(self, args):
        """随机数生成"""
        parts = args.split()
        if len(parts) == 0:
            return "用法: /rand <上限> 或 /rand <下限> <上限>", False
        try:
            if len(parts) == 1:
                upper = int(parts[0])
                return f"随机数 (1~{upper}): {random.randint(1, upper)}", False
            elif len(parts) == 2:
                lower = int(parts[0])
                upper = int(parts[1])
                return f"随机数 ({lower}~{upper}): {random.randint(lower, upper)}", False
        except:
            return "请使用有效的整数", False
        return "用法: /rand <上限> 或 /rand <下限> <上限>", False

    def cmd_prime(self, args):
        """质数判断"""
        if not args:
            return "用法: /prime <数字>", False
        try:
            n = int(args.strip())
            if n < 2:
                return f"{n} 不是质数", False
            for i in range(2, int(math.sqrt(n)) + 1):
                if n % i == 0:
                    return f"{n} = {i} × {n//i}，不是质数", False
            return f"{n} 是质数 ✅", False
        except:
            return "请输入有效的整数", False