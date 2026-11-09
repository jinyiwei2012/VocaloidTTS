"""Chinese text -> singable pinyin syllables and VOCALOID X-SAMPA phonemes."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

try:
    from pypinyin import Style, pinyin as _pinyin
except Exception:  # pragma: no cover - pypinyin is bundled in the release build
    _pinyin = None

from .edits import CharEdit, dictionary_overrides
from .progress import Reporter


# ---------------------------------------------------------------------------
# Text normalisation
# ---------------------------------------------------------------------------

_DIGITS = "零一二三四五六七八九"
_DIGIT_PINYIN = ["ling", "yi", "er", "san", "si", "wu", "liu", "qi", "ba", "jiu"]
_UNITS = ["", "十", "百", "千"]
_BIG_UNITS = ["", "万", "亿"]


def _section_to_chinese(n: int) -> str:
    """0 < n < 10000 -> Chinese reading."""
    out: list[str] = []
    zero = False
    for pos, unit in ((3, "千"), (2, "百"), (1, "十"), (0, "")):
        d = (n // (10 ** pos)) % 10
        if d:
            if zero and out:
                out.append("零")
            if not (d == 1 and pos == 1 and not out):
                out.append(_DIGITS[d])
            out.append(unit)
            zero = False
        elif out:
            zero = True
    return "".join(out)


def num_to_chinese(n: int) -> str:
    if n == 0:
        return "零"
    if n < 0:
        return "负" + num_to_chinese(-n)
    sections: list[int] = []
    while n > 0:
        n, sec = divmod(n, 10000)
        sections.append(sec)
    if len(sections) > len(_BIG_UNITS):
        # Keep unusually large decimal whole parts readable without indexing
        # beyond the supported units (ordinary long IDs already use digits).
        digits = str(sections[-1]) + "".join(f"{sec:04d}" for sec in reversed(sections[:-1]))
        return "".join(_DIGITS[int(c)] for c in digits)
    parts: list[str] = []
    missing_group = False
    for group in range(len(sections) - 1, -1, -1):
        sec = sections[group]
        if not sec:
            missing_group = True
            continue
        if parts and (missing_group or sec < 1000):
            parts.append("零")
        text = _section_to_chinese(sec)
        if parts and 10 <= sec < 20:
            # Omit 一 only at the start: 十万, but 一万零一十.
            text = "一" + text
        parts.append(text + _BIG_UNITS[group])
        missing_group = False
    return "".join(parts)


_UNIT_WORDS = set("元人个米吨次年月日号页条张件位名户家辆台套分时里克升斤岁倍份期届级层楼室排座项种类款批组队场轮票卡码")

#: Python 3.11+ 的 int() 默认只接受 4300 位十进制串，超了直接抛 ValueError。
#: 用户往输入框里粘一串 5000 位的「9」不该让整次生成失败，所以超过这个长度
#: 的数字一律逐位读，不经过 int()。
_MAX_INT_DIGITS = 4000


def _digits_to_chinese(digits: str) -> str:
    """逐位读，不经过 int()。"""
    return "".join(_DIGITS[int(c)] for c in digits if c in "0123456789")


def _number_token_to_chinese(tok: str, prev: str, next_: str) -> str:
    """Read a run of digits in a natural way (years / phone / decimals)."""
    if len(tok) > _MAX_INT_DIGITS:
        return _digits_to_chinese(tok)
    if "." in tok:
        whole, frac = tok.split(".", 1)
        return num_to_chinese(int(whole)) + "点" + "".join(_DIGITS[int(c)] for c in frac)
    if len(tok) > 1 and tok.startswith("0"):
        # 007 / 0123 这类编号要逐位读，int() 会把前导零吃掉
        return "".join(_DIGITS[int(c)] for c in tok)
    if len(tok) == 4 and tok.startswith(("19", "20")) and next_ in ("年",):
        return "".join(_DIGITS[int(c)] for c in tok)
    if len(tok) >= 7 and not (prev and prev.isdigit()):
        # phone / ID numbers are read digit by digit, but a number followed by
        # a unit or measure word (12345678元, 10000000人) reads as a number.
        if not (next_ and next_ in _UNIT_WORDS):
            return "".join(_DIGITS[int(c)] for c in tok)
    return num_to_chinese(int(tok))


def normalize_text(text: str) -> str:
    """Normalise punctuation, numbers and Latin fragments for the lyric parser."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    # 千分位和负号必须在标点替换之前处理：半角逗号马上就要变成全角停顿，
    # 负号不在任何分支里、会被静默丢掉（「温度-5度」读成「温度五度」）。
    text = re.sub(r"(?<=\d),(?=\d{3})", "", text)
    text = re.sub(r"(?<![\dA-Za-z])-(?=\d)", "负", text)
    # typographic punctuation -> concise set
    trans = {
        "，": "，", "、": "，", "；": "；", "：": "：", "。": "。",
        "！": "！", "？": "？", "…": "。", "—": "，", "～": "，",
        "「": "", "」": "", "『": "", "』": "", "（": "，", "）": "，",
        "(": "，", ")": "，", "【": "，", "】": "，", "《": "", "》": "",
        '"': "", "'": "", "“": "", "”": "", "‘": "", "’": "",
        ",": "，", ";": "；", ":": "：", "!": "！", "?": "？",
    }
    for a, b in trans.items():
        text = text.replace(a, b)

    # numbers
    def repl(m: re.Match) -> str:
        tok = m.group(0)
        start, end = m.start(), m.end()
        prev = text[start - 1] if start else ""
        nxt = text[end] if end < len(text) else ""
        if tok.endswith("%"):
            # 百分号后的数字按数值读（1000000% = 百分之一百万），不按逐位；
            # 只有长到 int() 都不肯收的超长串才退回逐位。
            number = tok[:-1]
            if len(number) > _MAX_INT_DIGITS:
                spoken = _digits_to_chinese(number)
            elif "." in number:
                spoken = _number_token_to_chinese(number, prev, nxt)
            else:
                spoken = num_to_chinese(int(number))
            return "百分之" + spoken
        return _number_token_to_chinese(tok, prev, nxt)

    text = re.sub(r"\d+(?:\.\d+)?%?", repl, text)
    # Decimal points have now become 点; remaining periods end clauses.
    text = text.replace(".", "。")
    # Preserve the reading of a standalone percent sign.
    text = text.replace("%", "百分之")
    return text


