# AGENTS.md · 大肥鱼桌宠

这份文件是**跨对话**的项目约定。本仓库是 Codex 桌面应用的本地项目根目录，
新开对话默认从这里起步，所以需要长期保留的规则都写在这里，
不要依赖某个超长对话的历史。

## 这是什么

Windows 桌面宠物（Python + PySide6）。大肥鱼 / 小鲸鱼形象常驻桌面，
显示 DeepSeek 余额、天气、当前播放的歌曲与歌词，带右键菜单、音效、开机自启、
可换形象，可打包成 exe 与中文安装包发布。

## 常用命令

```bash
# 运行（开发）
.venv\Scripts\pythonw.exe 桌宠.py      # 或直接双击 启动桌宠.bat

# 依赖（需要 Python 3.11+）
pip install -r requirements.txt

# 打包独立 exe —— 用 spec，不要手写参数（spec 里做了 ICU 过滤）
pyinstaller --noconfirm --clean 桌宠.spec

# 打包中文安装包（Inno Setup 6）
"F:\Codex\tools\innosetup\ISCC.exe" "/DMyAppVersion=1.0.x" installer.iss
```

产物在 `dist/`，不提交。发版流程见 `README.md` 的「改完代码怎么发版」：
版本号按现有最高版本 +1，保持连续、不跳号；内容没变不重发。

## 关键文件

| 文件 | 作用 |
| --- | --- |
| `桌宠.py` | 主程序，单文件，体量很大（27 万字符级别），改前先定位到具体类/方法 |
| `pet_ext/` | 新功能都放这里（`notify.py` 任务通知、`anim.py` 帧动画），只通过 `setup(pet)` 挂载，不改 `桌宠.py` 原有方法体；加载失败只打一行日志 |
| `config.json` | 运行时配置，**已被 .gitignore 忽略**，不要提交、不要当源码改 |
| `sprites/` `assets/` | 形象贴图与音效素材 |
| `sprites_anim/` | 灵动版形象的帧序列（35 段）+ `manifest.json`，由 `_build/` 的脚本转出来，**不在 git 里** |
| `桌宠.spec` `installer.iss` | PyInstaller / Inno Setup 打包脚本 |
| `CHANGELOG.md` | 每个版本改了什么 + 怎么验证的（含实测命令与截图路径） |
| `TODO.md` | 待办，以及「已经试过、没能解决的方案」 |
| `README.md` | 面向用户与维护者的说明 |

## 这个项目的习惯（请沿用）

- 交流、注释、提交信息都用中文。commit 风格：`feat: …` / `fix: …` / `perf: …` + 中文说明。
- 每次改动同步更新 `CHANGELOG.md`（写清改了什么、怎么验证）和 `TODO.md`。
- **验证方式要落到实测**：离屏脚本用 `F:\Codex\work\test_*.py`，真机探测用 `probe_*.py`，
  截图存 `shot_*.png` —— 这些放 `F:\Codex\work`，不要塞进仓库。
- 改动右键菜单（尤其新增二级菜单）后，必须用真鼠标点一遍子菜单。
- `dist/` `build/` `.venv/` `__pycache__/` 以及运行时文件（`config.json`、`usage.json`、
  `lyrics_cache.json`、`menu-debug.log`）都不提交。
- 用户的反馈常带截图和具体时间点，照原话记进 TODO / CHANGELOG，别改写成自己的说法。

### 改完怎么交给主人验收（2026-10-24 主人定的规矩）

主人不用 Codex，也不该为了验一个功能跑去开别的服务。每次交付固定讲清三件事：

1. **要他亲手测的**：说到点哪个菜单、按哪个脚本、该看到什么、什么算通过。
   别写"请自行验证"，也别让他猜怎么触发。
2. **我拿不准的**：哪些只喂过造出来的数据、哪些只有离屏数字、哪些是素材本身的限制，
   一条条摊开说，别用"应该没问题"糊过去。
3. **一个能双击就跑的脚本**：`手动测试.bat`（中文菜单，选 1~6，也能 `手动测试.bat 4` 直接跑）。
   菜单文案改 `_test/menu.py`，**别去改 .bat 里的中文**（见「已知的坑」）。
   以后每加一个可测的面就往 `ITEMS` 里加一项，别让主人记命令。

本轮的清单在 `本次验收清单.md`。脚本都在 `_test/`：

| 脚本 | 干什么 |
| --- | --- |
| `_test/menu.py` | 中文菜单本体（`手动测试.bat` 只是包一层找 python），要改文案改这里 |
| `preview_clips.py wide\|all\|<clip>` | 连播动作，看裁剪有没有被切、窗口怎么伸缩 |
| `preview_walk.py --live` | 贴屏幕右边演一遍"走过去 → 玩水枪 → 走回来"（菜单第 8 项）；不带 `--live` 是离屏出图 |
| `preview_notify.py [state] [--hidden] [--check]` | 造 TaskEvent 走正式回调，验气泡 / 托盘兜底 / 提示音 |
| `test_notify.py` `test_anim.py` `test_clip_size.py` `test_clip_window.py` `test_integration.py` `test_console_switch.py` | 离线自检，`手动测试.bat 6` 一把跑完 |
| `measure_drag.py [--steps N]` | 拖大小滑块每步耗时 / 重绘间隔 / 帧高度滞后（**真机平台，别设 offscreen**） |
| `measure_resize.py` | `setFixedSize` / `resize` / `setGeometry` / `resize+move` 的真实开销对照 |
| `repro_flash.py` | 挂钩子断言"大步改尺寸必须带 refresh"（闪回，确定性） |
| `repro_flash_screen.py` | 闪回的屏幕实拍版：截 DWM 合成后的桌面，找"先左跳再弹回"的 V 形 |
| `repro_paint_trace.py` | 抓"切动作闪弹"：hook paintEvent 逐帧算鱼身体在屏幕上的位置（**必须在建实例前 patch 类**） |
| `repro_switch_flash.py` | 闪弹的屏幕实拍版：30fps 实拍，量合成器真正显示出来的位置 |
| `repro_drag_walk.py` | 合成鼠标事件模拟"贴边做动作时拖它"，断言按下不瞬移 / 走位收干净 / 跟手 / 松手收尾 |
| `repro_shift_screen.py` | 60fps 实拍找"单帧横向平移"（GDI BitBlt + 一维列剖面互相关）；**别用 PIL ImageGrab，32fps 抓不到** |
| `measure_clip_center.py` | 逐段播动作，量鱼身屏幕位置差（判断要不要 dx 补偿）。只取脚部那一条，别用整体包围盒 |
| `monitor_pet.py` | **持续监控**：`PrintWindow` 抓桌宠窗口自己的内容（免疫背景/遮挡），每帧量动画中心点 + 窗口矩形，异常存前后 30 帧，F9 手动抓 |
| `_fastgrab.py` | ctypes GDI BitBlt 快速抓屏（1~2ms/次），给上面几个脚本共用 |
| `_probe_hit.py` | 探"半透明窗口 alpha=0 的区域挡不挡鼠标"（结论：不挡） |

`repro_*` 是"复现问题"用的，和上面 `test_*` 的正向断言是两回事；**都要真平台跑**
（offscreen 拿不到真实窗口，也测不到合成器的取帧行为）。

## 已知的坑（别重复踩）

- **二/三级子菜单**：Qt 弹出菜单拿不到鼠标捕获，悬停兜底、事件转发、延时关闭、
  原生消息层拦截、改成浮窗/对话框等方案都试过且无效。v1.0.10 起改为
  自己实现菜单窗口 + 自己持有捕获。细节在 `TODO.md` 末尾。
- **打包报 `DLL load failed while importing QtCore`**：PyInstaller 把本机其它运行时的
  ICU 打进了包。用 `桌宠.spec`（已加过滤）而不是手写命令行。
- **歌词**：网易云不报时间轴时按播放器时间对齐；切歌前不猜进度、失败不清空缓存。
- **`make_zip.py` 里的 `BASE` / `OUT` 还是旧机器路径（`D:\图图\大肥鱼\…`），
  在当前位置要用得先改这两个常量。
- **`.bat` 里不要写中文**（2026-10-24 又踩一次）：cmd 按系统代码页（中文 Windows 是 GBK）
  解析 .bat 的字节，文件存成 UTF-8 就会乱码；更糟的是多字节字符会把命令解析坏 ——
  现象是 `'""' 不是内部或外部命令`、`set "PY=…"` 没生效、菜单闪一下就没了。
  `chcp 65001` 只在纯 echo 的场合靠得住，一旦掺 `if` / `set` / 标签就说不准。
  所以：**bat 只留 ASCII**，中文菜单和调度放 `_test/menu.py`（用 Python 打印，
  控制台走 Unicode API，怎么存都不会乱）。文件名可以是中文，内容不行。
