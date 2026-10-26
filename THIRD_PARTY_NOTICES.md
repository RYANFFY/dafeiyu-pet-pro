# 第三方素材与代码声明

本项目自身以 MIT 协议发布（见 `LICENSE`）。下面这些**素材**来自第三方，按各自协议随本项目分发，
相应声明随源码与安装包一起提供。

---

## 1. 灵动版动作素材（106 段透明 WebM 中的 24 段）

- **文件**：`sprites_anim/<动作名>/*.webp`（由下列 WebM 逐帧转码而来）
- **来源仓库**：[PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)
  （`dsh-pet/assets/webm/*.webm`，透明 VP9 动画，640×360 / 24fps / 10 秒）
- **本项目取用的动作**：东张西望、优雅女仆舞、可爱宅舞、轻快摇摆舞、超大伸懒腰、哈欠连天、
  原地打盹、打瞌睡被惊醒、被吓一跳、偷吃被抓、吃冰淇淋、撸猫、变鸽子、扑克魔术、写代码、
  玩魔方、三球抛接、踢毽子、荡秋千、照镜子、尾巴拍地、女仆礼仪、小幽灵、被拎起来
  （另有 idle / move / lion / wave 四段沿用同一来源的原始素材）
- **授权**：MIT License

```text
MIT License

Copyright (c) 2026 PC2005-cloud

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

> 素材由上游项目用 AI 视频工具生成后经人工抠像处理，本项目只做转码（WebM → WebP 帧序列）、
> 统一裁剪与缩放，未修改角色形象本身。分发时请连同本文件一起提供。
>
> 2026-10-26 起，帧序列在转码时额外经过 **Real-ESRGAN**（`xinntao/Real-ESRGAN`，
> BSD-3-Clause，模型 `realesr-animevideov3`）做 2 倍超分再缩回原尺寸，用于去压缩噪点。
> 该工具**只在构建期使用**，不随程序分发；生成的是原素材的放大-缩回版本，角色形象未变。

---

## 2. 界面图标（Lucide）

- **文件**：`assets/icons/*.svg`（设置窗口、右键菜单里的小图标，文件名前缀 `nav.` / `page.` /
  `ui.` / `act.`）
- **来源**：[lucide-icons/lucide](https://github.com/lucide-icons/lucide)（`icons/*.svg`，24×24 网格）
- **授权**：ISC License，全文见 `assets/icons/LICENSE-lucide.txt`
- **本项目做的**：只改文件名、把 `currentColor` 换成主题色渲染（`ui_console.icon_pixmap`），
  图形本身未修改。`act.*` 那批是 2026-10-26 为「逗她一下」子菜单新增的 31 个。

## 3. 其余第三方组件

PySide6（LGPLv3）、requests、winsdk 等依赖的许可见各自发行包，未修改、未静态链接。
