# -*- coding: utf-8 -*-
"""灵动版形象 —— 用视频拆出来的帧序列做真动作。

素材从 `dsh-pet-indesktop` 的透明 WebM 拆出来（见 AGENTS.md），
每帧是真 alpha 的 WebP，已经裁边、跨动作统一框、脚底对齐。

三个设计考虑：

1. **内存**：一个动作 241 帧 × 209×270 ≈ 54MB（QPixmap 更胖）。所以**只保留当前
   动作**，切走就把上一个放掉；加载时直接按 `pet.cur_h` 缩放，不存原图。
2. **驱动**：自己的 QTimer（24fps ≈ 41ms），不侵入主 `tick()`。每帧只推进索引 +
   让桌宠重绘，绘制仍然由 `paintEvent` 负责。
3. **和程序化动作的关系**：灵动模式下不播 `play_action` 那套形变，动作全部由
   这个播放器负责；呼吸、按压 Q 弹、吸附翻转这些"底层手感"保留。
"""

import json
import os
import glob
import time

from PySide6.QtCore import QTimer, Qt, QSize
from PySide6.QtGui import QPixmap, QTransform, QImageReader

# 和 桌宠.py 里的 SKIN_ANIM 保持同一个值（那边是模块常量，这里不方便反向 import）
ANIM_SKIN = "灵动大肥鱼"

# 动作的中文名（右键「逗她一下」二级菜单、以后设置页的预览都从这里取）
# 素材清单 manifest.json 里每条 clip 自己也带 "name"，那边优先；这里是兜底文案。
CLIP_LABELS = {
    "idle": "待机呼吸",
    "move": "漂浮踏步",
    "lion": "舞狮头",
    "wave": "元气挥手",
}

# 每个动作在右键菜单里的小图标（`assets/icons/act.<clip>.svg`，Lucide 线稿，和设置窗口同一套）。
# 2026-10-26 主人：「能不能子项根据动作名称设计不一样的图标」——
# 之前子项统一继承父项那个鼠标指针，30 多条一模一样，展开像一列重复符号。
# 没登记的动作就继承父项图标（不会空着），以后新加一段素材也能只补这一行。
# 挑图标的思路：优先"动作里那个物件"（冰淇淋 / 鸽子 / 饼干 / 水枪 / 魔方），
# 没有物件的按感觉走（挥手=手掌、被吓=闪电、打盹=月亮）。
CLIP_ICONS = {
    "lion": "act.lion",                  # 舞狮头 → 面具
    "wave": "act.wave",                  # 元气挥手 → 手掌
    "look_around": "act.look_around",    # 东张西望 → 眼睛在扫
    "cute_dance": "act.cute_dance",      # 可爱宅舞 → 声波线
    "pet_cat": "act.pet_cat",            # 撸猫 → 猫
    "maid_dance": "act.maid_dance",      # 优雅女仆舞 → 唱片
    "sway_dance": "act.sway_dance",      # 轻快摇摆舞 → 波形
    "big_stretch": "act.big_stretch",    # 超大伸懒腰 → 向外撑开
    "yawn": "act.yawn",                  # 哈欠连天 → 一口气
    "nap": "act.nap",                    # 原地打盹 → 月亮
    "doze_wake": "act.doze_wake",        # 打瞌睡被惊醒 → 闹钟
    "startle": "act.startle",            # 被吓一跳 → 闪电
    "caught_snack": "ui.eye",            # 偷吃被抓 → 被看见了
    "icecream": "act.icecream",          # 吃冰淇淋 → 甜筒
    "dove": "act.dove",                  # 变鸽子 → 鸟
    "card_trick": "act.card_trick",      # 扑克魔术 → 黑桃
    "coding": "act.coding",              # 写代码 → 代码括号
    "rubik": "act.rubik",                # 玩魔方 → 方块
    "juggling": "act.juggling",          # 三球抛接 → 环绕
    "shuttlecock": "act.shuttlecock",    # 踢毽子 → 羽毛
    "swing": "act.swing",                # 荡秋千 → 左右摆
    "mirror": "act.mirror",              # 照镜子 → 扫脸框
    "tail_tap": "act.tail_tap",          # 尾巴拍地 → 脉冲
    "curtsy": "act.curtsy",              # 女仆礼仪 → 缎带
    "ghost": "act.ghost",                # 小幽灵 → 幽灵
    "drag_dangle": "act.drag_dangle",    # 被拎起来 → 抓取的手
    "snack": "act.snack",                # 大口吃零食 → 饼干
    "water_gun": "act.water_gun",        # 玩水枪 → 水滴
    "thinking": "act.thinking",          # 深度思考 → 大脑
    "bubbles": "act.bubbles",            # 吐泡泡 → 泡泡
}

# 「一次性」动作：播完回到待机 / 走路。loop 的那两个（idle / move）不算，
# 它们由状态自动接管，手动点名播反而会马上被 _sync 改回去。
# 2026-10-24 起不再写死清单：素材里除了这两个循环动作，其余都当一次性动作，
# 新加一段视频（manifest 加一条）就自动出现在右键菜单里，不用改代码。
# 循环 / 内部用的段：不进「逗她一下」菜单，也不参与随机
# crab_in / crab / crab_out 是走路的"转身 → 横着走 → 转回正面"三段
# （_build/convert_crab.py 从「螃蟹走路」切出来的），由桌宠自己调度
LOOP_CLIPS = ("idle", "move", "crab_in", "crab", "crab_out",
              "idle_left", "idle_right")   # 后两个是从 idle 里切出来的"向左看/向右看"