- **`.bat` 必须是 CRLF 换行**：LF 的 bat 在 cmd 里同样会 `set` / `goto` 解析错乱。
- **量窗口尺寸操作别用 `setFixedSize` 锁死后测 `resize`**（2026-10-24 踩过）：
  `setFixedSize` 会把 min=max 设死，之后再 `resize()` 会被 clamp 回去 —— 量出来
  0.14ms 的"极快"其实是空操作，据此写过"resize 比 setFixedSize 快 20 倍"的错结论。
  正确姿势：每次测量前显式 `setMinimumSize(1,1)` / `setMaximumSize(...)`，
  并**回读 `width()` 确认尺寸真的变了**（`_test/measure_resize.py` 已这么写）。
  真实数据（透明无边框窗口，真 Windows 平台）：`setFixedSize` 4.1~5.0ms、
  `resize` 4.6ms、**`setGeometry`（尺寸+位置一次）4.2ms**、`resize` 再 `move` 5.8~6.4ms、
  单独 `move` 1.7ms。所以"改尺寸顺带挪位置"一定合进一次 `setGeometry`。
- **`snap_into_screen()` 无条件 `move` 是隐形开销**：拖滑块时每步都白付 1.7ms。
  已改成只有真越界才动。
- **闪回/抽搐 = "窗口改宽"这件事本身**（2026-10-25 第十一轮，推翻第六轮的结论）：
  只要窗口宽度变了、而合成器取到的是旧画面，鱼就整体偏 **Δw/2** 一帧再弹回。
  `refresh=True` 只能减少，压不死 —— 实测 Δw=13 的一步照闪 9px。
  ⭐ **所以换动作时尺寸必须一帧改到位，不要分成十来步滑**：那段 200ms 缓动
  视觉上本来就是空的（鱼的绘制宽度只跟动作画布有关，窗口变宽是透明的），
  分步只会把 1 次闪烁机会放大成十来次。现在 `_apply_window_size` 里
  `(w,h) != 当前` 就直接 `_set_win_size(..., refresh=True)` 并 return。
  实拍检测 `_test/repro_shift_screen.py`（GDI BitBlt 64fps + 一维列剖面互相关，
  见下面那条"采样率"的坑）；挂钩子版 `_test/repro_flash.py` 只查"有没有带 refresh"，
  查不出这个。
- **别用 PIL `ImageGrab` 抓 16ms 级的事件**（2026-10-25 踩到）：一次约 30ms（32fps），
  采样比事件慢，跑十遍都是"没复现"。要抓单帧跳变用 `_test/_fastgrab.py`
  （ctypes + `BitBlt`，1~2ms/次，能到 60fps 以上）。
- **半透明窗口的 alpha=0 区域不挡鼠标**（2026-10-25 实测，`_test/_probe_hit.py`）：
  `WindowFromPoint` 在透明处返回的是下面那个窗口。所以"窗口比鱼宽"本身不会挡住点击，
  别再拿这个当理由拒绝固定宽度（真正拒绝它的理由是贴边观感，见 CHANGELOG 第十一轮）。
- ⭐ **窗口宽度固定之后，凡"按窗口宽贴边"的地方都要改成按鱼宽**（2026-10-25 第十二轮补）：
  一共四处，少改一处就瞬移 —— `_settle()` / `snap_into_screen()` /
  `_anim_clip_changed` 里的夹屏 / `_anim_walk_to_clip` 的目标点，全都要带
  `_content_margin()`（或 `_canvas_to_content_w()`）。
  踩到的正是**走位起步那一处**：它按"窗口贴边"又夹了一次，把 `_settle` 故意探出屏幕的
  130px 透明留白拽回来 → 该走 109px 变成只剩 20px → `crab` 只放 5 帧就"到位"，
  就是主人报的**「走路动画只放几帧」**。检测 `_test/test_edge_walk.py`（贴边/位移/帧推进）。
- **`_anim_home` 记的是窗口中心，不是鱼中心**：算目标点用 `anchor_cx - ww / 2`，
  别用 `anchor_cx - tw / 2`（鱼宽）。窗口固定成最宽画布后两者差一个留白，
  目标点会整体偏掉，而且 `abs(dest_cx - cur_cx) < WALK_GAP` 会误判成"不用走"。
- ⭐ **夹屏算出来的坐标必须取整再比**（2026-10-25 第十三轮）：
  留白 `_content_margin()` 是浮点（`crab` 鱼宽 183 → 121.5），夹出来的 `mx` 是 `495.5`，
  而 `self.x()` 是整数 495。`495.5 == 495` 永远不成立 → tick 里那条
  "到边了算到位"（`mx == self.x()`）**从来没触发过**，于是每 tick 都 `move(495.5)`
  被 Qt 截成 495，窗口一动不动硬等 2 秒卡住保护 —— 主人报的
  **「往回跑时顶着屏幕边缘原地踏步」**。一律 `mx = int(round(...))`。
- ⭐ **循环动画判"播完没"不能用已解帧数**（2026-10-25 第十三轮）：
  `_advance` 里 `raw`（该播第几帧）是无限增长的，`n = len(frames)` 是**已解码**数量。
  原来 `raw >= n` 就"停在最后一帧"，于是每段循环动作**播完一圈就卡住**
  （`idle` 241 帧 ≈ 10 秒，点别的动作重置时间轴才好）—— 主人报的「动画卡住了一次」。
  必须用 `total = len(self._files_for(clip))` 取模，只有 `i >= n`（那帧还没解到）才停。
- **`AnimExtension._sync()` 每 200ms 会按 `target` 把 clip 顶成 `move`/`idle`**：
  散步/跟随的「螃蟹走路」得让它先看 `_amb_phase`（非空就撒手），
  否则转身只播一瞬间就被顶回正面。
- ⭐ **灵动版不吃 `dir` / `facing`**（2026-10-25 第十五轮）：`_set_dir` 只影响三视图的
  `_sprite_key()`，灵动版是画帧动画、根本不看 —— 所以「原地待着跟鼠标转」那个开关
  对灵动版**一直是空操作**（主人报"开关没用"）。
  现在用**待机素材里本来就有**的"向左看 / 向右看"两段：`idle_left`（idle 90~115 帧）、
  `idle_right`（idle 150~172 帧），各切一个小循环（在 `LOOP_CLIPS` 里，不进动作菜单）。
  ⚠️ 方向别按包围盒判断：**包围盒往右偏的时候眼睛是看左的**（头发甩到另一侧）。
  还要接两处：`_sync()` 看到 `_still_side` 要撒手（不然 200ms 后顶回 idle）；
  状态没变但 clip 被别的动作顶掉时要重新播。检测 `_test/test_still_face.py`（菜单 14）。
  （第一版拿 `crab_in` 定格当侧身，主人说"像是卡住了"，已弃用。）
- **散步/跟随的走路动画是独立一套 `_amb_*`**（`_amb_walk_start/stop/after_once/sync_walk`），
  和"去那儿做动作"的 `_walk_phase` 三分段互不干扰。转身那两段要 `step = 0`
  （窗口站住），不拦就是"滑着转圈"（实测 150px 里滑掉 140px）。
  检测 `_test/test_amb_walk.py`（菜单第 10 项）。
- ⭐ **到位就当场转身，中间别加等待**（2026-10-25 再补，主人报「到了还在原地跑」）：
  `crab` 是循环动画，只要 clip 还是它、画面就在原地播。之前加过 0.3 秒延迟
  （想减少转身次数），那 0.3 秒就是"原地跑"。现在 `target` 变 None 那一帧立刻
  `_amb_walk_stop()`；`WALK_TURN_RATE` 提到 2.2（一段 0.5 秒）。
  转身期间可以被打断（鼠标真动了），但门槛 **8px** —— 死区只有 4px，
  光标抖动会让 target 一帧有一帧没有，转身被反复打断就**永远转不完**（实测）。
- **历史（已被上面那条取代，留着看思路）**：试过"到位后等 0.3~0.5 秒再转身"
  （想减少转身次数），结果那 0.3 秒里 `crab` 还在原地播 —— 主人报「到了还在原地跑」。
  那版还踩了个坑：`_amb_tick_stop()` 放 tick 末尾永远走不到（wander 的"休息"分支和
  still 分支都会提前 return），必须放 tick 开头。
