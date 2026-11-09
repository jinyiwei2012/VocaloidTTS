"""VSQX 4.0 writer tuned for VOCALOID4 FE + Chinese voicebanks."""
from __future__ import annotations

import os
from datetime import datetime

from .atomicio import atomic_write_text
from .exporters import lyric_for
from .prosody import Song
from .voicebank import Voicebank


def _comp_id(bank: Voicebank) -> str:
    """VOCALOID 只认 16 字符的 compID。

    长度不对时编辑器不会报错，而是静默回退到默认歌手——用户会以为选错了库。
    与其导出一个找不到声库的文件，不如在这里说清楚。
    """
    bid = (bank.id or "").strip()
    if len(bid) != 16 or not bid.isascii():
        raise ValueError(
            f"声库「{bank.display}」的 compID 不是 16 位"
            f"（实际 {len(bid)} 位：{bid!r}）。"
            "导出的 VSQX 会找不到这个声库，请到声库面板重新扫描。")
    return bid


def _cdata(text: str) -> str:
    return "<![CDATA[" + str(text).replace("]]>", "]]]]><![CDATA[>") + "]]>"


def _ctl_lines(controls: dict[str, list[tuple[int, int]]]) -> str:
    out: list[str] = []
    for cid in ("S", "P", "DYN", "BRE", "BRI", "CLE", "OPE", "GEN", "POR"):
        pts = controls.get(cid) or []
        for t, v in sorted(pts, key=lambda x: x[0]):
            if t < 0:
                continue
            v = max(-8192, min(8191, int(v))) if cid in ("P", "S") else max(0, min(127, int(v)))
            out.append(f"\t\t\t<cc><t>{int(t)}</t><v id=\"{cid}\">{v}</v></cc>\n")
    return "".join(out)


def _note_lines(song: Song) -> str:
    out: list[str] = []
    for n in song.notes:
        if n.dur <= 0:
            continue
        stress = n.syl.stress
        energy = song.options.energy
        accent = int(max(30, min(100, 38 + 42 * stress * energy)))
        opening = 127 if n.syl.tone != 5 else 112
        out.append(
            "\t\t\t<note>\n"
            f"\t\t\t\t<t>{int(n.start)}</t>\n"
            f"\t\t\t\t<dur>{int(n.dur)}</dur>\n"
            f"\t\t\t\t<n>{int(max(0, min(127, n.midi)))}</n>\n"
            f"\t\t\t\t<v>{int(max(1, min(127, n.velocity)))}</v>\n"
            f"\t\t\t\t<y>{_cdata(lyric_for(n))}</y>\n"
            f"\t\t\t\t<p>{_cdata(n.phonemes or 'a')}</p>\n"
            "\t\t\t\t<nStyle>\n"
            f"\t\t\t\t\t<v id=\"accent\">{accent}</v>\n"
            "\t\t\t\t\t<v id=\"bendDep\">8</v>\n"
            "\t\t\t\t\t<v id=\"bendLen\">0</v>\n"
            "\t\t\t\t\t<v id=\"decay\">50</v>\n"
            "\t\t\t\t\t<v id=\"fallPort\">0</v>\n"
            f"\t\t\t\t\t<v id=\"opening\">{opening}</v>\n"
            "\t\t\t\t\t<v id=\"risePort\">0</v>\n"
            "\t\t\t\t\t<v id=\"vibLen\">0</v>\n"
            "\t\t\t\t\t<v id=\"vibType\">0</v>\n"
            "\t\t\t\t</nStyle>\n"
            "\t\t\t</note>\n"
        )
    return "".join(out)


def write_vsqx(song: Song, path: str, voicebank: Voicebank,
               title: str = "VocaloidTTS 语调教", bpm: float | None = None,
               resolution: int | None = None,
               numerator: int | None = None,
               denominator: int | None = None) -> str:
    bpm = float(song.bpm if bpm is None else bpm)
    resolution = int(song.resolution if resolution is None else resolution)
    numerator = int(song.numerator if numerator is None else numerator)
    denominator = int(song.denominator if denominator is None else denominator)
    measure_ticks = max(1, int(round(resolution * 4 * numerator / denominator)))
    part_start = measure_ticks * 4
    # playTime 是 part 的播放长度，不含起点偏移；原来把 part_start 也加了进去，
    # 整段凭空长出 4 小节。起点只影响 <t>。
    play_time = max(measure_ticks, song.total_ticks + measure_ticks)
    comp_id = _comp_id(voicebank)
    seq_name = (title or "VocaloidTTS")[:120]
    comment = f"VocaloidTTS 语调教 / {voicebank.display} / {datetime.now():%Y-%m-%d %H:%M}"
    ctl = _ctl_lines(song.controls)
    notes = _note_lines(song)

    xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<vsq4 xmlns="http://www.yamaha.co.jp/vocaloid/schema/vsq4/"
      xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
      xsi:schemaLocation="http://www.yamaha.co.jp/vocaloid/schema/vsq4/ vsq4.xsd">