# ---------------------------------------------------------------------------
# Pinyin & phonemes
# ---------------------------------------------------------------------------

_INITIALS = ["zh", "ch", "sh", "b", "p", "m", "f", "d", "t", "n", "l",
             "g", "k", "h", "j", "q", "x", "r", "z", "c", "s"]

_INITIAL_PH = {
    "b": "p", "p": "p_h", "m": "m", "f": "f",
    "d": "t", "t": "t_h", "n": "n", "l": "l",
    "g": "k", "k": "k_h", "h": "x",
    "j": "ts\\", "q": "ts\\_h", "x": "s\\",
    "zh": "ts`", "ch": "ts`_h", "sh": "s`", "r": "z`",
    "z": "ts", "c": "ts_h", "s": "s",
}

_FINAL_PH = {
    "a": "a", "o": "o", "e": "7", "i": "i", "u": "u", "v": "y",
    "ai": "aI", "ei": "ei", "ao": "AU", "ou": "@U",
    "an": "a_n", "en": "@_n", "ang": "AN", "eng": "@N", "ong": "UN",
    "ia": "ia", "ie": "iE_r", "iao": "iAU", "iu": "i@U",
    "ian": "iE_n", "in": "i_n", "iang": "iAN", "ing": "iN", "iong": "iUN",
    "ua": "ua", "uo": "uo", "uai": "uaI", "ui": "uei",
    "uan": "ua_n", "un": "u@_n", "uang": "uAN", "ueng": "u@N",
    "ve": "yE_r", "van": "y{_n", "vn": "y_n",
    "er": "@`", "r": "r",
}

# 独立成音节的鼻音：嗯(n) / 呣(m) / 哼(ng)。它们不在 _FINAL_PH 里，
# 落空后会被兜底成 "a"，把「嗯」唱成「啊」。三个音素 VOCALOID 中文表都有。
_SYLLABIC_NASAL = {"n": "n", "m": "m", "ng": "N"}

_ZERO_INITIAL = {
    "a": "a", "o": "o", "e": "7", "ai": "aI", "ei": "ei", "ao": "AU",
    "ou": "@U", "an": "a_n", "en": "@_n", "ang": "AN", "eng": "@N",
    "er": "@`",
    "yo": "j o",
    "yi": "i", "ya": "ia", "ye": "iE_r", "yao": "iAU", "you": "i@U",
    "yan": "iE_n", "yin": "i_n", "yang": "iAN", "ying": "iN", "yong": "iUN",
    "yu": "y", "yue": "yE_r", "yuan": "y{_n", "yun": "y_n",
    "wu": "u", "wa": "ua", "wo": "uo", "wai": "uaI", "wei": "uei",
    "wan": "ua_n", "wen": "u@_n", "wang": "uAN", "weng": "u@N",
}