- **`_amb_phase` 停在 in/out 会把窗口冻住**（tick 里那两段 `step = 0`）：
  播完回调万一丢了就是**永久不动**（最像"功能失效"）。两道兜底 ——
  `_amb_sync_walk` 里超 1.5 秒强制重置、tick 里 `step = 0` 只维持 1.2 秒。
  检测 `_test/stress_follow.py`（菜单 13：不停挪光标 25 秒，判「有目标却不动」）。
- ⭐ **多屏：夹屏别用 `self.screen()`**（2026-10-25 第十四轮）：
  `self.screen()` 是**桌宠自己所在那块屏**，光标一到副屏，窗口立刻被夹回原屏边界 ——
  表现为"顶着屏幕边缘原地踏步"（和浮点那个 bug 长得一样，根因不同）。
  跟随时走路/夹屏要用 `_move_geo()` = **所有屏幕的并集**（`_all_screens_geo()`）。
  ⚠️ 不能用"光标那块屏"：窗口一上来就被 `max(geo.left()...)` 拽进目标屏，瞬移一百多像素。
  涉及三处：tick 移动、`snap_into_screen()`、`_anim_clip_changed()`。
- **跟随模式下 `_settle()` 直接跳过**（不贴边吸附）：不然光标在副屏、它被吸回原屏边。
  散步/去那儿做动作/松手吸附/拖大小都还是按自己那块屏，行为不变。
- **设置窗口（`self._console`）不算 `ui_open`**：`ui_open` 只管右键菜单和对话框。
  所以"设置窗口开着别跟随"要单独判 `_console_open()`（可见且没最小化）。
  检测 `_test/test_multiscreen_follow.py`（菜单第 12 项，假两块屏 + 修复前对照）。
- **各动作的鱼身位置已经是对齐的**（2026-10-25 实测，`_test/measure_clip_center.py`）：
  逐段播一遍量脚部中心，最大偏差 10.5px（`snack`），其余 ±5px 内。
  **别再给切动作加 dx 补偿** —— 第十轮加过，副作用是"水枪画面整体左移 47px"被回退。
  ⚠️ 量的时候只取脚部那一条：整体包围盒会被泡泡/水枪这些道具污染
  （「吐泡泡」整体中心比待机偏 177px，但鱼本身没动）。
- **拖动时别让窗口重排**（2026-10-24 第六轮）：`_anim_clip_changed` 见 `dragging` 就 return；
  取消走位时"家=当前位置 + 不夹屏"；松手后补一次重排。检测脚本 `_test/repro_drag_walk.py`。
- **PySide6 给已实例化的类重赋虚方法不生效**（2026-10-24 第七轮踩到）：
  `type(w).paintEvent = hook` 之后 `type(w).paintEvent is hook` 为 True，但 C++ 虚调用
  **不走新函数**（600ms 计数 0）。要 hook `paintEvent` / `moveEvent` 这类虚方法，
  必须**在创建实例之前** patch 类。普通 Python 方法（如 `_set_win_size`）随时可 hook。
  之前几轮依赖 paint 钩子的"脏帧检测"因此全是假阴性（结论碰巧没被带歪）。
- ⭐ **素材糊是源里就有的，别怪转码**（2026-10-25 第二十二轮）：dsh-pet 的源视频只有
  **640×360 / 约 400kbps / VP9 yuv420p**，而且 alpha 精度很低（背景是 alpha=1 不是 0，
  会在轮廓外留一层灰膜）。量过：现在的输出帧拉普拉斯 47.4，比原生裁框还高一点 ——
  也就是说旧管线没有额外弄糊。
  重做用 `_build/regen_anim_hd.py`（Real-ESRGAN `realesr-animevideov3` ×2 超分，
  再 LANCZOS 缩回 384 = 超采样）：**锐度 +30%（47.4 → 61.6）**，逐帧稳定性 1.10x
  （没有"沸腾"），体积反而小 12%（webp q88）。
  四个必须知道的：
  1. **`-g 0`（RTX 4060）会 `vkQueueSubmit failed -4`、输出全黑，必须 `-g 1`（核显）**。
  2. **webp `method=6` 每帧 1567ms、`method=4` 只要 29ms**，体积只差 1KB。用 4。
  3. **别"先喂色再超分"**：把不透明区颜色往外铺满再丢给模型，模型会照着那圈糊色
     重新画轮廓，结果比原来还软（实测）。也**别在超分后做"边缘去污染"**：轮廓那圈会被
     内圈的深色描边填满，看着像加粗了一圈黑边。Real-ESRGAN 自己已经把边收干净了。
  4. 输出要 **alpha<6 归零**：源里背景 alpha=1，不归零就是一层灰膜（半透明像素
     56.7% → 4.8%）。
- **切动作闪弹 ≠ 闪回**（2026-10-24 第七轮）：闪回是"改尺寸没当帧重画"（上一条），
  闪弹是"走位没收完就切动作"——上一趟的 `_walk_task` 残留，`_anim_clip_changed` 按
  **旧家** `_geom_glide`，窗口从走位半路 200ms 滑回旧家（实测 110px）。
  修法见「灵动版动作库」第七轮条目。检测 `_test/repro_paint_trace.py`（逐帧鱼身位置）
  与 `_test/repro_switch_flash.py`（屏幕实拍，量合成器实际显示的位置），两个都过才算不闪。
- ⭐ **原地转头别用"固定起点表"**（2026-10-25 第二十一轮，主人报「鼠标从左到右会跳帧」）：
  旧版 `STILL_TURN_CHAIN` 把每条过渡的起点写死（正面→看左从 70 起、正面→看右从 130 起），
  待机停在哪一帧都得先跳过去。实测帧差：190→70 **29.6**、117→130 **27.1**，
  而相邻帧只有 0.7~7.3 —— 就是那一下"跳帧"。现在 `_still_plan()` 按当前帧现场算：
  能顺着走就顺着走（帧差 0），绕不开才跳，跳就跳**实测差最小**的那一帧。
  ⚠️ 三个反直觉的数字，别再试：
  1. **idle 是 24fps / 241 帧 ≈ 10 秒一圈**，"绕过去"要 5~9 秒（190→115 是 166 帧 = 6.9 秒），
     所以"绕一圈"这条路根本不存在，必须允许跳。
  2. **正面段之间跳一下也不便宜**：1→20 差 13.3、116→130 差 28.2、173→200 差 28.2。
     "都是正面所以看不出来"是错的。
  3. **镜像救不了**：素材不对称，`mirror(172)` 和真正的 115 差 29.6（镜像自检 48.9），
     把"看右"镜像过来当"看左"用等于另一次硬跳。
  打分脚本 `_test/score_still_plan.py`（菜单 18，241 个起点逐个算接缝帧差，2 秒出结果）；
  运行时复现 `_test/repro_lr_scan.py`（菜单 19，量每次换段跳了几帧）。
  现状：平均接缝帧差 14.7 → 6.3，最大 37.9 → 23.6，>20 的次数 278 → 32。
  剩下 20 左右的跳都发生在"当前帧在看右那半边、却要转去看左"——素材里看左只有一段，
  物理上绕不开，已选全表最省的落点。
  ⚠️ **这些绝对数会随素材变**：2026-10-26 换成超分版素材后，同样的帧距像素差整体变大
  （最大 23.6 → 26.4、>20 的次数 32 → 124），但"新规则 / 旧规则"的比值没变
  （平均 0.43、最大 0.64）。**看比值，别看绝对值。**
- ⭐ **"看左"的来回播区间是 94~110，而且判据要用"皮肤重心"**（2026-10-26 第二十三轮，
  主人连着退回三次：「摆得大很多」→「还偏大一点」→「还是向左看偏大，眼睛的幅度」）。
  1. `idle` 里 90~115 名义上是"看左"，但**整段都在持续转头**（不是站定），
     111~115 更是已经在往回走；而 150~172 是真的站定。所以左段压不到"完全不动"，
     只能收窄到最平的那一段 —— 最终 **94~110**（17 帧，一个来回 0.71 秒）。
  2. **判据别选错**（这是连退三次的真正原因）：
     - 整只鱼重心漂移 → 90~110 时已经 1.00x，主人还说大；
     - 上半身亮部重心 → 91~110 时 1.06x，主人还说大（亮部混着蕾丝和皮肤高光，不敏感）；
     - **皮肤（暖亮区域）重心相对身体的位置 → 90~115 是 1.47x、91~110 是 0.61x、
       94~110 是 0.48x** —— 只有它和肉眼对得上。
  3. 脚本 `_test/check_still_sway.py`（菜单 21）五个指标一起量，判据以
     **皮肤重心 ≤1.10（不许比看右大）** 为主。脚本里带四行历史对照。
  4. ⚠️ 跑这个脚本时**别同时跑别的**：机器一忙，`menu 16` 的帧率会从 22.7 掉到 17、
     还会把采样空档误报成"大跳 4 次"（实测踩过，白查半小时）。
  5. ⚠️ **"把看右镜像过来当看左"不行**（主人 2026-10-26 提过，直觉上最省事）：
     角色不对称 —— 围裙上的鲸鱼和字母、头饰蕾丝/蝴蝶结、头发分缝都在特定一侧。
     实测任意一帧镜像后差 **31~48**（相邻帧才 1~8），围裙字母会变成镜像字。
     而且"切换镜像"那一下本身就是一次 30+ 的跳变。对比图 `_test/_video/mirror_compare.png`。

