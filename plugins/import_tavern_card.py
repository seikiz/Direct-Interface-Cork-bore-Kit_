# ============================================================
#   import_tavern_card.py - 酒馆卡片导入插件
#   核心：从酒馆卡（PNG/JSON）中分离角色设定与世界书
#
#   分离逻辑优化要点（v1.2）：
#   1. 合并所有达到阈值的角色条目（旧版只取最高分一条）
#   2. 评分综合硬标记/人设特征词/世界观特征词(负分)/卡片名关联/
#      常量注入/条目位置/内容长度
#   3. 跳过 enabled=False / disable 的条目
#   4. 回退链中已用作人设的内容不再重复充当场景
#   5. 世界书条目 keys/keywords/secondary_keys 统一归一化为 keywords
#   6. 示例对话解析支持 {{user}}/{{char}}/<user>/<char>/用户：/角色： 等格式
# ============================================================
import os
import json
import uuid
import base64
import re
from datetime import datetime
from tkinter import filedialog
from plugin_base import PluginBase

# 可选解析库
try:
    from tavern_card_parser import parse_png, parse_json
    PARSER_AVAILABLE = True
except ImportError:
    PARSER_AVAILABLE = False
    try:
        from PIL import Image
        PIL_AVAILABLE = True
    except ImportError:
        PIL_AVAILABLE = False