# 重排帧的节流参数：每次 tick 最多干 RELOAD_BUDGET_MS 毫秒的活，隔 RELOAD_PUMP_MS 再来。
# 用时间预算而不是固定帧数——帧越大解码越慢（384 高时约 2ms/帧），
# 死按"每次 4 帧"会在高档位上一 tick 占掉 8ms，动画就跟着卡。
# 7ms/10ms（≈70% 占空比）：全量 241 帧约 1 秒解完；帧周期是 41.7ms，
# 7ms 的主线程块肉眼无感。这些活都发生在防抖之后（用户已停手）。
RELOAD_PUMP_MS = 10
RELOAD_BUDGET_MS = 7.0
RELOAD_BATCH = 12          # 只是上限，防止某帧特别快时一口气全解完
# 停手多久之后才开始重排帧（拖滑块时一直在动，就不排）
RELOAD_DEBOUNCE_MS = 200

# 拖大小滑块期间，"正在显示的这一帧"按新高度重解的间隔（秒）。
# 调大 = 更省，但画面会滞后（帧比窗口小，被放大着看，发虚）；
# 调小 = 更清晰，但每步耗时上升。实测见 _test/measure_drag.py。
REFRESH_GAP = 0.035

# 播放帧率倍数：1 = 原样播（24fps，和素材一致）；2 = 两帧之间做一次交叉淡入，
# 视觉上变成 48fps，慢动作（呼吸、踏步）会更顺，但快速动作（舞狮甩头）会有轻微拖影。
# 想试就把它改成 2；默认 1，保持素材原貌、也最清晰。
ANIM_SUBFRAMES = 1