## 发版：主人说「推送 / 发布 / 发版」时怎么做

主人 2026-09-13 定的规矩（原话）：
> 之后如果我说推送等词，就把绿色安装版发送到 github 里，微信 zip 包留在之前一直放的文件夹里，
> 在回复里给我和以前一样写出来就可以，桌面命令可能因为项目创建原因好像不管用了

所以：**主人一说「推送」就由我（Codex）直接跑发布脚本**，别指望桌面上那个 `.bat`
（它是好的，但"没有代码改动"时整段跳过、连 Release 都不发，看起来就像"不管用"）。

1. 先看有没有代码改动（`git status --short`）：
   - **有改动** → 跑 `publish-pet.ps1`（自动：提交 → 推送 → 打包 → 发新版 Release）
   - **没改动、但当前版本的 Release 还没发** → 加 `-Force` 跑，否则等于什么都没做
   - **没改动、Release 也发过了** → 直接回主人「内容没变，不重发」，别硬发新版
2. 命令（脚本在 `F:\Codex\work\publish-pet.ps1`，**不在仓库里**，所以改它不用发版）：
   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File F:\Codex\work\publish-pet.ps1 `
     -Message "feat: 中文说明" [-Force]
   ```
3. **Release 里只放** `dafeiyu-pet-setup.exe`（Windows 中文安装包，能选安装位置）——
   主人 2026-09-13 要求「GitHub 里 exe 文件就给 windows 安装版就可以了，有这个版本的就只留这个，
   没有的不用变更」：**绿色版不再上传**（v1.0.12 及更早本来就只有绿色版，保持原样没动）；
   真没编出安装包时才兜底发绿色版。
4. **微信 zip 不上传**，只做在本地（主人要求「在本地给我」）：
   `F:\Codex\2026-09-11\deepseek-harness-dsh-ai-harness-deepseek\outputs\大肥鱼桌宠-vX.Y.Z-微信版.zip`
   - **zip 里就两样**（主人 2026-09-13 要求：「就是把 windows 安装版和教程打包就可以，其他不需要」；
     后来又批注「对换回安装版，之后的也都是只保留安装版」）：
     `大肥鱼桌宠/大肥鱼桌宠-安装版-vX.Y.Z.exe`（Windows 安装版）+ `大肥鱼桌宠/使用说明.txt`（教程，
     按"先装再用"写）。**不放绿色版、不放源码、不放别的东西**（`publish-pet.ps1` 里 `New-WechatZip` 已经这么做了）。
   - **回复里要给能直接点的链接**（主人 2026-09-13 要求「之后都给我一个可以直接点的链接」）：
     写成 Markdown 链接，别用 `代码块`/纯文本把路径括起来：
     `[大肥鱼桌宠-vX.Y.Z-微信版.zip](F:/Codex/2026-09-11/deepseek-harness-dsh-ai-harness-deepseek/outputs/大肥鱼桌宠-vX.Y.Z-微信版.zip)`
   - 只想补做 zip：`publish-pet.ps1 -ZipOnly -Version X.Y.Z`
5. 版本号规则（2026-09-14 主人改的，原话：
   > 「之后迭代就每20一版吧，比如1.2.0的上一版是1.1.19」
   ）：**补丁位每 20 个一进位** —— 一个次版本号带 20 个补丁版，
   `x.y.0` → `x.y.1` → … → `x.y.19`，下一版就是 `x.(y+1).0`。
   也就是**没有再发 `x.y.20` 这回事**，`.19` 用完直接进位。
   现有最高版本接上这条也不会跳号：v1.0.19 已经发过，所以下一版是 **v1.1.0**。
   脚本（`publish-pet.ps1`）如果还在按"最高版本 +1"算，得先改成这个规则。
   保持连续、不跳号，内容没变不重发。
   另：界面里显示的版本号在 `ui_console.py` 的 `APP_VERSION`，
   发版时**要跟版本号一起改**（关于页和侧边栏底部都读它）。
6. 打包用 `桌宠.spec`（别手写 PyInstaller 参数），安装包用
   `F:\Codex\tools\innosetup\ISCC.exe /DMyAppVersion=X.Y.Z installer.iss`。
7. **Release 说明怎么写**（主人 2026-09-13：「现在就改，减少不必要的文案，1.0.15 的就很好」）：
   顺序是 **标题 → `## 这一版改了什么`（用户视角的 `###` 小节）→ `## 下载` → 最后一句
   「每一项的实测数据都写在仓库的 CHANGELOG.md 里。」**，像 v1.0.15 那样。
   脚本生成说明时会**自动丢掉**：以 `- 实测` / `- 回归` 开头的行（连续行）、
   以及 `### 维护者相关（…）` 那一节之后的全部内容。
  所以 **CHANGELOG 每一节按这个顺序写**：用户能看懂的（放前面）→ `- 实测…` / `- 回归…` →
  `### 维护者相关（发版 / 仓库，不写进 Release 说明）`。别把脚本路径、截图名堆在用户部分里。
  另外（主人 2026-09-13 追加：「我 2026-09-13 提的需求：> 「…」这种话就删掉就好了」）：
  **发出去的说明里别写"某某说的 / 需求原话"这类引子**（`主人 … 反馈：`、`我 … 提的需求：`、
  后面跟一段引用，都不要），直接写**改了什么** —— 说明是以主人自己的口吻发出去的，不是转述。
  （内部记录照旧：主人的原话留在 `TODO.md` 里，那是不发出去的。）

## 对话与分支

- 一个任务开一个新对话，做完归档；用项目而不是用超长对话来保存上下文。
- 不要靠「分支」把整段历史带进新对话 —— 分支会继承父对话的全部历史，
  历史越大越容易撞上接口的请求体上限（413）。

---

## 待做清单（2026-10-23 定，尚未开工）

一句话目标：**桌宠从"会说话的挂件"变成"桌面的任务入口"** ——
能聊天（走 API）、能派活（走 Agent）、干完能通知（只报标题不报内容）。

> 这是决策记录，也是执行顺序。开工前先看最后一节「关键实测事实」，
> 那些都是当天现场验证过的，别重新摸索一遍。总估约 **1375 行**。

### P0 · 前置（必须先做完）

1. **建隔离环境跑通原版**

   ```bash
   python -m venv .venv
   .venv/Scripts/python.exe -m pip install "PySide6>=6.8" requests "winsdk>=1.0.0b10"
   .venv/Scripts/pythonw.exe 桌宠.py
   ```

   注意：`requirements.txt` 写的是 `PySide6>=6.5`，但 **Python 3.13 需要 6.8+**，按老声明装会卡。
   验证时要先退出正在跑的桌宠 —— 单实例检查会把新实例挡回去（v1.1.4 踩过）。

2. **F 盘不存在了**（开发在另一台机器）。本文上面那些 `F:\Codex\work\publish-pet.ps1`、
   `F:\Codex\tools\innosetup` 全部失效。发版流程要么重建，要么改成仓库内相对路径。

### P1 · 任务完成通知（最小、最独立、立刻见效，约 220 行）

**需求**：不显示结果，只弹一条像 Windows 右下角的提示，内容是 **Agent 自己生成的标题**。
**不管任务是不是桌宠派发的**，用户自己在 Codex / DSH 里开的任务，结束也要通知。

- 通知 UI：`self.tray.showMessage(标题, "干完了", self.icon)` —— 托盘已经有了，一行。
  （要更有辨识度再做 toast 浮窗，约 80 行，可后置）
- **Codex 监听**（~90 行）：
  - 标题：`~/.codex-deepseek/session_index.jsonl` → `{"id":…, "thread_name":"安装并封装 3dviz-pro_max 插件"}`
  - 完成：`~/.codex-deepseek/sessions/<年>/<月>/<日>/rollout-*.jsonl` 里 `event_msg` 的
    `{"type":"task_complete","last_agent_message":…}`
  - 复用现有 `scan_codex_usage`（@7586）的扫描器，**加 offset 增量读**，不要每次全文重扫