_LATIN = {
    "a": "ei", "b": "bi", "c": "xi", "d": "di", "e": "yi", "f": "ai fu",
    "g": "ji", "h": "ai chi", "i": "ai", "j": "jie", "k": "kai", "l": "ai le",
    "m": "ai mu", "n": "en", "o": "ou", "p": "pi", "q": "qiu", "r": "a er",
    "s": "ai si", "t": "ti", "u": "you", "v": "wei", "w": "da bu liu",
    "x": "ai ke si", "y": "wai", "z": "zei",
}


def split_initial_final(py: str) -> tuple[str, str]:
    py = py.strip().lower().replace("ü", "v").replace("u:", "v")
    if py in _ZERO_INITIAL:
        return "", py
    for ini in _INITIALS:
        if py.startswith(ini) and len(py) > len(ini):
            return ini, py[len(ini):]
    return "", py


def pinyin_to_phonemes(py: str) -> str:
    """Pinyin (no tone) -> VOCALOID Chinese X-SAMPA phoneme string."""
    py = py.strip().lower().replace("ü", "v").replace("u:", "v")
    if not py:
        return "a"
    nasal = _SYLLABIC_NASAL.get(py)
    if nasal:
        return nasal
    if py in _ZERO_INITIAL:
        return _ZERO_INITIAL[py]
    ini, fin = split_initial_final(py)
    if not ini and py in _ZERO_INITIAL:
        return _ZERO_INITIAL[py]
    # j/q/x + u is really ü
    if ini in ("j", "q", "x") and fin.startswith("u"):
        fin = "v" + fin[1:]
    # n/l + ue is usually nüe/lüe; b/p/m/f + o is phonetically [uo]
    if ini in ("n", "l") and fin == "ue":
        fin = "ve"
    if ini in ("b", "p", "m", "f") and fin == "o":
        fin = "uo"
    ph_ini = _INITIAL_PH.get(ini, "")
    if fin == "i" and ini in ("z", "c", "s"):
        # apical alveolar vowel: zi / ci / si
        ph_fin = "i\\"
    elif fin == "i" and ini in ("zh", "ch", "sh", "r"):
        # apical retroflex vowel: zhi / chi / shi / ri
        ph_fin = "i`"
    else:
        ph_fin = _FINAL_PH.get(fin)
    if ph_fin is None:
        # tolerate unknown finals by spelling the closest vowel
        ph_fin = _FINAL_PH.get(fin[:2]) or _FINAL_PH.get(fin[:1]) or "a"
    return (ph_ini + " " + ph_fin).strip()


def is_valid_pinyin(py: str) -> bool:
    """Validate a toneless pinyin syllable against the accepted final table."""
    py = py.strip().lower().replace("ü", "v").replace("u:", "v")
    if not py:
        return False
    if py in _ZERO_INITIAL:
        return True
    ini, fin = split_initial_final(py)
    if not ini:
        return False
    if ini in ("j", "q", "x") and fin.startswith("u"):
        fin = "v" + fin[1:]
    if ini in ("n", "l") and fin == "ue":
        fin = "ve"
    return fin in _FINAL_PH


@dataclass
class Syllable:
    text: str
    pinyin: str
    tone: int
    phonemes: str
    pause_after_ms: int = 0
    punct: str = ""
    stress: float = 0.0
    final: bool = False
    phrase: int = 0
    start_ms: float = 0.0
    dur_ms: float = 0.0
    index: int = 0
    src: int = -1   # 源文本里的字符偏移，逐字纠音靠它定位
    pause_lock: bool = False   # True 表示 pause_after_ms 是精确值，不再乘 pause_scale
    edit: CharEdit | None = None   # 解析阶段命中的逐字修正（时值阶段直接读它）


_CLAUSE_END = set("。！？；：\n")
_COMMA = set("，、,")
# characters that usually carry contrastive / emphatic focus
_FOCUS = set("最很太真非常特别十分极更再又一定千万必须居然竟然终于才就还没别不"
             "好坏快慢大小高低新旧第一次原来其实当然果然绝对完全")


def _split_pinyin(raw: str) -> tuple[str, int] | None:
    m = re.match(r"^([a-zA-ZüÜv:]+?)([1-5])?$", raw.strip())
    if not m:
        return None
    py = m.group(1).lower().replace("ü", "v").replace("u:", "v")
    tone = int(m.group(2) or 5)
    return py, tone


def _pinyin_for_char(ch: str) -> tuple[str, int] | None:
    if _pinyin is None:
        return None
    try:
        raw = _pinyin(ch, style=Style.TONE3, neutral_tone_with_five=True,
                      errors=lambda x: [""])[0][0]
    except Exception:
        return None
    if not raw:
        return None
    return _split_pinyin(raw)