class AnimPlayer:
    """帧动画播放器。`current()` 给 paintEvent 用，`play()` 给交互用。"""

    def __init__(self, pet, root: str):
        self.pet = pet
        self.root = root
        self.manifest = self._read_manifest()
        self.fps = int(self.manifest.get("fps") or 24)
        self.cache = {}            # clip → [QPixmap]，只留一个
        self.clip = None           # 当前动作名
        self.idx = 0
        self.loop = True
        # 播放倍速：1.0 = 正常。走路用的"转身/横着走"三段要能调快，
        # 否则一段 10 秒的素材按原速放，走到位要等两秒多（见 桌宠.py 的 WALK_TURN_RATE）
        self.rate = 1.0
        self.once_left = 0         # 单次播放剩几轮
        self._pix = None
        self._next_pix = None      # 插值用的下一帧（ANIM_SUBFRAMES=1 时恒为 None）
        self._blend = 0.0
        self._t0 = time.perf_counter()
        self._range = None         # 只播某段帧（原地转头做过渡用，见 play_range）
        self._dir_step = 1         # 区间播放方向：1 正序 / -1 倒序（来回播看左看右用）
        self._fx_from = None       # 跳帧时用来淡入的"旧那一帧"（见 begin_xfade）
        self._fx_t0 = 0.0
        self._fx_dur = 0.0
        self._scaled_h = 0         # 缓存对应的显示高度
        self._file_cache = {}      # clip → [帧路径]，避免拖滑块时反复 glob 240 个文件
        self._pending = None       # 正在后台重排的帧批次（见 schedule_reload）
        self._hold_until = 0.0     # 这之前暂停后台解码（用户正在拖大小滑块）
        self._timer = QTimer(pet)
        # 单次触发 + 每次自己算"离下一帧边界还差几毫秒"，比固定间隔轮询准得多
        # （固定 13ms 轮询实测 σ≈10ms，帧间隔在 39~52ms 之间跳；边界调度 σ≈1~2ms）。
        self._timer.setSingleShot(True)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._step)
        # 重排帧用的小定时器：一次只解几帧，别把 UI 线程堵住
        self._reload_timer = QTimer(pet)
        self._reload_timer.setInterval(RELOAD_PUMP_MS)
        self._reload_timer.timeout.connect(self._pump_reload)

    def hold(self, ms=400.0):
        """告诉播放器：用户正在改大小，后台解码先停一停。

        拖滑块时 set_size 会被连环调用，每 16ms 一次；解码一 tick 占 7ms，
        两者叠加实测能把单次 set_size 拖到 8~70ms。改大小的路每次都会调它，
        停手后 400ms 自动恢复解码（画面有旧帧顶着，看不出来）。
        """
        self._hold_until = time.perf_counter() + ms / 1000.0

    # ---------------------------------------------------------------- 素材
    def _read_manifest(self):
        p = os.path.join(self.root, "manifest.json")
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def clips(self):
        return list((self.manifest.get("clips") or {}).keys())

    def _files_for(self, clip):
        """某段动作的帧文件列表（缓存住：拖滑块时每步都 glob 240 个文件太浪费）。"""
        files = self._file_cache.get(clip)
        if files is None:
            files = sorted(glob.glob(os.path.join(self.root, clip, "*.webp")))
            self._file_cache[clip] = files
        return files

    def refresh_current(self, tol=8):
        """按**当前目标高度**重解"正在显示的这一帧"，立刻换上。

        干嘛用的：拖大小滑块时，缓存里的 241 帧还是旧高度，绘制时被放大 ——
        画面发虚、看着像掉帧。整批重排要 1.5 秒（后台分批），但"当前这一帧"
        重解只要 2~3ms，先把它换上，眼睛看到的立刻就是清晰的。

        `tol`：跟上次重解的高度差不到这么多像素就跳过 —— 差 4px 放大后肉眼看不出，
        但每步都解一张会把拖滑块的耗时从 0.6ms 顶到 7ms。
        """
        clip = self.clip
        if not clip:
            return False
        files = self._files_for(clip)
        if not files:
            return False
        h = self._want_h()
        last = getattr(self, "_refresh_h", 0)
        if last and abs(h - last) < tol:
            return False
        # 跟 _frame_fresh 共用同一个 _refresh_at 节流，免得两条路各解一张
        now = time.perf_counter()
        if now - getattr(self, "_refresh_at", 0.0) < REFRESH_GAP:
            return False
        try:
            idx = int(self.idx) % len(files)
        except Exception:
            idx = 0
        pm = self._decode(files[idx], h, self._clip_size(clip))
        if pm is None:
            return False
        # 顺手写回缓存：不然下一帧 _frame_fresh 又按同一高度解一遍（白干一倍）
        try:
            frames = self.cache.get("frames") or []
            if idx < len(frames):
                frames[idx] = pm
        except Exception:
            pass
        self._pix = pm
        self._next_pix = None
        self._blend = 0.0
        self._refresh_h = h
        self._refresh_at = time.perf_counter()
        try:
            self.pet.update()
        except Exception:
            pass
        return True

    def clip_dy(self, clip=None):
        """这段动作的垂直补偿（输出画布像素，负数=往上提）。

        每段素材的构图基线不一样：「大口吃零食」坐着吃，脚底比别的段低 18px；
        「被拎起来」「荡秋千」本来就腾空，清单里 dy=0。
        由 `_build/anim_offsets.py` 量出来写进 manifest，缺省 0。
        """
        name = clip or self.clip
        try:
            return int((self.manifest.get("clips", {}).get(name) or {}).get("dy", 0) or 0)
        except Exception:
            return 0

    def _manifest_size(self):
        """素材原始画面尺寸 (w, h)，用来算等比缩放后的宽度。"""
        try:
            w, h = self.manifest["size"]
            return int(w), int(h)
        except Exception:
            return 209, 270

    def _clip_size(self, clip):
        """某段动作自己的画布尺寸 (w, h)。

        2026-10-24 起每段动作有独立裁剪框（道具伸出老统一框的段不再被裁），
        宽度各不相同；清单里没写尺寸的老素材退回全局 size。
        """
        try:
            w, h = (self.manifest.get("clips") or {})[clip]["size"]
            return int(w), int(h)
        except Exception:
            return self._manifest_size()

    def canvas_size(self):
        """当前动作的画布尺寸 —— 桌宠算窗口宽度用（窗口跟着动作宽窄走）。"""
        if self.clip:
            return self._clip_size(self.clip)
        return self._manifest_size()

    def max_canvas(self):
        """所有动作里最宽的那块画布。

        2026-10-25 起窗口宽度**固定**用它，不再跟着当前动作变 ——
        换动作时改窗口宽度会让合成器把旧画面按新窗口左上角摆出去，
        实测在 240fps 录屏里是 2 帧、224px 的整体偏移（= Δw/2）。
        """
        best = self._manifest_size()
        try:
            for name in (self.manifest.get("clips") or {}):
                w, h = self._clip_size(name)
                if w > best[0]:
                    best = (w, h)
        except Exception:
            pass
        return best

    def clip_canvas(self, clip):
        """**别段**动作的画布尺寸（不切过去也能问）。

        走路编排要用：决定往哪走之前，得先知道「走路」这段的窗口该多宽，
        总不能为了问一句就先切过去播一下。
        """
        return self._clip_size(clip)

    def _decode(self, path, h, size):
        """按高度 h 解码一帧，宽度由该动作的画布宽高比算。

        用 QImageReader 直接让解码器输出目标尺寸，比"先解原图再 Smooth 缩放"
        快约 25%（实测 1.16ms vs 1.58ms/帧），而且边缘更干净。
        """
        tw, th = size
        w = max(1, int(round(tw * h / max(1, th))))
        r = QImageReader(path)
        r.setScaledSize(QSize(w, h))
        im = r.read()
        if im.isNull():
            return None
        return QPixmap.fromImage(im)

    def _load(self, clip):
        """把某个动作的帧读成 QPixmap（按当前显示高度缩放）。

        这是**同步**路径，只在第一次播某个动作时用（那时手上没帧可画）。
        改大小不走这里，走 `schedule_reload()`（分批、不阻塞）。
        """
        h = self._want_h()
        if self.cache.get("clip") == clip and self.cache.get("h") == h:
            return self.cache.get("frames") or []
        files = self._files_for(clip)
        if not files:
            return []
        size = self._clip_size(clip)
        frames = []
        for f in files:
            pm = self._decode(f, h, size)
            if pm is not None:
                frames.append(pm)
        # 只留一份，别的动作放掉
        self.cache = {"clip": clip, "h": h, "frames": frames}
        self._scaled_h = h
        self._pending = None
        self._next_pix = None
        self._blend = 0.0
        return frames

    def _want_h(self):
        """当前该按多高加载帧。

        优先问桌宠的 `_body_h()`：灵动版的画框留了余量（舞狮要举高、走路要飘），
        按画框高度等比缩放会让它比三视图小一圈，所以桌宠那边会乘一个补偿系数。
        桌宠没这个方法（老版本 / 单独测播放器）就退回 cur_h。
        """
        fn = getattr(self.pet, "_body_h", None)
        try:
            if callable(fn):
                return max(40, int(fn()))
        except Exception:
            pass
        try:
            return max(40, int(getattr(self.pet, "cur_h", 340)))
        except Exception:
            return 340

    @property
    def scaled_h(self):
        """缓存里那批帧是按多高缩放的（0 = 还没加载过）。"""
        return self._scaled_h

    @property
    def want_h(self):
        """当前应该用多高（桌宠大小决定，灵动版还乘了补偿系数）。"""
        return self._want_h()

    @property
    def has_pending(self):
        """是不是正在后台重排帧。"""
        return self._pending is not None

    def needs_reload(self, tol=0.06):
        """缓存高度和当前目标差得够多吗（差得少就别重排，浪费）。"""
        if not self._scaled_h:
            return False
        return abs(self._want_h() - self._scaled_h) > max(3, self._scaled_h * tol)

    def schedule_reload(self):
        """按新的显示高度重排帧 —— **不阻塞**，分批解码，解完整体换上去。

        旧代码在这里同步重载全部 241 帧，实测 250~315ms，而且拖滑块时每动一格
        就跑一遍，所以整段拖动都是顿的（2026-10-23 主人报的卡顿，就是这个）。
        现在改成：尺寸立刻生效（绘制时按目标高度缩放），帧慢慢补上来。
        补的过程中画面完全没变化，只是越补越清晰。
        """
        if not self.clip:
            return False
        h = self._want_h()
        if self._pending is not None:
            if self._pending["clip"] == self.clip and self._pending["h"] == h:
                return False                    # 已经在按这个高度排了
        if self._scaled_h and abs(h - self._scaled_h) <= 2:
            return False                        # 已经就是这个尺寸，别折腾
        return self._start_pending(self.clip, h)

    def _start_pending(self, clip, h, append=False):
        """开一批后台解码任务。

        `append=True`：解出来的帧直接往当前 cache 里塞（换动作用）——
                       第一帧到手就能开始播，边播边补齐，不用等 241 帧全解完。
        `append=False`：解到另一份列表里，全部好了再整体换（改尺寸用）——
                       这样播放不会被中途打断，旧尺寸的帧一直顶着。
        """
        files = self._files_for(clip)
        if not files:
            return False
        self._pending = {"clip": clip, "h": h, "files": files,
                         "size": self._clip_size(clip),
                         "frames": [], "i": 0, "append": append}
        if not self._reload_timer.isActive():
            self._reload_timer.start()
        return True

    def _pump_reload(self):
        """定时器回调：按**时间预算**解码，一次最多占主线程 RELOAD_BUDGET_MS。

        解码期间 `cache` 仍然是旧尺寸那批，照常播、照常画（绘制会缩放到目标大小），
        所以用户看不到任何跳变。
        """
        p = self._pending
        if p is None:
            self._reload_timer.stop()
            return
        if time.perf_counter() < self._hold_until:
            return                          # 用户在拖滑块：这批先不干，定时器留着
        if p["clip"] != self.clip:              # 中途换了动作，这批作废
            self._pending = None
            self._reload_timer.stop()
            return
        deadline = time.perf_counter() + RELOAD_BUDGET_MS / 1000.0
        budget = RELOAD_BATCH
        bucket = self.cache["frames"] if p.get("append") else p["frames"]
        while budget > 0 and p["i"] < len(p["files"]):
            path = p["files"][p["i"]]
            p["i"] += 1
            budget -= 1
            pm = self._decode(path, p["h"], p["size"])
            if pm is not None:
                bucket.append(pm)
            if time.perf_counter() >= deadline:
                break                           # 这一轮预算用完了，下个 tick 接着来
        if p["i"] < len(p["files"]):
            if p.get("append") and self._pix is None and self.cache.get("frames"):
                self._pix = self._frame()    # 第一帧一到就点亮，别等播放定时器那 16ms
            return                              # 还没排完，下个 tick 接着来
        if p.get("append"):
            # 换动作：帧是边播边补的，到这里就全齐了，什么都不用搬
            self._scaled_h = p["h"]
            self.idx = min(self.idx, max(0, len(self.cache["frames"]) - 1))
            if self._pix is None:
                self._pix = self._frame()
            self._advance()             # 立刻对一次时间轴（可能已经"播完"了，要收尾）
            if not self._timer.isActive():
                self._schedule_next()   # 兜底：万一播放定时器停了，接着播
        elif p["frames"]:
            self.cache = {"clip": p["clip"], "h": p["h"], "frames": p["frames"]}
            self._scaled_h = p["h"]
            self.idx = min(self.idx, len(p["frames"]) - 1)
            self._pix = self._frame()
            self._next_pix = None
            self._blend = 0.0
            self._advance()                     # 换完缓存后立刻按时间轴对齐一次
        self._pending = None
        self._reload_timer.stop()
        try:
            self.pet.update()
        except Exception:
            pass

    def cancel_reload(self):
        self._pending = None
        self._reload_timer.stop()

    def rescale(self):
        """兼容旧调用：等价于 schedule_reload()（同步版已删，别再阻塞主线程）。"""
        return self.schedule_reload()

    # ---------------------------------------------------------------- 播放
    def play(self, clip, loop=True, restart=False, rate=None):
        """切一段动作开播。`rate` 是播放倍速（None = 1.0，每次切动作都重置）。"""
        if clip not in (self.manifest.get("clips") or {}):
            return False
        self._range = None             # 普通播放 = 整段
        self._dir_step = 1
        self._fx_from = None           # 换动作不做淡入（新动作本来就是硬切，淡入反而糊）
        self.rate = 1.0 if not rate else max(0.25, min(4.0, float(rate)))
        if clip == self.clip and not restart:
            if not self._timer.isActive():
                self._schedule_next()
            return True

        want = self._want_h()
        has_it = (self.cache.get("clip") == clip and self.cache.get("h") == want)

        if not has_it:
            # 新动作走"边播边解"：第一帧到手就开始播（约 20ms），后台继续补后面的。
            # 241 帧 × 2.6ms ≈ 0.6 秒的解码活全在后台干，切动作、首次加载都不卡。
            # 手上有旧画面就先顶着（绘制时会缩放到目标高度，看不出跳变）；
            # 首次加载没有旧画面，也就空白十几毫秒，随后第一帧一到就开演。
            self.clip, self.idx, self.loop = clip, 0, loop
            self.cache = {"clip": clip, "h": want, "frames": []}
            self._scaled_h = want
            self._next_pix = None
            self._blend = 0.0
            self._t0 = time.perf_counter()
            self._notify_clip_changed()
            if self._start_pending(clip, want, append=True):
                self._schedule_next()
                return True
            # 后台起不来（素材缺失）就退回同步

        if not self._load(clip):
            return False
        self.clip, self.idx, self.loop = clip, 0, loop
        self._t0 = time.perf_counter()      # 时间轴原点：帧号一律由它算，不靠"加一"
        self._notify_clip_changed()
        self._pix = self._frame()
        self._schedule_next()               # 单次触发的定时器，每次自己算下次唤醒时刻
        try:
            self.pet.update()
        except Exception:
            pass
        return True

    def play_range(self, clip, start, end, loop=False, rate=None, step=1):
        """只播 `clip` 的 [start, end] 这几帧（2026-10-25：原地转头做过渡用）。

        为什么需要它：`idle` 那 241 帧里"正面 → 看左 → 正面 → 看右"是按顺序排的，
        直接换 clip 会硬切。用帧区间就能"顺着这段走过去"，看着是转身不是跳帧。

        `step=-1` = **倒着播**（end → start）。"一直看着左边"就是靠来回播实现的：
        那段素材的首尾差是相邻帧的 9.7 倍，直接循环 → 每 1 秒画面跳一下（主人报的卡顿感）；
        来回播每一帧都前后连续，压根没有跳变。

        ⚠️ 已经在同一段素材上时**不走 `play()`**：`play()` 会调
        `_notify_clip_changed()` → 桌宠重排窗口 / 夹屏，可这会儿窗口尺寸一点没变，
        白折腾一趟就是画面一跳（原地转头时会被看成"抽搐"）。这里只换播放区间。
        """
        if clip not in (self.manifest.get("clips") or {}):
            return False
        total = len(self._files_for(clip)) or 0
        if (self.clip != clip) or not (self.cache.get("frames")):
            if not self.play(clip, loop=loop, restart=True, rate=rate):
                return False
        else:
            # 同一段素材：只改播放区间（和倍速 / 是否循环），不惊动桌宠
            self.rate = 1.0 if not rate else max(0.25, min(4.0, float(rate)))
            self.loop = loop
        r0 = max(0, int(start))
        r1 = max(r0, int(end))
        if total:
            r1 = min(r1, total - 1)
        self._range = (r0, r1)
        self._dir_step = -1 if step < 0 else 1
        self._t0 = time.perf_counter()          # 从区间头开始算
        self._idx_in_range()
        self._schedule_next()
        try:
            self.pet.update()
        except Exception:
            pass
        return True

    def begin_xfade(self, ms=150):
        """（已停用，2026-10-25 第十九轮）

        原来在"跳帧多"的时候叠 0.15 秒淡入，想掩盖硬切。**实测不行**：
        `idle` 的相邻帧差只有 4.35，而 fade 期间旧帧 + 新帧同时可见 ——
        主人 240fps 录屏里看到的就是「重叠帧」（鱼的下边缘在两个高度之间跳：
        1.050s bot 250→270、1.092s 又回 250，那就是两张图的并集）。
        现在一律硬切 + 接帧（`seek`），不再叠图。
        """
        return

    def xfade(self):
        """（已停用，见 `begin_xfade`。）"""
        return None, 0.0

    def seek(self, idx):
        """整段循环时"从第 idx 帧接着播"。

        给"转回正面"用：过渡段停在 (115~145) 的最后一帧，回来时要是从第 0 帧重播，
        画面会**跳一下**（145 → 1）。把时间轴原点往前挪，就等于"接着那一帧往下播"，
        而且仍然是整段 idle 的循环（不会播着播着断掉）。
        """
        frames = self.cache.get("frames") or []
        if not frames or self._range is not None:
            return False
        n = len(frames)
        idx = max(0, min(int(idx), n - 1))
        rate = self.fps * ANIM_SUBFRAMES * self.rate
        self._t0 = time.perf_counter() - idx / max(1e-6, rate)
        self._advance()
        self._schedule_next()
        return True

    def replay_silent(self, clip, loop=True):
        """在同一段素材上重播，**但不通知桌宠重排窗口**。

        为什么需要（2026-10-25 主人报「原地跟鼠标转头时整体错位一下」）：
        `play(restart=True)` 会调 `_notify_clip_changed()` → 桌宠那边算窗口尺寸、夹屏、
        必要时 `move()` 一下。可原地转头时**窗口尺寸一点没变**（灵动版宽度固定、高度各段
        都一样），这一趟纯属白折腾，代价就是画面错位一帧。
        """
        if clip not in (self.manifest.get("clips") or {}):
            return False
        if self.clip != clip or not (self.cache.get("frames")):
            return self.play(clip, loop=loop, restart=True)   # 真换了素材，该重排就重排
        self.rate = 1.0
        self._range = None
        self._dir_step = 1
        self._fx_from = None        # 重播不做淡入（本来就是同一段素材）
        self.loop = loop
        self.idx = 0
        self._t0 = time.perf_counter()
        self._pix = self._frame()
        self._next_pix = None
        self._blend = 0.0
        self._schedule_next()
        try:
            self.pet.update()
        except Exception:
            pass
        return True

    def _range_span(self):
        """当前播放的帧区间 (r0, r1, 长度)。没有区间就是整段。"""
        frames = (self.cache.get("frames") or [])
        n = len(frames)
        total = (len(self._files_for(self.clip)) if self.clip else n) or n or 1
        if self._range:
            r0, r1 = self._range
            r1 = min(r1, total - 1)
        else:
            r0, r1 = 0, total - 1
        r0 = max(0, min(r0, total - 1))
        r1 = max(r0, r1)
        return r0, r1, (r1 - r0 + 1)

    def _idx_in_range(self):
        r0, r1, _span = self._range_span()
        self.idx = r0 if self._dir_step > 0 else r1
        # ⚠️ 2026-10-25：**别把 `_pix` 清成 None**。
        # `play_range` 末尾会 `pet.update()`，paintEvent 拿到 `anim_pix=None`
        # 就落到三视图那条分支去画精灵图 —— 那是一张大小/位置完全不同的图，
        # 表现就是「闪一帧别的鱼」（主人 240fps 录屏里 0.854~0.892s 那 38ms）。
        # 立刻取新帧；万一还没解出来（后台在补），就保留上一帧顶着。
        frame = self._frame()
        if frame is not None:
            self._pix = frame
        self._next_pix = None

    def stop(self):
        self._timer.stop()

    def _notify_clip_changed(self):
        """告诉桌宠"换动作了"：每段动作画布宽度不同，窗口要跟着重排。

        桌宠那边没有这个方法（老版本 / 单独测播放器）就什么都不做。
        """
        fn = getattr(self.pet, "_anim_clip_changed", None)
        if callable(fn):
            try:
                fn()
            except Exception as exc:
                print("[anim] 换动作后重排窗口失败:", exc)

    def is_playing(self, clip=None):
        return (self.clip == clip) if clip else (self.clip is not None)

    def current(self):
        return self._pix

    def draw_state(self):
        """给 paintEvent 用：(当前帧, 下一帧或 None, 混合权重)。

        不启用插值时第二项是 None，调用方只画一张，等价于原来的行为。
        """
        return (self._pix, self._next_pix, self._blend)

    # ---------------------------------------------------------------- 每帧
    def _frame_fresh(self, frames, i):
        """取第 i 帧；正在拖大小滑块（hold 期内）就现解一张新尺寸的顶上。

        不解的话，整段拖动都在拿旧高度的图硬放大 —— 发虚、看着像掉帧。
        一帧 2~3ms、24fps 下约占 7% 主线程，比"整批重排 1.5 秒"轻得多。
        """
        pm = frames[i]
        if pm is None:
            return None
        now = time.perf_counter()
        # 拖滑块时这里最多每 REFRESH_GAP 秒重解一张。间隔怎么定的：
        # 太短（每步都解）会把每步耗时顶到 7ms，反而更顿；太长（60ms）帧会落后
        # 六七十像素，看得见"糊一下突然变清晰"。35ms ≈ 每 2 帧刷一张，
        # 一帧 2~3ms 摊下来约 8% 主线程，滞后压到三十来像素。
        if now < self._hold_until and now - getattr(self, "_refresh_at", 0.0) >= REFRESH_GAP:
            want = self._want_h()
            if want and abs(pm.height() - want) > 8:
                files = self._files_for(self.clip)
                if files and i < len(files):
                    t_decode = time.perf_counter()
                    fresh = self._decode(files[i], want, self._clip_size(self.clip))
                    if fresh is not None:
                        frames[i] = fresh
                        pm = fresh
                    self._refresh_at = t_decode
        return pm

    def _frame(self):
        frames = (self.cache.get("frames") or [])
        if not frames:
            return None
        return self._frame_fresh(frames, self.idx % len(frames))

    def _advance(self):
        """按**真实时间**推进到该显示的帧，返回是否换了帧。

        为什么不用"每 tick 加一"：定时器根本不可能精确到 41.666ms，Windows 的
        CoarseTimer 还会往后拖（实测 41ms 的间隔跑成了 47ms、平均只有 21fps，
        偶尔还掉一帧 88ms）。改成按 elapsed × fps 算帧号之后，
        晚了就跳过、早了就等，长期平均正好是 24fps，也不会累积漂移。
        """
        frames = (self.cache.get("frames") or [])
        if not frames:
            return False                        # 还在解第一帧：保持上一帧不动
        n = len(frames)
        loading = self._pending is not None
        r0, r1, span = self._range_span()
        # 这段动作**总共有多少帧**（不是"已经解到多少帧"）。
        # ⚠️ 2026-10-25：循环播放必须用总帧数取模。原来直接拿已解帧数 `n` 判断
        # `raw >= n` 就"停在最后一帧"，而 raw 是无限增长的 —— 于是**每段循环动作
        # 播完一圈就卡在最后一帧不动**，点别的动作（重置时间轴）才恢复。
        # 主人报的「动画卡住了一次，点了其他动作恢复」就是它（idle 241 帧 @24fps ≈ 10 秒）。
        total = len(self._files_for(self.clip)) if self.clip else n
        if total <= 0:
            total = n
        rate = self.fps * ANIM_SUBFRAMES * self.rate   # 每秒推进多少个"格子"
        pos = (time.perf_counter() - self._t0) * rate
        sub = int(pos)
        raw = sub // ANIM_SUBFRAMES               # 想显示第几帧（可能超出已解到的）
        if not self.loop and raw >= span and not loading:
            # 播完了：停在**区间最后一帧**（倒着播就停在区间第一帧）
            last = max(0, min(r1 if self._dir_step > 0 else r0, n - 1))
            changed = self.idx != last
            self.idx = last
            self._blend = 0.0
            self._pix = self._frame_fresh(frames, last)
            self._next_pix = None
            if changed:
                self._repaint()
            self._timer.stop()
            self._on_finished()
            return changed
        off = raw % span
        i = (r0 + off) if self._dir_step > 0 else (r1 - off)
        if i >= n:
            # 这一帧还没解到（边播边解）：先停在已解到的最后一帧，等下一批
            i, blend, nxt = n - 1, 0.0, None
        else:
            if ANIM_SUBFRAMES > 1:
                blend = (pos - sub) / ANIM_SUBFRAMES        # 0 ~ 1/SUBFRAMES
            else:
                blend = 0.0
            nxt = frames[(i + 1) % n] if blend > 0.0 else None
        changed = (i != self.idx) or (nxt is not self._next_pix)
        self.idx = i
        self._pix = self._frame_fresh(frames, i)
        self._next_pix = nxt
        self._blend = blend
        return changed

    def _repaint(self):
        try:
            self.pet.update()          # 只重画，不动别的
        except Exception:
            self._timer.stop()

    def _schedule_next(self):
        """定下一次唤醒：**正好落在下一帧的边界上**（而不是固定间隔轮询）。

        固定间隔轮询有个躲不掉的问题：真实边界在 41.67ms，而 tick 在 39/52ms，
        于是帧间隔一会儿 39 一会儿 52（实测 σ≈10ms），看起来就是一跳一跳的。
        改成"每次算到下一帧边界还差多少毫秒"，误差只有一个定时器精度（1~2ms），
        而且每次都从当前时钟重新算，不会累积漂移。
        """
        frames = (self.cache.get("frames") or [])
        if not frames or not self.clip:
            if self._pending is not None:
                self._timer.start(16)    # 第一帧还在后台解，稍后再来看（不然就永远不播了）
            return
        n = len(frames)
        _r0, _r1, span = self._range_span()
        rate = self.fps * ANIM_SUBFRAMES * self.rate
        pos = (time.perf_counter() - self._t0) * rate
        # 单次播完的判定用**当前区间长度**（和 `_advance` 一致）。
        if not self.loop and pos >= span * ANIM_SUBFRAMES and self._pending is None:
            return                      # 单次播完了，_advance 里已经收尾
        # ↑ 注意 pending 还在解时**不能**提前撒手：等帧补齐后得有人把定时器再拉起来，
        #   否则一次性动作播到"已解到的最后一帧"就永远停那儿（实测踩过）。
        whole = int(pos)
        remain = (whole + 1 - pos) / rate              # 到下一个边界还有多久（秒）
        ms = int(round(remain * 1000.0))
        self._timer.start(max(1, min(100, ms)))

    def _step(self):
        changed = self._advance()
        if changed:
            self._repaint()
        self._schedule_next()           # 单次播完时 _advance 已把定时器停掉，这里不会再起

    def _on_finished(self):
        """单次播放结束 → 回到该回的状态。"""
        try:
            self.pet._anim_after_once(self.clip)
        except Exception:
            pass