- **DSH 监听**（~130 行）：
  - 文件：`~/.dsh/sessions/<cwd编码slug>/session-<uuid>/session.v4.jsonl.zstd`
  - 标题：`{"type":"session/title","data":{"title":"问候与介绍",…}}` —— **有两条，取最后一条**
    （第一条 `kind:"fallback"` 用原话，第二条 `kind:"provider"` 是 LLM 生成版）
  - 完成：`{"type":"turn/end","data":{"turn":1,"reason":{"kind":"completed"}}}` —— `reason.kind` 能区分失败/取消
  - **zstd 是多帧拼接的**，见最后一节

### P2 · 更多动作（状态：2026-10-23 已收敛）
**结论：三视图只保留原有的三个程序化动作（蹦跳 / 摇摆 / 拉伸），不再加形变类动作。**

- 当天试过 `shake 抖动 / squish 压扁 / lean 倾身 / nod 点头 / doze 打盹` 五个，主人看过说
  "动作有点诡异"，**已全部删除**。别再加回来 —— 静态立绘做形变，观感就是不如真帧动画。
- 现在的做法是**第三种形象「灵动大肥鱼」**（`SKIN_ANIM`，走 `pet_ext/anim.py` 播真帧），
  三视图 / 挂件保持原样，用户自己在「设置 → 桌宠形象」或右键「形象」里选。
- `ACTIONS` 表只剩三项，权重照搬原版写死的那三档 35 / 25 / 10（加起来 70 = 老规则的"七成动作"）。
- 右键「逗她一下」是二级菜单：灵动版列素材里的真动作，三视图 / 挂件列这三个，被 `actions_off`
  关掉的置灰保留（不隐藏）。
- **菜单图标两级表**（2026-10-26）：一级看 `MENU_ICONS`（按文字前缀匹配，菜单文案常带
  「（现在：话多）」这类后缀）；「逗她一下」的子项看**动作表** —— 灵动版 `pet_ext/anim.py`
  的 `CLIP_ICONS`（clip → 图标名），三视图 `桌宠.py` 的 `ACTION_ICONS`。
  `_iconize_menu` 是三级回退：菜单通用表 → 动作表 → 继承父项。
  ⚠️ 新加动作素材时**顺手补一行 `CLIP_ICONS`**，否则那一条会退回父项的鼠标指针，
  30 多条里混一个不一样的很难看；`_test/test_menu_icon_tease.py`（菜单 23）会报"没配图标"。
  ⚠️ 别用"动作自己的帧做缩略图"当图标：32px 能认，**16px 全糊成同一个蓝色小人**（试过，否掉）。
- 硬约束仍在：`paintEvent` 是 50 帧/秒热路径，将来真要加分支**只能纯算术**，不许查表/读文件。
- 待做：设置页「动作和互动」加一张「它会做什么」卡片（开关 + 频率 + 预览），组件够用
  （`page.card` + `page.row` + `page.seg` + `page.buttons`）。

### P3 · 设置窗口错位修正（约 120 行，纯搬移）

详见工作区《设置窗口分类审计》。**只做 A 档（搬 6 处），不做 B 档（合并页面）**，风险差一个量级。

1. `拖拽吸附四边`(2755) + `左吸附时翻面`(2757) → 从「桌宠形象→外观」搬到「动作和互动」
2. `高峰 / 空闲时段`整卡(3096) → 从「文案和语录」搬到「余额和用量」
3. `离开 / 返回提醒`(3113) + `全屏时静音`(3115) → 从「语录」卡拆出，搬到「应用联动」
4. `免打扰`卡(3329) → 从「性能和工具」搬到「应用联动」
5. `控制台外观`(2831-3064) → **只改名「界面外观」**，内容不动
6. `去哪个文件夹读对话记录`(2566) → 从「今日已用怎么算」拆成独立卡「每轮消耗统计」

> 若以后要做 B 档（合并页面、删 `sound` / `performance` 两个 key），**必须给
> `cfg["console_start_page"]` 加 fallback**，否则老配置打开设置窗口会一片空白。

### P4 · 侧边浮窗骨架（约 400 行）—— 聊天和派活共用

- **不要塞进 `paintEvent`**：现有气泡画在头顶（`BUBBLE_H = 112`，@245），窗口是
  `setFixedSize(win_w, cur_h + BUBBLE_H + MARGIN*2 + 10)`（@9817）。加宽窗口后透明的侧边区域会拦截鼠标。
- 做成**独立 frameless 窗口**，项目里已有先例：`_flyout`（二级菜单自研浮窗）那套"置顶 + 跟随 + 延时收起"
- 侧边浮窗同时解决「AI 回复太长装不下」这个老问题（当年 `max_tokens:100` + `reply[:28]+"…"` 硬砍 30 字就是这个原因）

### P5 · 聊天通道（走 API，约 120 行）

- 双通道分工：**聊天走 DeepSeek API**（`cfg["ds_api_key"]` 已有），**任务走 Agent**
- 原版实现躺在 git 里：`git show d6ae670^:桌宠.py` → `_call_ds`（旧 461-509）、
  `DS_SYSTEM`（旧 47）、`chat_history`（旧 418）、`_show_chat_dialog`（旧 822）
- 异步范式现成：`_queue_say`（@7119）
- 要做的是"捡骨架 + 换皮（浮窗）+ 去掉 30 字硬砍 + 加流式"
- 参考：`bm-github/clippy2-oh`、`ShellLM/clippy_py`（PySide6，MIT，带尾巴的说话气泡 + thinking 状态）

### P6 · 任务派发（约 270 行）

- **拖放要从零加**：现在零支持（`grep dragEnterEvent|dropEvent|setAcceptDrops` 无结果）
  - `setAcceptDrops(True)` + `dragEnterEvent` + `dropEvent`
  - 穿透状态下收不到 drop，拖放期间要临时退出穿透（对账逻辑已有 `_through_applied`）
- **Codex 走 ACP（推荐）**（~180 行）
  - 官方适配器 `@agentclientprotocol/codex-acp`（Apache 2.0，OpenAI + JetBrains + Zed 共同维护）
  - Python SDK：`pip install agent-client-protocol`
  - `spawn_agent_process(...)` → `initialize` → `new_session(cwd=…)` → `prompt`
  - 流式事件 `session_update`、权限请求 `request_permission`（**要弹窗，否则卡死**）、`stop_reason` 是完成信号
  - **asyncio 与 Qt 循环不能混**：ACP 跑独立线程的独立 event loop，结果走队列回主线程。
    **不要用 qasync**（会侵入整个 app 的事件循环）
  - 兜底：ACP 调不通就退回 `codex exec -s workspace-write`（跳过审批）
- **DSH 走 CLI**（~90 行）
  - `"E:\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd" --profile headless "任务"`
  - **不在 PATH**，要用绝对路径；`.cmd` 得走 `shell=True` 或经由 cmd 转发
  - 工作目录：**`subprocess.Popen(cwd=…)` 直接生效**，不需要 `--cd`（profile 里没有 workspace 配置，继承父进程）
  - 支持 `--json`（NDJSON 事件流）、`--session-id`、stdin 读任务
  - 不支持 ACP，所以没有流式 / 权限 / 中途状态

### 明显不做 / 先别碰

- **WB 不做**（2026-10-23 定）：没有 CLI，`~/.workbuddy/cli-env` 只有一个 `wecom-cli.sh`，派活做不到
- **番茄钟**：2026-09-14 删掉的（"好鸡肋"），别复活
- **抽卡 OCR**：脆且吃性能
- **主题包导入导出 / 全局字号缩放**：成本高（路径重写 / QSS 字号逐个写死）
- **帧动画**：要动 `_sprite_key` / `_ensure_sprites` / `_rebuild_sprites` 三处结构，且**素材一致性是主要成本**。
  真要做只做**正面 1~2 个**，且每个动作的第一帧必须是现在这张正面图。素材参考 `oyxdsg/Deepseek-pet`
  （PySide6 + MIT，已解决裁透明边 / 统一缩放 / 脚底对齐三个坑）

---

## 关键实测事实（2026-10-23 现场验证，别重新摸索）

