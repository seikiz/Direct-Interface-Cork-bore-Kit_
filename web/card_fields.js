// ⚠ 生成物：由 tools/gen_card_fields.py <seiki>‌​‌​‌​‍‌‌​​‎‌​‍‎‌‌‎‎‌​​‎‌​‎‎‌​‌​‌​‌‌‌‌‍​‌‌‎‎‌‌​‎‌​‍‌‌​‌‎‌‌‎‎​‎‌‎‌‍‌‍​‎​‎‌‍​‌​‎‍‌‌‍​‎​‎​‍‌‍‌‌从 design/card_fields.json 生成，别手改。
//   改分区/字段/折叠阈值：改 design/card_fields.json，再跑一次生成器。

// 分区/字段/阈值：与安卓 CardFields.kt 同一份（tools/gen_card_fields.py --check 盯着）
window.DICK_CARD_FIELDS = {
  version: 1,
  collapseLines: 8,
  kvValueChars: 120,
  maxTextChars: 4000,
  titleKeys: ["name", "char_name", "character_name", "title"],
  sections: [
    { id: "setting", mode: "body", labelKey: "card_sec_setting", keys: ["system_prompt", "prompt", "description", "background", "scenario", "setting", "world_setting", "context"] },
    { id: "persona", mode: "body", labelKey: "card_sec_persona", keys: ["personality", "性格", "个性", "appearance", "外貌", "外表", "speech", "speech_style", "语气"] },
    { id: "greeting", mode: "body", labelKey: "card_sec_greeting", keys: ["greeting", "first_mes", "opening", "first_message", "initial_scene", "alternate_greetings"] },
    { id: "profile", mode: "kv", labelKey: "card_sec_profile", keys: ["age", "gender", "occupation", "race", "species", "height", "birthday", "author", "version", "tags", "created_at", "time_period"] },
    { id: "era", mode: "kv", labelKey: "card_sec_era", keys: ["params.era", "params.era_kind", "params.space", "params.region", "era", "era_kind", "space", "region"] },
    { id: "rules", mode: "list", labelKey: "card_sec_rules", keys: ["rules", "narrative_tips", "factions", "geography", "example_dialogues"] },
  ],
  other: { id: "other", mode: "kv", labelKey: "card_sec_other" },
  fieldLabels: {
    "system_prompt": "card_f_system_prompt",
    "prompt": "card_f_system_prompt",
    "description": "card_f_system_prompt",
    "background": "card_f_background",
    "scenario": "card_f_background",
    "notes": "card_f_notes",
    "mes_example": "card_f_mes_example",
    "personality": "card_f_personality",
    "性格": "card_f_personality",
    "个性": "card_f_personality",
    "appearance": "card_f_appearance",
    "外貌": "card_f_appearance",
    "外表": "card_f_appearance",
    "speech": "card_f_speech",
    "speech_style": "card_f_speech",
    "语气": "card_f_speech",
    "age": "card_f_age",
    "gender": "card_f_gender",
    "occupation": "card_f_occupation",
    "race": "card_f_race",
    "species": "card_f_race",
    "height": "card_f_height",
    "birthday": "card_f_birthday",
    "author": "card_f_author",
    "version": "card_f_version",
    "tags": "card_f_tags",
    "created_at": "card_f_created_at",
    "time_period": "card_f_time_period",
    "params.era": "card_f_era",
    "era": "card_f_era",
    "params.era_kind": "card_f_era_kind",
    "era_kind": "card_f_era_kind",
    "params.space": "card_f_space",
    "space": "card_f_space",
    "params.region": "card_f_region",
    "region": "card_f_region",
  },
  hiddenKeys: ["card_data", "history_tree", "extensions", "world_entries"],
  hiddenPrefixes: ["_"]
};

// 分区标签：生成时就展开成 T.<键> 字面引用 —— 这样 tools/gen_i18n.py 的
// 「谁在用哪个键」扫描看得见它们（动态 T[labelKey] 会被判成死键）。文案仍只住 lang/strings.json。
window.DICK_CARD_LABEL = function (id) {
  switch (id) {
    case "setting": return T.card_sec_setting || '';
    case "persona": return T.card_sec_persona || '';
    case "greeting": return T.card_sec_greeting || '';
    case "profile": return T.card_sec_profile || '';
    case "era": return T.card_sec_era || '';
    case "rules": return T.card_sec_rules || '';
    case "other": return T.card_sec_other || '';
    default: return '';
  }
};

// 字段标签（同一套：字面引用，扫描可见）。没登记的键返回空串 —— 渲染器退回显示键名本身。
window.DICK_CARD_FIELD_LABEL = function (key) {
  if (["system_prompt", "prompt", "description"].indexOf(key) >= 0) return T.card_f_system_prompt || '';
  if (["background", "scenario"].indexOf(key) >= 0) return T.card_f_background || '';
  if (["notes"].indexOf(key) >= 0) return T.card_f_notes || '';
  if (["mes_example"].indexOf(key) >= 0) return T.card_f_mes_example || '';
  if (["personality", "性格", "个性"].indexOf(key) >= 0) return T.card_f_personality || '';
  if (["appearance", "外貌", "外表"].indexOf(key) >= 0) return T.card_f_appearance || '';
  if (["speech", "speech_style", "语气"].indexOf(key) >= 0) return T.card_f_speech || '';
  if (["age"].indexOf(key) >= 0) return T.card_f_age || '';
  if (["gender"].indexOf(key) >= 0) return T.card_f_gender || '';
  if (["occupation"].indexOf(key) >= 0) return T.card_f_occupation || '';
  if (["race", "species"].indexOf(key) >= 0) return T.card_f_race || '';
  if (["height"].indexOf(key) >= 0) return T.card_f_height || '';
  if (["birthday"].indexOf(key) >= 0) return T.card_f_birthday || '';
  if (["author"].indexOf(key) >= 0) return T.card_f_author || '';
  if (["version"].indexOf(key) >= 0) return T.card_f_version || '';
  if (["tags"].indexOf(key) >= 0) return T.card_f_tags || '';
  if (["created_at"].indexOf(key) >= 0) return T.card_f_created_at || '';
  if (["time_period"].indexOf(key) >= 0) return T.card_f_time_period || '';
  if (["params.era", "era"].indexOf(key) >= 0) return T.card_f_era || '';
  if (["params.era_kind", "era_kind"].indexOf(key) >= 0) return T.card_f_era_kind || '';
  if (["params.space", "space"].indexOf(key) >= 0) return T.card_f_space || '';
  if (["params.region", "region"].indexOf(key) >= 0) return T.card_f_region || '';
  return '';
};