def _apply_tone_sandhi(syls: list[Syllable],
                       neutral_syls: set[int] | frozenset[int] = frozenset()) -> None:
    """一/不 变调与三声连读。

    两步用的基准不同，不能合并：
    - 一/不 看**词法**声调。「一个」的「个」原调是去声，所以「一」读阳平；
      必须先于轻声化，否则「个」成了 5 声就查不出去声。
    - 三声连读要**跳过**即将轻声化的音节。「姐姐」后字轻声，前字保持三声；
      不跳过就会读成 jié jie。neutral_syls 是这些音节的对象 id 集合。
    """
    for i, s in enumerate(syls):
        # 按汉字判定，不按拼音：衣/医/依/壹 的拼音也是 yi，布/步/部/怖 也是 bu，
        # 按拼音匹配会把「衣服」读成 yì fu、「布置」读成 bú zhì。
        if s.text == "一" and s.tone == 1:
            nxt = syls[i + 1] if i + 1 < len(syls) else None
            if nxt and nxt.tone == 4:
                s.tone = 2
            elif nxt and nxt.tone in (1, 2, 3):
                s.tone = 4
        if s.text == "不" and s.tone == 4:
            nxt = syls[i + 1] if i + 1 < len(syls) else None
            if nxt and nxt.tone == 4:
                s.tone = 2
    # 3-3 sandhi, left to right
    for i in range(len(syls) - 1):
        if id(syls[i]) in neutral_syls or id(syls[i + 1]) in neutral_syls:
            continue
        if syls[i].tone == 3 and syls[i + 1].tone == 3:
            syls[i].tone = 2


_FOCUS_PINYIN = set(
    "zui hen tai zhen fei chang te bie shi fen geng yi ding qian wan bi xu "
    "ju ran jing zhong yu cai jiu hai mei bu hao huai kuai man da xiao gao di "
    "xin ci yuan lai qi dang jue dui quan".split()
)


def _apply_stress(local: list[Syllable], final: bool, mode: str) -> None:
    """Shared prominence model for Chinese-character and pinyin input."""
    focus = _FOCUS if mode == "char" else _FOCUS_PINYIN
    for j, s in enumerate(local):
        key = s.text if mode == "char" else s.pinyin
        s.stress = 0.12 if s.tone == 5 else 0.55
        if key in focus:
            s.stress += 0.55
        if j == 0:
            s.stress += 0.25
        if s.final:
            s.stress += 0.20
        s.stress = min(1.65, s.stress)
    if len(local) >= 2:
        candidates = [j for j, s in enumerate(local) if s.tone != 5]
        if candidates:
            def score(j: int) -> float:
                s = local[j]
                key = s.text if mode == "char" else s.pinyin
                return s.stress + (0.30 if key in focus else 0.0) \
                    - (0.45 if j == len(local) - 1 else 0.0)
            idx = max(candidates, key=score)
            local[idx].stress = min(1.8, local[idx].stress + 0.45)
    for j in range(1, len(local) - 1, 3):
        if local[j].tone != 5:
            local[j].stress = min(1.8, local[j].stress + 0.12)


_NEUTRAL_WORDS = {
    word: (1,) for word in (
        "妈妈 爸爸 哥哥 姐姐 弟弟 妹妹 奶奶 爷爷 姥姥 姥爷 叔叔 舅舅 姑姑 婶婶 "
        "伯伯 婆婆 公公 太太 宝宝 娃娃 星星 谢谢 朋友 时候 东西 明白 知道 喜欢 "
        "便宜 舒服 漂亮 意思 故事 月亮 衣服 眼睛 嘴巴 耳朵 头发 桌子 椅子 被子 "
        "枕头 石头 木头 馒头 包子 饺子 儿子 我们 你们 他们 她们 它们 人们 咱们 "
        "什么 怎么 这么 那么 多么 一个 这个 那个 哪个 每个 地方 告诉 收拾 商量 "
        "清楚 新鲜 关系 事情 热闹 先生 学生 医生 护士 姑娘 太阳 云彩 葡萄 萝卜 "
        "豆腐 玻璃 骨头 叶子 本子 房子 鞋子 袜子 帽子 裤子 裙子 影子 样子 法子 "
        "日子 面子 里子 记得 觉得 懂得 显得 舍得 值得"
    ).split()
}

