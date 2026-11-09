# 全仓审查修复清单（第二轮）

更新日期：2026-11-09。基线：`0be6e0b`（v1.2.0 + 13 个 fix 提交）。

## 背景

v1.2.0 发布后对全仓做了首次完整审查（`python-code-review` + 人工复核），
累计记录 150 余条。影响真实数据或常见操作的 30 余条已经修完，本文是**剩余部分**
的执行清单：写清每条的现象、位置、修法、验证方式，按批次推进。

验证基线：**167 项测试通过**（1 项按平台跳过），
`ruff check vocaloidtts tests tools` 无告警，`VocaloidTTS.py --selftest` 退出码 0。

## 阅读约定

- 位置写 `文件:行号（函数/类）`，行号基于 `0be6e0b`；修复后行号会漂移，以函数名为准。
- 标记：**[已复现]** 本轮用探针脚本实测过；**[代码确认]** 读代码即可确定；**[待复现]** 来自审查记录，动手前先复现。
- 严重度：**P1** 用户能直接听出来或看出来的；**P2** 数据正确性与健壮性；**P3** 界面细节。
- 每条修完补一条回归测试（GUI/Win32 项补可测的纯函数部分，其余标注为需真机验证）。

## 批次总览

| 批次 | 主题 | 条目 | 状态 |
|---|---|---|---|
| A | 中文听感 | A1–A3 | 已完成 |
| B | VSQX 导出数据 | B1–B3 | 已完成 |
| C | 文本导入编码 | C1–C3 | 已完成 |
| D | 应用健壮性 | D1–D4 | 已完成（D2/D3 复测为误报，已撤销） |
| E | Win32 平台层 | E1–E8 | 已完成（E1/E2 复测为误报，已撤销） |
| F | 界面细节 | F1–F3 | 已完成（F2/F3 复测后撤销） |
| G | 收尾与更正 | G1–G2 | 已完成 |
| N | 暂不修（第三轮） | N1–N6 | 记录在案 |

---

## 批 A：中文听感（P1）

### A1 叠词的三声变调被轻声化打断 [已复现]

- **位置**：`vocaloidtts/pinyin.py:594`（`text_to_syllables.flush`）、`pinyin.py:311`（`_apply_tone_sandhi`）
- **现象**：`姐姐` → `jié jie`（tone 2 + 5），正确是 `jiě jie`（3 + 5）。同样中招：
  奶奶、宝宝、姥姥、婶婶。实测输出见下表。

  | 输入 | 现状 | 应为 |
  |---|---|---|
  | 姐姐 | 2 + 5 | 3 + 5 |
  | 奶奶 | 2 + 5 | 3 + 5 |
  | 宝宝 | 2 + 5 | 3 + 5 |

- **原因**：`_apply_tone_sandhi` 在 `neutral_positions` 写回 `tone = 5` 之前执行，
  即将轻声化的下一音节仍按 3 声参与 3+3 连读，把前一音节降成了 2 声。
  代码注释写的「变调基于词法声调」是语言学立场，但忽略了「后字轻声时不触发三声连读」。
- **修法**：把待轻声化的音节集合传给 `_apply_tone_sandhi`，3+3 判定时跳过这些位置。
  一/不 变调不受影响（「一个」的「个」虽轻声，但「一」的变调看的是原调去声，结论相同）。
- **验证**：新增测试断言 姐姐/奶奶/宝宝 首音节 `tone == 3`、次音节 `tone == 5`；
  回归「买东西」的西仍是 5、普通 3+3（你好）仍是 2+3。

### A2 成音节鼻音被读成「啊」 [已复现]

- **位置**：`vocaloidtts/pinyin.py:199`（`pinyin_to_phonemes`）、`pinyin.py:156`（`_FINAL_PH`）
- **现象**：`嗯` 的拼音是 `n`，实测 `pinyin_to_phonemes("n")` 返回 `a`，唱出来是「啊」。
  `pinyin_to_phonemes("m")` 同样是 `a`；`pinyin_to_phonemes("ng")` 返回 `n a`（多一个 a）。
- **原因**：`_FINAL_PH` 只有普通韵母，没有 `n` / `m` / `ng` 这类独立成音节的鼻音；
  `split_initial_final("n")` 返回 `("", "n")`，查表落空后兜底成 `a`。
