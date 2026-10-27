# -*- coding: utf-8 -*-
"""工作与休息提醒（GitHub issue #3）：久坐提醒 + 喝水提醒。

背景（这条得写在最前面，不然下一个改的人会把它做成番茄钟）：
    主人 2026-09-14 亲手删过番茄钟 ——「番茄钟这个功能好鸡肋，删了」。
    但 issue #3 里有人需要"久坐提醒 / 喝水提醒"。所以这个功能的定位是：

      **默认关着**（`rest_reminder.on` 不写就是 False），
      设置 → 应用联动 → 工作与休息 里那个开关打开才计时；
      关着的时候它一步都不走、一句话都不说，对不喜欢的人等于不存在。

    刻意不做成番茄钟：没有倒计时窗口、没有开始/暂停、没有"专注"概念，
    只在"该起来动动"和"该喝水"的时候说一句，其余时间完全安静。

三条实现上的取舍：
  1. **人不在就当休息过了**：键鼠静 `away_min`（默认 3 分钟）以上，
     工作 / 喝水计时一起清零。番茄钟最烦人的地方就是"我去开个会它还在数"。
  2. **说话走 `pet._say_reminder()`**：免打扰 / 全屏游戏期间自动攒着，
     结束后统一汇总 —— 和「应用启动 / 用久了 / 定时」那几条提醒完全一致，
     不另开一条会跟它们抢气泡的通道。
  3. **纯逻辑抽在 `step(dt, idle)`**：不碰 Qt、不碰窗口，
     `_test/test_rest_reminder.py` 用假时钟能把一整天的作息跑完。

配置（`config.json` 的 `rest_reminder`，缺键就用 DEFAULTS）::

    {"on": false, "work_min": 45, "break_min": 5,
     "water_on": true, "water_min": 60, "away_min": 3}
"""

from __future__ import annotations

import random
import sys
import time

# 默认值：不写进 config.json 也能跑（老配置里根本没有这个键）
DEFAULTS = {
    "on": False,          # 默认关 —— 谁需要谁打开（见模块开头的背景）
    "work_min": 45,       # 连续用电脑多少分钟提醒起来动动
    "break_min": 5,       # 提醒之后安静多少分钟（这段时间不再提醒）
    "water_on": True,     # 喝水提醒（总开关打开时才有效）
    "water_min": 60,      # 多久提醒喝一次水
    "away_min": 3,        # 键鼠静这么久就算"人离开了"，回来重新计时
}

POLL_MS = 5000            # 每 5 秒喂一次时钟：够准，也不占 CPU
MAX_DT = 20.0             # 单次最多补 20 秒（睡了一觉 / 卡住就别补计时了）


