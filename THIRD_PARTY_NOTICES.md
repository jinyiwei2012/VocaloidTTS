# 第三方代码声明

本项目主体采用 MIT 协议（见 [LICENSE](LICENSE)）。以下部分参考或改编自其他
MIT 项目，按 MIT 要求保留原版权与许可声明。

## LibreSVIP

- 仓库：<https://github.com/SoulMelody/LibreSVIP>
- 许可证：MIT
- 用到的部分：下面这些导出格式的字段结构、时间单位换算和版本号约定，参考自
  `libresvip/plugins/` 下对应的插件目录。**只参考了结构，没有复制运行时代码**，
  也没有引入它的 pydantic 模型、yapsy 插件框架和本地化层。

| 本项目的模块 | 参考的 LibreSVIP 插件 | 具体借鉴了什么 |
|---|---|---|
| `formats/svp.py` | `plugins/svp/` | 字段结构、`TICK_RATE = 1,470,000`（480 tick = 1 个四分音符 = 705,600,000 blick）、版本号约定 |
| `formats/s5p.py` | `plugins/s5p/` | `version: 7`、meter/tempo/tracks 结构、blick 换算、`dbDefaults` 默认值 |
| `formats/acep.py` | `plugins/acep/` | zstd + base64 容器（`version: 1000` 表示未加密）、`version: 9` 的工程结构、音符/patter 字段 |
| `formats/vpr.py` | `plugins/vpr/` | zip 内 `Project/sequence.json` 的结构、控制器名（含 gender→`character`）、BPM 的 1/100 倍率 |
| `formats/__init__.py` | `plugins/` 的组织方式 | 「每个格式一个模块 + 元数据自带」的注册表思路 |

各格式都只移植了**写**方向，并按本项目需要做了简化（单轨、不写参数曲线或只写
少数几条、不生成声库/分组引用等），具体简化写在每个模块的 docstring 里。

原项目版权声明：

> Copyright (c) SoulMelody and contributors

完整 MIT 许可文本见
<https://github.com/SoulMelody/LibreSVIP/blob/main/LICENSE>。

## pypinyin

- 仓库：<https://github.com/mozillazg/python-pinyin>
- 许可证：MIT
- 用途：汉字转拼音与词组分词。

## 其他参考（未复制代码）

- VSQX 结构参考 VOCALOID4 自带 `vsq4.xsd`、Job Plugin SDK 与
  [3c1u/vsqx](https://github.com/3c1u/vsqx) 的测试工程。
- PIT/PBS 的 VSQX 表示参考 [EDITUNE](https://js-bach.org/vsqx/editune.html)（小川P）。
- Synthesizer V 的文件结构另有
  [SVP 工程文件格式全解析](http://je1ght.top/posts/svp-project-file-format/)
  与 Dreamtonics 官方脚本手册可对照。