# 含轻声词但不该轻声的词形。查表是按子串做的，「东西南北」里的「东西」
# 会被当成「买东西」的轻声词；只有泛指物品或骂人的「东西」才读 dōng xi。
_NEUTRAL_EXCEPT = frozenset((
    "东西南北", "东西南北中", "东西向", "东西方", "东西半球",
))
_EXCEPT_LENS = (5, 4, 3)

# 地 as an adverbial suffix is de5, but 土地/大地/目的地 etc. keep dì.
_DI_ADVERB_CHARS = set("慢轻悄静默偷狠渐缓匆猛愤疯忽蓦霍紧紧牢牢深深远远早早好好美美甜甜冷冷热热淡淡浓浓")
_DI_ADVERBS = set(
    "慢慢 轻轻 悄悄 静静 默默 偷偷 狠狠 渐渐 缓缓 匆匆 猛然 愤愤 飞快 高兴 "
    "认真 仔细 大声 小声 用力 努力 开心 伤心 生气 温柔 兴奋 急忙 连忙 舒服 "
    "紧紧 牢牢 深深 远远 早早 好好 美美 甜甜 冷冷 热热 淡淡 浓浓 高高 大大 "
    "小小 愤怒 焦急 无奈 轻松 自然 安静 平稳 迅速 缓慢 坚定 惊讶".split()
)

# V + 得 + complement: 跑得快 / 说得好 / 睡得香
_DE_VERBS = set(
    "跑说做睡长写唱画打玩吃喝走来去想看听学干办弄洗擦飞游跳笑哭讲问答活累忙"
    "冷热快慢好坏难易拉推拿放站坐躺爬喊叫读背记忘爱恨怕急气乐美丑胖瘦高矮远近早晚多少大小懂显舍"
)
_DE_WORDS = {"觉得", "记得", "懂得", "显得", "舍得", "值得", "漂亮", "高兴",
             "开心", "认真", "仔细", "大声", "小声", "飞快", "舒服", "温柔",
             "生气", "伤心", "兴奋", "急忙"}

_REDUP_VERBS = set("看说想试听写问找等笑玩尝摸擦洗睡走坐站唱跳跑读弹画做弄")


def _neutral_marks(text: str, reporter: Reporter | None = None) -> set[int]:
    """Indices that should be sung with neutral tone (tone 5)."""
    rep = reporter or Reporter()
    marks: set[int] = set()
    n = len(text)
    words_rep = rep.child(0.0, 0.6)
    for i in range(n):
        if (i & 0xFF) == 0:
            rep.check()
            words_rep.report("parse", i / n)
        if not any(text[i:i + ln] in _NEUTRAL_EXCEPT for ln in _EXCEPT_LENS):
            for length in (3, 2):
                word = text[i:i + length]
                pos = _NEUTRAL_WORDS.get(word)
                if pos:
                    for p in pos:
                        if i + p < n:
                            marks.add(i + p)
                    break
        # AA verb reduplication: 看看 / 试试 / 想想
        if i + 1 < n and text[i] == text[i + 1] and text[i] in _REDUP_VERBS:
            marks.add(i + 1)
    tail_rep = rep.child(0.6, 1.0)
    for i, ch in enumerate(text):
        if (i & 0xFF) == 0:
            rep.check()
            tail_rep.report("parse", i / n)
        if ch == "地" and i > 0:
            prev1 = text[i - 1]
            prev2 = text[i - 2:i]
            if prev1 in _DI_ADVERB_CHARS or prev2 in _DI_ADVERBS:
                marks.add(i)
        elif ch == "得" and i > 0:
            prev1 = text[i - 1]
            prev2 = text[i - 2:i]
            if prev1 in _DE_VERBS or prev2 in _DE_WORDS:
                marks.add(i)
    return marks


def _context_pinyin(text: str,
                    reporter: Reporter | None = None) -> dict[int, tuple[str, int]]:
    """Phrase-aware pinyin for each Chinese character.

    Calling pypinyin on the whole run (rather than one character at a time)
    lets it use its phrase dictionary for 目的/着急/了解/觉得 etc.
    """
    rep = reporter or Reporter()
    out: dict[int, tuple[str, int]] = {}
    if _pinyin is None:
        return out
    n = len(text)
    for m in re.finditer(r"[\u4e00-\u9fff]+", text):
        rep.check()
        rep.report("parse", m.start() / n)
        run = m.group()
        try:
            vals = _pinyin(run, style=Style.TONE3, neutral_tone_with_five=True,
                           errors=lambda x: ["" for _ in x])
        except Exception:
            continue
        if len(vals) != len(run):
            continue
        for k, item in enumerate(vals):
            if not item:
                continue
            got = _split_pinyin(item[0])
            if got:
                out[m.start() + k] = got
    return out


