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
| A | 中文听感 | A1–A3 | 待做 |
| B | VSQX 导出数据 | B1–B3 | 待做 |
| C | 文本导入编码 | C1–C3 | 待做 |
| D | 应用健壮性 | D1–D4 | 待做 |
| E | Win32 平台层 | E1–E8 | 待做 |
| F | 界面细节 | F1–F3 | 待做 |
| G | 收尾与更正 | G1–G2 | 待做 |
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

### C1 UTF-32LE 被当成 UTF-16LE [待复现]

- **位置**：`vocaloidtts/textio.py`（BOM 探测段）
- **现象**：UTF-32LE 的 BOM 是 `FF FE 00 00`，前两字节与 UTF-16LE 的 `FF FE` 相同。
  若先判 UTF-16 就会按 2 字节切分，读出满屏 NUL 或乱码。
- **修法**：BOM 判定按长度从长到短（4 字节 → 3 字节 → 2 字节），先试 UTF-32 再试 UTF-16。
- **验证**：构造 UTF-32LE/UTF-32BE 字节样本，断言解码出原文。

### C2 无 BOM 的 UTF-16BE 认不出 [待复现]

- **位置**：`vocaloidtts/textio.py`（同上）
- **现象**：无 BOM 时只按 UTF-16LE 猜，UTF-16BE 文本读成乱码。
- **修法**：无 BOM 时用 NUL 字节分布判端序（ASCII 文本在 BE 下 NUL 在偶数位、LE 下在奇数位），
  命中才采用，否则维持现有 UTF-8 → GBK 顺序。
- **验证**：构造无 BOM 的 UTF-16BE/LE 样本，断言都能正确解码。

### C3 解码失败时没剥掉 BOM [待复现]

- **位置**：`vocaloidtts/textio.py`（候选编码循环）
- **现象**：某编码解码抛错后直接 `break`，BOM 字符留在文本开头，第一条歌词带 `\ufeff`。
- **修法**：解码成功后统一 `lstrip("\ufeff")`，与失败分支解耦。
- **验证**：构造「BOM + 非法字节」样本，断言输出首字符不是 BOM。

---

## 批 D：应用健壮性（P2）

### D1 `_bpm()` / `_meter()` 不回写控件 [待复现]

- **位置**：`vocaloidtts/app.py`（`_bpm` / `_meter`）
- **现象**：BPM 框里填了非法值（空、0、字母），程序回退到默认值继续生成，
  但输入框仍显示非法文本——用户以为用了自己填的数。
- **修法**：解析失败时把控件内容改回实际生效值，并给一次状态栏提示。
- **验证**：抽出纯函数 `parse_bpm(text, default) -> (value, ok)`，测试非法输入返回默认值且 `ok=False`。

### D2 `os.startfile` 前把整个文件读进内存 [代码确认]

- **位置**：`vocaloidtts/app.py`（打开导出目录/文件的分支）
- **现象**：为了判断文件是否存在或取路径，把大文件整体读入；导出的 VSQX 可能几十 MB。
- **修法**：只做 `Path.exists()` 检查后交给 `os.startfile`，不读内容。
- **验证**：测试用 1 MB 临时文件，断言打开路径不触发读取（用 `Path.stat` 计数或直接审阅代码路径）。

### D3 `_ensure_tray` 失败后窗口不销毁 [代码确认]

- **位置**：`vocaloidtts/app.py`（`_ensure_tray`）
- **现象**：托盘创建失败时只记日志，主窗口仍被隐藏，用户既看不到窗口也没有托盘图标。
- **修法**：失败时回滚为「不隐藏窗口」，并把错误显示在状态栏。
- **验证**：模拟托盘构造抛异常，断言窗口 `state()` 不是 `withdrawn`。

### D4 `main()` 没有全局异常钩子 [代码确认]

- **位置**：`vocaloidtts/app.py`（`main`）
- **现象**：Tk 回调里未捕获的异常只在控制台打印；`console=False` 构建下用户什么都看不到，
  窗口卡住也不知道发生了什么。
- **修法**：安装 `sys.excepthook` 与 `Tk.report_callback_exception`，写日志 + 弹一次错误框（去重）。
- **验证**：测试钩子函数对同一异常只弹一次；日志文件出现堆栈。

---