| 事实 | 细节 |
|---|---|
| Codex 标题 | `~/.codex-deepseek/session_index.jsonl` → `thread_name`（本机 18 条，中文语义标题） |
| Codex 完成 | `rollout-*.jsonl` 的 `event_msg.task_complete`，含 `last_agent_message` |
| Codex 来源 | 同上有 `task_started.turn_attribution.turn_trigger`（`composer` = 用户输入框） |
| Codex 通知钩子 | `config.toml` 的 `notify = [exe, "turn-ended"]`，但**是"命令 + 参数"二元数组**，已被 `codex-computer-use` 占用 |
| DSH 标题 | `session/title` 事件，**两条，取最后一条**（第一条 fallback 用原话，第二条 LLM 生成） |
| DSH 完成 | `turn/end` → `reason.kind`（completed / 失败 / 取消，比 Codex 细） |
| **DSH zstd 多帧** | `session.v4.jsonl.zstd` 是**多个独立 zstd 帧拼接**。`zstdDecompressSync` 和流式解压都**只出第一帧**（244 字节）。必须**按魔数 `28 B5 2F FD` 切分逐帧解压再拼接**（13849 → 40154 字节，23 行全出） |
| DSH 消息过滤 | 一个回合里 `user/message` 有 3 条，只有 `source.kind == "user"` 那条是真实输入，另两条是系统注入（runtime context / skills 列表） |
| Codex ACP | `@agentclientprotocol/codex-acp`，`npx -y` 直接跑，自带兼容版 Codex |
| Agent 检测 | Codex：`which codex` + `~/.codex/auth.json`（已登录）；DSH：`E:\...\dsh.cmd` + `~/.dsh/profiles/headless` |
| 参考项目 | `thunguo/miku-on-desktop`（**PySide6 桌宠 + 流式气泡 + acp_delegate 委派 Codex**，最对口，但无明确 LICENSE 声明，勿搬代码）；`oyxdsg/Deepseek-pet`（PySide6 + MIT，帧动画） |

## 两套菜单，别搞错

- `_make_menu()` @8270 按 `cfg["classic_menu"]` 切换
- **默认用 `_build_quick_menu`（@7682）：10 项、零子菜单** —— 只留「看一眼」和「救命通道」两类，
  这是 v1.1.0 定的规矩，**加功能不要往这里塞**
- `_build_menu`（@7739）是经典版，22 项 14 子菜单，入口在「通用 → 排查问题」
- 设置类入口一律进设置窗口，不进菜单

## 灵动版 / 尺寸调整的性能红线（2026-10-23 实测，改之前先读）

拖大小滑块这条路径对耗时极度敏感，踩过的坑：

| 事项 | 实测数字 | 结论 |
|---|---|---|
| 同步重载 241 帧（`QPixmap`+`scaledToHeight`） | 250~315 ms | **绝不能放在 `set_size` 里**，必须分批/后台 |
| 改用 `QImageReader.setScaledSize` 直接解码到目标尺寸 | 1.16 ms/帧（原 1.58） | 重排时用它 |
| `_ensure_sprites` 每次新高度 | 0.7~1.5 ms | 灵动版不画精灵，拖动时直接跳过 |
| Python 全量 GC（gen2） | 偶发 60~70 ms | 启动后 `gc.collect()+gc.freeze()` |
| `setFixedSize`（真机，60 次中位） | 4.1~5.0 ms | 不再用；见下面"改尺寸一次做完" |
| `resize` 单独 | 4.6 ms | 只改尺寸时可以 |
| **`setGeometry`（尺寸+位置一次）** | **4.2 ms** | **改尺寸顺带挪位置时一律用它** |
| `resize` 再 `move`（分两次） | 5.8~6.4 ms | 别这么写，白多付 1.7ms 的 `move` |
| 单独 `move` | 1.7 ms | 能合就合 |

现在的做法（别改回同步）：
1. `paintEvent` 把帧**缩放到目标高度**再画，所以尺寸永远立刻生效，与帧缓存尺寸无关；
2. 帧重排在 `AnimPlayer.schedule_reload()` 里分批（`RELOAD_BATCH=4` / `RELOAD_PUMP_MS=12`），
   解完整体换缓存，换之前画面无变化；
3. 用 `AnimExtension.schedule_reload_soon()` 做 260ms 防抖。**注意**：`_sync`（200ms）里
   不能在防抖已排队时再排一次，否则 200<260 永远触发不了（这个坑踩过，用 `reload_scheduled` 判断）；
4. **改尺寸 + 挪位置一律走 `_set_win_size(w, h, x, y)` → `setGeometry` 一次做完**；
   拖动期间不再做尺寸量化（`WIN_RESIZE_STEP*` 两个常量已废弃），按 8ms 节流跟随鼠标；
5. 拖动期间"当前这一帧"按新高度重解，节流 `REFRESH_GAP=0.035`（`pet_ext/anim.py`）；
   拉到 0.06 时帧高度滞后中位 61px，看得见"糊一下突然变清晰"，0.035 能压到 1px；
6. 桌宠脚底锚点始终是 `self.height() - MARGIN - 10`（贴窗口下沿），与尺寸无关。

**当前实测（2026-10-24，`_test/measure_drag.py`，拖动 0.54→0.76 共 60 步，
真 Windows 平台）**：每步 `set_size` 中位 6.6~8.7ms / p90 9.2~14.1ms，
重绘间隔 18~21ms（约 50fps），帧高度滞后中位 1.0px，
相邻两次改窗口的跳幅 3px。

**两个"卡顿"的真正来源（2026-10-24 才挖到，别再走弯路）**：

1. **窗口宽度跟三视图精灵取 max** —— `self.sprites` 只缓存用户到过的档位，
   `cur_h` 连续变化时有的高度命中（精灵宽 230）、有的没命中（`spec_w` 退回 0），
   窗口就在 276 / 270 之间反复跳 6px。灵动版根本不画三视图，不该看它。
2. **`_calc_window_size` 里提前 `int()`** —— `cur_h` 每步只 +1.27，
   `int()` 截断把它放大成"这步 +1、下步 +2"，再乘 `ANIM_BODY_ZOOM=1.18` 和画布宽高比，
   变成 3~4px 的台阶。现在全程用浮点 `body_f` 算，最后才 `round`。

另外：鼠标回报率可以到 1000Hz，而改一次窗口要 4.2ms —— 所以 `_apply_window_size`
在 `quantize=True`（拖滑块）这条路上按 `DRAG_RESIZE_GAP=8ms` 节流，
差值 ≥`DRAG_RESIZE_JUMP=4px` 时立刻跟。


## 动画播放器（2026-10-23 二轮：帧率与清晰度，改之前先读）

- **帧号一律按真实时间算**：`_advance()` 用 `(now - _t0) × fps`，不是"每 tick +1"。
  固定间隔定时器在 Windows 上跑 41.67ms 会拖成 47ms（实测平均 21fps、σ≈9ms）；
  配合"每次算到下一帧边界再定唤醒"（`_schedule_next`，单次 PreciseTimer），
  稳态实测 24.0fps、σ=0.6ms、无跳帧。
- **`play()` 是异步的**：立即返回，帧在后台"边播边解"（append 模式）。切动作从
  阻塞 630ms 降到 8ms；首帧约 70ms 出现，全量 241 帧约 0.9~1.7 秒解完。
  **别把它改回同步 `_load`**。
- 素材已重建为 298×384（原 209×270）：0.9 档清晰度指标 +31%。`manifest.json` 的
  `size/box/height` 是新值，`_build/regen_anim.py` 是重建脚本（覆盖写入，别用
  rmtree——批量删 ≥50 文件会被安全策略掐断，踩过）。
- 灵动版绘制**不叠加呼吸缩放/摇摆**（那是模糊主因，清晰度指标 3911→5639）。
  24fps 下的"不够顺"想用插值补的话改 `ANIM_SUBFRAMES=2`（48fps 交叉淡化，
  代价是轻微拖影），默认 1。
- 解码泵按时间预算节流（`RELOAD_BUDGET_MS=7` / `RELOAD_PUMP_MS=10`）；
  用户拖滑块时 `hold()` 暂停解码（否则叠加实测中位 8.6ms、尖峰 71ms）。
- **坑**：一次性动作播放中后台还在补帧时，`_schedule_next` 不能因 `pos>=n`
  提前撒手——必须等 pending 解完再收尾，否则永远停在半截（实测踩过）。

## 灵动版动作库（2026-10-24：4 段 → 32 段）