class AnimExtension:
    """把播放器挂到桌宠上，并提供"什么时候播什么"的判断。"""

    IDLE = "idle"
    MOVE = "move"
    LION = "lion"
    WAVE = "wave"

    def __init__(self, pet):
        root = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "sprites_anim")
        self.pet = pet
        self.root = root
        self.player = AnimPlayer(pet, root)
        self.available = bool(self.player.manifest.get("clips"))
        self._last_mode = None

    # --- 生命周期
    def start(self):
        if not self.available:
            print("[anim] 没找到 sprites_anim/manifest.json，灵动版不可用")
            return self
        # 顺着主循环看状态：待机 / 走路 自动切换
        self._timer = QTimer(self.pet)
        self._timer.timeout.connect(self._sync)
        self._timer.start(200)
        print(f"[anim] 灵动版素材就绪：{self.player.clips()}")
        return self

    def _sync(self):
        """根据桌宠当前状态决定循环播哪个（只在灵动模式下）。"""
        if not self._is_anim_skin():
            if self.player.is_playing():
                self.player.stop()
            return
        # 兜底：万一哪条改大小的路没通知到，这里发现尺寸漂了也补一次。
        # 注意别在"已经排上队"时再来一次 —— 200ms 的 _sync 会把 260ms 的防抖
        # 一次次往后推，永远等不到触发（这个坑实测踩到过）。
        if (self.player.clip and self.player.needs_reload(tol=0.10)
                and not self.reload_scheduled):
            self.schedule_reload_soon()
        busy = self.player.clip in self.once_clips()
        if busy:
            return                        # 一次性动作正在播，别打断
        # 桌宠正在"走过去"（换动作 / 回原位）：这期间它自己管播放，别插嘴 ——
        # 否则 _sync 每 200ms 一次会把走路切回待机，最后一段变成"站着滑"。
        if getattr(self.pet, "_anim_walking", False):
            return
        # 散步 / 跟随的「螃蟹走路」三段（`_amb_phase`）由 PetWindow 那条路管，这里别插嘴：
        # 否则 200ms 一到就把 crab 切回正面 `move` —— 实测散步时只有那一瞬间能看见转身。
        if getattr(self.pet, "_amb_phase", None) is not None:
            return
        # 「原地待着 + 跟鼠标转」时是**侧身站姿**（crab_in 的最后一帧停住），
        # 别按 target 有没有把它顶回正面待机。
        if getattr(self.pet, "_still_side", None):
            return
        walking = getattr(self.pet, "target", None) is not None
        want = self.MOVE if walking else self.IDLE
        if self.player.clip != want:
            self.player.play(want, loop=True)

    def schedule_reload_soon(self, delay_ms=RELOAD_DEBOUNCE_MS):
        """改大小后叫它重排帧，但**防抖**：拖滑块时会被连环调用，
        只在停手 delay_ms 之后才真正开始（不然一路拖一路排，白烧 CPU）。
        """
        if not hasattr(self, "_reload_debounce"):
            self._reload_debounce = QTimer(self.pet)
            self._reload_debounce.setSingleShot(True)
            self._reload_debounce.timeout.connect(self._do_reload)
        self._reload_debounce.start(delay_ms)

    @property
    def reload_scheduled(self):
        """是不是已经有一个"稍后重排"在等（正在等防抖，或者正在解码）。"""
        if self.player.has_pending:
            return True
        timer = getattr(self, "_reload_debounce", None)
        return bool(timer is not None and timer.isActive())

    def _do_reload(self):
        if self._is_anim_skin():
            self.player.schedule_reload()

    def _is_anim_skin(self):
        """以桌宠自己的 `skin` 为准（set_skin 会同步改它），不看 cfg 里可能过期的值。"""
        try:
            return getattr(self.pet, "skin", "") == ANIM_SKIN
        except Exception:
            return False

    def on_skin_changed(self):
        """切到灵动版就开播待机，切走就停掉帧动画。"""
        if not self.available:
            return
        if self._is_anim_skin():
            self.player.play(self.IDLE, loop=True, restart=True)
        else:
            self.player.stop()

    # --- 给右键菜单 / 交互用
    def play_once(self, clip):
        if not self._is_anim_skin():
            return False
        return self.player.play(clip, loop=False, restart=True)

    def random_once(self):
        """'逗她一下'：在当前可用的一次性动作里随机挑一个。"""
        pool = self.once_clips()
        if not pool:
            return False
        import random
        return self.play_once(random.choice(pool))

    def once_clips(self):
        """当前素材里真正可用的一次性动作 key 列表（清单里除了 idle/move 的全部）。

        顺序就是 manifest 里的顺序 —— 菜单照这个顺序排，想让某个动作靠前就调清单顺序。
        """
        return [c for c in self.player.clips() if c not in LOOP_CLIPS]

    def clip_dy(self, clip=None):
        """这段动作的垂直补偿（输出画布像素，负数=往上提）。

        每段素材的构图基线不一样：「大口吃零食」坐着吃，脚底比别的段低 15px；
        「被拎起来」「荡秋千」本来就腾空，清单里 dy=0。
        由 `_build/anim_offsets.py` 量出来写进 manifest，缺省 0。
        """
        name = clip or self.clip
        try:
            return int((self.manifest.get("clips", {}).get(name) or {}).get("dy", 0) or 0)
        except Exception:
            return 0

    def clip_canvas(self, clip):
        """某段动作的画布尺寸 —— 转发给播放器（走路编排要先问「走路」多宽）。"""
        return self.player.clip_canvas(clip)

    def icon_for(self, clip):
        """这个动作在菜单里用哪个图标（没登记就空串 → 调用方继承父项）。"""
        return CLIP_ICONS.get(clip, "")

    def once_choices(self):
        """给菜单用：[("舞狮头", "lion"), ...]，素材缺的自动不出现。"""
        names = self.player.manifest.get("clips") or {}
        out = []
        for c in self.once_clips():
            label = (names.get(c) or {}).get("name") or CLIP_LABELS.get(c) or c
            out.append((label, c))
        return out


def setup(pet):
    return AnimExtension(pet).start()
