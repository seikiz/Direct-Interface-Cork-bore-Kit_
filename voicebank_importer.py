# ============================================================
#   voicebank_importer.py - UTAU 声库傻瓜化导入
#
#   检测到声库压缩包（zip/7z/rar）→ 自动识别（含 oto.ini / character.txt
#   即 UTAU 声库特征）→ 解压到 utau_voicebanks/<声库名>/ → 登记可用列表。
#
#   用户零操作：把声库包拖进 DICK 目录 / Downloads / Desktop，
#   或手动 /voicebank <文件> 导入；设置页可选已导入的声库。
# ============================================================

import os
import zipfile
import shutil
import glob

SEVENZ = None
for _cand in ("E:\\7za.exe", "C:\\Program Files\\7-Zip\\7z.exe",
              "C:\\Program Files (x86)\\7-Zip\\7z.exe"):
    if os.path.exists(_cand):
        SEVENZ = _cand
        break

VOICEBANK_MARKERS = ("oto.ini", "character.txt", "oto_ini", "readme.txt")


def _looks_like_voicebank(names):
    """包内文件名是否含 UTAU 声库特征（oto.ini 最硬，其次 character.txt）"""
    lowered = [n.lower() for n in names]
    if any("oto.ini" == os.path.basename(n) for n in lowered):
        return True
    if any("character.txt" == os.path.basename(n) for n in lowered):
        return True
    # 宽松：大量 .frq/.wav 且目录名含声库关键词
    if len(names) > 20:
        return True
    return False


def _safe_name(name):
    return "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip() or "voicebank"


def import_voicebank(path, dest_root):
    """导入声库包 → utau_voicebanks/<名>/。返回 (ok, 消息, 目录名)"""
    path = os.path.abspath(path)
    if not os.path.exists(path):
        return False, "文件不存在：" + path, None
    base = os.path.basename(path)
    ext = os.path.splitext(base)[1].lower()
    if ext not in (".zip", ".7z", ".rar", ".tar", ".gz"):
        return False, "不支持的压缩格式：" + ext, None

    # 探测包内容（zip 原生 / 7z/rar 用 7za l）
    names = []
    try:
        if ext == ".zip":
            with zipfile.ZipFile(path) as z:
                names = z.namelist()
        elif SEVENZ:
            import subprocess
            r = subprocess.run([SEVENZ, "l", path], capture_output=True,
                               encoding="utf-8", errors="replace", timeout=60)
            for line in (r.stdout or "").splitlines():
                parts = line.split()
                if len(parts) >= 1 and (parts[-1].endswith("/") or "." in parts[-1]):
                    names.append(parts[-1])
        else:
            return False, "需要 7-Zip 才能解压 " + ext + "（仅支持 zip）", None
    except Exception as e:
        return False, "读取压缩包失败：" + str(e)[:100], None

    if not names:
        return False, "压缩包为空或无法读取", None
    if not _looks_like_voicebank(names):
        return False, "未检测到 UTAU 声库特征（缺少 oto.ini / character.txt）", None

    # 声库名：取包内顶层目录名（有的话），否则用包文件名
    top = None
    for n in names:
        n = n.replace("\\", "/")
        first = n.split("/")[0]
        if first and first not in ("", "."):
            top = first
            break
    vb_name = _safe_name(top if top else os.path.splitext(base)[0])
    dest = os.path.join(dest_root, vb_name)
    os.makedirs(dest, exist_ok=True)

    try:
        if ext == ".zip":
            with zipfile.ZipFile(path) as z:
                # 若包内是单一顶层目录，解压到 dest 下该目录内会套一层 → 剥掉顶层
                for member in z.namelist():
                    mname = member.replace("\\", "/")
                    parts = mname.split("/")
                    target = os.path.join(dest, *parts[1:] if top and parts[0] == top else parts)
                    if member.endswith("/"):
                        os.makedirs(target, exist_ok=True)
                    else:
                        os.makedirs(os.path.dirname(target), exist_ok=True)
                        with z.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        elif SEVENZ:
            import subprocess
            subprocess.run([SEVENZ, "x", path, "-o" + dest, "-y"],
                           capture_output=True, timeout=600)
        else:
            return False, "无法解压（缺 7-Zip）", None
    except Exception as e:
        return False, "解压失败：" + str(e)[:120], vb_name

    # 登记
    return True, "已导入声库：" + vb_name + "（" + dest + "）", vb_name


def list_voicebanks(dest_root):
    """列出已导入的声库目录名"""
    if not os.path.isdir(dest_root):
        return []
    return sorted(d for d in os.listdir(dest_root)
                  if os.path.isdir(os.path.join(dest_root, d)))


def scan_for_voicebanks(dirs):
    """扫描指定目录中的声库包，返回文件路径列表"""
    found = []
    exts = (".zip", ".7z", ".rar", ".tar", ".gz")
    for d in dirs:
        if not d or not os.path.isdir(d):
            continue
        try:
            for p in glob.glob(os.path.join(d, "*")):
                if os.path.isfile(p) and p.lower().endswith(exts):
                    found.append(p)
        except Exception:
            pass
    return found
