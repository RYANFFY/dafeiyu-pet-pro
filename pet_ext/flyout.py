# -*- coding: utf-8 -*-
"""侧边浮窗（P4）：聊天（P5）和派活（P6）共用的那块"从桌宠旁边滑出来"的板子。

为什么必须是独立窗口，而不是把桌宠窗口加宽：
    桌宠窗口是「无边框 + 半透明 + 置顶」，加宽之后**透明的侧边区域照样拦截鼠标**，
    底下那个窗口就点不到了。要做区域遮罩能行，但很难调（见 `三项功能可行性评估.md` 2.1）。
    所以做成独立 frameless 窗口贴在旁边，跟 `_flyout`（二级菜单那套自研浮窗）是同一个思路。

这一版只做骨架（主人 2026-10-26 交代的顺序是 P4 → P5 → P6）：
    ✅ 圆角卡片 + 标题栏 + 关闭按钮 + Esc
    ✅ 消息区（可滚动，长回复装得下）
    ✅ 输入框 + 发送（`set_send_handler` 挂真正的处理函数）
    ✅ 从桌宠旁边滑出来 / 滑回去，跟着桌宠走，贴边时自动换到另一侧
    ⬜ 真正的聊天通道（P5 接 DeepSeek）
    ⬜ 拖文件派活（P6 接 Agent）

对外接口（P5 / P6 只用这几个，别直接摸控件）：
    ext.show(title="和她聊聊")      打开（没建就建）
    ext.hide()                      收起
    ext.toggle()                    开关
    ext.add("me" | "her" | "note", text)   往消息区加一条
    ext.clear()                     清空
    ext.set_busy(True / False)      "她正在想…"：输入框禁用
    ext.set_send_handler(fn)        用户按回车 / 点发送时调 fn(text)
    ext.set_title(text)             改标题
"""

from __future__ import annotations

from PySide6.QtCore import (Property, QEasingCurve, QEvent, QParallelAnimationGroup, QPoint,
                            QPropertyAnimation, QRect, QRectF, QSequentialAnimationGroup,
                            QSize, Qt, QTimer, Signal)
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout,
                               QLabel, QLayout, QLineEdit, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

try:                                    # 主题色跟设置窗口共用一套，别自己另配
    import ui_console
except Exception:                       # 界面模块没起来也要能用（退回一套中性色）
    ui_console = None


# 2026-10-26 主人：「窗口过于大了，和桌宠本身过于割裂」→ 从 404×520 收到 340×430，
# 并且和桌宠之间的空隙从 12 收到 4、加一个小尖角指着桌宠，看着是"长在鱼身上"的。
# 尺寸**跟着鱼走**：主人 2026-10-26 说"太大"，固定 340×430 对着一条两百来像素宽的鱼
# 确实压人。现在按鱼的宽高按比例算，再夹在下面这个范围里。
W_DEFAULT = 300          # 兜底宽（算不出来时用）
H_DEFAULT = 380          # 兜底高
W_MIN, W_MAX = 200, 340  # 宽度范围（跟着鱼**本体**走；200 是"鱼很小"时的下限）
H_MIN, H_MAX = 240, 420  # 高度范围
W_RATIO, H_RATIO = 1.45, 1.35   # 相对鱼的宽 / 高
MARGIN = 10              # 四周留白：画"假阴影"和尖角用，窗口本身是透明的
GAP = 2                  # 和**鱼**之间的空隙（兜底下限；实际按鱼身宽算，见 GAP_RATIO）
GAP_RATIO = 0.03         # 空隙 = 鱼身宽 × 3%（主人 2026-10-27：任何大小都要**恒定比例**的距离）
SLIDE_MS = 170           # 滑出 / 滑回时长
FOLLOW_MS = 60           # 跟随时重新对位的间隔
FOLLOW_EPS = 2           # 位置差这么点就别动了（省得每 60ms 都 move 一次）
MIN_W = 200              # 旁边放不下时最窄收这么宽（再窄输入框就不好用了）
RADIUS = 14.0            # 卡片圆角（正常状态）
MORPH_MS = 320           # 从圆形长成卡片的时间（240 有点急，主人说"太生硬"）
# 尖角（气泡尾巴）：2026-10-26 主人说"三角形和聊天框衔接不够自然"。
# 原来是三角形叠在卡片上：底边压在卡片内 1px、两条斜边各描一次线，卡片边框又横穿
# 尾巴根部 —— 接缝处两道线交叉，看着是"贴上去的贴纸"。现在和卡片**并成一条轮廓**
# （见 `_body_path`），填充和描边都只走外圈，根部再用微凹曲线过渡，是一整块。
TAIL_HALF = 7.0          # 根部半高（总高 14）
TAIL_DEPTH = 7.0         # 从卡片边缘往外伸多少（留 3px 给阴影，伸满 MARGIN 会把阴影裁掉）


def _fallback_tokens():
    """ui_console 没加载时的中性配色（亮色）。"""
    return {"surface": "#ffffff", "surface_alt": "#eef0f6", "border": "#dfe2ea",
            "text": "#1d2030", "text_dim": "#7b8093", "accent": "#3b7bf6",
            "accent_text": "#ffffff", "shadow": QColor(0, 0, 0, 45)}


def _blend(c1, c2, k):
    """把 c1 往 c2 混 k（0~1），返回 QColor。"""
    a, b = QColor(c1), QColor(c2)
    return QColor(int(a.red() + (b.red() - a.red()) * k),
                  int(a.green() + (b.green() - a.green()) * k),
                  int(a.blue() + (b.blue() - a.blue()) * k))


def tokens():
    if ui_console is not None:
        try:
            return ui_console.tokens()
        except Exception:
            pass
    return _fallback_tokens()


class _Bubble(QLabel):
    """一条消息。`role` 决定左右和配色：me = 靠右强调色，her = 靠左浅底，note = 居中灰字。"""

    def __init__(self, role, text, parent=None):
        super().__init__(text, parent)
        self.role = role
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        # ⚠️ wordWrap 的 QLabel 必须让布局按 heightForWidth 算高度，否则它按"单行宽度"
        # 报 sizeHint，长一点的消息会被**横向截掉**（实测"收到 2 个文件：报告.txt…"
        # 显示成"收到 2 个文件：报"）。原来那行 `setSizePolicy(自己, 自己)` 是空操作。
        sp = self.sizePolicy()
        sp.setHeightForWidth(True)
        sp.setVerticalPolicy(QSizePolicy.Policy.Minimum)
        self.setSizePolicy(sp)
        self.apply_theme()

    def apply_theme(self):
        t = tokens()
        pad = "10px 12px"
        if self.role == "me":
            self.setStyleSheet(
                f"QLabel {{ background: {t['accent']}; color: {t['accent_text']};"
                f" border-radius: 10px; padding: {pad}; }}")
        elif self.role == "note":
            self.setStyleSheet(
                f"QLabel {{ color: {t['text_dim']}; padding: 2px 6px; }}")
        else:
            self.setStyleSheet(
                f"QLabel {{ background: {t['surface_alt']}; color: {t['text']};"
                f" border-radius: 10px; padding: {pad}; }}")


