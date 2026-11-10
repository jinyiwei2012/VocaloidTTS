# VocaloidTTS

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

<img src="assets/vocaloidtts.png" width="96" alt="VocaloidTTS icon">

> 把文字变成歌姬的「说话声」：自动生成音符、拼音歌词、PIT 音高曲线与 DYN/BRI/CLE/OPE 表情参数，输出 VOCALOID4/5 的 `.vsqx`，也可导出 VOCALOID 5/6、VOCALOID2、Synthesizer V、ACE Studio、X Studio 3、OpenUTAU、TuneLab、袅袅、VocalSharp、DiffScope 等二十多种工程，以及标准 MIDI 与 LRC/SRT/ASS 时间轴歌词；附带可选的 V4 Job Plugin。

**最新版本**：`v1.2.1` — 下载与每版说明见 [GitHub Releases](https://github.com/jinyiwei2012/VocaloidTTS/releases)。

本仓库以 MIT 协议公开源码，包含图标与演示工程。要现成的 Windows 程序，直接用 Releases 里的 `VocaloidTTS_v1.2.1.zip`（解压后双击 `VocaloidTTS.exe`）。

---

## 快速开始

### 方式 A：打包好的 EXE（推荐）

1. 解压 Releases 里的 zip，双击 `VocaloidTTS.exe`；
2. 左上角选 **中文文本** 或 **拼音输入**；
3. 输入文字，或点预设（自然朗读 / 戏剧朗读 / 新闻播报 / 甜系撒娇 / 气声耳语 / 故事旁白）；
4. 点 **生成工程 ▼** 选格式：默认 `VOCALOID VSQX`，其余格式见下方[导出格式](#导出格式)；
5. 用对应软件打开：V4/V5 用 `Ctrl+O` 打开 `.vsqx`；X Studio 3 / OpenUTAU 打开后把临时歌手改选为本机声库；
6. 按空格试听；V4/V5 可 `文件 → 导出 → 波形` 导出 WAV。

也可以点 **载入 V4/V5**：程序会尝试自动完成「打开文件」对话框。V5 已实测；V4 失败时手动 `Ctrl+O` 即可。

### 方式 B：从源码运行

需要 Python 3.10+、Windows 10/11。

```bat
git clone https://github.com/jinyiwei2012/VocaloidTTS.git
cd VocaloidTTS
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt
python VocaloidTTS.py
```

---

## 界面与参数

| 参数 | 作用 | 建议 |
|---|---|---|
| 歌姬 | 启动自动扫描注册表与常见 `VoiceDB`，可手动添加文件夹 | 本机测试：洛天依 · 中文 Meng、乐正绫 · V3 |
| 风格 | 一键套用一组语速/语调/气声/颤音，同时重置五个声调基准 | 先选风格，再微调 |
| **BPM / 拍号** | 工程速度与节拍 | 默认 120、4/4 |
| 一声 / 二声 / 三声 / 四声 / 轻声 | 各声调的基准音高，独立滑条 | 默认 G3 / F#3 / E3 / F3 / E3 |
| 语速 | 音节时长与停顿的整体缩放 | 0.9–1.15 |
| **起伏** | 句调、焦点重音、局部音高变化强度 | 1.2–1.5 自然；1.6–1.9 戏剧化 |
| **力度** | DYN 动态范围、起音冲击、velocity | 1.1–1.4 自然；1.5–1.7 有力 |
| 停顿 | 逗号/句号停顿的缩放 | 0.8–1.2 |
| 气声 | BRE / CLE 配比 | 12–25 更自然 |
| **性别** | GEN 性别参数，映射到目标格式 | 默认 0；-100 低沉，+100 明亮 |
| 颤音 | 长音 PIT 上的轻微颤音 | 10–22 |
| 种子 | 控制微小随机扰动 | 固定种子可复现 |

> 五个声调滑条各自独立，可拖动 / 滚轮 / 方向键调整，双击复位。二声先压低再升起，三声低降回升，四声先升后落，轻声最低最短最弱。

**声库与编辑器**：启动时自动扫描注册表、`VoiceDB` 与常见安装路径；没扫到就点「歌姬」右侧 **＋ 添加文件夹**（目录会保存，下次继续扫）。找不到编辑器时点右上角 **编辑器** 选择 `VOCALOID4.exe` / `VOCALOID5.exe`。

**拼音直输**：适合多音字读错、要精确控制声调的场景。空格分隔音节、数字 1–5 标声调（5/0 轻声）：`ni3 hao3, shi4 jie4.`，也支持带调拼音 `nǐ hǎo`。拼音模式不做自动变调——你输入的声调就是最终声调。某个音素仍不准时可用 `ni3|n_i` 覆盖。

**逐字纠音与词典**：选中文字点 **纠音** 可逐字改拼音/声调，或设置强调、拉长、精确停顿；**用户词典**（`词语 → 带声调拼音`）跨项目共享，存在 `%APPDATA%\VocaloidTTS\userdict.json`。项目文件 `.vttsproj` 保存原文与全部设置，每 2.5 秒自动存一份、下次启动恢复。

---

## 导出格式

二十多种格式共用同一份 `Song` 数据（音符、PIT、DYN、BRE、GEN），不需要重复调参。
加格式只需要在 `vocaloidtts/formats/` 下加一个模块并在注册表里加一行，
「生成工程 ▼」菜单会自动列出来。

### VOCALOID 系

| 格式 | 扩展名 | 说明 |
|---|---|---|
| VOCALOID VSQX | `.vsqx` | V4/V5 原生工程；歌词写**拼音**（VOCALOID 的中文歌词栏按拼音解析） |
| VOCALOID 5/6 | `.vpr` | V5/V6 原生工程；zip 包，歌词写汉字、音素写 X-SAMPA |
| VOCALOID2 | `.vsq` | V2 序列；MIDI 文件里装 INI 风格文本，歌词写拼音 |

### 歌声合成编辑器

| 格式 | 扩展名 | 说明 |
|---|---|---|
| Synthesizer V 2 | `.s5p` | SynthV Studio 2 工程 |
| Synthesizer V（旧） | `.svp` | SynthV Studio 1 工程；歌词写汉字，发音交给编辑器生成 |
| ACE Studio | `.acep` | zstd 压缩容器；参数曲线交给 ACE 自己算 |
| ACE Virtual Singer | `.ace` | 手机版工程；时间用秒，`pitch` 是 MIDI + 12 |
| X Studio 3 | `.svip3` | 网易云 X Studio 3 工程；protobuf 手写 |
| OpenUTAU | `.ustx` | OpenUTAU 0.10 YAML 工程 |
| Yuan77 | `.y77` | 音符内嵌 500 点音高曲线；音高轴是 `88 - MIDI` |
| AISingers | `.aisp` | 「一行 JSON 头 + 一行 JSON 体」 |
| TuneLab（旧 / 新） | `.tlp` / `.tlpx` | 结构相同，`.tlpx` 用 CBOR |
| 袅袅虚拟歌手 | `.nn` | 纯文本按行排，音高包络 100 点 |
| VocalSharp | `.vspx` | XML 工程 |
| DiffScope | `.dspx` | zstd 压缩的 JSON |
| Vogen | `.vog` | zip 包里的 `chart.json` |
| VOX Factory | `.vfp` | 键值表 + order 数组的 JSON |
| VX-β | `.vxf` | MIDI 2.0 UMP 二进制流 |
| Muta | `.mtp` | 二进制，UTF-16LE 字符串 |
| OpenSVIP | `.svip` | JSON 交换工程，可继续转换 |

### 通用与歌词

| 格式 | 扩展名 | 说明 |
|---|---|---|
| 标准 MIDI | `.mid` | 单轨 SMF，任何 DAW 都能读；只带音符、歌词、速度、拍号 |
| LRC / SRT / ASS | `.lrc` / `.srt` / `.ass` | 按停顿切句的时间轴歌词与字幕 |

### 各格式的注意事项

- **VOCALOID VSQX / VPR / VSQ**：需要先选一个本机声库。VSQX 和 VPR 会把 compID 写进工程，compID 不是 16 位会直接报错——VOCALOID 遇到不认识的声库不报错，只会静默回退到默认歌手。
- **ACE Studio / ACE Virtual Singer**：默认歌手是占位值，打开后请改选本机声库。
- **X Studio 3**：没有公开的洛天依 UUID，临时借用内置女声「陈水若」的 ID，轨道名仍写「洛天依」；打开后请改选本机歌手。
- **OpenUTAU / VocalSharp / Muta**：只写占位歌手，不绑定真实声库。
- **OpenSVIP**：实验性 JSON 导出。

> 这些格式的**容器和结构**都有回归测试覆盖（每种的测试都自带独立写的读取器），
> 但除了 VSQX 之外，都还没有在对应编辑器里逐一实测过。遇到打不开请开 issue。

---

## V4 Job Plugin（可选）

> V5 不需要插件，直接打开 `.vsqx` 即可。

在 VocaloidTTS 里点 **安装 V4 插件**，然后在 V4 的 `任务 → 管理任务插件 → 添加` 里注册一次 `jobplugin/VocaloidTTS.lua`。之后生成一次、选中 Musical Part，运行 **VocaloidTTS 语调教导入**，音符和控制点会写入当前 Part——适合「工程里想加一段话」的场景。

---

## 工作原理

文本 → 切分音节 / 转拼音与 X-SAMPA 音素 → 按四声 + 句调 + 停顿 + 重音生成语音音高曲线 → 写成 `PIT`/`PBS` 控制点与 `DYN/BRI/CLE/OPE/BRE/GEN/POR` 表情参数 → 输出 `.vsqx`、`.vpr`、`.s5p`、`.acep` 等二十多种格式。

模型是**规则驱动**的（不是神经网络 TTS）：可控、可解释、离线、生成快。每个音节的音符落在自己的声调基准（G3/F#3/E3/F3），PIT 只负责该声调内部的升降，所以 V4/V5 钢琴卷帘里能看到四声的高度差，又不会在音符边界产生多余滑音。细节与参数说明见 [PLAN.md](PLAN.md)、[docs/improvements.md](docs/improvements.md) 与 `vocaloidtts/` 源码。

---

## 常见问题

**生成后没有声音？**
检查 V4 是否加载了声库、Part 是否在播放范围内；先按空格播放，看播放头是否经过第 5 小节。

**某个字读音不对？**
中文模式用词组级 `pypinyin`，多音字仍可能错。切到「拼音输入」直接写拼音，或用 `ni3|n_i` 覆盖音素；也可在 `vocaloidtts/pinyin.py` 的音素表里加规则。

**轻声识别不准？**
轻声词表在 `vocaloidtts/pinyin.py` 的 `_NEUTRAL_WORDS` / `_DI_ADVERBS` / `_DE_VERBS`，可自行补充；最可靠是用拼音模式写 `ma5`、`de5`。

**「载入 V4/V5」失败？**
V4 的自动载入是实验性 Win32 自动化，不同窗口布局/缩放可能失败；失败时手动打开 `.vsqx` 即可，工程本身没问题。

**程序出错，日志在哪？**
`%LOCALAPPDATA%\VocaloidTTS\log.txt`，超过 1 MB 自动轮转为 `log.old.txt`。

**输出 WAV 前面有几秒空白？**
V4 的 4 个预小节会计入导出（120/4/4 约 8 秒）。用音频软件裁掉前 4 小节，或在 V4 里把 Part 往前拖。

**还是觉得平？**
「起伏」拉到 1.55–1.8、「力度」拉到 1.45–1.7、语速降到 0.92–0.98，或直接选「戏剧朗读」。

---

## 构建

```bat
python -m pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --clean --onedir ^
  --name VocaloidTTS ^
  --icon assets/vocaloidtts.ico ^
  --add-data "jobplugin;jobplugin" ^
  --add-data "assets;assets" ^
  --collect-all pypinyin ^
  VocaloidTTS.py
```

产物在 `dist\VocaloidTTS\VocaloidTTS.exe`。用 `--onedir` 是为了避免部分机器上 onefile 解压临时目录失败。

发版走 `release` 分支：平时推 `main` 只跑测试，不构建也不发布；要发版时改好版本号并推到 `main`，再执行

```bat
git push origin main:release
```

[GitHub Actions](.github/workflows/release.yml) 会跑测试、构建、冒烟、打包 zip，并按 `vocaloidtts/__init__.py` 的版本号创建 Release。同一版本重推只替换产物，保留手写的发布说明。

---

## 开发验证

```bat
python -B -m unittest discover -s tests -v
ruff check vocaloidtts tests
python VocaloidTTS.py --selftest
```

测试用标准库 `unittest`，不需要声库、GUI 或目标编辑器。

---

## 已知限制

- 只针对 **中文声库** 优化；日文/英文声库需要换音素表。
- 多音字、儿化、轻声是规则 + 词典，不保证 100% 正确。
- 未内置映射的声库会显示出来，但 `bs/pc` 可能不对，需在 `voicebanks.json` 里覆盖。
- X Studio 3 的 DYN/BRE/GEN 尚未映射；OpenSVIP 是实验性导出。
- 「载入 V4/V5」是实验性自动化；失败请手动 `Ctrl+O`。
- 没有内置试听；试听请在 V4/V5、X Studio 3 或 OpenUTAU 中进行。

---

## 致谢与声明

- 拼音数据与分词建议：[pypinyin](https://github.com/mozillazg/python-pinyin)（MIT）。
- VSQX 结构参考：VOCALOID4 自带 `vsq4.xsd`、Job Plugin SDK、[3c1u/vsqx](https://github.com/3c1u/vsqx)。
- PIT/PBS 的 VSQX 表示参考：[EDITUNE](https://js-bach.org/vsqx/editune.html)（小川P）。
- VOCALOID 是 Yamaha 的商标；本项目与 Yamaha 无隶属关系。第三方声库、编辑器及相关商标的权利归各自权利人所有。

## 许可证

本项目采用 [MIT License](LICENSE)。MIT 不授予 VOCALOID、X Studio、OpenUTAU 所用第三方声库、编辑器或商标的权利；第三方依赖遵循各自许可证。