\t<vender>{_cdata("Yamaha corporation")}</vender>
\t<version>{_cdata("4.0.0.3")}</version>
\t<vVoiceTable>
\t\t<vVoice>
\t\t\t<bs>{int(voicebank.bs)}</bs>
\t\t\t<pc>{int(voicebank.pc)}</pc>
\t\t\t<id>{_cdata(comp_id)}</id>
\t\t\t<name>{_cdata(voicebank.name)}</name>
\t\t\t<vPrm>
\t\t\t\t<bre>0</bre>
\t\t\t\t<bri>0</bri>
\t\t\t\t<cle>0</cle>
\t\t\t\t<gen>0</gen>
\t\t\t\t<ope>0</ope>
\t\t\t</vPrm>
\t\t</vVoice>
\t</vVoiceTable>
\t<mixer>
\t\t<masterUnit>
\t\t\t<oDev>0</oDev>
\t\t\t<rLvl>0</rLvl>
\t\t\t<vol>0</vol>
\t\t</masterUnit>
\t\t<vsUnit>
\t\t\t<tNo>0</tNo>
\t\t\t<iGin>0</iGin>
\t\t\t<sLvl>-898</sLvl>
\t\t\t<sEnable>0</sEnable>
\t\t\t<m>0</m>
\t\t\t<s>0</s>
\t\t\t<pan>64</pan>
\t\t\t<vol>0</vol>
\t\t</vsUnit>
\t\t<monoUnit>
\t\t\t<iGin>0</iGin>
\t\t\t<sLvl>-898</sLvl>
\t\t\t<sEnable>0</sEnable>
\t\t\t<m>0</m>
\t\t\t<s>0</s>
\t\t\t<pan>64</pan>
\t\t\t<vol>0</vol>
\t\t</monoUnit>
\t\t<stUnit>
\t\t\t<iGin>0</iGin>
\t\t\t<m>0</m>
\t\t\t<s>0</s>
\t\t\t<vol>-129</vol>
\t\t</stUnit>
\t</mixer>
\t<masterTrack>
\t\t<seqName>{_cdata(seq_name)}</seqName>
\t\t<comment>{_cdata(comment)}</comment>
\t\t<resolution>{int(resolution)}</resolution>
\t\t<preMeasure>4</preMeasure>
\t\t<timeSig><m>0</m><nu>{int(numerator)}</nu><de>{int(denominator)}</de></timeSig>
\t\t<tempo><t>0</t><v>{int(round(bpm * 100))}</v></tempo>
\t</masterTrack>
\t<vsTrack>
\t\t<tNo>0</tNo>
\t\t<name>{_cdata("VocaloidTTS Vocal")}</name>
\t\t<comment>{_cdata("VocaloidTTS speech-like vocal")}</comment>
\t\t<vsPart>
\t\t\t<t>{part_start}</t>
\t\t\t<playTime>{play_time}</playTime>
\t\t\t<name>{_cdata("VocaloidTTS")}</name>
\t\t\t<comment>{_cdata("Generated by VocaloidTTS Studio")}</comment>
\t\t\t<sPlug>
\t\t\t\t<id>{_cdata("ACA9C502-A04B-42b5-B2EB-5CEA36D16FCE")}</id>
\t\t\t\t<name>{_cdata("VOCALOID2 Compatible Style")}</name>
\t\t\t\t<version>{_cdata("3.0.0.1")}</version>
\t\t\t</sPlug>
\t\t\t<pStyle>
\t\t\t\t<v id="accent">50</v>
\t\t\t\t<v id="bendDep">8</v>
\t\t\t\t<v id="bendLen">0</v>
\t\t\t\t<v id="decay">50</v>
\t\t\t\t<v id="fallPort">0</v>
\t\t\t\t<v id="opening">127</v>
\t\t\t\t<v id="risePort">0</v>
\t\t\t</pStyle>
\t\t\t<singer>
\t\t\t\t<t>0</t>
\t\t\t\t<bs>{int(voicebank.bs)}</bs>
\t\t\t\t<pc>{int(voicebank.pc)}</pc>
\t\t\t</singer>
{ctl}{notes}\t\t\t<plane>0</plane>
\t\t</vsPart>
\t</vsTrack>
\t<monoTrack>
\t</monoTrack>
\t<stTrack>
\t</stTrack>
\t<aux>
\t\t<id>{_cdata("AUX_VST_HOST_CHUNK_INFO")}</id>
\t\t<content>{_cdata("VlNDSwAAAAADAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=")}</content>
\t</aux>
</vsq4>
"""
    path = os.path.abspath(path)
    atomic_write_text(path, xml)
    return path