## 批 E：Win32 平台层（P2）

这一批没有自动化测试，只能靠读代码 + 真机验证，改动要格外保守。

### E1 `RegisterClassW` 不检查返回值 [代码确认]

- 位置：`vocaloidtts/tray.py`（窗口类注册）
- 现象：类已存在时返回 0，后续 `CreateWindowExW` 拿到空句柄，托盘静默不出现。
- 修法：检查返回值与 `GetLastError() == ERROR_CLASS_ALREADY_EXISTS (1410)`，其余情况抛错。

### E2 `NIM_SETVERSION` 之后才设 tooltip [代码确认]

- 位置：`vocaloidtts/tray.py`（`NIM_ADD` 流程）
- 现象：`NIM_SETVERSION` 会重置部分字段，之后设置的 tooltip 在某些 shell 版本上不生效。
- 修法：把 tooltip 设置移到 `NIM_SETVERSION` 之前，或在其后再发一次 `NIM_MODIFY`。

### E3 `TaskbarCreated` 后不重发 `NIM_SETVERSION` [代码确认]

- 位置：`vocaloidtts/tray.py`（消息循环）
- 现象：explorer.exe 重启后托盘重建，但版本号没重设，气泡通知行为回退到旧版。
- 修法：重建流程里补一次 `NIM_SETVERSION`。

### E4 `GetParent` 未声明 `restype` [代码确认]

- 位置：`vocaloidtts/tray.py` / `v4bridge.py`（ctypes 声明区）
- 现象：默认 `c_int` 截断 64 位句柄，极端情况下拿到错误的父窗口。
- 修法：`argtypes` / `restype` 全部显式声明为 `HWND`。

### E5 `SendMessageW` 没有超时 [代码确认]

- 位置：`vocaloidtts/v4bridge.py`
- 现象：目标编辑器无响应时，`SendMessageW` 会一直阻塞，整个导出流程卡死。
- 修法：改用 `SendMessageTimeoutW`，超时后报「编辑器无响应」。

### E6 UIPI 拦截后静默失败 [代码确认]

- 位置：`vocaloidtts/v4bridge.py`
- 现象：编辑器以管理员权限运行时，普通权限进程发消息被 UIPI 丢弃，返回值看着像成功。
- 修法：检测返回值 + `GetLastError() == ERROR_ACCESS_DENIED (5)`，给出「请以相同权限运行」的提示。

### E7 `GetForegroundWindow` 未声明 `restype` [代码确认]

- 位置：`vocaloidtts/v4bridge.py`
- 现象：同 E4，句柄被截断成 32 位。
- 修法：显式声明 `restype = HWND`。

### E8 `Popen(cwd="")` [代码确认]

- 位置：`vocaloidtts/v4bridge.py`
- 现象：`cwd` 为空字符串时行为依赖平台，可能抛 `FileNotFoundError`。
- 修法：`cwd or None`。

---

## 批 F：界面细节（P3）

### F1 `RoundedButton` 固定 `bg` 露出黑角 [代码确认]

- 位置：`vocaloidtts/app.py`（`RoundedButton`）
- 现象：圆角之外的四角画的是固定背景色，父容器换了底色就露黑角。
- 修法：构造时接受父容器底色，或改用 `place` 布局遮罩。

### F2 高 DPI 下固定高度裁切 [代码确认]

- 位置：`vocaloidtts/app.py`（按钮/进度条高度）
- 现象：125%/150% 缩放下固定像素高度装不下文字，下缘被切。
- 修法：高度按 `tk scaling` 换算，或改用 `pack` 的自然高度。

### F3 `_bank_badge_text` 硬编码 [代码确认]

- 位置：`vocaloidtts/app.py`（`_bank_badge_text`）
- 现象：声库类型徽标写死几种，新增版本显示为空。
- 修法：按 `voicebank.version` 生成，未知版本回退到「未知」。

---

## 批 G：收尾与更正（P3）

### G1 `docs/improvements.md` 补登记第 12 批之后的修复 [代码确认]

- 现象：进度表停在「批次 12」，之后 13 个 fix 提交没有登记。
- 修法：追加批次 13–14 行，写清条目、状态、验证方式。

### G2 撤销「`total_ticks` 不含句尾停顿」这条 [已复现，不成立]

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