def _offset_map(original: str, normalized: str) -> dict[int, int]:
    """原文下标 → 归一化下标，线性扫描。

    ``normalize_text`` 的改动是局部的（数字/百分号展开成几个汉字、标点替换），
    所以遇到不匹配时就在归一化文本里往前找原文的当前字符：找到说明这里刚被
    展开过，跳过那几个字继续对齐；找不到说明这个字符被删掉了（多余空格之类），
    原文侧前进一格。

    早先版本用 ``difflib.SequenceMatcher``，在长文本上最坏 O(n²)——实测两万字
    要十几秒，期间连取消按钮都没反应。这个版本是线性的。
    """
    out: dict[int, int] = {}
    i = j = 0
    n, m = len(original), len(normalized)
    while i < n and j < m:
        if original[i] == normalized[j]:
            out[i] = j
            i += 1
            j += 1
            continue
        found = normalized.find(original[i], j, min(m, j + 32))
        if found < 0:
            i += 1
        else:
            j = found
    return out


def _apply_char_edits(syls: list[Syllable], edits: dict[int, CharEdit],
                      text: str) -> None:
    """把逐字修正盖到已经算好的音节上。

    在变调、轻声归并和重音分配之后调用，所以用户的显式设置总是最后生效。
    ``CharEdit.char`` 用来兜底：只有「偏移处仍然是当初那个字」才应用，文本被
    改过、偏移漂移时宁可跳过也不错配。没有 ``char`` 的条目一律跳过——那是
    手工改过的 JSON，无法确认位置。
    """
    for s in syls:
        if s.src < 0:
            continue
        edit = edits.get(s.src)
        if edit is None or not edit.char:
            continue
        if s.src >= len(text) or text[s.src] != edit.char:
            continue
        # 记到音节上：时值阶段（拉长/精确停顿）也读这一条，避免两个阶段
        # 各拿一套偏移基准去查同一份字典。
        s.edit = edit
        if edit.pinyin and is_valid_pinyin(edit.pinyin):
            s.pinyin = edit.pinyin
            s.phonemes = edit.phonemes or pinyin_to_phonemes(edit.pinyin)
        elif edit.phonemes:
            s.phonemes = edit.phonemes
        if edit.tone:
            s.tone = edit.tone
        if edit.stress is not None:
            s.stress = max(0.0, min(1.6, s.stress + edit.stress))


