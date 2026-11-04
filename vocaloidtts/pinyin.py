"""Chinese text -> singable pinyin syllables and VOCALOID X-SAMPA phonemes."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable

try:
    from pypinyin import Style, pinyin as _pinyin
except Exception:  # pragma: no cover - pypinyin is bundled in the release build
    _pinyin = None


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
    parts: list[str] = []
    group = 0
    while n > 0:
        sec = n % 10000
        if sec:
            text = _section_to_chinese(sec) + _BIG_UNITS[group]
            parts.append(text)
        elif parts:
            parts.append("零")
        n //= 10000
        group += 1
    return "".join(reversed(parts)).replace("零零", "零").strip("零") or "零"


def _number_token_to_chinese(tok: str, prev: str, next_: str) -> str:
    """Read a run of digits in a natural way (years / phone / decimals)."""
    if "." in tok:
        whole, frac = tok.split(".", 1)
        return num_to_chinese(int(whole)) + "点" + "".join(_DIGITS[int(c)] for c in frac)
    if len(tok) == 4 and tok.startswith(("19", "20")) and next_ in ("年",):
        return "".join(_DIGITS[int(c)] for c in tok)
    if len(tok) >= 7 and not (prev and prev.isdigit()):
        # phone / ID numbers are read digit by digit
        return "".join(_DIGITS[int(c)] for c in tok)
    return num_to_chinese(int(tok))


def normalize_text(text: str) -> str:
    """Normalise punctuation, numbers and Latin fragments for the lyric parser."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
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
        return _number_token_to_chinese(tok, prev, nxt)

    text = re.sub(r"\d+(?:\.\d+)?", repl, text)
    # percent
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
    stress: float = 0.0
    final: bool = False
    phrase: int = 0
    start_ms: float = 0.0
    dur_ms: float = 0.0
    index: int = 0


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


def _apply_tone_sandhi(syls: list[Syllable]) -> None:
    for i, s in enumerate(syls):
        if s.pinyin == "yi" and s.tone == 1:
            nxt = syls[i + 1] if i + 1 < len(syls) else None
            if nxt and nxt.tone == 4:
                s.tone = 2
            elif nxt and nxt.tone in (1, 2, 3):
                s.tone = 4
        if s.pinyin == "bu" and s.tone == 4:
            nxt = syls[i + 1] if i + 1 < len(syls) else None
            if nxt and nxt.tone == 4:
                s.tone = 2
    # 3-3 sandhi, left to right
    for i in range(len(syls) - 1):
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


def _neutral_marks(text: str) -> set[int]:
    """Indices that should be sung with neutral tone (tone 5)."""
    marks: set[int] = set()
    n = len(text)
    for i in range(n):
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
    for i, ch in enumerate(text):
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


def _context_pinyin(text: str) -> dict[int, tuple[str, int]]:
    """Phrase-aware pinyin for each Chinese character.

    Calling pypinyin on the whole run (rather than one character at a time)
    lets it use its phrase dictionary for 目的/着急/了解/觉得 etc.
    """
    out: dict[int, tuple[str, int]] = {}
    if _pinyin is None:
        return out
    for m in re.finditer(r"[\u4e00-\u9fff]+", text):
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


def text_to_syllables(text: str) -> list[Syllable]:
    """Parse Chinese text into a flat list of syllables, with pauses."""
    text = normalize_text(text)
    ctx = _context_pinyin(text)
    neutral = _neutral_marks(text)
    syls: list[Syllable] = []
    phrase = 0
    buffer: list[tuple[str, int]] = []

    def flush(pause_ms: int, final: bool = False) -> None:
        nonlocal buffer, phrase
        if not buffer:
            if pause_ms and syls:
                syls[-1].pause_after_ms = max(syls[-1].pause_after_ms, pause_ms)
            return
        local: list[Syllable] = []
        neutral_positions: list[tuple[int, str]] = []
        for ch, idx in buffer:
            got = ctx.get(idx) or _pinyin_for_char(ch)
            if not got:
                continue
            py, tone = got
            ph = pinyin_to_phonemes(py)
            local.append(Syllable(text=ch, pinyin=py, tone=tone, phonemes=ph,
                                  phrase=phrase))
            if idx in neutral:
                neutral_positions.append((len(local) - 1, ch))
        # Tone sandhi (一/不/3+3) is based on the lexical tones, before the
        # neutral-tone reduction is applied.
        _apply_tone_sandhi(local)
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
            if pause_ms:
                local[-1].pause_after_ms = pause_ms
            syls.extend(local)
        buffer = []
        phrase += 1

    for idx, ch in enumerate(text):
        if ch in _CLAUSE_END:
            flush({"。": 420, "！": 380, "？": 400, "；": 280, "：": 260,
                   "\n": 420}.get(ch, 350), final=True)
        elif ch in _COMMA:
            flush(230, final=False)
        elif ch.isspace():
            flush(120, final=False)
        elif "\u4e00" <= ch <= "\u9fff":
            buffer.append((ch, idx))
        elif ch.isascii() and ch.isalpha():
            # English fragments: spell letters with Chinese syllables
            py = _LATIN.get(ch.lower(), "a").split()[0]
            syl = Syllable(text=ch, pinyin=py, tone=1,
                           phonemes=pinyin_to_phonemes(py),
                           stress=0.30, phrase=phrase)
            syls.append(syl)
        elif ch.isdigit():
            buffer.append((ch, idx))
    flush(0, final=True)
    for i, s in enumerate(syls):
        s.index = i
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


def pinyin_text_to_syllables(text: str) -> list[Syllable]:
    """Parse whitespace-separated pinyin (tone digits/marks) into syllables.

    Examples:
        ni3 hao3 shi4 jie4
        nǐ hǎo，shì jiè！
        ni3|n_i hao3          # override the phonemes for one syllable
    """
    text = text.replace("u:", "v").replace("U:", "v").replace("’", "'")
    syls: list[Syllable] = []
    phrase = 0
    buffer: list[str] = []

    def flush(pause_ms: int, final: bool = False) -> None:
        nonlocal buffer, phrase
        if not buffer:
            if pause_ms and syls:
                syls[-1].pause_after_ms = max(syls[-1].pause_after_ms, pause_ms)
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
        syls.extend(local)
        buffer = []
        phrase += 1

    i = 0
    while i < len(text):
        ch = text[i]
        if ch in _PINYIN_CLAUSE:
            flush(_PINYIN_PAUSE.get(ch, 350), final=True)
            i += 1
        elif ch in _PINYIN_COMMA:
            flush(230, final=False)
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
    return syls