素材来自参考项目 [PC2005-cloud/dsh-pet](https://github.com/PC2005-cloud/dsh-pet)（MIT，106 段透明 WebM，
`dsh-pet/assets/webm/<中文名>.webm`，640×360 / 24fps / 10 秒）。本项目取了 28 段，加上原有 4 段共 32。
manifest 实际 35 条 —— 多出的 3 条是下面「螃蟹走路」的 `crab_in` / `crab` / `crab_out`，
只给走位用，不进「逗她一下」菜单。

**转码脚本**：`_build/fetch_dsh.py`（下载，`WANT` 是中文名→clip id）+ `_build/clip_boxes.py`（量框）+
`_build/convert_dsh.py`（转帧）。都可重复跑：已存在的帧会复用，不会重复解码。

关键参数（改之前想清楚）：
- **每段动作一个裁剪框**（2026-10-24 改）：`_build/clip_boxes.py` 全帧扫 alpha 包围盒，
  写 `_build/dsh/boxes.json`；`convert_dsh.py` 按各自的框裁。
  框的规矩：**关于 x=320 对称**（角色水平居中）、**底边固定 360**（脚底对齐）、
  x 留 6px / y 留 4px 余量；宽度下限是老框一半（140），所以窄动作不缩窗。
  老统一框 `(180,31,460,360)` 只能装 280 宽，鸽子（468）、幽灵（413）、
  玩水枪（689）、大口吃零食（686）、深度思考（556）、吐泡泡（497）都会被切掉伸出部分。
  实测各段画布宽 326~689、高 384（`manifest.json` 每条 clip 的 `size`）。
- **窗口宽度跟着当前动作走**：`_apply_window_size` 读 `player.canvas_size()`，
  `AnimPlayer.play()` 切动作后回调桌宠 `_anim_clip_changed()` 重排窗口。
  **不要改成所有动作取最大宽度**——那样透明区会长期挡住下面窗口的点击
  （PetWindow 没有 setMask，整个矩形都吃事件）。
  实测窗口宽度（默认「中」档，body=288）：待机 300 → 变鸽子 397 → 玩水枪 562，播完收回。
- **位置锚点是"家"，不是"当前位置"**（2026-10-24）：`_anim_home = (中心x, 底边y)` 由
  `moveEvent` 维护，任何外部移动（用户拖、恢复位置、吸附、改大小）都会顺手更新它；
  自己的滑动动画期间用 `_geom_glide_busy` 挡住，不让动画污染锚点。
  每段动作都从"家"推导目标几何，装不下屏幕就夹回来，所以播完回待机必然回原位
  （实测 628 → 448 → 628，漂移 0）。**别改成按当前位置增量算** —— 那样每播一个宽动作就漂一格。
- **窗口宽度固定，换动作不改尺寸**（2026-10-25 第十二轮，240fps 录屏实锤）：
  改尺寸那一下，合成器会把**旧画面**按新窗口左上角摆出去 —— 鱼整体偏 **Δw/2**，
  240fps 下能占 2 帧（实测 6.9173~6.9224 偏 −224px，正好是 待机298→水枪689 的一半）。
  `refresh=True` 拦不住（它在改完之后重画，旧表面已被取走）。前几轮只把改宽次数
  从 10 降到 1，没根治。现在 `_calc_window_size` 用 `max_canvas()`，
  **宽度恒为最宽画布**，换动作时 `(w,h)` 不变 → 根本不进 `_set_win_size`。
  ⚠️ 配套：窗口比窄动作宽，所以 `_settle` 吸附 / 夹屏 / `snap_into_screen`
  全部改用 `_content_margin()`（按鱼的可见宽度），否则鱼会离屏幕边 170 多像素。
  检测 `_test/check_fixed_width.py`（逐段播动作断言窗口尺寸不变）。
- **历史：换动作的窗口变化**（第十一轮，已被上面取代）：尺寸一帧到位。
  原来交给 `_geom_glide` 用 200ms `OutCubic` 分十来步滑宽度，每一步都是一次
  "改宽 + 重画"，合成器撞上任意一步就闪 Δw/2 —— 12 次改宽就是 12 次抽奖，
  主人看到的"抽搐"就是这么来的。现在 `_apply_window_size` 里尺寸一变就直接
  `_set_win_size(..., refresh=True)`，只有"尺寸没变、纯挪位置"才走 `_geom_glide`。
  ⚠️ 别再改回分步滑：那段缓动视觉上是空的（`pw` 只跟动作画布有关，窗口变宽透明），
  分步不产生任何观感收益，只放大闪烁概率。检测 `_test/repro_shift_screen.py`。
- **要挪位置：三段接力**（2026-10-24 第五轮，主人原话"走路动画有一个启动流程，
  但是在启动流程的时候你就强行让它开始移动了……只有正面的走路样式，没有侧面转身的过渡"）。
  素材换成上游 `PC2005-cloud/dsh-pet` 的**「螃蟹走路」**，切成三段
  （`_build/convert_crab.py`）：`crab_in` 原地转身 / `crab` 侧身横着走 /
  `crab_out` 转回正面。`_anim_walk_to_clip()` 只开头：收窄窗口 → 播 `crab_in` →
  **这时不给 target**（原地转身，窗口一动不动）；`crab_in` 播完由 `_walk_after_once`
  给 target；走完 `_on_walk_arrived` 播 `crab_out`；`crab_out` 播完 `_finish_walk_task`
  才接动作。实测 184px：转身 0.63s / 走 0.99s / 转回 0.71s，共 2.33s。
  播放器为此加了倍速（`play(..., rate=)`），转身两段 `WALK_TURN_RATE=1.6`。
- **方向**：「螃蟹走路」朝左，往右走要镜像（`_walk_flip`，paintEvent 里跟 `flip_x` 异或）。
  不然回程会倒着走。实测去程朝左、回程朝右（`_shot/走路-去程朝左回程朝右.png`）。
- `tick()` 里那道"目标被清掉 → 当作到位"的兜底**只在 `_walk_phase == "walk"` 时生效**：
  转身/转回那两段本来就没有 target，不排除会把整趟掐掉（实测 `crab_out` 只播 30ms）。
- ⚠️ **走位途中切动作**（第七轮根因，主人"切动作闪弹几率很高"）：
  上一趟的 `_walk_task` 残留时，`_anim_walk_to_clip` 必须**作废它再正常判断**
  （cancel 后照常算 dest vs cur）——直接 return False 的话新动作会原地播出、
  `_anim_clip_changed` 再按**旧家** `_geom_glide`，窗口从走位半路 200ms 滑回旧家
  （实测 110px）。`_anim_clip_changed` 的 walking 分支同理：被顶掉时 cancel 后
  **家 = 当前位置**。检测 `_test/repro_paint_trace.py`（逐帧鱼身屏幕位置，0 突跳）、
  `_test/repro_switch_flash.py`（屏幕实拍，量合成器真正显示出来的位置）——两个都过才算不闪。
- 老素材没有这三段时退回上一版（`move` + 立刻给 target），不至于不走。
  - `tick()` 的 still 分支从"无脑 return"改成"有 `target` 就走"；任务走位靠
    `_walk_task` 和散步区分：速度 `WALK_SPEED=180`、
    **步长夹到剩余距离 + 到位判定 2px**（散步是 12px，那个会落偏，接动作时还得挤一下）。
  - 走到（或走不动）→ `_on_walk_arrived()` 播目标动作；
    被拖 / 改大小 → `_stop_geom_glide()` → `_cancel_walk(play_task=True)`（动作照播）。
  - **三种模式都走**：`follow` 分支加了 `has_task` 让路（不然每帧被鼠标位置覆盖）；
    散步模式本来就是"`target is None` 才抽新目标"，任务设了 target 就自然接管。
    `tick()` 里另有一道兜底（`target is None` 但还有 `_walk_task` → 当到位处理）。
  - `mode != "still"` 时，锚点用**当前位置**而不是"家"（它一直在动，没有"回去"这回事），
    并且设目标时顺手把 `_anim_home` 挪过去 —— 否则到位 `_anim_clip_changed` 会按旧家摆。
  - ⭐ **速度**：`WALK_SPEED=180`。螃蟹走是侧身碎步，180px/秒 时一步约 60~75px，
    和步频对得上；调快了就又变"滑"（这条是第四轮踩出来的）。
  - `moveEvent` 在 `_anim_walking` 期间**不更新"家"**：家要留在原地，否则走过去之后
    家跟着挪，做完动作回不去。
- ⚠️ **走路的判断必须在 `play()` 之前做**。`_anim_clip_changed()` 是 `AnimPlayer.play()`
  **内部**调起来的，在那里再调 `play("move")` 会把外层刚排的后台解码顶掉
  （`_pump_reload` 见 `pending["clip"] != self.clip` 整批作废），表现是"窗口在走、
  鱼站着不动"。这个坑实测踩过，别再挪回去。
- ⚠️ **衔接那一下必须是一帧，而且是"当帧重画"**（主人报的"左右抽搐 / 向左闪一下"）：
  1. 到位别用 200ms 缓动张开：走 `_anim_snap_size`，一帧给足宽度（否则水柱"长"出来）。
  2. 改完尺寸要 `_set_win_size(..., refresh=True)`（内部同步 `repaint()`）。
     **绝对不要用 `setUpdatesEnabled(False)` 包** —— 那等于保证中间不重画，
     合成器拿旧的窄画面去凑新窗口，鱼看着往左跳半个宽度、下一帧弹回（实测踩过两次）。
  `test_clip_window.py` 断言"衔接那一刻 705px，之后 200ms 最宽 705px"。
- ⚠️ **拖动与边缘动作的冲突**（第六轮主人报"贴边开始动作时一拖就异常"，三处一起看）：
  1. **取消走位要"家=当前位置 + 不夹屏"**：`_cancel_walk(play_task=True)` 里先把
     `_anim_home` 改成当前中心/脚底，再 `_anim_snap_noclamp=True` 播动作。
     否则走到一半被抓，窗口按旧家重排 → 瞬移 48~180px；贴边时长窗口一长大就被
     屏幕夹住，鱼从鼠标手里"挣脱"跳 50~100px（`_anim_clip_changed` 见 noclamp 就跳过夹屏）。
  2. **拖拽期间不重排窗口**：`_anim_clip_changed` 开头 `if self.dragging: return`。
     否则动作播完时 play("idle") 起一条 200ms 窗口动画，跟拖拽打架（动画每 16ms 挪一下）。
  3. **松手补排**：`mouseReleaseEvent` 的拖拽分支里，`_snap_to_edge()` 之后调一次
     `_anim_clip_changed()`，把被闸门挡掉的宽度重排补上。
  `_test/repro_drag_walk.py`（合成鼠标事件）断言：按下不瞬移、走位状态清干净且动作照播、
  每步位移跟鼠标一致、松手后宽度收回。
- 剩下的轻微左右晃是**素材的步态摆动**（下半身原生 15px 峰峰、3Hz，慢升快落），
  散步时一模一样。要压掉只能重裁 `move` 的 241 帧，别在代码里加滤镜。
- `TARGET_H = 384`、`WEBP_Q = 82` —— 每段约 6.2MB，宽的段（水枪/零食）约 7~8MB。
- 画布越高的段（nap 336 / doze_wake 344 / swing 348，其余 329）角色会小 2%~6%，
  因为绘制按高度缩放到 `_body_h()`；这几段都是短暂动作，实测看不出来。
- **构图基线**（角色脚底在原生画布的 y，全体中位 328）：snack 343（+15，坐着吃东西）、
  swing 321（−7，荡起来）、drag_dangle 297（−31，"被拎起来"本来就该高）。
  **已用 manifest 的 per-clip `dy` 抹平**（2026-10-24）：全 29 段扫过，27 段偏差 ≤1px 不补，
  只有 snack 写 `dy: -16`（实测与待机差 +1px）；`swing` / `drag_dangle` 在
  `_build/anim_offsets.py` 的 `EXEMPT` 里故意豁免 —— 脚本来就不着地，跟着姿势走才对。
  绘制时按 `_body_h()/384` 换算，切动作 0.22 秒渐变（`_anim_dy_now()`），不硬跳。
  重新量：`python _build/anim_offsets.py`（加 `--write` 才落盘）。

**清单驱动**：`manifest.json` 每条 clip = `{"frames", "loop", "name", "box", "size", "dy"}`。
`AnimExtension.once_clips()` 直接取「除 idle/move 之外的全部」，
所以**加动作只需要放目录 + 加一条清单**，菜单和「随机来一个」自动跟上，不用改代码。
新加一段的动作素材要先用 `_build/clip_boxes.py` 量框、`_build/convert_dsh.py <clip>` 转帧，
`box` / `size` 两个字段由脚本自己写，手写清单时别漏（漏了就退回全局 `size`，会被裁）。
`dy` 是垂直补偿（脚底对齐），漏了也能跑但那一段会比待机低 15px 左右。

**注意**：
- 老 4 段画布是 298×384，新 28 段是 326~689×384。播放器按高度缩放，视觉大小一致；
  窗口宽度按**当前动作**的 `size` 算，播宽动作时窗口临时变宽，播完收回。
- 每段 241 帧，切动作时后台边播边解（`append` 模式），首帧约 40ms，全量约 1.5 秒。
- 验证脚本：`_build/verify_boxes.py` 逐帧量输出帧四边余量（贴边=被裁；snack 下边=0
  是源视频本身碎屑贴底，不是裁的），`_test/test_clip_size.py` 验按段尺寸解码、
  `_test/test_clip_window.py` 验窗口伸缩、位置锚定、**走路过去**（含帧是否真在推进）、
  dy 对齐；`_test/preview_walk.py --live` 开真窗口演一遍（`手动测试.bat 8`）。

## 任务完成通知（2026-10-24 已实现，含提示音与托盘兜底）

三个开关，都在 `cfg_defaults` 里（setdefault，老配置自动兼容）：

| 键 | 默认 | 作用 |
|---|---|---|
| `task_notify_on` | true | 总开关，不盯会话就不解析日志 |
| `task_notify_sound` | true | 只控「叮」那**一声**，关掉气泡照旧 |
| `sound_on` / `volume` | 沿用 | 全局音效开关和音量，提示音跟着走 |

- 提示音**独立成一套**（2026-10-24 第四轮，主人："不要与点击音效放在同一个模块里，
  可统一归到音效大板块下"）：设置页两张卡，上面「点击音效」一行没动，下面
  「任务完成提示音」是新的。配置键 `task_sound_set` / `task_sounds`，
  自定义文件放 `用户目录/sounds/task/`，和点击音的 `sound_set` / `custom_sounds` 互不相干。
  内置只有一声「叮」（`assets/notify-chime.wav`），能试听、能换成自己的、能删；
  时长**只挡 1 分钟以上**（`TASK_SOUND_MAX_SEC=60`），不像点击音那样卡最适合区间。
- 内置那声怎么来的：E6 1318.5Hz 基音 + 2.0/3.0/5.4 倍泛音，4ms 起音 + 指数衰减，
  0.42s，峰值 0.62。重算 `python _build/make_chime.py`（自带"起音次数必须是 1"的自检）。
- **设置里能关**：设置 → 音效 → 「任务完成提示音」（`ui_console._page_sound` 里那行
  `Switch`，回调 `pet.set_task_notify_sound`）。打开时当场响一声。
  位置是临时的 —— 主人说等设置界面重构再定放哪，所以 UI 只挂一行、逻辑只改配置。
  `_test/test_console_switch.py` 断言"点开关 → 配置翻转"以及"关掉提示音气泡照旧"。
- 播放：`NotifyExtension._play_chime(force=False)`，**先响再冒泡**（QSoundEffect 起播有延迟，
  压在 `say()` 前面更自然）。路径现问 `pet.task_sound_path()`，换过音频就重建 QSoundEffect
  （它按 source 缓存，不换会继续放旧的）。`force=True` 是试听用（跳过开关）。
  音量 `min(1.0, 0.8 × volume)`。QtMultimedia 起不来就安静跳过 —— 绝不能让气泡跟着崩。
- **气泡 / 托盘的分工（主人明确要求：桌宠在线时只走气泡，保底弹窗要保留）**：
  `_on_event()` 里只有 `not pet.isVisible()` 才 `tray.showMessage`，其余一律 `say()`。
  `_test/preview_notify.py --check` 断言这一条；`--hidden --check` 断反方向。
- "用户自己在 Codex / DSH 里发起的任务也要通知"：轮询是扫会话日志的完成标记，
  不区分是谁派的任务，所以天然覆盖。

## 灵动版动作的"画面完整"三件套（2026-10-24）

改素材或改绘制时，这三件事一起看，少一件就会觉得"被裁了 / 跳了 / 飘了"：

1. **裁剪框**（`_build/clip_boxes.py` → `boxes.json`）：每段自己的框，关于 x=320 对称、
   底边 360。用统一框就会切掉伸出去的道具。
2. **垂直补偿**（`manifest.json` 每条 clip 的 `dy`）：按脚底行投影算，`_build/anim_offsets.py`
   可重跑。现在只有 snack 需要 `-16`。
3. **窗口位置锚点**（`桌宠.py` 的 `_anim_home`）：锚点是"家"不是"当前位置"；
   要挪位置时走**"转身 → 横着走 → 转回正面"三段**（`crab_in/crab/crab_out`），
   转身和转回时窗口**不动**，只有横着走那段才平移（`WALK_SPEED=180`）。
   接动作那一下要一帧到位（`_anim_snap_size` + `refresh=True`），
   不然水柱会"长"出来、或者画面往左闪一格。

水枪那类"看起来被切"的断面，多半是**源视频本身就硬断**（源帧到 x=595 就没了，
右边 45px 全透明）。对比图生成脚本：`_build/shot_watergun.py` → `_shot/水枪-源帧对比.png`。