def text_to_syllables(text: str,
                      reporter: Reporter | None = None,
                      edits: dict[int, CharEdit] | None = None,
                      dictionary: dict[str, str] | None = None
                      ) -> list[Syllable]:
    """Parse Chinese text into a flat list of syllables, with pauses.

    ``reporter`` 收到的是「解析阶段内部进度」0..1，调用方用
    :meth:`Reporter.child` 把它映射到整条流水线的区间里。

    ``edits`` 以字符偏移为键，覆盖单个字的拼音/声调；``dictionary`` 是用户
    专名词典，命中后整词覆盖。优先级：逐字纠音 > 词典 > pypinyin 上下文。
    """
    rep = reporter or Reporter()
    rep.stage("parse", 0.0)
    original = text
    text = normalize_text(text)
    if edits and text != original:
        # 归一化可能改变长度（100 → 一百），把用户按原文位置设的纠音搬到
        # 归一化后的位置上；对不齐的条目直接丢掉，交给 char 校验兜底。
        mapping = _offset_map(original, text)
        edits = {mapping[offset]: edit
                 for offset, edit in edits.items() if offset in mapping}
    rep.check()
    ctx = _context_pinyin(text, rep.child(0.0, 0.45))
    if dictionary:
        ctx.update(dictionary_overrides(text, dictionary))
    rep.check()
    neutral = _neutral_marks(text, rep.child(0.45, 0.6))
    total = len(text)
    scan_rep = rep.child(0.6, 1.0)
    syls: list[Syllable] = []
    phrase = 0
    buffer: list[tuple[str, int]] = []

    def flush(pause_ms: int, final: bool = False, punct: str = "") -> None:
        nonlocal buffer, phrase
        if not buffer:
            # 连续标点（？！、！？）只保留第一个：问号决定句尾要不要抬高，
            # 被后面的感叹号盖掉就变成陈述句了。末尾的空白或逗号也要补上
            # final，否则最后一个音节会按非句尾处理，短一截、也没有句尾降调。
            if syls:
                if pause_ms:
                    syls[-1].pause_after_ms = max(syls[-1].pause_after_ms,
                                                 pause_ms)
                if punct and not syls[-1].punct:
                    syls[-1].punct = punct
                if final:
                    syls[-1].final = True
            return
        local: list[Syllable] = []
        neutral_positions: list[tuple[int, str]] = []
        chinese_run: list[Syllable] = []
        for ch, idx in buffer:
            if ch.isascii() and ch.isalpha():
                # Letters belong to the same prosodic phrase, but their names
                # are not Chinese words eligible for 一/不/3+3 sandhi.
                _apply_tone_sandhi(chinese_run,
                                   {id(local[pos]) for pos, _ in neutral_positions})
                chinese_run = []
                for py in _LATIN[ch.lower()].split():
                    # 一个字母会拆成好几个音节（w -> da/bu/liu），共用一个 src
                    # 会让一条纠音同时套到三个音节上。字母不支持纠音，标 -1。
                    local.append(Syllable(text=ch, pinyin=py, tone=1,
                                          phonemes=pinyin_to_phonemes(py),
                                          phrase=phrase, src=-1))
                continue
            got = ctx.get(idx) or _pinyin_for_char(ch)
            if not got:
                continue
            py, tone = got
            ph = pinyin_to_phonemes(py)
            local.append(Syllable(text=ch, pinyin=py, tone=tone, phonemes=ph,
                                  phrase=phrase, src=idx))
            chinese_run.append(local[-1])
            if idx in neutral:
                neutral_positions.append((len(local) - 1, ch))
        # Tone sandhi (一/不/3+3) is based on the lexical tones, before the
        # neutral-tone reduction is applied.
        _apply_tone_sandhi(chinese_run,
                           {id(local[pos]) for pos, _ in neutral_positions})
        for pos, ch in neutral_positions:
            s = local[pos]
            s.tone = 5
            if ch == "地":
                # 地 as an adverbial suffix is "de", not "di"
                s.pinyin = "de"
                s.phonemes = pinyin_to_phonemes("de")
        if local:
            if final:
                local[-1].final = True
            _apply_stress(local, final, "char")
            if edits:
                _apply_char_edits(local, edits, text)
            if pause_ms:
                local[-1].pause_after_ms = pause_ms
            if punct:
                local[-1].punct = punct
            syls.extend(local)
        buffer = []
        phrase += 1

    for idx, ch in enumerate(text):
        if (idx & 0xFF) == 0:
            rep.check()
            scan_rep.report("parse", idx / total)
        if ch in _CLAUSE_END:
            flush({"。": 420, "！": 380, "？": 400, "；": 280, "：": 260,
                   "\n": 420}.get(ch, 350), final=True, punct=ch)
        elif ch in _COMMA:
            flush(230, final=False, punct=ch)
        elif ch.isspace():
            flush(120, final=False)
        elif "\u4e00" <= ch <= "\u9fff":
            buffer.append((ch, idx))
        elif ch.isascii() and ch.isalpha():
            buffer.append((ch, idx))
        elif ch.isdigit():
            buffer.append((ch, idx))
    flush(0, final=True)
    for i, s in enumerate(syls):
        s.index = i
    rep.report("parse", 1.0, force=True)
    return syls

# ---------------------------------------------------------------------------
# Pinyin direct-input mode
# ---------------------------------------------------------------------------

_TONE_MARK = {
    "ā": ("a", 1), "á": ("a", 2), "ǎ": ("a", 3), "à": ("a", 4),
    "ē": ("e", 1), "é": ("e", 2), "ě": ("e", 3), "è": ("e", 4),
    "ī": ("i", 1), "í": ("i", 2), "ǐ": ("i", 3), "ì": ("i", 4),
    "ō": ("o", 1), "ó": ("o", 2), "ǒ": ("o", 3), "ò": ("o", 4),
    "ū": ("u", 1), "ú": ("u", 2), "ǔ": ("u", 3), "ù": ("u", 4),
    "ǖ": ("v", 1), "ǘ": ("v", 2), "ǚ": ("v", 3), "ǜ": ("v", 4),
    "ń": ("n", 2), "ň": ("n", 3), "ǹ": ("n", 4),
}

_PINYIN_CLAUSE = set("。！？；：\n.!?;:")
_PINYIN_COMMA = set("，、,")
_PINYIN_PAUSE = {
    "。": 420, ".": 420, "！": 380, "!": 380, "？": 400, "?": 400,
    "；": 280, ";": 280, "：": 260, ":": 260, "\n": 420,
}


