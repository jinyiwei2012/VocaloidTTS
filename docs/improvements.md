# VocaloidTTS 改进候选清单（PLAN.md 之外）

更新日期：2026-11-07。源码基线：`c7ffd93`（v1.1.1）。

本文是**候选池**，不是承诺：`PLAN.md` 定义正式路线，本文记录它没覆盖、但读代码或实跑确认可以改进的点。每条给出位置、证据和建议，便于逐条决定是否纳入后续轮次。

来源分两批：

1. 声库点位实测（Lead，2026-11-07）：在临时目录构造三种声库目录形态，调用 `scan_voicebank_folder()` 观察结果。
2. 独立审查 + 复核（2026-11-07）：对 `prosody/pinyin/exporters/vsqx/tray/v4bridge/app` 逐文件审查；带数字的结论由 Lead 用 `.venv`（Python 3.14.7）复跑确认，条件写在条目里。

阅读约定：

- `位置` 精确到 `文件:行号`，基于 `c7ffd93`。
- `影响` 写实际会发生什么，不写「可能有问题」这类空话。
- 严重度：**H** 会出错或误导人；**M** 影响体验或工程化；**L** 锦上添花。
- 未在真实 VOCALOID4/V5/X Studio 中验证的结论，会在第 7 节统一标注。

---

## 0. 进度（2026-11-07）

按第 5 节的顺序，以下批次已经落地，每个批次都有独立提交和验证：

| 批次 | 条目 | 状态 | 验证 |
|---|---|---|---|
| 1 | H9 / H10 / H11：V5 命名、中文库优先、版本区分 | 已修复 | 35 项测试；`C:\vc` 12 条全对 |
| 2 | H1 / H6：删除假声库、GBK 导入 | 已修复 | 36 / 43 项测试；GBK 样本解析出正确音节 |
| 3 | 1.3 + S1–S4：点位 JSON、覆盖、导入导出、管理面板 | 已实现 | 52 项测试；覆盖与往返导出 |
| 4 | H8：原子写 | 已修复 | 46 项测试；失败时旧文件保留 |
| 5 | S7 + 后台化：扫描缓存、生成线程 | 已实现 | 55 项测试；缓存命中与失效 |
| 6 | M9 / M10：四声软限幅、P 点抽稀 | 已修复 | 57 项测试；夹点 27 → 0，P 点 -67% |
| 7 | M11 / H2–H4：托盘重建、生成顺序、设置逐项恢复、文件日志 | 已修复 | 57 项测试；selftest |
| 8 | H5：非 Windows 导入降级 | 已修复 | 58 项测试 |

尚未处理：第 3 节的 M1–M8、M12–M13，第 4 节的 L1–L7。

---

## 1. 声库扫描与点位管理

这是当前最值得先做的一块：它本身是缺口，又是「多语种」的前置——多语种要按声库语言切换音素表，前提是声库能识别准、来源看得见、点位可管理。

### 1.1 现状实测

先回答一个关键问题：**用户自己单开的文件夹（例如 `C:\vc\洛`）能不能被扫到？**

结论：**能被扫到，但组件 ID 与 bs/pc 的推断不可靠。**