def _fit_chipbox(box, btns, avail):
    """把一批按钮塞进 `avail` 宽：放得下按自然宽，放不下换两行，再不行才省略。

    ⚠️ 自然宽一律用 `sizeHint()`（样式内边距算在里面）。早先用
    `fontMetrics().horizontalAdvance() + 20` 估，估少了按钮就被定窄、**字被裁掉**
    （主人 2026-10-27：「输出文件打开桌面看成果文字显示不全」，当时只剩半个字）。
    """
    btns = [b for b in (btns or []) if b is not None]
    if not btns:
        return
    avail = max(80, int(avail))
    nat = []
    for b in btns:
        b.setMaximumWidth(16777215)
        b.setText(b._dfy_text)
        b.setToolTip(b._dfy_text)          # 真截了也能看全文
        nat.append(max(44, b.sizeHint().width()))
    if sum(nat) + 6 * (len(btns) - 1) <= avail:
        for b, w in zip(btns, nat):
            b.setFixedWidth(w)
        box.relayout(btns, len(btns))
        return
    per_row = max(1, (len(btns) + 1) // 2)     # 一行放不下 → 两行
    per = max(46, (avail - 6 * (per_row - 1)) // per_row)
    for b in btns:
        b.setFixedWidth(per)
        fm = b.fontMetrics()
        b.setText(fm.elidedText(b._dfy_text, Qt.TextElideMode.ElideRight,
                                max(24, per - 16)))
    box.relayout(btns, per_row)


class _ChipBox(QWidget):
    """那排 chip 的容器：**宽度不许影响整块板子的宽度**，放不下时自己换成两行。

    为什么需要它：QWidget 的最小宽度来自布局，布局的最小宽度来自每个 QPushButton 的
    minimumSizeHint（含文字宽度）。所以只要这排按钮存在，板子的最小宽度就被顶到
    336（鱼才 155~217 宽），布局锁住之后 `_place()` 的 resize 压不回来 ——
    板子比鱼还宽，贴上去就盖住鱼（主人 2026-10-27）。
    把 minimumSizeHint / sizeHint 的宽度改成 0，宽度就只由 `_place()` 说了算。
    ⚠️ 别改用 `QSizePolicy.Ignored`：那样内层布局会把按钮压成**宽度 0**（整排直接看不见，
    主人 2026-10-27 报的「交给谁全部消失」就是这个）。按钮的宽度由 `_fit_chips()` 明确给。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cols = QVBoxLayout(self)
        self.cols.setContentsMargins(0, 0, 0, 0)
        self.cols.setSpacing(4)
        self.row_layouts = []

    def minimumSizeHint(self):          # noqa: N802
        s = super().minimumSizeHint()
        return QSize(0, s.height())

    def sizeHint(self):                 # noqa: N802
        s = super().sizeHint()
        return QSize(0, s.height())

    def relayout(self, buttons, per_row):
        """把按钮重新分到若干行（按钮本身不删，只是从旧布局里摘下来）。"""
        while self.cols.count():
            it = self.cols.takeAt(0)
            lay = it.layout() if it is not None else None
            if lay is not None:
                while lay.count():
                    lay.takeAt(0)
                lay.deleteLater()
        self.row_layouts = []
        n = max(1, int(per_row or len(buttons) or 1))
        for i in range(0, len(buttons), n):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            for b in buttons[i:i + n]:
                row.addWidget(b)
            row.addStretch(1)
            self.cols.addLayout(row)
            self.row_layouts.append(row)


class FlyoutWindow(QWidget):
    """贴边的那块板子。自己管显示 / 隐藏 / 跟随，内容由外面通过 `add()` 喂。"""

    closed = Signal()          # 收起来了（聊天那边要据此把桌宠身上的小圆按钮放回去）
    closing = Signal()         # **开始收**（收起动画第一帧就发，圆按钮这时候回来"接住"它）

    def __init__(self, pet):
        # 挂成桌宠的子窗口：桌宠销毁时它跟着销毁，桌宠隐藏时它也隐藏（不会孤零零留在屏幕上）
        super().__init__(pet)
        self.pet = pet
        self._send_handler = None
        self._clear_slot = None
        self._anim = None
        self._target = QPoint(0, 0)
        self._side = "right"
        self._busy = False
        self._want_w, self._want_h = W_DEFAULT, H_DEFAULT
        self._radius = RADIUS            # 圆角：从圆形（=圆的一半）动画到 12
        self._tail_y = None              # 尖角指的高度（窗口坐标），None = 不画
        self._tail_side = "left"         # 尖角长在哪条边（"left" = 窗口在桌宠右边）
        self._anchor_y = None            # 尖角指着的全局 y（= 那个圆形按钮的中心）
        self._anchor_dy = None           # 按钮中心相对**鱼顶**的偏移（鱼走动后尖角才不会指错）
        self._circle_size = 0            # 打开时那个圆的直径 + 阴影边（收起来要缩回这个大小）
        self._tail_grow = 1.0            # 尖角"长出来"的进度（0~1）
        self._tail_anim = None           # 换边时"缩回→换边→长出"那条动画
        self._pending_tail_side = None   # 换边动画缩到 0 之后要换成哪一侧
        self._hover = False              # 光标在板子上（这时冻住位置，见下）
        self._mode = ""                  # 这块板子现在在干哪件事："chat" / "task" / ""
        self._status_text = ""           # 状态行原文（`status.text()` 是 elide 过的）
        self._stoppable = False          # 状态行右边要不要露「停止」
        self._stop_handler = None        # 「停止」按钮的回调（派活挂的）
        self._pops = set()               # 正在跑的新消息出场动画（留住引用，别被回收）
        self._fade = None                # 内容淡入那条动画（留住引用，别被回收）

        self.setWindowFlags(Qt.WindowType.Tool
                            | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.resize(W_DEFAULT, H_DEFAULT)

        self._build()
        self.apply_theme()

        # 跟着桌宠走：桌宠被拖 / 自己走路 / 换大小，位置都会变
        self._follow = QTimer(self)
        self._follow.setInterval(FOLLOW_MS)
        self._follow.timeout.connect(self._on_follow)
        # ⚠️ 光靠 60ms 定时器跟，拖桌宠的时候板子是一跳一跳追（主人 2026-10-26：
        # 「聊天窗口拖动有延迟卡顿」）。装个事件过滤器，桌宠每移一下就立刻重排，
        # 定时器只当兜底（鱼自己走路、换尺寸这些）。
        try:
            self.pet.installEventFilter(self)
        except Exception:
            pass

    # ------------------------------------------------------------------ 界面
    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        outer.setSpacing(0)

        self.card = QWidget(self)
        self.card.setObjectName("card")
        # 内容淡入用：给整张卡片套一个透明度特效，动画里从 0 补到 1。
        # （直接 show/hide 会"啪"一下蹦出来 —— 主人说的"太生硬"就是它）
        self._fx = QGraphicsOpacityEffect(self.card)
        self._fx.setOpacity(1.0)
        self.card.setGraphicsEffect(self._fx)
        outer.addWidget(self.card)

        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(10)

        # 标题栏
        head = QHBoxLayout()
        head.setSpacing(8)
        # 标题前一个小圆点：一点点装饰，不然整块板子太素
        self.dot = QLabel(self.card)
        self.dot.setObjectName("dot")
        self.dot.setFixedSize(7, 7)
        head.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.title = QLabel("和她聊聊", self.card)
        f = self.title.font()
        f.setPointSizeF(f.pointSizeF() + 1.0)
        f.setBold(True)
        self.title.setFont(f)
        head.addWidget(self.title, 1)
        # 「清空对话」：只有挂了 `set_clear_handler` 才显示（P4 骨架阶段没这个键）
        self.btn_clear = QPushButton(self.card)
        self.btn_clear.setObjectName("close")
        self.btn_clear.setFixedSize(24, 24)
        self.btn_clear.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear.setToolTip("清空对话")
        self.btn_clear.hide()
        head.addWidget(self.btn_clear, 0, Qt.AlignmentFlag.AlignTop)
        # 关闭键用设置窗口同一套图标：直接写 "×" 字符在个别字体下会显示成方框
        self.btn_close = QPushButton(self.card)
        self.btn_close.setObjectName("close")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("收起（Esc）")
        self.btn_close.clicked.connect(self.hide_animated)
        head.addWidget(self.btn_close, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(head)

        # 标题下面一条极淡的分隔线：让"标题 / 内容"分开，不然一大片同色很闷
        self.head_line = QFrame(self.card)
        self.head_line.setObjectName("headline")
        self.head_line.setFixedHeight(1)
        lay.addWidget(self.head_line)

        self.subtitle = QLabel("", self.card)
        self.subtitle.setWordWrap(True)
        self.subtitle.hide()
        lay.addWidget(self.subtitle)

        # 一排小按钮（派活用：Codex / DSH / 只打开）。没设就整排不占地方。
        self.actions_box = _ChipBox(self.card)
        # ⚠️ 2026-10-27 主人：「派活界面加载的文案信息会让窗口越来越长会挡道桌宠」。
        # 真凶是这排 chip 的 sizeHint 会把整块板子的**最小宽度**顶上去（实测 260 → 336）。
        # 用 `_ChipBox` 把它的宽度贡献清零，按钮宽度由 `_fit_chips()` 明确给。
        self._chip_btns = []                 # 顺序即显示顺序（跨行也在这一份里）
        self.actions_box.hide()
        lay.addWidget(self.actions_box)

        # 消息区
        self.scroll = QScrollArea(self.card)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # ⚠️ 最小尺寸：给消息区留一块**看得见**的地方。
        # 只写 0 的话，板子矮的时候（20% 档 240 高）标题 + 交给谁 + 两行 chip + 输入框
        # 就把高度吃光，消息区被挤成 0 —— 拖进来的文件列表直接看不见
        # （主人 2026-10-27 截图：「选项显示不全」）。
        # 高度不够时让**窗口**长高（Qt 会按布局最小尺寸顶上去），宽度仍然锁死不动。
        self.scroll.setMinimumSize(0, 70)
        self.scroll.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.body = QWidget()
        self.body.setObjectName("body")
        self.msgs = QVBoxLayout(self.body)
        self.msgs.setContentsMargins(0, 0, 6, 0)
        self.msgs.setSpacing(8)
        self.msgs.addStretch(1)
        self.scroll.setWidget(self.body)
        lay.addWidget(self.scroll, 1)

        # 运行状态行（派活用）：'● Codex 正在跑 · 12 秒 · 正在读笔记.txt'
        # 主人 2026-10-26：「dsh/codex 接收太慢，而且我根本不知道成功没有」——
        # 光等一个"跑完了"的结论太没底，这里实时显示谁在跑、跑了多久、最后吐了什么。
        # 2026-10-27：右边加一颗「停止」（有任务在跑时才出现）—— 原来想掐掉只能改代码。
        self.status_row = QWidget(self.card)
        _srow = QHBoxLayout(self.status_row)
        _srow.setContentsMargins(0, 0, 0, 0)
        _srow.setSpacing(6)
        self.status = QLabel("", self.card)
        self.status.setObjectName("status")
        self.status.setWordWrap(False)
        # ⚠️ Ignored：这一行很长时**不许把板子撑宽**（见 set_status 的说明）。
        self.status.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        _srow.addWidget(self.status, 1)
        self.btn_stop = QPushButton("停止", self.card)
        self.btn_stop.setObjectName("mini")
        self.btn_stop.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_stop.setToolTip("停掉正在跑的 Agent 任务")
        # ⚠️ 高度钉死：按钮比那行小字高 8px，一出现就把整块板子撑高 8px
        # （主人 2026-10-27：「文案会让窗口越来越长」的另一种表现）。
        self.btn_stop.setFixedHeight(18)
        self.btn_stop.clicked.connect(self._on_stop)
        self.btn_stop.hide()
        _srow.addWidget(self.btn_stop, 0)
        self.status_row.hide()
        # 高度钉死：有没有「停止」键都是这么高，不许把板子顶高（见上面 btn_stop 的注释）
        self.status_row.setFixedHeight(24)
        lay.addWidget(self.status_row)

        # 输入行
        row = QHBoxLayout()
        row.setSpacing(8)
        self.input = QLineEdit(self.card)
        self.input.setPlaceholderText("说点什么，回车发送…")
        self.input.setMinimumHeight(34)
        self.input.returnPressed.connect(self._on_send)
        row.addWidget(self.input, 1)
        self.btn_send = QPushButton("发送", self.card)
        self.btn_send.setMinimumHeight(34)
        self.btn_send.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_send.clicked.connect(self._on_send)
        row.addWidget(self.btn_send, 0)
        lay.addLayout(row)

    def apply_theme(self):
        """按当前主题重新上色（每次显示都刷一遍：设置里换了主题不用重启）。"""
        t = tokens()
        # 卡片底：从上到下一点点往强调色偏（6%），看着有厚度，不是一块死板的色块
        top_c = QColor(t["surface"])
        bot_c = _blend(t["surface"], t.get("accent") or t["surface"], 0.06)
        self._card_top = top_c
        self._card_bot = bot_c
        # 底色由 `paintEvent` 画（见 `_card_grad`），卡片自己是透明的 ——
        # 这样"内容淡入"的时候壳还在，不会露出中间一片灰。
        self.card.setStyleSheet(
            f"QWidget#card {{ background: transparent; border: none; }}"
            f"QWidget#body {{ background: transparent; }}"
            f"QLabel {{ color: {t['text']}; }}"
            f"QLineEdit {{ background: {t['surface_alt']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 8px; padding: 6px 10px; }}"
            f"QLineEdit:focus {{ border: 1px solid {t['accent']}; outline: none; }}"
            f"QLineEdit:disabled {{ background: {t['surface']}; color: {t['text_dim']};"
            f" border: 1px solid {t['border']}; outline: none; }}"
            f"QPushButton {{ background: {t['accent']}; color: {t['accent_text']};"
            f" border: none; border-radius: 8px; padding: 6px 14px; }}"
            # ⚠️ 必须清掉 focus/outline：按钮禁用之后 Qt 还会画一圈焦点框，
            # 主人看到的"发送按钮灰下去右边还有一条蓝边"就是它（2026-10-26）。
            f"QPushButton:focus {{ outline: none; border: none; }}"
            f"QPushButton:hover {{ background: {t['accent_hover'] if 'accent_hover' in t else t['accent']}; }}"
            f"QPushButton:disabled {{ background: {t['border']}; color: {t['text_dim']};"
            f" border: none; outline: none; }}"
            f"QPushButton#chip {{ background: {t['surface_alt']}; color: {t['text']};"
            f" border: 1px solid {t['border']}; border-radius: 13px;"
            f" padding: 6px 13px; font-size: 12px; }}"
            f"QPushButton#chip:hover {{ border: 1px solid {t['accent']};"
            f" color: {t['accent']}; }}"
            # 选中那颗：实底强调色 + 加粗，一眼看出"现在交给谁"
            f"QPushButton#chipOn {{ background: {t['accent']}; color: {t['accent_text']};"
            f" border: 1px solid {t['accent']}; border-radius: 13px;"
            f" padding: 6px 13px; font-size: 12px; font-weight: 600; }}"
            # 比 chip 更小一号：状态行右边那颗「停止」，不能把状态行撑高
            f"QPushButton#mini {{ background: {t['surface_alt']}; color: {t['text_dim']};"
            f" border: 1px solid {t['border']}; border-radius: 9px;"
            f" padding: 1px 9px; font-size: 11px; }}"
            f"QPushButton#mini:hover {{ border: 1px solid {t['accent']}; color: {t['accent']}; }}"
            f"QPushButton#close {{ background: transparent; color: {t['text_dim']};"
            f" border: none; border-radius: 6px; padding: 0px; font-size: 16px; }}"
            f"QPushButton#close:hover {{ background: {t['surface_alt']}; color: {t['text']}; }}"
            f"QLabel#dot {{ background: {t['accent']}; border-radius: 3px; }}"
            f"QLabel#status {{ color: {t['text_dim']}; font-size: 11px; padding: 0 2px 2px 2px; }}"
            f"QFrame#headline {{ background: {t['border']}; border: none; }}"
            f"QScrollArea {{ background: transparent; border: none; }}"
            f"QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}"
            f"QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 4px;"
            f" min-height: 24px; }}"
            f"QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}"
            f"QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}")
        if ui_console is not None:
            try:
                self.btn_close.setIcon(ui_console.icon("ui.close", t["text_dim"], 13))
                self.btn_clear.setIcon(ui_console.icon("ui.delete", t["text_dim"], 13))
            except Exception:
                self.btn_close.setText("×")
                self.btn_clear.setText("清")
        else:
            self.btn_close.setText("×")
            self.btn_clear.setText("清")
        for i in range(self.msgs.count()):
            w = self.msgs.itemAt(i).widget()
            if isinstance(w, _Bubble):
                w.apply_theme()
        self.update()

    def paintEvent(self, ev):
        """画圆角卡片 + 一圈"假阴影"。

        不用 QGraphicsDropShadowEffect：它作用在整窗口上时，`WA_TranslucentBackground`
        下经常出现方块底或者干脆不显示。手画阴影最稳。
        阴影做法 2026-10-26 改过：原来是 5 个层层放大的圆角矩形，**尖角没有阴影**，
        看着像一张贴纸浮在卡片旁边；现在按同一轮廓描边，尾巴也跟着有柔边。
        """
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        t = tokens()
        shadow = t.get("shadow") or QColor(0, 0, 0, 45)
        rect = self.rect().adjusted(MARGIN, MARGIN, -MARGIN, -MARGIN)
        # 圆形→卡片 的过渡：圆角等于一半高度时就是个正圆
        r = max(1.0, min(float(self._radius), min(rect.width(), rect.height()) / 2.0))
        body = self._body_path(rect, r)

        # 阴影：沿轮廓描边（外扩 i 像素），层数越靠外越淡
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, alpha in ((5, 7), (4, 9), (3, 11), (2, 15), (1, 20)):
            col = QColor(shadow)
            col.setAlpha(alpha)
            pen = QPen(col, float(i * 2))
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.drawPath(body.translated(0.0, 1.0))

        # 卡片底：淡渐变（上浅下稍微偏强调色），跟着圆角一起变
        grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
        grad.setColorAt(0.0, getattr(self, "_card_top", QColor(t["surface"])))
        grad.setColorAt(1.0, getattr(self, "_card_bot", QColor(t["surface"])))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(grad)
        p.drawPath(body)

        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(t["border"]), 1))
        p.drawPath(body)
        p.end()

    def _body_path(self, rect, r):
        """卡片 + 尖角 = **一条**闭合轮廓。

        尖角和卡片分开画的时候，交界处必然出现"卡片边框横穿尾巴根部"的两条线，
        这就是主人说的"衔接不够自然"。合成一条路径后填充/描边都只走外圈，
        根部用一点微凹曲线过渡（不是生硬的直角三角）。
        没设 `_tail_y`（比如从右键菜单滑出来的那种）就只返回圆角矩形。
        """
        body = QPainterPath()
        body.addRoundedRect(QRectF(rect), r, r)
        grow = getattr(self, "_tail_grow", 1.0)
        if self._tail_y is None or grow <= 0.02:
            return body

        half = TAIL_HALF
        depth = TAIL_DEPTH * grow
        # 允许尖角再往圆角带里靠一点（以前卡在 r + half，按钮稍高一点就被推下来）
        cy = max(rect.top() + r * 0.6 + half,
                 min(float(self._tail_y), rect.bottom() - r * 0.6 - half))
        side = self._tail_side
        if side == "left":
            bx = float(rect.left()) + 0.5          # 探进卡片半个像素，并集不留缝
            tip_x = bx - depth
        else:
            bx = float(rect.right()) - 0.5
            tip_x = bx + depth

        tail = QPainterPath()
        tail.moveTo(bx, cy + half)
        # 下半边：控制点压在卡片边缘上 → 略微内凹，像"从卡片里挤出来"的
        tail.quadTo(bx, cy + half * 0.28, tip_x, cy)
        tail.quadTo(bx, cy - half * 0.28, bx, cy - half)
        tail.closeSubpath()
        return body.united(tail)

    def _set_tail_side(self, side):
        """尾巴换边。

        主人 2026-10-26：板子从鱼右边跳到左边时，尾巴是**瞬切**到另一侧的，跨屏时很跳。
        现在先缩回去、换边、再长出来（约 0.26 秒），看着像"收起来换个方向探出去"。
        打开/收起动画期间（`_anim`）不搞这套，直接切 —— 那时候本来就看不清。
        """
        if side == self._tail_side:
            return
        if self._anim is not None or not self.isVisible() or self._tail_grow <= 0.02:
            self._tail_side = side
            self.update()
            return
        if self._tail_anim is not None:
            self._pending_tail_side = side      # 动画在跑：只改目标，别重启（否则一直抖）
            return
        self._pending_tail_side = side
        self._start_tail_flip()

    def _start_tail_flip(self):
        self._stop_tail_anim()
        seq = QSequentialAnimationGroup(self)
        shrink = QPropertyAnimation(self, b"tailGrow", seq)
        shrink.setDuration(110)
        shrink.setStartValue(float(self._tail_grow))
        shrink.setEndValue(0.0)
        shrink.setEasingCurve(QEasingCurve.Type.InCubic)
        grow = QPropertyAnimation(self, b"tailGrow", seq)
        grow.setDuration(150)
        grow.setStartValue(0.0)
        grow.setEndValue(1.0)
        grow.setEasingCurve(QEasingCurve.Type.OutCubic)
        seq.addAnimation(shrink)
        seq.addAnimation(grow)
        shrink.finished.connect(self._apply_pending_tail_side)
        seq.finished.connect(self._tail_flip_done)
        self._tail_anim = seq
        seq.start()

    def _apply_pending_tail_side(self):
        """缩到 0 了：这时候才换边（看不见的那一瞬间切，最自然）。"""
        if self._pending_tail_side is not None:
            self._tail_side = self._pending_tail_side
            self._pending_tail_side = None
            self.update()

    def _tail_flip_done(self):
        self._tail_anim = None

    def _stop_tail_anim(self):
        if self._tail_anim is not None:
            try:
                self._tail_anim.stop()
            except RuntimeError:
                pass
            self._tail_anim = None

    # 圆角做成属性，才能用 QPropertyAnimation 从"正圆"补间到"圆角卡片"
    def _get_radius(self):
        return float(self._radius)

    def _set_radius(self, v):
        self._radius = float(v)
        self.update()

    radius = Property(float, _get_radius, _set_radius)

    def _get_tail(self):
        return float(self._tail_grow)

    def _set_tail(self, v):
        self._tail_grow = float(v)
        self.update()

    tailGrow = Property(float, _get_tail, _set_tail)

    # ------------------------------------------------------------------ 内容
    def add(self, role, text, animate=True):
        """加一条消息。role: "me" / "her" / "note"。

        `animate=False` 用于**重绘历史**：一次铺十几条时不该每条都淡入
        （每条一个 `QGraphicsOpacityEffect` 会强制离屏渲染，一起跑明显卡）。
        """
        text = str(text or "").strip()
        if not text:
            return None
        b = _Bubble(role, text, self.body)
        if role == "me":
            self.msgs.insertWidget(self.msgs.count() - 1, b, 0, Qt.AlignmentFlag.AlignRight)
        elif role == "note":
            b.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.msgs.insertWidget(self.msgs.count() - 1, b, 0, Qt.AlignmentFlag.AlignHCenter)
        else:
            self.msgs.insertWidget(self.msgs.count() - 1, b, 0, Qt.AlignmentFlag.AlignLeft)
        # ⚠️ 宽度/高度要在**进了布局之后**再定：没加进去时 style 还没 polish，
        # `heightForWidth()` 会给出偏小的值（实测 76 vs 实际要 90）。
        self._fit_bubble(b)
        # 自己的话立刻出现，不做淡入 —— 淡入会让人觉得"点了发送要等一下才出来"
        # （主人 2026-10-26：「点发送有延迟」）。动效只给她的回复。
        if role != "me" and animate:
            self._pop_in(b)
        else:
            QTimer.singleShot(0, self._scroll_to_bottom)
        return b

    def _pop_in(self, bubble):
        """新消息淡入。

        主人 2026-10-26：「回复的话没有动效，像突然出来的」—— 原来 `insertWidget`
        之后就那么杵在那儿了，一屏刷新好几条时特别生硬。

        ⚠️ 别顺手加"高度从 0 长出来"的动画：`maximumHeight` 一压，`wordWrap` 的 QLabel
        会按压缩后的宽度重排，长出来的过程中文字被横向截掉（实测"收到 2 个文件：报"）。
        纯淡入最稳，也不会碰布局。

        动画结束把 `QGraphicsOpacityEffect` 摘掉：每条气泡挂一个特效，40 条一起滚
        会明显变卡（而且 effect 强制走离屏渲染）。
        """
        try:
            eff = QGraphicsOpacityEffect(bubble)
            eff.setOpacity(0.0)
            bubble.setGraphicsEffect(eff)
        except RuntimeError:
            return
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def _done():
            try:
                bubble.setGraphicsEffect(None)
            except RuntimeError:
                pass
            self._scroll_to_bottom()
        anim.finished.connect(_done)
        self._pops.add(anim)
        anim.finished.connect(lambda: self._pops.discard(anim))
        anim.start()

    def clear(self):
        while self.msgs.count() > 1:
            item = self.msgs.takeAt(0)
            w = item.widget()
            if w is not None:
                # 先摘掉再 deleteLater：`deleteLater` 要等事件循环空闲才真删，
                # 手动转 processEvents 的地方（测试）会看到"清不干净"。
                w.setParent(None)
                w.deleteLater()

    def _scroll_to_bottom(self):
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def set_title(self, text):
        self.title.setText(str(text or ""))
        self.updateGeometry()

    def set_subtitle(self, text):
        text = str(text or "")
        self.subtitle.setText(text)
        self.subtitle.setVisible(bool(text))

    def set_send_handler(self, fn):
        """fn(text) —— 用户按回车 / 点发送时调它。传 None 就退回"还没接上"的提示。"""
        self._send_handler = fn

    def set_quick_actions(self, actions):
        """标题下面那排小按钮：`[(文字, 回调[, 是否选中]), ...]`。传空就整排收起来。

        第三项是可选的"选中"标记 —— 选中那颗用强调色实底画，一眼能看出"现在交给谁"
        （主人 2026-10-26：给谁的按钮不够明显，之前只是文字前面加个「· 」）。

        2026-10-26：**数量没变就只改文字、不重建按钮**。原来每次都 `setParent(None)`
        + `deleteLater()`，而 `_refresh_actions` 正是从「点击回调」里调过来的 ——
        等于在按钮自己的 clicked 处理过程中把它删掉（实测：点完再拿旧引用就是
        "Internal C++ object already deleted"）。复用也不会闪一下。
        """
        entries = []
        for item in (actions or []):
            entries.append((str(item[0]), item[1], bool(item[2]) if len(item) > 2 else False))
        if not entries:
            self._clear_quick_actions()
            self.actions_box.hide()
            return
        if len(self._chip_btns) == len(entries):
            for b, (text, cb, on) in zip(self._chip_btns, entries):
                b._dfy_text = text
                b.setText(text)
                b.setObjectName("chipOn" if on else "chip")
                prev = getattr(b, "_dfy_cb", None)
                if prev is not None:
                    try:
                        b.clicked.disconnect(prev)
                    except (RuntimeError, TypeError):
                        pass
                b._dfy_cb = cb
                b.clicked.connect(cb)
            self.actions_box.show()
            self.apply_theme()
            self._fit_chips()
            return
        self._clear_quick_actions()
        for text, cb, on in entries:
            b = QPushButton(text, self.actions_box)
            b.setObjectName("chipOn" if on else "chip")
            b._dfy_text = text                  # 原文留着，窄的时候按它截（见 _fit_chips）
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b._dfy_cb = cb
            b.clicked.connect(cb)
            self._chip_btns.append(b)
        self.actions_box.show()
        self.apply_theme()          # 新按钮要跟着当前主题上色
        self._fit_chips()
        # chip 变了之后，把板子按鱼重新摆一次 —— 不然它可能还留着上一次被撑宽的尺寸
        if self.isVisible() and self._anim is None:
            self._target = self._place()[0]

    @property
    def actions_row(self):
        """第一行（测试和老代码在用）。多行时用 `chip_buttons()` 取全部。"""
        rows = getattr(self.actions_box, "row_layouts", [])
        return rows[0] if rows else None

    def chip_buttons(self):
        """这排 chip 的全部按钮（跨行，按显示顺序）。"""
        return [b for b in getattr(self, "_chip_btns", []) if b is not None]

    def _inner_w(self):
        """卡片**里面**真正能用的宽度。

        ⚠️ 不能拿 `self.width() - 2*MARGIN` 当可用宽：卡片自己还有左右各 14 的内边距
        （`lay.setContentsMargins(14, 12, 14, 12)`）。少算这 28px，按钮就会比卡片宽、
        右边被卡片裁掉（主人 2026-10-27：「按钮显示不全，右边给截断了一部分」）。
        """
        try:
            w = self.card.width()
            if w > 40:
                return max(100, w - 28)
        except (RuntimeError, AttributeError):
            pass
        return max(100, self.width() - 2 * MARGIN - 28)

    def _fit_chips(self):
        """按当前宽度安排这排 chip：**先按真实宽度试一行，放不下就换两行**。

        主人 2026-10-27：「交给谁的ui选项仍然没有，而且输出文件打开桌面看成果文字显示不全」。
        两个原因：
          1. 原来拿 `fontMetrics().horizontalAdvance() + 20` 估宽度 —— **没算样式内边距**，
             估少了就把按钮定成 56px，字被裁掉（"Codex" 只剩半个，看着像没有）；
          2. 板子窄（最小 200）时三颗本来就挤不下，硬挤只能裁字。
        现在：自然宽一律用 `sizeHint()`（样式内边距算在里面）；一行放不下就分成两行，
        每行均分宽度，实在还不够才省略（tooltip 看全文）。
        """
        btns = self.chip_buttons()
        if not btns:
            return
        _fit_chipbox(self.actions_box, btns, self._inner_w())

    def _clear_quick_actions(self):
        """清空那排 chip。⚠️ `_dfy_cb` 要一起清，否则复用时会去 disconnect 死对象。"""
        for b in getattr(self, "_chip_btns", []):
            if b is None:
                continue
            b._dfy_cb = None
            b.setParent(None)
            b.deleteLater()
        self._chip_btns = []
        try:
            self.actions_box.relayout([], 1)
        except (RuntimeError, AttributeError):
            pass

    def set_clear_handler(self, fn):
        """挂上「清空对话」键（fn 负责清数据，界面上的气泡这里自己清）。"""
        # ⚠️ 别写 `btn.clicked.disconnect()`：没连过的时候 PySide 会打一条
        # "Failed to disconnect (None) from signal" 的 RuntimeWarning（实测）。
        # 记住自己连上去的那个槽，只断它。
        if self._clear_slot is not None:
            try:
                self.btn_clear.clicked.disconnect(self._clear_slot)
            except (RuntimeError, TypeError):
                pass
            self._clear_slot = None
        if fn is None:
            self.btn_clear.hide()
            return
        self._clear_slot = lambda: (self.clear(), fn())
        self.btn_clear.show()
        self.btn_clear.clicked.connect(self._clear_slot)

    def set_status(self, text, stoppable=None):
        """输入框上面那行运行状态。传空就整行收起来（不占地方）。

        ⚠️ 这行是**单行不换行**的。文字一长（「● Codex 正在跑 · 12 秒 · 正在读 xxx」）
        它的 sizeHint 就把整块板子撑宽（实测 **260 → 481**），直接糊到桌宠身上。
        所以这里两件事一起做：`QSizePolicy.Ignored`（sizeHint 不参与布局，压得下去）
        + 按当前宽度 elide（多的字用 … 收掉，不换行、不改窗口尺寸）。

        `stoppable=True` 时右边出现「停止」按钮（派活跑着的时候）。
        """
        self._status_text = str(text or "")
        if stoppable is not None:
            self._stoppable = bool(stoppable)
        self._fit_status()
        has = bool(self._status_text)
        self.status_row.setVisible(has)
        self.btn_stop.setVisible(has and self._stoppable)

    def _fit_status(self):
        """按当前卡片宽度把状态行截到放得下（`resizeEvent` 里也会调）。"""
        try:
            avail = max(60, self.width() - 48)
            self.status.setText(self.status.fontMetrics().elidedText(
                self._status_text, Qt.TextElideMode.ElideRight, avail))
        except (RuntimeError, AttributeError):
            pass

    def status_text(self):
        """状态行的**原文**（测试用；`status.text()` 是 elide 过的）。"""
        return self._status_text

    def set_stop_handler(self, fn):
        """挂上「停止」按钮（fn 负责真的杀任务）。传 None 就不显示这颗按钮。"""
        self._stop_handler = fn
        if fn is None:
            self.btn_stop.hide()

    def _on_stop(self, _checked=False):
        """点了「停止」。⚠️ `clicked` 会带一个 checked(bool)，别让它顶掉参数。"""
        if self._stop_handler is None:
            return
        try:
            self._stop_handler()
        except Exception:
            pass
        # 立刻回一句，别等 700ms 的轮询；任务真死掉后 `_poll` 会把状态行收掉
        self.set_status("● 正在停…")

    def add_with_actions(self, role, text, actions):
        """一条消息 + 下面几颗小按钮（`[(文字, 回调), …]`）。

        用途：**你正在聊天时**派活跑完了 —— 不该把「再派一个」那排糊上来（一点就清空
        聊天记录），但「打开输出文件」这个入口不能丢。所以按钮跟着**这一条消息**走，
        会随聊天流一起滚上去。
        """
        text = str(text or "").strip()
        if not text:
            return None
        box = QWidget(self.body)
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        b = _Bubble(role, text, box)
        v.addWidget(b, 0, Qt.AlignmentFlag.AlignLeft)
        # 按钮也放进 _ChipBox：板子窄的时候自动换成两行，字不会被裁
        # （主人 2026-10-27：「输出文件打开桌面看成果文字显示不全」）。
        chipbox = _ChipBox(box)
        btns = []
        for label, cb in (actions or []):
            btn = QPushButton(str(label), chipbox)
            btn.setObjectName("chip")
            btn._dfy_text = str(label)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn._dfy_cb = cb          # 留住引用：否则 Python 回收后点了就是 RuntimeError
            btn.clicked.connect(cb)
            btns.append(btn)
        chipbox._dfy_btns = btns
        v.addWidget(chipbox)
        _fit_chipbox(chipbox, btns, max(100, self._inner_w() - 8))
        self.msgs.insertWidget(self.msgs.count() - 1, box)
        # ⚠️ 宽度要在进了布局之后算（和 add 里同一个理由）
        self._fit_bubble(b)
        QTimer.singleShot(0, self._scroll_to_bottom)
        return b

    def set_busy(self, on):
        """她正在想的时候：输入框和发送键禁用，占位文字换掉。"""
        was = self._busy
        self._busy = bool(on)
        self.input.setEnabled(not self._busy)
        self.btn_send.setEnabled(not self._busy)
        self.input.setPlaceholderText("她正在想…" if self._busy else "说点什么，回车发送…")
        # ⚠️ 只在"忙 → 闲"这一下把焦点还给输入框。原来无条件 setFocus() ——
        # 派活收尾也会调 `set_busy(False)`，于是你在别处打字时焦点被抢走。
        if was and not self._busy:
            self.input.setFocus()

    def set_mode(self, mode):
        """这块板子现在在干哪件事："chat"（跟她说）/"task"（派活）。

        两件事共用一块板子（主人定的：聊天走 API、任务走 Agent），但**不能互相打断**：
        派活跑完时如果你正在聊天，就不该把「打开输出文件 / 再派一个」那排按钮
        糊到聊天框上 —— 尤其「再派一个」会 `clear()`，一下把聊天记录全清了。
        """
        self._mode = str(mode or "")

    @property
    def mode(self):
        return self._mode

    def message_count(self):
        """板子上现在有几条消息（末尾那个 stretch 不算）。重绘历史前用它判空。"""
        return max(0, self.msgs.count() - 1)

    @property
    def busy(self):
        return self._busy

    def _on_send(self):
        if self._busy:
            return
        text = self.input.text().strip()
        if not text:
            return
        self.input.clear()
        self.add("me", text)
        if self._send_handler is None:
            self.add("note", "（聊天通道还没接上，下一步 P5）")
            return
        try:
            self._send_handler(text)
        except Exception as exc:                    # 别让一句报错把窗口打死
            self.add("note", f"出错了：{exc}")

    # ------------------------------------------------------------------ 位置
    def _pet_rect(self):
        try:
            return self.pet.geometry()
        except RuntimeError:
            return None

    def _screen_geo(self):
        scr = None
        try:
            scr = self.pet.screen()
        except Exception:
            scr = None
        if scr is None:
            scr = QApplication.primaryScreen()
        return scr.availableGeometry()

    def _place(self, apply=True):
        """算出该贴在哪（右边放不下就换左边），返回 (目标点, 靠哪一侧)。

        `apply=False` 时**只算不应用**（不改窗口尺寸/位置，只更新尖角的朝向和高度）——
        光标停在板子上时用得到：位置要冻住（不然点不中按钮），但尾巴还得跟着鱼。

        三种情况：
          1. 挑宽敞的那一侧，正常放下（1920 宽的屏基本都是这条）；
          2. 那一侧不够宽 → **把板子收窄**（最低 `MIN_W`），别硬挤到屏外；
          3. 连 `MIN_W` 都放不下（小屏 + 大号桌宠）→ 收窄到能放，还不行就和桌宠叠一点。
             宁可叠一点，也不要把板子推出屏幕（推出去就点不到了）。
        """
        pet = self._pet_rect()
        geo = self._screen_geo()
        if pet is None:
            return QPoint(geo.center().x(), geo.center().y()), "right"

        # ⚠️ 锚点用**鱼**，不是窗口：灵动版的窗口宽度是按"最宽画布"固定的（548px），
        # 鱼只占中间两百来像素。按窗口摆的话，板子离鱼还空着一大截
        # —— 主人 2026-10-26 说的「太远了」就是这个。
        try:
            # 用**鱼本体**（有像素的那块），不是画布：画布四周有透明留白，
            # 按画布摆会"离得太远"，画布比鱼窄时又会压到头发（主人 2026-10-27）。
            _local = self.pet.sprite_body_rect()
            pet = QRect(pet.x() + _local.x(), pet.y() + _local.y(),
                        _local.width(), _local.height())
        except Exception:
            try:
                _local = self.pet.sprite_rect()
                pet = QRect(pet.x() + _local.x(), pet.y() + _local.y(),
                            _local.width(), _local.height())
            except Exception:
                pass

        # 空隙跟鱼身宽成比例（2% ~ 12px），小鱼的板子不会离得远、大鱼也不会贴太紧
        gap = max(GAP, min(12, int(round(pet.width() * GAP_RATIO))))
        room_right = geo.right() - (pet.right() + gap) + 1
        room_left = (pet.left() - gap) - geo.left()
        side = "right" if room_right >= room_left else "left"
        room = max(room_right, room_left)

        # 想要多大：按鱼的比例算（鱼 217 宽 → 板子 315 宽；鱼 155 宽 → 260 宽）
        want_w = max(MIN_W, min(W_MAX, int(pet.width() * W_RATIO)))
        want_h = max(H_MIN, min(H_MAX, int(pet.height() * H_RATIO)))
        # ⚠️ 2026-10-27：原来这里是 `min(want_w, max(MIN_W, room), geo.width())` ——
        # 那一侧的**空位比 MIN_W 还小**时（鱼贴着屏幕边 / 鱼特别大），宽度会被撑到
        # 比空位还宽，下面夹屏 `min(x, geo.right()-w+1)` 就把板子**推到鱼身上**了
        # （主人报的「把桌宠挡住了」）。改成"绝不超过空位"，宁可窄一点。
        w = max(140, min(want_w, room, geo.width()))
        h = min(want_h, geo.height())
        if apply:
            # ⚠️ 加个死区：鱼换动作时窗口/画布会差十几像素，跟着改就会**一直抽**
            # （主人 2026-10-27：「较小……仍会挡住」「放大后又离得太远」有一部分就是它）。
            # 只有真的改了大小时（滑块 / 换档，一档差几十像素）才跟着变。
            if abs(w - self.width()) >= 24 or abs(h - self.height()) >= 24:
                self.resize(w, h)
            else:
                w, h = self.width(), self.height()

        x = pet.right() + gap if side == "right" else pet.left() - gap - w
        y = pet.top() - 14                          # 卡片顶比鱼头高一点点，别顶到眼睛
        x = max(geo.left(), min(x, geo.right() - w + 1))
        y = max(geo.top(), min(y, geo.bottom() - h + 1))

        # 兜底硬约束：算完要是还压着鱼（浮点误差 / 夹屏），就换到另一侧再试；
        # 换过去也压着，就只把窗口挪到鱼的上下方 —— **任何情况下都不许盖住鱼**。
        _w_use = w if apply else self.width()
        _h_use = h if apply else self.height()
        _card = QRect(x + MARGIN, y + MARGIN, _w_use - 2 * MARGIN, _h_use - 2 * MARGIN)
        if _card.intersects(pet):
            _other = "left" if side == "right" else "right"
            _ox = pet.right() + gap if _other == "right" else pet.left() - gap - _w_use
            _ox = max(geo.left(), min(_ox, geo.right() - _w_use + 1))
            if not QRect(_ox + MARGIN, y + MARGIN,
                         _w_use - 2 * MARGIN, _h_use - 2 * MARGIN).intersects(pet):
                x, side = _ox, _other
            else:
                _oy = pet.bottom() + gap
                if _oy + _h_use > geo.bottom():
                    _oy = max(geo.top(), pet.top() - gap - _h_use)
                y = _oy
                x = max(geo.left(), min(pet.center().x() - _w_use // 2,
                                        geo.right() - _w_use + 1))

        # 尖角：指回"圆形按钮"的高度（没给就指桌宠身上部三分之一处）
        # ⚠️ 别直接拿打开时记的 `_anchor_y`（屏幕坐标）：鱼会走、会被拖，那个值早就过时了，
        #    尖角就会指着空气。`_anchor_dy` 记的是"相对鱼顶"，跟着鱼一起挪。
        if self._anchor_dy is not None:
            tail_y = (pet.top() + self._anchor_dy) - y
        elif self._anchor_y is not None:
            tail_y = self._anchor_y - y
        else:
            tail_y = pet.top() - y + int(pet.height() * 0.22)
        # 尖角朝哪边 —— 按窗口**最终**（夹屏之后）落在鱼的哪一侧算，别用 `side` 这个名字：
        # `side` 只是"想放哪边"，x 被夹屏之后窗口可能已经跨到鱼的另一侧了，
        # 那会儿再按 side 画尾巴，尾巴就长在背离鱼的那一边（主人 2026-10-26：换边后
        # 「三角形没有转过来」）。
        tail_side = "right" if (x + (w if apply else self.width()) / 2.0) < pet.center().x() \
            else "left"
        # 换边 / 换高度都要重画。⚠️ 阈值别太小：拖动桌宠时 `y` 每帧都变，尾巴高度跟着变，
        # 按 0.5px 判就会**每帧重绘整个卡片（5 层阴影 + 路径）**，拖动直接变卡
        # （主人 2026-10-26：「聊天窗口拖动有延迟卡顿」）。1.5px 内看不出差别。
        if abs(tail_y - (self._tail_y or 0)) > 1.5:
            self.update()
        self._set_tail_side(tail_side)      # 换边走"缩回→换向→长出"的小动画（内部会 update）
        self._tail_y = tail_y
        return QPoint(x, y), side

    def _on_follow(self):
        if not self.isVisible():
            self._follow.stop()
            return
        if self._anim is not None:      # 正在跑动画（滑出 / 滑回 / 圆形变形）→ 别插手
            return
        # ⚠️ 光标在板子上时**位置一毫米都别动**（2026-10-26）：板子跟着鱼走，鱼跟着光标走，
        # 光标一旦落到按钮上，板子还在挪 —— 按下和抬起落在两个像素点上，`clicked` 就不发。
        # 表现是"按钮点不动"，但事件其实都收得到（实测事件流 press+release 齐全）。
        # 位置冻住，但尖角朝向/高度还是要更新（`apply=False`）：鱼在旁边走的时候，
        # 尾巴得一直指着它，不然看着像断开了。
        if self._hover:
            self._place(apply=False)
            return
        try:
            if not self.pet.isVisible():
                self.hide_flyout()          # 桌宠被隐藏了，浮窗也别留着
                return
        except RuntimeError:
            self.hide_flyout()
            return
        target, side = self._place()
        if side != self._side:
            self._side = side
        if (target - self._target).manhattanLength() > FOLLOW_EPS:
            self._target = target
            self.move(target)

    # ------------------------------------------------------------------ 显隐
    def show_at_pet(self, animate=True, anchor_y=None):
        """从桌宠旁边滑出来（老入口：右键菜单）。`anchor_y` 给了就让尖角指着它。"""
        self.card.setVisible(True)      # 上次收起时把内容藏了，这里要放回来
        self._anchor_y = anchor_y
        self._anchor_dy = None          # 这条入口只给了屏幕 y，不跟鱼绑定
        self._radius = RADIUS           # 上次可能是"缩成圆"收起来的，圆角要还原
        self._tail_grow = 1.0
        if self._fx is not None:
            self._fx.setOpacity(1.0)    # 上次收起时内容淡到 0 了，不还原会是一块白板
        self.apply_theme()
        target, side = self._place()
        self._side = side
        self._target = target
        if animate:
            # 从桌宠那一侧滑出来：起点往桌宠方向缩 26px，同时淡入
            dx = 26 if side == "right" else -26
            start = QPoint(target.x() - dx, target.y())
            self.move(start)
            self.setWindowOpacity(0.0)
            self.show()
            self.raise_()
            self._run_anim(start, target, 0.0, 1.0)
        else:
            self.move(target)
            self.setWindowOpacity(1.0)
            self.show()
            self.raise_()
        self._follow.start()
        if not self._busy:
            self.input.setFocus()

    def show_from_circle(self, circle_rect, anchor_y=None):
        """从桌宠右上角那个圆形按钮"长"成整块板子（主人 2026-10-26 要的过渡）。

        做法：窗口先摆成**和那个圆一样大**（再留出 MARGIN 的阴影边），圆角设成半径
        = 正圆，然后把 `geometry` 补间到目标位置、圆角补间到 12、透明度 0.2→1。
        补间期间把卡片内容藏起来（54px 宽时排版会挤成一团），长完了再露出来。
        """
        self._anchor_y = anchor_y if anchor_y is not None else circle_rect.center().y()
        # 记"按钮中心相对**鱼顶**"的偏移：鱼会走 / 会被拖，光记屏幕 y 的话尖角会指到空气里
        try:
            _spr = self.pet.sprite_rect()
            _fish_top = self.pet.geometry().top() + _spr.top()
            self._anchor_dy = float(self._anchor_y) - _fish_top
        except Exception:
            self._anchor_dy = None
        self.apply_theme()
        target, side = self._place()
        self._side = side
        self._target = target

        size = max(24, circle_rect.width()) + MARGIN * 2
        self._circle_size = size        # 收起时缩回这个大小（和打开对称）
        # 起点：一般就是按钮那儿。但如果按钮和落点隔了半块屏（鱼贴着屏幕右边、
        # 板子只能去左边），从按钮起飞会横穿整个屏幕，很怪 —— 这种情况改成
        # 从"落点靠鱼的那条边"长出来，视觉上还是"从鱼身上长出来的"。
        cx, cy = circle_rect.center().x(), circle_rect.center().y()
        if abs(cx - target.x()) > 200:
            cx = target.x() if side == "left" else target.x() + self.width()
            cy = max(target.y() + MARGIN, min(cy, target.y() + self.height() - MARGIN))
        start = QRect(cx - size // 2, cy - size // 2, size, size)

        # ⚠️ 终点尺寸要在 `setGeometry(start)` **之前**取！`_place()` 已经把窗口
        # resize 成目标大小了，先设成小方块再读 `self.size()` 拿到的是 54×54 ——
        # 动画就只长到 54，然后"啪"一下变成整块（主人说的"太生硬"就是它）。
        end = QRect(target, self.size())
        self._release_min_size()          # 起点是 54×54 的圆，别被布局最小值顶到 179
        self.card.setVisible(True)
        self._fx.setOpacity(0.0)          # 内容先透明，长到一半再淡进来
        self._tail_grow = 0.0
        self.setGeometry(start)
        self._radius = size / 2.0
        self.setWindowOpacity(0.0)
        self.show()
        self.raise_()
        self._run_morph(start, end, size / 2.0, RADIUS,
                        0.0, 1.0, on_done=self._morph_done)
        # ⚠️ 这里**不要** `self._follow.start()`：跟随定时器会调 `_place()`，
        # 里面有 `resize()`，会把正在跑的 geometry 动画打断（实测：尖角位置也跟着算错）。

    def _release_min_size(self):
        """放开"窗口不能小于内容"的限制。

        ⭐ 这是收起动效那个"小方框"的真正元凶：顶层窗口的布局会把 `minimumSize`
        钉成自己的最小值（实测 179×185）。几何动画缩到 179 就被掐住不动了 ——
        屏幕上看到的就是**先缩成一个小方框，然后直接消失**，而圆按钮在别处。
        把 `sizeConstraint` 设成 `SetNoConstraint` 才允许缩到那颗圆的 54×54。
        """
        try:
            lay = self.layout()
            if lay is not None:
                lay.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        except (RuntimeError, AttributeError):
            pass
        try:
            self.setMinimumSize(0, 0)
        except RuntimeError:
            pass

    def _restore_min_size(self):
        """恢复默认约束（正常显示时还是让布局兜住最小尺寸）。"""
        try:
            self.setMinimumSize(0, 0)
            lay = self.layout()
            if lay is not None:
                lay.setSizeConstraint(QLayout.SizeConstraint.SetDefaultConstraint)
        except (RuntimeError, AttributeError):
            pass

    def _morph_done(self):
        self.card.setVisible(True)
        if self._fx is not None:
            self._fx.setOpacity(1.0)
        self._tail_grow = 1.0
        # 长完了重新算一次位置：尖角这时才知道自己该指哪儿
        target, side = self._place()
        self._side = side
        self._target = target
        self.move(target)
        self._restore_min_size()
        self._follow.start()
        if not self._busy:
            self.input.setFocus()

    def _run_morph(self, g0, g1, r0, r1, o0, o1, on_done=None,
                   tail_from=0.0, tail_to=1.0):
        """位置 + 圆角 + 透明度 + 尖角 四条一起补间（圆形→卡片，或反过来缩回去）。

        收起（`o1 < o0`）用 InOut* 的缓动：打开是"立刻长开、慢慢收尾"，
        反过来如果直接用 InQuint，前 150ms 只缩 2px（数学上是镜像，眼睛看着像
        "先不动、然后啪一下没了"），所以收起选两头都缓的 InOutCubic。
        """
        closing = o1 < o0
        self._stop_anim()
        grp = QParallelAnimationGroup(self)
        a_geo = QPropertyAnimation(self, b"geometry", grp)
        a_geo.setDuration(MORPH_MS)
        a_geo.setStartValue(g0)
        a_geo.setEndValue(g1)
        # ⚠️ 收起必须和展开用**同一条**曲线（OutQuint），只是方向相反。
        # 原来收起用 InOutCubic：前 40% 只缩了一点点，缩到一半（还有 200px 宽）时
        # 圆角才 20 —— 看着就是"一个方框在慢慢变小"（主人 2026-10-26：「展开很顺滑，
        # 回收却是先缩成一个更小的方框再消失」）。OutQuint 在 p=0.25 就已经缩到 125px、
        # 圆角 24，读起来才是"缩回那颗圆按钮"。
        a_geo.setEasingCurve(QEasingCurve.Type.OutQuint)
        a_r = QPropertyAnimation(self, b"radius", grp)
        a_r.setDuration(MORPH_MS)
        a_r.setStartValue(r0)
        a_r.setEndValue(r1)
        a_r.setEasingCurve(QEasingCurve.Type.OutQuint)   # 同上：和展开一致
        a_op = QPropertyAnimation(self, b"windowOpacity", grp)
        a_op.setDuration(MORPH_MS)
        a_op.setStartValue(o0)
        a_op.setEndValue(o1)
        # 透明度**尽量晚掉**：主人 2026-10-26 说收起时"有一帧更小的半透明方块然后
        # 直接消失"。根因是 `InCubic` 在 p=0.5 时已经掉到 0.12，缩到一半就半透明了。
        # 换 InQuint：p=0.5 → 0.03（几乎不透明），p=0.9 → 0.59，最后才化掉。
        a_op.setEasingCurve(QEasingCurve.Type.InQuint if closing
                            else QEasingCurve.Type.InOutSine)
        a_tail = QPropertyAnimation(self, b"tailGrow", grp)
        a_tail.setDuration(int(MORPH_MS * 0.8))
        a_tail.setStartValue(float(tail_from))
        a_tail.setEndValue(float(tail_to))
        a_tail.setEasingCurve(QEasingCurve.Type.InCubic if tail_to < tail_from
                              else QEasingCurve.Type.OutCubic)
        grp.finished.connect(self._anim_finished)
        if on_done is not None:
            grp.finished.connect(on_done)
        self._anim = grp
        grp.start()
        if self._fx is not None and o0 < 0.9:
            self._fade_in()

    def _fade_in(self):
        """内容淡入：从 45% 时刻开始，和卡片长大错开半拍，看起来是"长开 → 里面亮起来"。"""
        self._stop_fade()
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(int(MORPH_MS * 0.62))
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._fade = anim
        QTimer.singleShot(int(MORPH_MS * 0.42), anim.start)

    def _stop_fade(self):
        if self._fade is not None:
            try:
                self._fade.stop()
            except RuntimeError:
                pass
            self._fade = None

    def _fade_out(self):
        """收起时内容快速淡掉，**淡完就把内容藏起来**。

        几何用了 OutQuint（前 25% 就缩掉 3/4），排版会在几十像素宽里挤成一团
        —— 实测 70ms 时还能看到"在这儿跟她说话吧"被压成三行小字。所以：
        0.18 个动画时长（≈58ms，约 4 帧）内把内容淡干净，然后 `setVisible(False)`，
        接下来缩小的只是一个干净的圆角形状，和展开时"先成形、内容后亮起来"正好对称。
        """
        if self._fx is None:
            return
        self._stop_fade()
        anim = QPropertyAnimation(self._fx, b"opacity", self)
        anim.setDuration(max(50, int(MORPH_MS * 0.18)))
        try:
            anim.setStartValue(float(self._fx.opacity()))
        except RuntimeError:
            return
        anim.setEndValue(0.0)
        anim.setEasingCurve(QEasingCurve.Type.InQuad)

        def _hide_card():
            # 内容彻底看不见了，藏掉：不然缩小过程中它会被挤成一坨（很难看）
            try:
                self.card.setVisible(False)
            except RuntimeError:
                pass
        anim.finished.connect(_hide_card)
        self._fade = anim
        anim.start()

    def hide_animated(self):
        """收起来：**和打开相反** —— 原路缩回那个圆形按钮，不做横向平移。

        主人 2026-10-26：「关闭窗口动效不够自然，和打开一样缩回去就可以，不要平移消失」。
        原来是往鱼的反方向平移 26px + 淡出，像抽屉被推走；现在是几何 + 圆角 +
        透明度 + 尖角四条一起反向补间，最后收成一个和按钮一样大的圆。
        """
        if not self.isVisible():
            return
        self._follow.stop()          # 收起期间别再跟着鱼挪，否则终点会飘
        self._stop_fade()
        start = QRect(self.geometry())
        self._release_min_size()         # 不放开就只能缩到 179×185（"小方框"的元凶）
        # 终点要钉在**那颗圆按钮自己身上**（不是按尖角高度估的小方块）。
        # 圆按钮此刻可能还没回来 / 位置是旧的，所以先量一次、发完 closing
        # （它会在 `refresh_bubble` 里 reposition）再量第二次。
        end = self._circle_target_rect()
        self._fade_out()
        try:
            self.closing.emit()      # 圆按钮先回来"接住"它
        except RuntimeError:
            pass
        if end is None:
            end = self._circle_target_rect() or self._collapse_rect(start)
        self._circle_size = end.width()
        self._run_morph(start, end, float(self._radius), end.width() / 2.0,
                        self.windowOpacity(), 0.0,
                        on_done=self._hide_after_morph,
                        tail_from=self._tail_grow, tail_to=0.0)

    def _hide_after_morph(self):
        """动画跑完**隔一帧**再隐藏。

        直接 hide 的话，Windows 合成器有时会把"上一帧那个小方块"多留一帧，
        看着就是"半透明小方块闪一下然后没了"（主人 2026-10-26 描述的）。
        """
        QTimer.singleShot(20, self._hide_and_restore)

    def _circle_target_rect(self):
        """圆按钮**现在**在屏幕上的矩形（窗口尺寸 = 圆 + 四周阴影留白）。

        量到了就把收起终点钉死在它身上：缩完和那颗圆严丝合缝，不会出现
        "缩成一个小方框 → 消失 → 圆按钮在旁边冒出来"（主人 2026-10-26 报的观感）。
        量不到（聊天入口关掉了 / 没有圆）返回 None，走老的估算。
        """
        chat = (getattr(self.pet, "ext", None) or {}).get("chat")
        b = getattr(chat, "bubble", None) if chat is not None else None
        if b is None:
            return None
        try:
            if not b.isVisible() or b.width() <= 0:
                return None
            r = b.global_rect()
            w, h = int(r.width()), int(r.height())
        except (RuntimeError, AttributeError, TypeError):
            return None
        c = r.center()
        size_w, size_h = w + MARGIN * 2, h + MARGIN * 2
        return QRect(int(c.x() - size_w / 2.0), int(c.y() - size_h / 2.0),
                     size_w, size_h)

    def _collapse_rect(self, start):
        """收起终点：贴着鱼那条边、尖角那个高度上的一个小方块（约等于那个圆按钮）。

        不做"缩回打开时记下的那个坐标"：鱼会走、会被拖，那个坐标早就过时了，
        缩回旧位置会变成"缩到空气里"。这里按**当前**的贴边位置和尖角高度算。
        """
        size = int(self._circle_size or 0)
        if size <= 0:
            size = 34 + MARGIN * 2          # 不知道按钮多大就按 34 直径算
        size = max(24, min(size, start.width(), start.height()))
        if self._tail_y is not None:
            cy = start.top() + self._tail_y
        elif self._anchor_y is not None:
            cy = self._anchor_y
        else:
            cy = start.top() + start.height() * 0.22
        if self._tail_side == "left":        # 窗口在鱼右边 → 贴着卡片左边缘缩
            cx = start.left() + MARGIN
        else:
            cx = start.left() + start.width() - MARGIN
        geo = self._screen_geo()
        half = size / 2.0
        cx = max(geo.left() + half, min(float(cx), geo.right() + 1 - half))
        cy = max(geo.top() + half, min(float(cy), geo.bottom() + 1 - half))
        return QRect(int(cx - half), int(cy - half), size, size)

    def _hide_and_restore(self):
        self.hide_flyout()
        self._restore_min_size()         # 收完了把"不能小于内容"的限制还回去

    def hide_flyout(self):
        """立刻收起（不走动画）。"""
        try:
            self.card.setVisible(True)  # 收起动画会把内容藏掉，这里恢复（下次打开才是整块）
        except RuntimeError:
            pass
        self._follow.stop()
        self._stop_anim()
        self._stop_fade()
        self._anchor_y = None
        self._anchor_dy = None
        self._tail_y = None
        try:
            self.hide()
        except RuntimeError:
            pass

    def _anim_finished(self):
        """动画跑完了：把 `_anim` 清掉，跟随定时器才能重新接管。"""
        self._anim = None

    def _stop_anim(self):
        if self._anim is not None:
            try:
                self._anim.stop()
            except RuntimeError:
                pass
            self._anim = None

    def _run_anim(self, p0, p1, o0, o1, on_done=None):
        self._stop_anim()
        grp = QParallelAnimationGroup(self)
        a_pos = QPropertyAnimation(self, b"pos", grp)
        a_pos.setDuration(SLIDE_MS)
        a_pos.setStartValue(p0)
        a_pos.setEndValue(p1)
        a_pos.setEasingCurve(QEasingCurve.Type.OutCubic)
        a_op = QPropertyAnimation(self, b"windowOpacity", grp)
        a_op.setDuration(SLIDE_MS)
        a_op.setStartValue(o0)
        a_op.setEndValue(o1)
        a_op.setEasingCurve(QEasingCurve.Type.OutCubic)
        grp.finished.connect(self._anim_finished)
        if on_done is not None:
            grp.finished.connect(on_done)
        self._anim = grp
        grp.start()

    def _fit_bubble(self, bubble):
        """按当前视口宽度定气泡宽度和最小高度。

        ⚠️ 这里踩过两次：
        1. `QLabel` 开着 wordWrap，布局仍按"单行宽度"给它排 → 长句右边直接消失。
        2. 只对"超过 maxw"的才钉宽度也不行 —— 文字宽刚好卡在"maxw 减 padding"那个
           缝里时判定成"不用换行"，结果照样被裁（实测「好，你把文件拖到我【身上吧。】」）。
        现在统一：**宽度 = min(文字宽 + padding, 可用宽)**，高度按换行后的实际行数给。
        """
        maxw = max(120, self.scroll.viewport().width() - 24)
        try:
            fm = bubble.fontMetrics()
            note = getattr(bubble, "role", "") == "note"
            pad_w = 14 if note else 26          # QSS：note 是左右 6+6，普通气泡 12+12 + 边框
            pad_h = 8 if note else 22           # 上下 2+2 / 10+10 + 边框
            tw = fm.horizontalAdvance(bubble.text())
            # +8 是余量：`horizontalAdvance` 和真实渲染差一两像素时，
            # 正好卡满的气泡会把最后一个字裁掉（实测「…第二列求【和】」）
            w = max(60, min(tw + pad_w + 8, maxw))
            bubble.setFixedWidth(w)
            br = fm.boundingRect(QRect(0, 0, max(40, w - pad_w), 10000),
                                 int(Qt.TextFlag.TextWordWrap)
                                 | int(Qt.AlignmentFlag.AlignLeft),
                                 bubble.text())
            bubble.setMinimumHeight(br.height() + pad_h)
        except (RuntimeError, AttributeError):
            pass

    # ------------------------------------------------------------------ 事件
    def eventFilter(self, obj, ev):
        """桌宠每移一下，板子立刻跟着走（别等 60ms 的定时器）。

        拖动的时候桌宠一帧移十几像素、50 帧/秒，靠定时器追就是"一跳一跳"；
        这里直接同步，视觉上是黏在一起的。
        """
        try:
            if obj is self.pet and ev.type() in (QEvent.Type.Move, QEvent.Type.Resize):
                if self.isVisible() and self._anim is None and not self._hover:
                    self._on_follow()
        except RuntimeError:
            return False
        return False

    def resizeEvent(self, ev):
        """窗口变宽/变窄：所有气泡的宽度跟着重算（不然换行位置还是旧的）。"""
        super().resizeEvent(ev)
        try:
            for b in self.body.findChildren(_Bubble):
                self._fit_bubble(b)
        except (RuntimeError, AttributeError):
            pass
        self._fit_status()
        self._fit_chips()
        # 消息里那几排按钮（派活结果下面那两颗）也跟着重排
        try:
            for cb in self.body.findChildren(_ChipBox):
                _fit_chipbox(cb, getattr(cb, "_dfy_btns", []),
                             max(100, self._inner_w() - 8))
        except (RuntimeError, AttributeError):
            pass

    def enterEvent(self, ev):
        """光标进到板子上：停住跟随（否则按钮一直在躲光标，点不中）。"""
        self._hover = True
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False
        if self.isVisible() and self._anim is None:
            self._follow.start()
        super().leaveEvent(ev)

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.hide_animated()
            ev.accept()
            return
        super().keyPressEvent(ev)

    def showEvent(self, ev):
        super().showEvent(ev)
        self._follow.start()

    def hideEvent(self, ev):
        self._follow.stop()
        super().hideEvent(ev)
        try:
            self.closed.emit()
        except RuntimeError:
            pass

    def sizeHint(self):
        return QSize(W_DEFAULT, H_DEFAULT)


class FlyoutExtension:
    """挂到 `pet.ext["flyout"]` 上。窗口懒建（第一次要才建）。"""

    def __init__(self, pet):
        self.pet = pet
        self._win = None
        # ⚠️ 窗口是懒建的：`chat.open()` 先 `set_mode("chat")` 再 `show_from_circle()`，
        # 这时窗口还不存在 —— 模式必须缓存在扩展上，建窗口时补进去（不然第一次点圆按钮
        # 打开聊天，mode 永远是空，派活跑完照样会打断聊天）。
        self._mode = ""

    def start(self):
        return self

    def window(self):
        if self._win is None:
            self._win = FlyoutWindow(self.pet)
            self._win.set_mode(self._mode)
        return self._win

    @property
    def visible(self):
        try:
            return self._win is not None and self._win.isVisible()
        except RuntimeError:
            self._win = None
            return False

    def show(self, title=None, subtitle=None, animate=True, anchor_y=None):
        w = self.window()
        if title is not None:
            w.set_title(title)
        if subtitle is not None:
            w.set_subtitle(subtitle)
        w.show_at_pet(animate=animate, anchor_y=anchor_y)
        return w

    def show_from_circle(self, circle_rect, title=None, subtitle=None, anchor_y=None):
        """从桌宠身上那个圆形按钮长成整块板子（过渡动画见 `FlyoutWindow.show_from_circle`）。"""
        w = self.window()
        if title is not None:
            w.set_title(title)
        if subtitle is not None:
            w.set_subtitle(subtitle)
        w.show_from_circle(circle_rect, anchor_y=anchor_y)
        return w

    def hide(self):
        if self._win is not None:
            try:
                self._win.hide_animated()
            except RuntimeError:
                self._win = None

    def toggle(self, title=None):
        if self.visible:
            self.hide()
        else:
            self.show(title)
        return self.visible

    # 转发几个最常用的（P5 / P6 直接 ext.add(...) 就行）
    def add(self, role, text, animate=True):
        return self.window().add(role, text, animate=animate)

    def clear(self):
        if self._win is not None:
            self._win.clear()

    def message_count(self):
        """板子上有几条消息（聊天重绘历史前判空用；窗口没建就是 0）。"""
        if self._win is None:
            return 0
        try:
            return self._win.message_count()
        except RuntimeError:
            self._win = None
            return 0

    def set_mode(self, mode):
        self._mode = str(mode or "")
        if self._win is not None:
            try:
                self._win.set_mode(self._mode)
            except RuntimeError:
                self._win = None

    @property
    def mode(self):
        try:
            return self._win.mode if self._win is not None else self._mode
        except RuntimeError:
            self._win = None
            return self._mode

    def set_busy(self, on):
        if self._win is not None:
            self._win.set_busy(on)

    def add_with_actions(self, role, text, actions):
        """一条消息 + 下面几颗按钮（`[(文字, 回调), …]`），见窗口里的同名方法。"""
        return self.window().add_with_actions(role, text, actions)

    def set_status(self, text, stoppable=None):
        if self._win is not None:
            self._win.set_status(text, stoppable=stoppable)

    def set_stop_handler(self, fn):
        self.window().set_stop_handler(fn)

    def set_send_handler(self, fn):
        self.window().set_send_handler(fn)

    def set_title(self, text):
        if self._win is not None:
            self._win.set_title(text)

    def set_subtitle(self, text):
        if self._win is not None:
            self._win.set_subtitle(text)

    def set_clear_handler(self, fn):
        self.window().set_clear_handler(fn)

    def set_quick_actions(self, actions):
        self.window().set_quick_actions(actions)


def setup(pet):
    return FlyoutExtension(pet).start()
