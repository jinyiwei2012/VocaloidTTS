VocaloidTTS 1.1 · 发布动画（HTML）
==================================

打开方式
--------
双击 index.html 即可，不需要服务器、不需要联网。
建议使用 Chrome / Edge 最新版，全屏（F11）观看。

翻页
----
- 鼠标左键点击页面空白处：下一页
- 鼠标右键点击页面空白处：上一页
- 滚轮：上一页 / 下一页
- 键盘：← → / PageUp / PageDown / 空格
- 左侧竖排导航、底部圆点、PREV / NEXT 均可点击

页面结构
--------
01 封面：VocaloidTTS 1.1 / 让文字开口歌唱
02 能力：文本、五声、PIT、BPM/拍号、四种格式、桌面端
03 音高：五声与 PIT 曲线，1.10 时长 + 5ms / 40ms
04 工作流：真实 GUI 截图、格式下拉、TXT 导入、托盘驻留
05 演示：视频位 + GUI fallback + 工程统计
06 下载：Windows 构建说明 / GitHub 源码包

放入自己的演示视频
------------------
把视频命名为 demo.mp4，放到：
    assets/demo.mp4
建议 H.264 MP4，16:10 或 16:9，无声或保留原声。
页面会自动检测并播放；没有视频时显示模糊 GUI 背景和 DEMO REEL 占位。

替换截图 / 图标
---------------
    assets/gui.png   软件界面截图
    assets/icon.png  图标（透明 PNG）

源码与构建
--------
开源仓库不包含预编译 EXE 或 ZIP。页面中的按钮分别链接到 GitHub
仓库的 Windows 构建说明和 main 分支源码 ZIP；下载时需要联网。
    https://github.com/jinyiwei2012/VocaloidTTS

本地生成的 downloads/ 和 previews/ 不纳入 Git。

修改文案
--------
直接用编辑器修改 index.html；所有样式和脚本都在文件内，无外部依赖。