| 目录形态 | 识别结果 | 问题 |
|---|---|---|
| `C:\vc\洛` 下直接放 `.vvd` | 能识别；`id` = `洛`（目录名），`path` = `C:\vc`（父目录） | `id` 不是 VOCALOID 组件 ID；`path` 指向父级，与常规声库语义不一致 |
| `C:\vc\绫\YuezhenglingV4_CHN\` 下放 `.vvd` | 能识别；`id` = `YuezhenglingV4_CHN`，`bs=4 pc=0` | 正确，这是 VoiceDB 的标准形态 |
| `C:\vc\自定义\` 下放 `.vvd`，文件名含「中文」 | 能识别；`bs=4 pc=0` 靠 `_CHINESE_MARKERS` 中的「中文」蒙对 | 命中靠关键字；若文件名叫「我的声库.vvd」，会落到 `bs=1 pc=0`（日文默认），在 V4 中无声 |
| `C:\vc\洛\BD79E492NWWK3DDF\` 等（安装程序释放的组件目录） | 能识别；`id` = 组件目录名（正是 compID），`path` = 声库根 | **id 天然正确**；仍可能猜错 bs/pc（见 1.1.1） |

对应代码：

- `_scan_folder()` 用 `os.walk` 最深 8 层找 `.vvd`：`vocaloidtts/voicebank.py:350-380`。
- `bid = comp.name`（用目录名当组件 ID）：`vocaloidtts/voicebank.py:374`。
- `path` 传 `comp.parent`：`vocaloidtts/voicebank.py:379`。
- bs/pc 推断顺序：`_make_bank()` → `_match_known()` → `_infer_unknown()`：`vocaloidtts/voicebank.py:214-243`。
- 中文/日文关键字表：`vocaloidtts/voicebank.py:171-174`。

### 1.1.1 组件 ID 是否跨机器一致

用户提供的实际结构是 `C:\vc\洛\BD79E492NWWK3DDF` 这类：声库根下平铺若干个 16 位大写字母数字目录，每个由安装程序释放。这正是 VOCALOID 的**组件目录**形态。

**结论：组件 ID（compID）在同一安装包/版本下跨机器一致。** 依据：

1. VSQX 的 `vVoiceTable` 里 `compID` 的语义就是 VoiceDB 下的组件目录名。社区整理的 [vVoiceTable 文档](http://kimi.secret.jp/wiki/dtm.php?vVoiceTable) 明确写了 compID「voicedbdir/以下のディレクトリ名と一致」，并给出实例 `BDRE87E2FTTKTDBA` / `VY1V3`。
2. 正因为 compID 稳定，VSQX 才能跨机交换：A 机生成、B 机打开时，编辑器用 compID 找同款声库；找不到会弹「重新映射歌手」对话框（同上资料）。
3. 项目内旁证：README 第 60 行写死乐正绫 V3 的 `bs=4 / pc=1 / id=BE8A88G3FWXLTEBD`，并声称在 V4 中直接以 YuezhenglingV3 打开；fallback 写死洛天依 · 中文 Meng的 `BK8H76TAEHXWSKDB`（`voicebank.py:460`）。

边界：

- 「一致」的前提是**同一个安装包/版本**。V3 盒装与 V4 升级包、再版、不同语言包之间，compID 可能不同。
- 一套声库常有多个组件（不同音色/语言），每个组件一个独立 compID——用户给的三个编码很可能就是三个组件。
- 因此代码里 `bid = comp.name` 对这种结构**恰好是正确的**（目录名就是 compID），不需要点位级 `id` 覆盖；`id` 覆盖只用于 A 形态（用户自建中文目录）。

真正需要补的是 **bs/pc**：当 `.vvd` 文件名是不透明编码（不含 `luotianyi`/「中文」等线索）时，`_match_known` 返回 `None`，`_infer_unknown` 落到 `(1, 0)`（日文默认）。实测：

```
纯编码目录名 + 纯编码/中文 .vvd → known=None, inferred=(1, 0, name)
```

这种组件在 V4 里可能无声，所以点位配置应支持**只覆盖 bs/pc、留空 id**。

### 1.1.2 真机实测：`C:\vc`（2026-11-07）

在用户机器上以 `C:\vc` 为根调用 `scan_voicebank_folder()`：0.98 秒返回 12 条。

| 识别结果 | 真实声库 | 判定 |
|---|---|---|
| `BETDB8W6KWZPYEB9` → 洛天依 · 中文 Meng（bs=4 pc=0） | 洛天依 · 中文 Meng V3，目录内有 `Tianyi_CHN.vvd` | 正确 |
| `BE8A88G3FWXLTEBD` → 乐正绫 · V3（bs=4 pc=1） | 乐正绫 V3，目录内有真名 `.vvd` | 正确 |
| `BMTD9EC6G4RPWMB3` → 言和 · 中文（bs=4 pc=0） | 言和 V3，`YANHE.vvd` | 正确 |
| `BNGE7CP7EMTRSNC3` → 初音未来（**bs=1 pc=0**） | Miku V4 **Chinese**，`MIKU_V4_Chinese.vvd` | bs/pc 错 |
| `BD79E492NWWK3DDF`、`BL8CEAM5N4XN3LFK`、`BP8CDDH5M7XN2PED` → `_v4compatible`（bs=1 pc=0） | 洛天依 · 中文 Meng **V5**「凝/婉/萌」，组件里只有 `_v4compatible.vvd` + `.ddb/.ddi`；EULA 文件名为 `LICENSES_V5_SHANGHAI HENIAN Luo Tianyi_CHS.txt` | 名字与参数全错 |
| `BMBNDB8EM5222MK3`、`BY98KLLZTDYH7YEE` → `_v4compatible` | 乐正绫 **V5**「悠/赤」（`Yuezheng_Ling_You/Chi.ddb`） | 全错 |
| `BMA8DBBZM5ZH2MDE`、`BN69LCH2W6TK8NEF` → `_v4compatible` | 言和 **V5**「牧/清」（`Yan_He_Mu/Qing.ddb`） | 全错 |
| `BE9C82Y5FDYNTEDD` → `_v4compatible` | 墨清弦 **V5**（`Moqingxian.ddb`） | 全错 |

**12 条里只有 3 条完全正确。** 两个根因：

1. **V5 组件里唯一的 `.vvd` 是兼容标记**。V5 声库向下兼容 V4，组件目录只有 237 字节的 `_v4compatible.vvd`，真实名字在 `.ddb/.ddi`（`Luo_Tianyi_Ning` 等）。V3/V4 组件有真名 `<Name>.vvd`，所以不受影响。`_scan_folder` 取 `.vvd` 的 stem 当名字（`voicebank.py:378`），于是 8 个 V5 组件全被叫成 `_v4compatible`，`_match_known` 失效，bs/pc 落到 `(1, 0)`。
2. **`miku` 先于中文判断命中**。`_KNOWN` 里 `("miku", (1, 0, "初音未来"))` 让 `MIKU_V4_Chinese` 被判成日文；`_CHINESE_MARKERS` 里本来有 `chn`，但 `_match_known` 先返回了。

修复方向：

- 命名候选改为 `*.vvd`（**排除 `_v4compatible`**）→ `*.ddi` → `*.ddb` 的 stem；`_v4compatible.vvd` 永不作为声库名。
- `_match_known` 增加中文优先：名字含 `chn/chinese/中文` 时先判 4/0，再看 `miku/luka` 等。
- `Yan_He_Mu` 这类空格分隔的名字，`_KNOWN` 需补 `yan he` 条目（现在只有 `yanhe`）。

验收：在 `C:\vc` 上重扫，`_v4compatible` 条目数为 0；洛天依 · 中文 Meng V5 / 乐正绫 V5 / 言和 V5 显示正确名与 `bs=4`。

**状态：已修复（2026-11-07，`c7ffd93` 之后）。** 重扫 `C:\vc` 的 12 条全部正确：名字取自真名 `.vvd` / `.ddi` / `.ddb`，版本标注为 V3/V4/V5，`bs` 全为 4。回归测试见 `tests/test_voicebank.py`。

### 1.1.3 多版本声库的区分

用户会同时装同一歌手的多个版本（洛天依 · 中文 Meng V3 + V5、乐正绫 V3 + V5，之后可能还有 V4）。

**现状：没有区分。**

- `Voicebank` 数据类只有 `id/name/display/bs/pc/path/source`，没有版本字段（`voicebank.py:177-191`）。
- display 来自 `_KNOWN` 或 `_infer_unknown`；`_KNOWN` 只给乐正绫做了 V3 特例（`("yuezhenglingv3", (4,1,"乐正绫 · V3"))`，`voicebank.py:155-156`），天依只有一条 `("luotianyi", (4,0,"洛天依 · 中文 Meng"))`。
- 下拉框只显示 label，没有版本列。

**数据层其实是有区分的**：compID、path、`name`、`version` 都不同。同一台机器的实测（`C:\vc`）：

| 歌手 | 版本 | compID | `.ddb` 文件名 | 当前显示 |
|---|---|---|---|---|
| 洛天依 · 中文 Meng | V3 | `BETDB8W6KWZPYEB9` | `Tianyi_CHN` | 洛天依 · 中文 Meng |
| 洛天依 · 中文 Meng | V5 | `BD79E492NWWK3DDF` | `Luo_Tianyi_Ning` | `_v4compatible`（错） |
| 乐正绫 | V3 | `BE8A88G3FWXLTEBD` | 真名 `.vvd` | 乐正绫 · V3 |
| 乐正绫 | V5 | `BMBNDB8EM5222MK3` | `Yuezheng_Ling_You` | `_v4compatible`（错） |
| 初音未来 | V4 | `BNGE7CP7EMTRSNC3` | `MIKU_V4_Chinese` | 初音未来（bs 错） |

本机版本分布：V3 三个（洛/绫/言）、V4 一个（初音中文）、V5 八个（洛 3 音色、绫 2、言 2、墨 1）。

**可用的版本信号**（按可靠度排序）：

1. **EULA 文件名**：V5 组件带 `LICENSES_V5_SHANGHAI HENIAN Luo Tianyi_CHS.txt` 这类文件，版本号直接写在文件名里（实测 8 个 V5 组件全部命中）。
2. `_v4compatible.vvd` 是否存在：V5 组件只有 237 字节的兼容标记；V3/V4 组件有真名 `<Name>.vvd`（实测 3 个 V3 + 1 个 V4 都有真名、8 个 V5 都没有）。
3. `.ddb/.ddi` 文件名：`MIKU_V4_Chinese` 自带 V4 字样；V5 的 `Luo_Tianyi_Ning/Wan/Meng` 不带版本号，无法单独判定。
4. 注册表来源：V3 键与 V4 键分别对应。
5. `.vvd` 内容里的版本字段：文件是编码后的键值对，暂不解码。

**修复方案**：

- `Voicebank` 增加 `version: str`（`V3`/`V4`/`V5`/`unknown`），按 EULA → `_v4compatible` → 文件名 → 路径的顺序推断。
- display 统一拼版本：`洛天依 · 中文 Meng · V3` / `洛天依 · 中文 Meng · V5`；同名同版本时追加 compID 后四位。
- 下拉框排序：歌手 → 版本 → compID；保留点位级 `display` 覆盖。

**V5 的额外缺口**：`_scan_registry()` 只覆盖 V4/V3 的 `DATABASE` 键（`voicebank.py:249-254`），没有 `VOCALOID5\DATABASE`。本机 V5 库放在自定义目录（`C:\vc` 下），只能靠手动加点位；装了 V5 编辑器但声库登记在注册表的机器会漏扫。

**本机实测边界**：`detect_voicebanks()` 全机只返回 1 条 fallback（注册表无 `DATABASE` 键、`_voice_db_roots()` 为空、未加自定义根）。把 `C:\vc` 加入自定义根后才能看到上述 12 条。

### 1.2 点位能力现状

| 能力 | 现状 | 证据 |
|---|---|---|
| 手动添加目录 | 已有 | `app.py:577`「＋ 添加文件夹」→ `app.py:1175 add_voicebank_folder()` |
| 持久化 | 已有，纯文本一行一个 | `%APPDATA%\VocaloidTTS\voicebank_roots.txt`，`voicebank.py:283` |
| 重新扫描 | 已有 | `app.py:583`「↻ 重扫」 |
| 查看已添加目录 | 只能看启动日志 | `app.py:337-339` 打印一次，无后续入口 |
| 移除已添加目录 | **函数存在但无调用** | `voicebank.py:332 remove_voicebank_root()`，全项目零调用 |
| 导入 / 导出点位 | 无 | 只能手改文本文件 |
| 关闭全盘探测 | 无，硬编码 | `voicebank.py:399-431` 遍历盘符 × 厂商目录 |
| 扫描深度 | 无，硬编码 8 | `voicebank.py:366` |
| 来源标注 | 字段有，UI 不显示 | `Voicebank.source`（registry/filesystem/custom/fallback），`voicebank.py:231-243` |
| 编辑 bs/pc | 只能手改 `voicebanks.json`，无 UI、无示例 | `voicebank.py:205-212`，README 仅一句带过 |

### 1.3 建议的点位配置模型

把「点位」从一行文本升级为一个 JSON 文件（`%APPDATA%\VocaloidTTS\voicebank_roots.json`），保留对旧 `.txt` 的只读兼容：

```json
{
  "schema": 1,
  "scan": {
    "full_scan": true,
    "max_depth": 8
  },
  "roots": [
    {
      "path": "C:\\vc\\洛",
      "enabled": true,
      "language": "zh",
      "bs": 4,
      "pc": 0,
      "id": "",
      "display": "洛天依 · 中文 Meng"
    },
    {
      "path": "D:\\VOCALOID\\VoiceDB",
      "enabled": true,
      "language": "auto"
    }
  ]
}
```

字段语义：

- `path`：用户单开的任意命名目录（`C:\vc\洛` 就是合法点位），不要求是 VoiceDB 结构。
- `language`：`zh` / `ja` / `en` / `auto`。决定音素表与默认 bs/pc；`auto` 时按现有关键字推断。
- `bs` / `pc` / `display`：**点位级显式覆盖，优先级最高**。`bs/pc` 用于解决「不透明文件名猜错语言」；`display` 用于给人看。
- `id`：通常**留空**——标准组件结构下目录名就是 compID，无需覆盖；仅在 A 形态（用户自建中文目录、目录名不是 compID）时才需要填真实 compID。
- `enabled`：临时禁用而不删除。
- `scan.full_scan`：关掉后只扫注册表 + roots，适合声库多、盘慢的机器。
- `scan.max_depth`：替代硬编码的 8。

**覆盖优先级**（建议明确写入文档，避免当前多点匹配的不可预期）：

```
点位级（roots[].bs/pc/id） > voicebanks.json 按 id/name > _KNOWN 表 > _infer_unknown 关键字 > 默认 1/0
```

### 1.4 改造条目

| 编号 | 条目 | 位置 | 做法 | 验证 |
|---|---|---|---|---|
| S1 | 点亮移除能力 | `voicebank.py:332`（死代码） | 点位面板加「移除」，调用已有函数；移除后立即重扫 | 加目录 → 移除 → 重扫后列表不含 |
| S2 | 点位可视化 | `app.py:560-620` 声库区 | 列出已添加点位（路径、来源、识别到的声库数、启用状态） | 手动点开能看到 `C:\vc\洛` |
| S3 | 导入 / 导出点位 | 新增 | 导出为 1.3 的 JSON；导入时合并去重、展示差异 | 导出→删配置→导入→列表一致 |
| S4 | 点位级 bs/pc/display 覆盖 | `voicebank.py:231-243` | `_make_bank()` 增加 root 参数；优先级按 1.3 | 给 `C:\vc\洛` 指定 bs=4/pc=0，生成工程在 V4 有声 |
| S5 | 关闭全盘探测开关 | `voicebank.py:445-449` | 读 `scan.full_scan`，false 时跳过 `_scan_filesystem()` | 关掉后启动不遍历盘符（可测量耗时） |
| S6 | 扫描深度可配 | `voicebank.py:366` | 从配置读 `max_depth`，默认 8 | 设 2 后深层声库不再出现 |
| S7 | 扫描缓存 | `app.py:323`、`voicebank.py:452` | 缓存键 = (注册表快照, 各根 mtime/目录数)；命中则跳过 os.walk | 二次启动耗时下降；增删 .vvd 后缓存失效 |
| S8 | 来源与失败可见 | `app.py:336` | 每行标注 `[registry] / [filesystem] / [custom] / [fallback]` | 日志能看出 `C:\vc\洛` 是 custom 来源 |
| S9 | 同名组件不吞 | `voicebank.py:374-376` | `seen` 从目录名改为全路径小写 | 两个盘的同名组件都能列出 |

### 1.5 UI 草案（不改现有布局结构）

声库卡片（`_build_options_card` 内）追加一行链接式按钮：

```
歌姬  [下拉框                        ]
      ＋ 添加文件夹   ↻ 重扫   管理点位…
