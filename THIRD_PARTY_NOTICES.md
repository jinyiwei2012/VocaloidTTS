# 第三方代码声明

本项目主体采用 MIT 协议（见 [LICENSE](LICENSE)）。以下部分参考或改编自其他
MIT 项目，按 MIT 要求保留原版权与许可声明。

## LibreSVIP

- 仓库：<https://github.com/SoulMelody/LibreSVIP>
- 许可证：MIT
- 用到的部分：`vocaloidtts/formats/svp.py` 的 SVP 字段结构、时间单位换算
  （`TICK_RATE = 1,470,000`，即 1 tick = 1,470,000 blick、480 tick = 1 个四分音符）
  和版本号约定，参考自 `libresvip/plugins/svp/` 下的 `model.py`、
  `constants.py`、`synthv_generator.py`、`options.py`。

本项目只移植了**写**方向，并做了简化：单轨、不生成 `groups`/`library` 引用、
`phonemes` 留空交给编辑器自动生成、只写 `pitchDelta` 一条曲线。没有直接复制
LibreSVIP 的运行时代码，也没有引入它的 pydantic 模型和插件框架。

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