- **修法**：`pinyin_to_phonemes` 开头加成音节鼻音表 `{"n": "n", "ng": "N", "m": "m"}`，
  命中直接返回。这三个都是 VOCALOID 中文音素表里存在的音素。
- **验证**：测试断言 `pinyin_to_phonemes("n") == "n"`、`"ng" → "N"`、`"m" → "m"`；
  `嗯` 的音素不再是 `a`；回归 `en`/`an`/`ang` 等普通韵母不受影响。

### A3 轻声词表按子串匹配，误伤非轻声词 [已复现]

- **位置**：`vocaloidtts/pinyin.py:386`（`_neutral_marks`）、`pinyin.py:352`（`_NEUTRAL_WORDS`）
- **现象**：`东西南北` 的「西」被标成轻声（tone 5），正确是 `xī`。
  「买东西」的「西」读轻声是对的，说明词表本身没错，是**没有词边界**。
- **原因**：`_neutral_marks` 对每个位置取 `text[i:i+2]` / `text[i:i+3]` 直接查表，
  只要出现「东西」两个字就命中，不管它后面跟的是不是「南北」。
- **修法**：加一张反例表 `_NEUTRAL_EXCEPT`，记录「这些词形里不含轻声」的上下文
  （东西南北、东西向、东西南北中、不是东西 等），命中反例时跳过。
  优先做「固定反例表」而不是引入分词，理由是：词表本来就是枚举式的小词典，
  加反例与它同构、零依赖、可测试；引入分词会带来新的运行时依赖和不确定性。
- **验证**：测试断言「东西南北」西为 1 声、「买东西」西为 5 声、「东西」单独出现为 5 声。

---

## 批 B：VSQX 导出数据（P1）

### B1 `<y>` 歌词没走统一的 `lyric_for` [代码确认]

- **位置**：`vocaloidtts/vsqx.py:43`（`_note_lines`）
- **现象**：中文项目导出 VSQX 后歌词是拼音（`n.lyric`），而 `.ustx` / `.svip3` / `.svip` / jobfile
  都走 `exporters.lyric_for`，写的是汉字。同一个项目导出成不同格式，歌词不一致。
- **修法**：`vsqx.py` 改用 `from .exporters import lyric_for`（`exporters` 目前不 import `vsqx`，
  无循环依赖）。`<p>` 音素保持不变，纠音结果不受影响。
- **验证**：导出含汉字的 Song，断言 `<y>` 里是汉字；拼音输入的 Song 仍写拼音。

### B2 `vVoice/<id>` 没校验 compID 长度 [代码确认]

- **位置**：`vocaloidtts/vsqx.py:88`（`write_vsqx`）
- **现象**：`voicebank.id` 直接写进 `<id>`。VOCALOID4/5 要求这里是 16 字符 compID，
  长度不对时编辑器要么认不出声库、要么静默回退到默认歌手。
- **修法**：导出前校验 `len(id) == 16` 且为 ASCII，不满足抛 `ExportError` 并说明实际值。
  比补零或截断更诚实——错位的 compID 不会因为补齐而变对。
- **验证**：测试构造 15/17 字符 id 断言抛错；正常 16 字符 id 通过。

### B3 `playTime` 把 `part_start` 算进了长度 [代码确认]

- **位置**：`vocaloidtts/vsqx.py:71`（`write_vsqx`）
- **现象**：`part_start = measure_ticks * 4`，`play_time = part_start + max(...)`。
  `playTime` 是 part 的播放长度，不该包含起始偏移，导致 VSQX 里整段被拉长 4 小节。
- **修法**：`play_time = max(measure_ticks, song.total_ticks + measure_ticks)`，
  起点偏移只用于 `<t>`，不进长度。
- **验证**：测试断言 `playTime` 与 `total_ticks` 同量级，不随 `part_start` 增长。

---

## 批 C：文本导入编码（P1）

### C1 UTF-32LE 被当成 UTF-16LE [已复现]

- **位置**：`vocaloidtts/textio.py`（`_BOMS`、`decode_text`）
- **现象**：UTF-32LE 的 BOM 是 `FF FE 00 00`，前两字节与 UTF-16LE 的 `FF FE` 相同。
  实测 `"你好世界".encode("utf-32")` 被 `utf-16-le` 解成 `\x00你\x00好\x00世\x00界`；
  UTF-32BE 更糟，走 `utf-16` fallback 解成 `\x00￾\x00恏\x00絙…`。