```

「管理点位…」弹出一个 Toplevel：表格（路径 / 语言 / bs / pc / 来源 / 声库数 / 启用），底部「导入」「导出」「移除选中」。选择某行可内联编辑 bs/pc/display——这就是 1.1 里「中文目录名猜不出组件 ID」的用户出口。

### 1.6 验收标准

1. 添加 `C:\vc\洛`（.vvd 直接放或隔一层组件目录均可）后，重启仍能在列表看到，来源标为 custom。
2. 你这种 `C:\vc\洛\<compID>\` 结构：先确认扫出来的 `id` 与目录名一致（应自动一致），再给不透明组件的点位写 `bs=4 pc=0`，生成工程在 VOCALOID4 中能发声；把工程拷到另一台装了同版本声库的机器打开，应直接匹配、不弹「重新映射歌手」。
3. 导出点位 JSON，删掉本地配置，再导入，列表与 bs/pc 完全恢复。
4. 关闭 `full_scan` 后，启动耗时下降，且注册表声库与 roots 仍可见。
5. 移除点位后重扫，该目录下声库不再出现。

### 1.7 风险与回滚

- 风险：改为 JSON 后旧 `.txt` 用户丢配置。缓解：首次启动读旧 `.txt` 并迁移，迁移前备份为 `.txt.bak`。
- 风险：点位级 bs/pc 写错导致无声。缓解：保留「自动推断」选项，并在 UI 标明当前值来自哪个优先级。
- 回滚：配置读取失败时退回当前硬编码扫描路径，保证至少不崩。

---

## 2. 正确性与稳健性

| 编号 | 严重度 | 位置 | 现象 | 影响 | 建议 |
|---|---|---|---|---|---|
| H1 | 高 | `voicebank.py:459-463` | 找不到任何声库时，塞入一个硬编码 fallback 条目，路径指向可能存在的 `C:\Program Files (x86)\VoiceDB\LuoTianyiV4_CHN` | `_validate()` 只判断列表非空（`app.py:1126`），于是**真没声库也能生成**，产出的 VSQX 写了个不存在的声库 ID，V4 打开无声，用户不知道原因 | 删除 fallback；改为「未检测到声库」并阻止生成，或至少红色警告 |
| H2 | 高 | `app.py:1227→1240` | 先 `compose()` 再 `asksaveasfilename`；`self.export_format = fmt`（`:1234`）在取消保存前就落定 | 长文本要等算完才弹保存框；用户取消后默认格式已被悄悄改掉 | 先选路径再计算；取消时不动 `export_format` |
| H3 | 高 | `app.py:1442-1501` | `_apply_settings` 整体包在一个 `try/except: pass` 里 | 任一项失败，后面全部跳过且无日志，表现为「设置莫名没恢复」 | 逐项 try，失败写日志 |
| H4 | 高 | `tray.py`、`app.py:1440`、`app.py:1500` | 大量 `except Exception: pass` | 托盘、设置、导出失败完全静默，用户只能猜 | 至少落一份 `%LOCALAPPDATA%\VocaloidTTS\log.txt` |
| H5 | 中 | `voicebank.py:17`、`v4bridge.py:17-18` | 模块级 `import winreg` 与顶层 `ctypes.windll.user32` | 非 Windows 上连 `import vocaloidtts.app` 都失败；`tray.py:15` 有平台守卫，这两个模块没有，降级策略不一致 | 与 `tray.py` 对齐：`try: import winreg except ImportError: winreg = None`，扫描入口直接返回 `[]` |
| H6 | 高 | `app.py:1004-1012` | 解码顺序是 `("utf-8-sig", "utf-16", "gb18030")`；**无 BOM 时 `utf-16` 也会成功**，把 GBK 字节解成私有区/Hangul 码位 | 中文 Windows 上最常见的 ANSI/GBK 记事本文件导入后是乱码，解析出 0 个音节，用户只看到「生成失败：没有解析出可演唱的音节」 | 先按 BOM 判定；无 BOM 时顺序改为 `utf-8-sig → gb18030 → utf-16`，解码出可疑码位时提示 |
| H7 | 高 | `app.py:943-974` | 切换「中文文本 ↔ 拼音输入」时，若正文非空会直接清空并填入预设示例 | 用户手打的内容被下拉框一次切换静默清空，只有日志留痕 | 保留原文；确需替换时先 `askyesno` 确认 |
| H8 | 高 | `vsqx.py:182`、`exporters.py:261/389/467`、`jobfile.py:32` | 全部直接写目标路径，没有 tmp+rename；`app.py:1251-1253` 还是「先写 VSQX 再写 job」两步 | 覆盖同名工程时若中途失败（磁盘满等），用户已有工程被截断；job 写失败会弹「生成失败」，但 VSQX 其实已被覆盖 | 统一写 `*.tmp` 再 `os.replace()`；两个文件都成功才报成功 |
| H9 | 高 | `voicebank.py:371-379` | 声库名只从 `.vvd` 的 stem 取；V5 组件的唯一 `.vvd` 是 237 字节的 `_v4compatible.vvd` 兼容标记 | 真机 `C:\vc` 上 12 条里 8 条被叫成 `_v4compatible`，bs/pc 全落 `(1,0)`，用户看到的歌姬列表不可用（详见 1.1.2） | 名字候选改为 `*.vvd`（排除 `_v4compatible`）→ `*.ddi` → `*.ddb`。**已修复** |
| H10 | 高 | `voicebank.py:154-174`、`:214-219` | `_KNOWN` 的 `("miku", (1,0,...))` 先于中文标记命中 | `MIKU_V4_Chinese` 被判成日文 `bs=1`，中文库在 V4 中可能无声（1.1.2 实测） | 名字含 `chn/chinese/中文` 时先判 4/0，再看厂商关键字。**已修复** |
| H11 | 高 | `voicebank.py:177-191`、`:154-174` | `Voicebank` 无版本字段；display 只对乐正绫做了 V3 特例 | 同一天依的 V3/V4/V5 全叫「洛天依 · 中文 Meng」，下拉框无法区分；工程 compID 其实不同，但用户选错就会用错版本（详见 1.1.3） | 加 `version` 字段 + display 拼版本。**已修复** |

## 3. 体验与工程化

| 编号 | 严重度 | 位置 | 现象 | 建议 |
|---|---|---|---|---|
| M1 | 中 | `VocaloidTTS.spec:36` | `console=True`，GUI 程序靠 `ShowWindow(hwnd,0)`（`app.py:1532`）隐藏控制台 | 改 `console=False`；`--selftest` 已写文件，不依赖 stdout |
| M2 | 中 | `.github/workflows/tests.yml:23` | CI 只跑 unittest，无 lint/type 门槛 | 加 `ruff check`，后续加 `mypy --ignore-missing-imports`（限 `vocaloidtts/`） |
| M3 | 中 | `tests/` | `voicebank` / `tray` / `v4bridge` / `app` 零覆盖 | 先给纯函数加测试：`_match_known`、`_infer_unknown`、`_scan_folder`、`_make_bank`（不需要真声库） |
| M4 | 中 | `__init__.py`、README、`release_web/index.html` | 版本号三处不一致：代码 1.1.1，页面与下载包 1.1 | 版本单一来源；页面与文件名从 `__version__` 生成 |
| M5 | 中 | `release_web/` | 52KB 手写单页 + 手工放入的下载包（17MB） | `tools/build_release.py` 生成页面与 SHA-256 |
| M6 | 中 | `app.py:983` | 拖拽只收 `.txt/.text/.md`，拖 `.vsqx` 报「不支持」 | 拖入 `.vsqx` 时提示「这是工程文件，可载入回填」或直接解析回填 |
| M7 | 中 | `v4bridge.py:183` | `keybd_event` 注入全局 Ctrl+O，可能打到别的窗口 | 记录前台窗口，注入后校验是否命中目标 |
| M8 | 低 | `app.py:346` | 启动 300ms 后弹「未找到编辑器」 | 延后到首次点「载入」时再询问 |
| M9 | 中 | `prosody.py:164`、`:219`、`:340-344` | 四声末点 −11.55 半音，经 `shape_scale` 与句内 base 叠加后超过 `pbs=12` 的可表示范围，在 `int(round(st*8192/pbs))` 处被夹到 ±8192 | 按 `pbs` 归一化轮廓幅度（如 `shape_scale = min(1.0, pbs/12)`），或把四声末点收在可表示区间内 |
| M10 | 中 | `prosody.py:245`、`:484-485` | 采样 `step = max(2, int(round(5.0*tpm)))`，`_ctrl_points` 的抽稀步长又用同一个 `step`，等于「每个采样点都保留」，抽稀参数实际失效 | 让抽稀步长独立于采样步长（例如 20–24 tick），保留 `|Δv|>=60` 的拐点 |
| M11 | 中 | `tray.py:171`、`:198-221` | 只做一次 `NIM_ADD`，消息循环没有 `TaskbarCreated` 重建分支 | Explorer 重启后图标消失，而主窗口已 `withdraw()`（`app.py:1524`），用户既看不到窗口也点不到托盘，只能杀进程 | 注册 `RegisterWindowMessageW("TaskbarCreated")`，收到后重新 `NIM_ADD` |
| M12 | 中 | `exporters.py:70-73`（用于 `:183`、`:399`） | `lyric_for` 对不含汉字的歌词一律返回「啦」，而 `:359-362` 的 `write_ustx` 在同样情况下改用拼音 | 同一份拼音输入，`.svip3/.svip` 里每个音符歌词都是「啦」，`.ustx` 里却是 `ni/hao` | 三个导出器统一走一个 lyric 决策函数 |
| M13 | 中 | `.github/workflows/tests.yml:23`、`app.py:1540-1557` | CI 没调用 `main()` 里已有的 `--selftest`；打包（spec/bat）也无 CI 校验 | 加一步 `python VocaloidTTS.py --selftest` 并校验 `.ok` 文件 |

## 4. 低优先级

| 编号 | 位置 | 现象 | 建议 |
|---|---|---|---|
| L1 | `app.py:1433` | 同时存 `voicebank` 索引与 `voicebank_id` | 只存 id，索引保留读取兼容 |
| L2 | `voicebank.py:464-471` | 排序硬编码「含 luo 优先、乐正绫第二」 | 排序规则可配，或按最近使用 |
| L3 | 全项目 | 无「最近工程」入口 | 记最近 10 个路径，菜单可重开 |
| L4 | `app.py:1113-1116` | 「音域」用 `pitch_span`（含 PIT），「最高音」却只用音符锚点 `max(n.midi)` | 同一屏两个数互相矛盾（音域 15.8 半音，最高音却标 G3）；统一用 `pitch_span[1]`，或标注「音符最高」 |
| L5 | `app.py:1299-1301` | 生成失败的弹窗带完整 `traceback` | 用户把 `ni3` 打成 `ni4x`，看到的是整段堆栈 | 对 `ValueError` 只显示 `str(exc)`，堆栈写日志 |
| L6 | `prosody.py:184-199`、`pinyin.py:484` | 句调靠 `punct == 400` / `punct == 380` 精确比较毫秒数来识别问号/感叹号，两处各有一份标点停顿表 | 任一方改停顿或加标点，句尾抬高与起音增强会静默失效 | `Syllable` 带 `punct` 字段，按标点类型判断 |
| L7 | `pinyin.py:82-84` | ≥7 位的数字一律逐位读 | `12345678元`、`10000000人` 会被读成「一二三四五六七八元」，金额/规模读错 | 增加单位白名单判断，或超过 8 位才逐位 |

---

## 5. 建议的落地顺序

1. **H9 + H10**（V4 组件名与中文 miku）——真机 `C:\vc` 实测 12 条里 9 条不可用，这是现在最伤体验的识别问题，且改动集中在 `_scan_folder` 与 `_match_known`。
2. **H1**（fallback 假声库）+ **H6**（导入编码）——两个都小、都是「用户一眼可见的失败」。
3. **1.3 + S1–S4**（点位配置与覆盖）——用户点名的能力，也是多语种前置。先确认组件的 `compID` 与目录名一致（1.1.1），再只给不透明组件补 `bs/pc`。
4. **H8**（原子写）——防止覆盖丢工程，改动集中在几个写出函数。
5. **S7 + PLAN 第二轮第 1 条**（后台化 + 扫描缓存）——合并成一轮，避免 `detect_voicebanks()` 改两次。
6. **M9/M10**（四声夹死与 P 点密度）——纯参数/采样调整，可用现有 benchmark 脚本对比点数与形状。
7. **M11**（托盘重建）、**H2–H4**（生成顺序与日志）等其余条目按需。

## 6. 明确不在本轮范围

- 不改四声韵律模型本身、不做多语种音素表（那是 1.2 的另一条线）。
- 不做声库「试听/校验」功能（需要真机与目标编辑器，无法在 CI 验证）。
- 不引入新第三方依赖（点位 JSON 用标准库 `json` 即可）。

## 7. 验证边界

本机实测（`.venv`，Python 3.14.7，`c7ffd93`）：

- 声库目录四种形态：临时目录构造后调用 `scan_voicebank_folder()`，观察 `id/name/bs/pc/path/source`。其中标准组件结构（声库根下平铺 16 位 compID 目录）实测 `id` 与目录名一致；纯编码 `.vvd` 名会得到 `known=None, inferred=(1,0)`。
- 真机 `C:\vc`（2026-11-07）：`scan_voicebank_folder()` 0.98 秒返回 12 条，3 条正确、1 条 bs/pc 错、8 条被识别为 `_v4compatible`（详见 1.1.2）。
- H6：`"你好世界，今天天气真好。".encode("gb18030")`（24 字节）用 `utf-16` 解码成功，得到 `0xe3c4/0xc3ba/…` 码位，`compose()` 解析出 0 个音节。
- M9：文本「大地上的人们都在看着这场戏剧，世界就在我们面前。」（22 个音符），read 与 drama 风格各 1022 个 P 点，其中 27 个被夹到 −8192。
- M10：拼音串重复 270 次（1080 音节），P 点 58,538 个，时长 305 秒，导出 VSQX 3,835 KB（约 192 点/秒）。
- M12：`compose("ni3 hao3", input_mode="pinyin")` 的 `note.lyric == "ni"`，而 `lyric_for(note) == "啦"`。

**没有**在真实 VOCALOID4/V5、X Studio 3 或 OpenUTAU 中打开、试听、保存——这些需要在装有编辑器的机器上人工验证。第 1.6 节第 2 条（`C:\vc\洛` 指定 bs/pc 后在 V4 发声）属于必须人工确认的项。