def _parse_pinyin_token(tok: str) -> tuple[str, int, str]:
    raw = tok.strip()
    override = None
    if "|" in raw:
        raw, ov = raw.split("|", 1)
        ov = ov.replace("_", " ").strip()
        if ov:
            override = ov
    tone = 0
    chars: list[str] = []
    for ch in raw:
        if ch in _TONE_MARK:
            base, t = _TONE_MARK[ch]
            chars.append(base)
            tone = t
        elif ch in "üÜ":
            chars.append("v")
        else:
            chars.append(ch)
    py = "".join(chars).lower().strip()
    m = re.search(r"([0-5])$", py)
    if m:
        tone = int(m.group(1))
        py = py[:-1]
    if not py:
        raise ValueError(f"无法识别拼音：{tok}")
    if tone == 0:
        tone = 5
    if not is_valid_pinyin(py):
        raise ValueError(f"无法识别拼音：{tok}（请检查声母/韵母，或使用 拼音|音素 覆盖）")
    ph = override if override else pinyin_to_phonemes(py)
    return py, tone, ph


def char_readings(text: str,
                  dictionary: dict[str, str] | None = None
                  ) -> dict[int, tuple[str, int]]:
    """原文每个下标对应的自动读音 ``(拼音, 声调)``。

    只返回能对齐到音节的字符：标点、空格、以及数字展开出来的字都不在其中。
    纠音对话框用它预填「自动读音」——直接拿 ``Syllable.src`` 当原文下标会错位，
    因为那是 ``normalize_text`` 之后的位置。
    """
    normalized = normalize_text(text)
    if normalized == text:
        mapping = {i: i for i in range(len(text))}
    else:
        mapping = _offset_map(text, normalized)
    by_src = {s.src: (s.pinyin, s.tone)
              for s in text_to_syllables(text, dictionary=dictionary)}
    out: dict[int, tuple[str, int]] = {}
    for offset in range(len(text)):
        target = mapping.get(offset)
        if target is not None and target in by_src:
            out[offset] = by_src[target]
    return out


def pinyin_text_to_syllables(text: str,
                             reporter: Reporter | None = None) -> list[Syllable]:
    """Parse whitespace-separated pinyin (tone digits/marks) into syllables.

    Examples:
        ni3 hao3 shi4 jie4
        nǐ hǎo，shì jiè！
        ni3|n_i hao3          # override the phonemes for one syllable
    """
    rep = reporter or Reporter()
    rep.stage("parse", 0.0)
    text = text.replace("u:", "v").replace("U:", "v").replace("’", "'")
    total = len(text)
    syls: list[Syllable] = []
    phrase = 0
    buffer: list[str] = []

    def flush(pause_ms: int, final: bool = False, punct: str = "") -> None:
        nonlocal buffer, phrase
        if not buffer:
            # 连续标点（？！、！？）只保留第一个：问号决定句尾要不要抬高，
            # 被后面的感叹号盖掉就变成陈述句了。末尾的空白或逗号也要补上
            # final，否则最后一个音节会按非句尾处理，短一截、也没有句尾降调。
            if syls:
                if pause_ms:
                    syls[-1].pause_after_ms = max(syls[-1].pause_after_ms,
                                                 pause_ms)
                if punct and not syls[-1].punct:
                    syls[-1].punct = punct
                if final:
                    syls[-1].final = True
            return
        local: list[Syllable] = []
        for tok in buffer:
            py, tone, ph = _parse_pinyin_token(tok)
            local.append(Syllable(text=tok, pinyin=py, tone=tone, phonemes=ph,
                                  phrase=phrase))
        if not local:
            buffer = []
            return
        if final:
            local[-1].final = True
        _apply_stress(local, final, "pinyin")
        if pause_ms:
            local[-1].pause_after_ms = pause_ms
        if punct:
            local[-1].punct = punct
        syls.extend(local)
        buffer = []
        phrase += 1

    i = 0
    while i < len(text):
        # Token-wise input: one iteration per token, so check every time and
        # let the reporter throttle the callbacks.
        rep.check()
        rep.report("parse", i / total)
        ch = text[i]
        if ch in _PINYIN_CLAUSE:
            flush(_PINYIN_PAUSE.get(ch, 350), final=True, punct=ch)
            i += 1
        elif ch in _PINYIN_COMMA:
            flush(230, final=False, punct=ch)
            i += 1
        elif ch.isspace():
            i += 1
        else:
            j = i
            while (j < len(text) and not text[j].isspace()
                   and text[j] not in _PINYIN_CLAUSE
                   and text[j] not in _PINYIN_COMMA):
                j += 1
            token = text[i:j]
            for part in re.split(r"['\-]", token):
                if part:
                    buffer.append(part)
            i = j
    flush(0, final=True)
    for k, s in enumerate(syls):
        s.index = k
    rep.report("parse", 1.0, force=True)
    return syls