- **修法**：`_BOMS` 按长度从长到短排（4 字节 → 3 字节 → 2 字节），加 `utf-32-le` / `utf-32-be`。
- **验证**：构造 UTF-32LE/BE 字节样本，断言解码出原文且 encoding 标注正确。

### C2 无 BOM 的 UTF-16 认不出 [已复现]

- **位置**：`vocaloidtts/textio.py`（`_utf16_by_nul`、`decode_text`）
- **现象**：无 BOM 时只按 UTF-16LE 猜，实测 `"hello world".encode("utf-16-be")`
  被 `utf-8-sig` 解成 `\x00h\x00e\x00l…`（满是 NUL）。
- **修法**：无 BOM 时用 NUL 字节分布判端序（ASCII 文本在 BE 下 NUL 在偶数位、LE 下在奇数位），
  命中才采用，否则维持现有 UTF-8 → GBK 顺序。
  **已知限制**：纯中文的 UTF-16 没有 NUL 可依据，与普通 UTF-8 无法可靠区分，
  因此不猜——宁可留成乱码让用户换编码，也不做会误伤正常文本的猜测。
- **验证**：ASCII 为主的 UTF-16BE/LE 样本断言正确解码；纯中文 UTF-16 断言不产生控制字符。

### C3 解码失败时没剥掉 BOM [已复现]

- **位置**：`vocaloidtts/textio.py`（`decode_text` 的 BOM 分支）
- **现象**：BOM 分支解码失败后 `break` 掉进 fallback，实测 `EF BB BF FF FE FD`
  整份被 `utf-16` 读成 `믯﾿\ufdff`（韩文 + 替换符），编码来源也丢了。
- **修法**：BOM 分支失败时按声明编码 + `errors="replace"` 解码并返回，
  编码标注加 `(replace)` 后缀，不再掉进 utf-16；所有返回路径统一 `lstrip("\ufeff")`。
  另外 fallback 增加一条：解出控制字符（NUL、`\x16` 等）的结果一律否决。
- **验证**：构造「BOM + 非法字节」样本，断言 encoding 以 `utf-8-sig` 开头、结果里没有韩文。

---

## 批 D：应用健壮性（P2）

### D1 `_bpm()` / `_meter()` 不回写控件 [已复现]

- **位置**：`vocaloidtts/app.py`（`parse_bpm` / `parse_meter` / `_bpm` / `_meter`）
- **现象**：BPM 框里填了非法值（空、字母、0），程序回落到 120 继续生成，
  但输入框仍显示原文——用户以为用了自己填的数。拍号同理。
- **修法**：解析逻辑抽成模块级 `parse_bpm` / `parse_meter`，`_bpm()` / `_meter()`
  发现控件文本与生效值不一致时回写控件。
- **验证**：`ParseInputTests` 3 项断言回落与夹取；回写行为需 GUI 手工确认。

### D2 撤销：`os.startfile` 前把整个文件读进内存 [已复测，不成立]

原记录称打开导出文件前会整体读入。实测 `app.py` 里只有两处 `read_bytes`：
`_load_text_file`（导入文本本来就要读全文，且有 20 万字符截断）和
`dest.write_bytes(src.read_bytes())`（复制工程文件）。三处 `os.startfile()`
调用都是直接传路径，不读内容。**这条是误报**，不再列入待修。

### D3 撤销：`_ensure_tray` 失败后窗口不销毁 [已复测，不成立]

原记录称托盘创建失败时窗口仍被隐藏。实测 `_minimize_to_tray` 在
`_ensure_tray()` 返回 False 时先弹窗问「现在直接退出吗」，用户选「否」
就 `return`，而 `self.withdraw()` 在成功路径末尾——窗口保持显示。
**这条是误报**，不再列入待修。

### D4 `main()` 没有全局异常钩子 [已复现]

- **位置**：`vocaloidtts/app.py`（`_install_excepthooks` / `main`）
- **现象**：`main()` 直接 `VocaloidTTSApp().mainloop()`，Tk 回调里的异常只在
  控制台打印；`console=False` 构建下窗口「没反应」，日志里也没有痕迹。
- **修法**：安装 `sys.excepthook` 与 `Tk.report_callback_exception`，统一写日志；
  同一个异常只弹一次框（`after` 回调出错时可能每帧都抛）。