class ImportTavernCard(PluginBase):
    name = "酒馆卡片导入"
    version = "1.2"
    description = "通用分离：自动识别角色设定，独立导出世界卡"
    author = "seiki"
    enabled = True

    # 分离阈值：条目得分 >= 该值视为角色设定
    CHARACTER_SCORE_THRESHOLD = 40

    # 人设强特征词（每类 +25，最多计 3 类）
    ROLE_STRONG_KW = [
        '姓名', '名字', '年龄', '性别', '性格', '个性', '外貌', '长相', '穿着',
        '打扮', '身份', '职业', '出身', '口头禅', '说话风格', '语气', '喜好',
        '讨厌', '目标', '动机', '经历', '身高', '体重', '发色', '瞳色',
    ]
    # 人设弱特征词（只加一次 +10）
    ROLE_WEAK_KW = ['角色', '人物', '人设', '设定', '介绍', '她', '他']
    # 世界观特征词（每类 -20，最多扣 3 类）
    WORLD_KW = [
        '世界观', '世界设定', '地理', '历史', '势力', '国家', '城市', '城镇',
        '种族', '魔法', '科技', '组织', '军队', '星球', '大陆', '地图', '纪年',
        '制度', '政治', '经济', '文化', '气候', '环境',
    ]

    def __init__(self, core):
        super().__init__(core)
        self.save_dir = None
        self.world_dir = None
        self.index_dir = None
        self.core = core
        self.last_merge_count = 0  # 最近一次分离合并的角色条目数

        if hasattr(core, 'save_dir') and core.save_dir:
            self.save_dir = core.save_dir
        if hasattr(core, 'world_dir') and core.world_dir:
            self.world_dir = core.world_dir

        if self.save_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.save_dir = os.path.join(base_dir, "saves")
        if self.world_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.world_dir = os.path.join(base_dir, "worlds")

        self.index_dir = os.path.join(self.world_dir, ".indices")
        for d in [self.save_dir, self.world_dir, self.index_dir]:
            os.makedirs(d, exist_ok=True)

    def on_load(self):
        if not PARSER_AVAILABLE and not PIL_AVAILABLE:
            print("[酒馆卡片导入] 请安装 Pillow: pip install Pillow")
        else:
            print("[酒馆卡片导入] 已加载（纯 Python 分离 v1.2）")

    def on_command(self, command, args):
        if command == "import_card":
            return self._import_card(), False
        elif command == "import_help":
            return self._help(), False
        return None

    def _help(self):
        return "📋 /import_card  导入酒馆卡，自动分离角色设定与世界观", False

    # ============================================================
    # 核心导入入口
    # ============================================================
    def _import_card(self):
        file_path = filedialog.askopenfilename(
            title="选择酒馆卡 (PNG/JSON)",
            filetypes=[("卡片文件", "*.png *.json"), ("PNG图片", "*.png"), ("JSON文件", "*.json"), ("所有文件", "*.*")]
        )
        if not file_path:
            return "已取消", False

        try:
            if PARSER_AVAILABLE:
                card, raw_book = self._parse_with_library(file_path)
            else:
                card, raw_book = self._parse_with_pil(file_path)

            if not card:
                return "❌ 无法解析文件", False

            # 分离角色和世界
            character_card, world_book = self._extract_character_and_world(card, raw_book)

            result = self._save_extracted(character_card, world_book)
            if self.last_merge_count > 0:
                result.insert(0, f"🧩 已从世界书分离并合并 {self.last_merge_count} 个角色设定条目")

            self._refresh_ui()
            return "\n".join(result), False

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"❌ 导入失败: {e}", False

    # ============================================================
    # 保存分离结果（角色卡 + 世界卡 + 索引）
    # ============================================================
    def _save_extracted(self, character_card, world_book):
        """保存分离结果，返回结果消息列表"""
        result = []

        # ----- 角色卡 -----
        safe_name = re.sub(r'[\\/:*?"<>|\s]+', '_', character_card["name"]).strip('_.')
        if not safe_name:
            safe_name = "未命名角色"
        char_filename = f"{safe_name}.json"
        char_path = os.path.join(self.save_dir, char_filename)
        if os.path.exists(char_path):
            base, ext = os.path.splitext(char_path)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            char_path = f"{base}_{i}{ext}"

        with open(char_path, 'w', encoding='utf-8') as f:
            json.dump(character_card, f, ensure_ascii=False, indent=2)
        result.append(f"✅ 角色卡已保存: {os.path.basename(char_path)}")

        # ----- 世界卡 -----
        if not world_book or not isinstance(world_book, dict):
            result.append("⚠️ 未检测到世界书，仅保存角色卡")
            return result

        world_book = self._normalize_world_book(world_book)
        # 过滤被作者禁用的条目（运行时注入不检查 enabled，必须在这里过滤）
        active_entries = [e for e in world_book.get('entries', [])
                          if not (e.get('enabled') is False or e.get('disable'))]
        skipped = len(world_book.get('entries', [])) - len(active_entries)

        if not active_entries:
            result.append("⚠️ 未检测到有效世界观条目，仅保存角色卡")
            return result

        safe_book = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '_',
                           world_book.get('name') or character_card['name'])
        world_filename = f"{safe_book}.json"
        world_path = os.path.join(self.world_dir, world_filename)
        if os.path.exists(world_path):
            base, ext = os.path.splitext(world_path)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            world_path = f"{base}_{i}{ext}"

        world_data = {
            "name": world_book.get('name') or f"{character_card['name']}的世界",
            "description": world_book.get('description') or f"从「{character_card['name']}」提取的世界书",
            "rules": world_book.get('rules', []),
            "entries": active_entries,
        }

        with open(world_path, 'w', encoding='utf-8') as f:
            json.dump(world_data, f, ensure_ascii=False, indent=2)
        msg = f"🌍 世界卡已保存: {os.path.basename(world_path)}（{len(active_entries)} 个条目"
        if skipped:
            msg += f"，跳过 {skipped} 个禁用条目"
        result.append(msg + "）")

        # 生成索引
        index_data = self._build_index(active_entries, world_data['name'], character_card['name'])
        if index_data['entries']:
            index_filename = self._generate_index_filename(world_data['name'], character_card['name'])
            index_path = os.path.join(self.index_dir, index_filename)
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(index_data, f, ensure_ascii=False, indent=2)
            result.append(f"📇 索引已创建: {index_filename}")

        return result

    # ============================================================
    # 核心分离逻辑（纯 Python）
    # ============================================================
    def _score_entry_as_character(self, entry, card_name, position=0, total=0):
        """
        判断 character_book 中的一条目是否为角色设定，返回分数（越高越像角色）。
        综合：硬标记、人设特征词（分类计数）、世界观特征词（负分）、
              卡片名关联、常量注入、条目位置、内容长度。
        """
        content = str(entry.get('content', '') or '')
        comment = str(entry.get('comment', '') or '')
        keys = entry.get('keys') or entry.get('keywords') or []
        if isinstance(keys, str):
            keys = [keys]
        if not content.strip():
            return 0

        score = 0

        # 1. 硬标记（爱丽丝卡 <character_information 结构）
        if '<character_information' in content:
            score += 120

        # 2. 人设强特征词：分类计数，最多计 3 类
        strong_hits = [kw for kw in self.ROLE_STRONG_KW if kw in content]
        score += min(len(strong_hits), 3) * 25

        # 3. 通用角色词（弱特征，只加一次）
        if any(kw in content for kw in self.ROLE_WEAK_KW):
            score += 10

        # 4. 世界观特征词：负分（最多 -60）
        world_hits = [kw for kw in self.WORLD_KW if kw in content]
        score -= min(len(world_hits), 3) * 20

        # 5. 与卡片名关联（comment/内容/keys）
        if card_name:
            name_l = card_name.lower()
            if name_l in comment.lower():
                score += 40
            if name_l in content.lower():
                score += 20
            if any(name_l in str(k).lower() for k in keys):
                score += 30

        # 6. 常量注入条目（constant / always）通常承载核心人设
        if entry.get('constant') or entry.get('always'):
            score += 30
        if any(str(k).strip().lower() == 'always' for k in keys):
            score += 30

        # 7. 位置加权：靠前的条目更可能是人设
        if position == 0:
            score += 8
        elif position == 1:
            score += 5

        # 8. 长度适中
        if 100 <= len(content) <= 6000:
            score += 10

        return score

    def _extract_character_and_world(self, card_data, raw_book):
        """
        从酒馆卡数据中分离角色卡和世界卡。
        返回 (角色卡字典, 世界书字典)

        优化点：
        - 合并所有达到阈值的角色条目（按原顺序），而非仅取最高分一条；
        - 跳过 enabled=False / disable 的条目；
        - 回退链中已用作人设的内容不再重复充当场景；
        - 场景优先级：first_mes > scenario > 剩余的 system_prompt；
        - 世界书条目统一归一化 keys/keywords → keywords。
        """
        name = card_data.get('name', '未命名角色')
        inner = card_data.get('data') if isinstance(card_data.get('data'), dict) else {}

        system_prompt = card_data.get('system_prompt', '') or inner.get('system_prompt', '')

        world_book = raw_book
        character_blocks = []
        self.last_merge_count = 0

        # 从 character_book 中识别角色条目
        if isinstance(raw_book, dict):
            entries = raw_book.get('entries') or []
            if entries:
                selected_positions = []
                for idx, entry in enumerate(entries):
                    if not isinstance(entry, dict):
                        continue
                    # 作者禁用的条目不参与角色提取
                    if entry.get('enabled') is False or entry.get('disable'):
                        continue
                    s = self._score_entry_as_character(entry, name, idx, len(entries))
                    if s >= self.CHARACTER_SCORE_THRESHOLD:
                        selected_positions.append(idx)

                if selected_positions:
                    for idx in selected_positions:
                        block = str(entries[idx].get('content', '') or '').strip()
                        if block:
                            character_blocks.append(block)
                    self.last_merge_count = len(character_blocks)
                    selected_set = set(selected_positions)
                    world_book = dict(raw_book)
                    world_book['entries'] = [e for i, e in enumerate(entries)
                                             if i not in selected_set]

        # ----- 角色设定内容（回退链：用过的不复用） -----
        if character_blocks:
            character_content = "\n\n".join(character_blocks).strip()
        elif system_prompt:
            character_content = system_prompt
            system_prompt = ""  # 已用作人设，不再充当场景
        else:
            alt = card_data.get('alternate_greetings') or inner.get('alternate_greetings')
            if isinstance(alt, list) and alt and str(alt[0]).strip():
                character_content = str(alt[0]).strip()
            else:
                character_content = f"你是{name}。请扮演这个角色与用户互动。"

        # ----- 场景：first_mes > scenario > 剩余的 system_prompt -----
        first_mes = card_data.get('first_mes', '') or inner.get('first_mes', '')
        scenario = card_data.get('scenario', '') or inner.get('scenario', '')
        initial_scene = first_mes or scenario or system_prompt
        if initial_scene in ("", "【PW-AIC】"):
            initial_scene = ""

        # ----- 性格标签（去重保序） -----
        personality_raw = card_data.get('personality', '') or inner.get('personality', '')
        personality_list = self._split_personality(personality_raw)

        # ----- 背景（description 优先，缺失时用 creator_notes 兜底） -----
        background = card_data.get('description', '') or inner.get('description', '')
        if not background:
            creator_notes = card_data.get('creator_notes', '') or inner.get('creator_notes', '')
            if creator_notes:
                background = creator_notes

        # ----- 示例对话 -----
        mes_example = card_data.get('mes_example', '') or inner.get('mes_example', '')
        example_dialogue = self._parse_examples(mes_example)

        # ----- 构建角色卡 -----
        sys_id = str(uuid.uuid4())
        history_tree = {
            "nodes": {
                sys_id: {
                    "id": sys_id,
                    "role": "system",
                    "content": character_content,
                    "parent_id": None,
                    "children_ids": [],
                    "timestamp": datetime.now().isoformat(),
                    "metadata": {}
                }
            },
            "root_id": sys_id,
            "current_leaf_id": sys_id
        }

        character_card = {
            "name": name,
            "system_prompt": character_content,
            "background": background,
            "initial_scene": initial_scene,
            "personality": personality_list,
            "example_dialogue": example_dialogue,
            "speech_style": "",
            "unlocked": False,
            "history_tree": history_tree
        }
        tags = card_data.get('tags') or inner.get('tags')
        if isinstance(tags, list) and tags:
            character_card["tags"] = [str(t) for t in tags if str(t).strip()]

        return character_card, world_book

    # ============================================================
    # 辅助解析
    # ============================================================
    def _split_personality(self, personality_raw):
        """性格标签拆分：兼容逗号/顿号/分号/换行分隔与列表，去重保序"""
        if not personality_raw:
            return []
        if isinstance(personality_raw, list):
            items = [str(p).strip() for p in personality_raw if str(p).strip()]
        else:
            items = [p.strip() for p in re.split(r'[，,、;；\n]+', str(personality_raw)) if p.strip()]
        seen = set()
        uniq = []
        for it in items:
            key = it.lower()
            if key not in seen:
                seen.add(key)
                uniq.append(it)
        return uniq

    def _split_speaker(self, line):
        """识别行首说话者前缀，返回 (speaker, 内容) 或 (None, 原行)"""
        patterns = [
            (r'^\s*\{\{user\}\}\s*[:：]\s*(.*)$', 'user'),
            (r'^\s*\{\{char\}\}\s*[:：]\s*(.*)$', 'char'),
            (r'^\s*<user>\s*[:：]?\s*(.*)$', 'user'),
            (r'^\s*<char>\s*[:：]?\s*(.*)$', 'char'),
            (r'^\s*[（(]?用户[)）]?\s*[:：]\s*(.*)$', 'user'),
            (r'^\s*[（(]?角色[)）]?\s*[:：]\s*(.*)$', 'char'),
            (r'^\s*User\s*[:：]\s*(.*)$', 'user'),
            (r'^\s*Char\s*[:：]\s*(.*)$', 'char'),
        ]
        for pat, speaker in patterns:
            m = re.match(pat, line, re.IGNORECASE)
            if m:
                return speaker, m.group(1).strip()
        return None, line

    def _parse_examples(self, mes_example):
        """
        示例对话解析：支持 {{user}}:/{{char}}:、<user>/<char>、用户：/角色：、
        User:/Char: 前缀；无前缀行按 用户→角色 交替配对；跳过 <START> 与分隔线。
        返回 [{"user":..., "assistant":...}, ...]
        """
        if not mes_example:
            return []
        result = []
        buf = None  # {"user": str, "assistant": str}
        for raw in str(mes_example).strip().split('\n'):
            line = raw.strip()
            if not line:
                continue
            if line == '<START>' or set(line) <= set('-*=_~'):
                continue
            speaker, text = self._split_speaker(line)
            if speaker == 'user':
                if buf and buf['assistant']:
                    result.append(buf)
                    buf = None
                if buf is None:
                    buf = {'user': text, 'assistant': ''}
                else:
                    buf['user'] += '\n' + text
            elif speaker == 'char':
                if buf is None:
                    continue  # 无对应 user 行，丢弃
                buf['assistant'] += ('\n' if buf['assistant'] else '') + text
            else:
                # 无前缀行：交替归入
                if buf is None:
                    buf = {'user': line, 'assistant': ''}
                elif not buf['assistant']:
                    buf['assistant'] += ('\n' if buf['assistant'] else '') + line
                else:
                    result.append(buf)
                    buf = {'user': line, 'assistant': ''}
        if buf and buf['user'].strip() and buf['assistant'].strip():
            result.append(buf)
        return result

    def _normalize_world_book(self, book):
        """归一化世界书条目：合并 keys/keywords/secondary_keys → keywords（去重保序）"""
        if not isinstance(book, dict):
            return book
        book = dict(book)
        entries = []
        for e in book.get('entries') or []:
            if not isinstance(e, dict):
                continue
            e = dict(e)
            merged = []
            for field in ('keys', 'keywords', 'secondary_keys'):
                val = e.get(field)
                if isinstance(val, str):
                    val = [val]
                if isinstance(val, list):
                    for k in val:
                        if isinstance(k, str) and k.strip():
                            merged.append(k.strip())
            seen = set()
            uniq = []
            for k in merged:
                key = k.lower()
                if key not in seen:
                    seen.add(key)
                    uniq.append(k)
            e['keywords'] = uniq
            entries.append(e)
        book['entries'] = entries
        return book

    # ============================================================
    # 索引构建及辅助函数
    # ============================================================
    def _build_index(self, entries, book_name, char_name):
        indexed = []
        for entry in entries:
            if not entry.get('enabled', True):
                continue
            keys = entry.get('keywords', [])
            content = entry.get('content', '')
            comment = entry.get('comment', '')
            if not content:
                continue
            all_keys = list(set(keys))
            if comment:
                all_keys.append(comment)
                for word in re.split(r'[，,、\s]+', comment):
                    if len(word) >= 2:
                        all_keys.append(word)
            all_keys = [k.strip() for k in all_keys if k and len(k.strip()) >= 2]
            if not all_keys:
                all_keys = [comment] if comment else ["unknown"]
            indexed.append({
                "keywords": all_keys,
                "content": content,
                "comment": comment,
                "priority": entry.get('priority', 100),
                "id": 0
            })
        indexed.sort(key=lambda x: x['priority'])
        return {
            "name": book_name,
            "character": char_name,
            "created_at": datetime.now().isoformat(),
            "total_entries": len(indexed),
            "entries": indexed
        }

    def _generate_index_filename(self, book_name, char_name):
        safe_book = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '_', book_name or '未知世界')
        safe_char = re.sub(r'[^a-zA-Z0-9\u4e00-\u9fa5]', '_', char_name or '未知角色')
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return f"{safe_char}_{safe_book}_{timestamp}.index.json"

    def _refresh_ui(self):
        if hasattr(self.core, 'refresh_archive_list'):
            self.core.refresh_archive_list()
        if hasattr(self.core, 'refresh_world_list'):
            self.core.refresh_world_list()

    # ============================================================
    # 解析函数
    # ============================================================
    def _parse_with_library(self, file_path):
        if file_path.lower().endswith('.png'):
            card = parse_png(file_path)
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                raw_data = json.load(f)
            card = parse_json(raw_data)

        data = {
            'name': card.name or "未命名角色",
            'description': card.description or "",
            'personality': card.personality or "",
            'scenario': card.scenario or "",
            'first_mes': card.first_mes or "",
            'mes_example': card.mes_example or "",
            'creator_notes': card.creator_notes or "",
            'tags': card.tags or [],
            'alternate_greetings': card.alternate_greetings or [],
            'system_prompt': getattr(card, 'system_prompt', ''),
        }

        raw_book = None
        if hasattr(card, 'character_book') and card.character_book:
            raw_book = card.character_book
        elif hasattr(card, 'extensions') and isinstance(card.extensions, dict):
            raw_book = card.extensions.get('character_book')

        return data, raw_book

    def _parse_with_pil(self, file_path):
        if file_path.lower().endswith('.png'):
            img = Image.open(file_path)
            raw_data = None
            if 'chara' in img.text:
                raw_data = img.text['chara']
            elif 'ccv3' in img.text:
                raw_data = img.text['ccv3']
            if raw_data:
                try:
                    if raw_data.startswith('{'):
                        data = json.loads(raw_data)
                    else:
                        decoded = base64.b64decode(raw_data).decode('utf-8')
                        data = json.loads(decoded)
                    return self._parse_json_with_raw(data)
                except Exception as e:
                    raise ValueError(f"解析 PNG 元数据失败: {e}")
            raise ValueError("PNG 中未找到角色卡数据")
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return self._parse_json_with_raw(data)

    def _parse_json_with_raw(self, data):
        raw_book = None
        if isinstance(data.get('data'), dict):
            inner = data['data']
            raw_book = inner.get('character_book') or (inner.get('extensions') or {}).get('character_book')
            for key in ['name', 'description', 'personality', 'scenario', 'first_mes', 'mes_example', 'creator_notes', 'system_prompt', 'tags', 'alternate_greetings']:
                if key in inner:
                    data[key] = inner[key]

        data.setdefault('name', '未命名角色')
        data.setdefault('description', '')
        data.setdefault('personality', '')
        data.setdefault('scenario', '')
        data.setdefault('first_mes', '')
        data.setdefault('mes_example', '')
        data.setdefault('creator_notes', '')
        data.setdefault('system_prompt', '')
        data.setdefault('tags', [])
        data.setdefault('alternate_greetings', [])

        if not raw_book:
            raw_book = data.get('character_book') or (data.get('extensions') or {}).get('character_book')

        return data, raw_book

    # 保留旧接口（兼容）
    def _decouple(self):
        return "请使用 /import_card 导入角色卡", False

    def _export_tavern(self):
        return "导出功能已移除", False

    def _export_merged(self):
        return "导出功能已移除", False