def _idle_seconds():
    """键鼠静了多久（秒）；拿不到就返回 None。

    优先借主程序那份 `idle_seconds()`（同一套 Win32 调用，别写两份），
    单测 / 脱离主程序跑的时候再自己调一次。
    """
    for name in ("__main__", "桌宠"):
        mod = sys.modules.get(name)
        fn = getattr(mod, "idle_seconds", None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                break
    try:
        import ctypes
        from ctypes import wintypes

        class _LastInput(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = _LastInput()
        info.cbSize = ctypes.sizeof(_LastInput)
        if not ctypes.WinDLL("user32.dll").GetLastInputInfo(ctypes.byref(info)):
            return None
        tick = ctypes.WinDLL("kernel32.dll").GetTickCount()
        return max(0.0, ((tick - info.dwTime) & 0xFFFFFFFF) / 1000.0)
    except Exception:
        return None


def _as_int(value, default, low, high):
    """配置里的数字：类型不对 / 超范围都夹回来（手改 config.json 也不会疯）。"""
    try:
        got = int(float(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, got))


class RestReminder:
    """久坐 / 喝水计时器。挂到 `pet.ext["rest"]` 上。"""

    def __init__(self, pet, now_fn=None, idle_fn=None):
        self.pet = pet
        self.now_fn = now_fn or time.monotonic
        self.idle_fn = idle_fn or _idle_seconds
        self._timer = None
        self._last = None
        self._work = 0.0        # 这一轮连续用了多久（秒）
        self._water = 0.0       # 距离上次喝水提醒过了多久（秒）
        self._break_left = 0.0  # 休息还剩多久（秒，0 = 没在休息）
        self._said_at = {}      # 上一次说某类提醒的时刻（调试 / 自测用）

    # ---------------- 生命周期 ----------------
    def start(self):
        from PySide6.QtCore import QTimer
        self._timer = QTimer(self.pet)
        self._timer.timeout.connect(self.poll)
        self._timer.start(POLL_MS)
        self._last = self.now_fn()
        return self

    def stop(self):
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    # ---------------- 配置 ----------------
    def opts(self):
        """现读配置（每 5 秒读一次，改设置立刻生效，不用重启）。"""
        box = self.pet.cfg.get("rest_reminder")
        if not isinstance(box, dict):
            box = {}
        got = dict(DEFAULTS)
        for key in DEFAULTS:
            if key in box:
                got[key] = box[key]
        got["on"] = bool(got["on"])
        got["water_on"] = bool(got["water_on"])
        got["work_min"] = _as_int(got["work_min"], DEFAULTS["work_min"], 1, 600)
        got["break_min"] = _as_int(got["break_min"], DEFAULTS["break_min"], 1, 120)
        got["water_min"] = _as_int(got["water_min"], DEFAULTS["water_min"], 5, 600)
        got["away_min"] = _as_int(got["away_min"], DEFAULTS["away_min"], 1, 120)
        return got

    @property
    def enabled(self):
        return bool(self.opts()["on"])

    def on_option_changed(self, key, value):
        """设置窗口改了一项。开着的时候从"现在"重新算，别把改之前的时间算进去。"""
        if key == "on":
            self.reset()
            if value:
                self._last = self.now_fn()

    def reset(self):
        """重新计时（换设置 / 手动「重新计时」都走这儿）。"""
        self._work = self._water = self._break_left = 0.0
        self._last = self.now_fn()

    # ---------------- 计时（纯逻辑）----------------
    def step(self, dt, idle=None):
        """喂一段时间，返回这次该说的提醒：`[]` / `["rest"]` / `["water"]`。

        不碰 Qt、不碰窗口 —— 自测就是拿这个函数把一天的作息跑一遍。
        """
        o = self.opts()
        if not o["on"]:
            self._work = self._water = self._break_left = 0.0
            return []
        if dt <= 0:
            return []
        if idle is None:
            idle = 0.0
        # 人不在电脑前：当作已经休息过了，回来重新计时
        if idle >= o["away_min"] * 60:
            self._work = self._water = self._break_left = 0.0
            return []
        # 休息中：不提醒，时间到了重新开始算
        if self._break_left > 0:
            self._break_left = max(0.0, self._break_left - dt)
            if self._break_left == 0:
                self._work = self._water = 0.0
            return []
        self._work += dt
        self._water += dt
        if self._work >= o["work_min"] * 60:
            self._work = 0.0
            self._water = 0.0
            self._break_left = float(o["break_min"] * 60)
            self._said_at["rest"] = self.now_fn()
            return ["rest"]
        if o["water_on"] and self._water >= o["water_min"] * 60:
            self._water = 0.0
            self._said_at["water"] = self.now_fn()
            return ["water"]
        return []

    def poll(self):
        """定时器回调：算这一段时间，然后把该说的话说出去。"""
        now = self.now_fn()
        if self._last is None:
            self._last = now
            return
        dt = min(max(0.0, now - self._last), MAX_DT)
        self._last = now
        # 关着的时候连 idle_seconds() 都不调：那是一次 Win32 调用，
        # 不喜欢这个功能的人不该为它付任何代价。
        if not self.enabled:
            return
        for kind in self.step(dt, self.idle_fn()):
            self.speak(kind)

    # ---------------- 说话 ----------------
    def speak(self, kind):
        """说一句提醒。台词走 `lines_for_say`：整块被关掉 / 用户清空就不出声。"""
        key = "REST_LINES" if kind == "rest" else "WATER_LINES"
        try:
            words = self.pet.lines_for_say(key) or []
        except Exception:
            words = []
        if not words:
            return
        try:
            self.pet._say_reminder(random.choice(words))
        except Exception as exc:
            print("[rest] 提醒没说出来:", exc)

    # ---------------- 手动 / 状态 ----------------
    def breaking(self):
        return self._break_left > 0

    def start_break(self, minutes=None):
        """「现在休息一下」：手动开始一段休息（这段时间内不再提醒）。"""
        o = self.opts()
        mins = _as_int(minutes if minutes is not None else o["break_min"],
                       o["break_min"], 1, 120)
        self._work = self._water = 0.0
        self._break_left = float(mins * 60)
        try:
            self.pet.say(f"好，我安静 {mins} 分钟，到点叫你", seconds=3.0, again=True)
        except Exception:
            pass
        return mins

    def end_break(self):
        self._break_left = 0.0
        self.reset()

    def status_text(self):
        """设置卡片下面那行小字：现在到底在不在计时。"""
        o = self.opts()
        if not o["on"]:
            return "关着（不提醒）。要用就打开上面那个开关。"

        def mins(sec):
            """剩多少分钟（向上取整）：45:00 就是 45，不是 46。"""
            return max(0, -(-int(sec) // 60))

        if self._break_left > 0:
            return f"正在休息，还有约 {mins(self._break_left)} 分钟；休息完重新计时。"
        work_left = max(0, o["work_min"] * 60 - self._work)
        parts = [f"已连续用 {int(self._work // 60)} 分钟，"
                 f"还有约 {mins(work_left)} 分钟提醒你起来动动"]
        if o["water_on"]:
            water_left = max(0, o["water_min"] * 60 - self._water)
            parts.append(f"喝水还有约 {mins(water_left)} 分钟")
        return "；".join(parts) + "。"


def setup(pet):
    """桌宠启动时被 `pet_ext.load_extensions` 调到。"""
    return RestReminder(pet).start()


# ---------------------------------------------------------------- 自测
if __name__ == "__main__":
    class _FakePet:
        def __init__(self):
            self.cfg = {"rest_reminder": {"on": True}}
            self.said = []

        def lines_for_say(self, key):
            return ["台词"]

        def _say_reminder(self, text):
            self.said.append(text)

        def say(self, *a, **k):
            pass

    clock = [0.0]
    fp = _FakePet()
    rr = RestReminder(fp, now_fn=lambda: clock[0], idle_fn=lambda: 0.0)
    got = []
    for _ in range(int(50 * 60 / 5)):       # 50 分钟，每 5 秒一步
        clock[0] += 5.0
        got += rr.step(5.0, 0.0)
    print("50 分钟里该说的:", got)