- **验证**：`ExcepthookTests` 断言同一异常调用三次只弹一次、日志写三次。
  弹窗本身需真机确认。

---

## 批 E：Win32 平台层（P2）

真正的窗口、托盘和编辑器交互没法在单元测试里跑。这一批把能测的规则
抽出来放进 `tests/test_win32_guards.py`（托盘重建要重设版本号、消息要带超时），
其余仍需真机确认。

### E1 撤销：`RegisterClassW` 不检查返回值 [已复测，不成立]

原记录称类已存在时 `CreateWindowExW` 会拿到空句柄。实际上类已注册时
`CreateWindowExW` 仍然成功（窗口类还在），而注册真失败时 `CreateWindowExW`
会返回 0，代码里已有 `if not hwnd: return` 兜底。**这条不成立**，不改。

### E2 撤销：`NIM_SETVERSION` 之后才设 tooltip [已复测，不成立]

原记录称 tooltip 在 `NIM_SETVERSION` 之后才设置。实测 `tray.py` 的顺序是
`nid.szTip = ...` → `NIM_ADD` → `NIM_SETVERSION`，tooltip 在添加图标时
就带上了，`NIM_SETVERSION` 只改 `uVersion` 字段。**这条不成立**，不改。

### E3 `TaskbarCreated` 后不重发 `NIM_SETVERSION` [已修复]

- **位置**：`vocaloidtts/tray.py`（`_add_icon`、`_proc`）
- **现象**：explorer.exe 重启后只发 `NIM_ADD`，版本号没重设，气泡通知行为回退到 0 版。
- **修法**：把「添加图标 + 设版本」抽成 `_add_icon()`，`_run()` 与 `TaskbarCreated`
  分支都走它。
- **验证**：`TrayRebuildTests` 断言 `_add_icon()` 依次发出 `NIM_ADD`、`NIM_SETVERSION`，
  且 `uVersion == 4`；失败时返回 False。explorer 重启本身需真机确认。

### E4 `GetParent` 未声明 `restype` [已修复]

- **位置**：`vocaloidtts/tray.py`（ctypes 声明区）
- **现象**：默认 `c_int` 会截断 64 位句柄，`_hook_top` 可能拿到错误的父窗口。
- **修法**：`GetParent.restype = wintypes.HWND`，`argtypes = [wintypes.HWND]`。
- **验证**：无法自动测，靠类型声明审阅；拖拽与关闭拦截需真机点一遍。

### E5 `SendMessageW` 没有超时 [已修复]

- **位置**：`vocaloidtts/v4bridge.py`（`_send`）
- **现象**：目标编辑器无响应时 `SendMessageW` 会无限期阻塞，把载入线程吊死。
- **修法**：改用 `SendMessageTimeoutW` + `SMTO_ABORTIFHUNG`，默认 3 秒。
- **验证**：`SendTimeoutTests` 断言使用 `SMTO_ABORTIFHUNG` 且传了结果指针。

### E6 UIPI 拦截后静默失败 [已修复]

- **位置**：`vocaloidtts/v4bridge.py`（`_no_response`、`open_vsqx`）
- **现象**：编辑器以管理员权限运行时，普通权限进程的消息被 UIPI 丢弃，
  用户只看到「载入失败」却不知道原因。
- **修法**：`_send` 返回 False 时给出 `_no_response` 提示，明确写出「可能是
  权限不一致，请用相同权限运行」，并附上文件路径让用户手动打开。
- **验证**：`SendTimeoutTests.test_no_response_says_why` 断言提示里含「管理员权限」和路径。

### E7 `GetForegroundWindow` 未声明 `restype` [已修复]

- **位置**：`vocaloidtts/v4bridge.py`（ctypes 声明区）
- **现象**：同 E4，句柄被截断成 32 位，`_send_ctrl_o` 的前台窗口比对可能失准。
- **修法**：`GetForegroundWindow.restype = wintypes.HWND`。

### E8 `Popen(cwd="")` [已修复]

- **位置**：`vocaloidtts/v4bridge.py`（`launch_editor`）
- **现象**：`exe` 没有目录部分时 `os.path.dirname()` 返回空串，`cwd=""`
  在 Windows 上不是「当前目录」，`Popen` 直接抛错。
- **修法**：`cwd=os.path.dirname(exe) or None`。

---

## 批 F：界面细节（P3）

### F1 `RoundedButton` 固定 `bg` 露出黑角 [已修复]

- 位置：`vocaloidtts/app.py`（`RoundedButton.__init__`）
- 现象：圆角之外的四角画的是 Canvas 自己的底色，写死 `BG` 后按钮放到
  卡片或状态栏上会露出四个深色角。
- 修法：构造时读 `parent.cget("bg")` 当底色，读不到再回退 `BG`。
  现有调用点的父容器本来就是 `BG`，外观不变。
- 验证：无法自动测，需真机看一遍按钮落在卡片上的四角。

### F2 撤销：高 DPI 下固定高度裁切 [未验证，暂不改]

原记录称 125%/150% 缩放下 38px 固定高度会裁字。这条**没有实测**，而且
Tk 的 `tk scaling` 与进程 DPI 感知（`SetProcessDpiAwareness`）是两套机制，
盲改高度换算可能在标准 DPI 下反而变形。留待有高分屏的机器实测后再动。

### F3 撤销：`_bank_badge_text` 硬编码 [已复测，不是缺陷]

原记录称「新增版本显示为空」。实测未知声库会走 `vb.name.upper()` 分支
（如 `MOQINGXIAN`），不会为空，只是没有内置那几种的风格化缩写。
换成按 `display` 拼接会让徽标变成「洛天依 · 中文 Meng · V5」，比现在更长、
更容易撑破顶部布局，收益不抵风险。**这条不改**。

---

## 批 G：收尾与更正（P3）

### G1 `docs/improvements.md` 补登记第 12 批之后的修复 [已修复]

- 现象：进度表停在「批次 12」，之后 13 个 fix 提交没有登记。
- 修法：追加批次 13（全仓首次审查）与批次 14（本文批 A–F）两行，
  并在「尚未处理」段补上本轮新增的手工验证项与撤销条目。

### G2 撤销「`total_ticks` 不含句尾停顿」这条 [已复现，不成立，已登记]

- 原记录称 `total_ticks` 漏算句尾停顿。实测：

  | 输入 | total_ticks | 最后音符结束 | 差 |
  |---|---|---|---|
  | 你好世界 | 1131 | 1131 | 0 |
  | 你好世界。 | 1146 | 1146 | 0 |
  | 你好世界，再见。 | 1863 | 1863 | 0 |

  句尾停顿已经计入（带句号比不带多 15 tick）。**这条是误报**，在本文与
  `docs/improvements.md` 里都标注为「已复测，不成立」，不再列入待修。

---

## 暂不修（N）

以下六条需要**词组级韵律**或**听感 A/B 定夺**，属于第三轮范畴。现在改只会把
「能听出来的错」换成「说不清对错的另一种」，故明确排除在本轮之外。

| 编号 | 条目 | 为什么现在不修 |
|---|---|---|
| N1 | 三声连读不认词边界 | 需要分词才能判定「我很好」该读 `wǒ hén hǎo` 还是 `wó hén hǎo`，无词典时任何规则都是猜 |
| N2 | 儿化韵缺失（花儿/哪儿） | 需要完整的韵母儿化表（ar/or/er/ir/ur/vr 及鼻音尾脱落），漏一条就是新的错读 |
| N3 | `_FOCUS_PINYIN` 同音字全命中 | 拼音输入模式本身没有汉字信息，缩小词表只是换一种偏，不能解决 |
| N4 | `pbs` 归一化导致振幅不随 pbs 缩放 | 需要重新标定整条 P 曲线，必须 A/B 试听 |
| N5 | `start_ms` 与 `_start_tick` 漂移 8ms | 影响小于一帧，改动会波及全部时序测试，收益不足 |
| N6 | `compose` 不调 `apply_style` | 风格参数目前只在 GUI 侧生效，是否下沉到核心需要先定接口 |

---

## 验证方式

每批完成后跑同一套命令，结果写进提交信息：

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests
.\.venv\Scripts\python.exe -B -m ruff check vocaloidtts tests tools
.\.venv\Scripts\python.exe -B VocaloidTTS.py --selftest
```

需要真机确认、本清单无法自动验证的：

- 真实 VOCALOID4 / V5 载入 VSQX 后声库是否正确、歌词是否可读（B1/B2）
- 逐字修饰的实际听感（A1/A2/A3）
- 托盘在 explorer.exe 重启后的重建（E2/E3）
- `console=False` 构建下的异常提示（D4）
