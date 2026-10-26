# -*- coding: utf-8 -*-
"""任务派发（P6）：把文件拖到桌宠身上 → 选一个 Agent → 后台跑 → 回来说结果。

和聊天（P5）是**两条分开的通道**（主人定的）：聊天走 API，任务走 Agent，互不干扰。

流程（对应 `三项功能可行性评估.md` 3.3）：
    ① 拖文件到桌宠身上 → 她"嗯"一声 + 气泡报文件名
    ② 侧边浮窗打开：上面列出收到的文件，底部一排小按钮选 Agent（Codex / DSH / 只打开）
    ③ 输入要它干什么 → 回车 → 后台起进程，她播「深度思考」
    ④ 进程退出 → 浮窗里贴出最后几行输出 + 「打开输出文件」；她冒一句短的

为什么用 `subprocess.Popen` + `proc.poll()` 而不是 ACP：
    可行性评估 3.4 的结论就是这条最可靠 —— 不看日志格式、不管协议，
    **进程结束就是结束**。ACP 要额外装 `@agentclientprotocol/codex-acp` +
    asyncio 跑独立线程 loop，收益是能流式看到中间过程，但现在不需要，先不上。

⚠️ 三条硬规矩：
  1. 起进程只在主线程做（`Popen` 本身很快），**读输出 / 等退出绝不能在主线程**；
     这里用"进程把输出直接写文件 + 定时器 poll 状态"，主线程不碰管道。
  2. 输出可能几十 KB —— 只截最后几行给浮窗看，全文留在日志文件里。
  3. 拖放要求窗口没开"鼠标穿透"（`WA_TransparentForMouseEvents` 会把拖放也吃掉）。
"""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from PySide6.QtCore import QObject, QTimer

# 每个 Agent 最多同时跑几个（多了会互相抢 CPU，也看不过来）
MAX_RUNNING = 3
POLL_MS = 700                 # 多久看一次进程有没有退出
TAIL_LINES = 12               # 浮窗里贴多少行输出
LOG_DIR = os.path.join(tempfile.gettempdir(), "dafeiyu-dispatch")
DSH_CMD = r"E:\DeepSeek Harness\resources\runtime\cli\bin\dsh.cmd"


def _wrap(exe):
    """把一个可执行名 / 路径变成能直接给 `Popen` 的前缀。

    ⚠️ Windows 上 `codex` / `dsh` 都是 **.cmd**（npm 装的 / Harness 自带的），
    而 `CreateProcess` **不能直接执行 .cmd** —— `Popen(["codex", ...])` 会
    `FileNotFoundError: [WinError 2]`（实测）。所以 .cmd / .bat 前面要垫一层 shell。
    """
    path = shutil.which(exe) or exe
    if path.lower().endswith((".cmd", ".bat")):
        return [os.environ.get("COMSPEC") or "cmd.exe", "/c", path]
    return [path]


# 日志里的"框架噪音"：codex / dsh 都会打一堆模板行和大块 HTML/JSON。
# 2026-10-26 主人说「派活没拿到任何文件和提示词」—— 其实它全拿到了（日志里有完整的
# 文件和指令），但浮窗只贴"最后 12 行"，而那 12 行正好是 MCP 报错的 HTML 和
# `tokens used` 之类的样板，看着像什么都没干。这里把噪音滤掉，只留人话。
_NOISE_PREFIX = (
    "OpenAI Codex v", "Reading prompt from stdin", "workdir:", "model:",
    "provider:", "approval:", "sandbox:", "reasoning effort:", "reasoning summaries:",
    "session id:", "tokens used", "mcp:", "exec", "exited ", "succeeded in",
    "--------", "user ", "codex_", "ERROR ", "WARN ",
)


def split_args(text):
    """把配置里那串参数拆成 list。

    用 `posix=False`：这样才能保住 Windows 路径里的反斜杠和用户自己写的引号
    （`posix=True` 会把 `C:////a` 吃成 `C:a`）。
    """
    text = (text or "").strip()
    if not text:
        return []
    try:
        return shlex.split(text, posix=False)
    except ValueError:
        return text.split()


def tail_text(path, lines=TAIL_LINES, limit=1800):
    """读文件最后几行**人话**（文件可能很大，只读尾巴）。

    - 丢掉超长行（HTML / 压缩 JSON，动辄几千字符，贴进浮窗就是一屏乱码）
    - 丢掉 codex / dsh 的样板行（`tokens used`、`mcp:`、`exec ...` 这些）
    - 剩下的还是空的，就退回"原始最后几行"，至少让人知道它确实干活了
    """
    try:
        size = os.path.getsize(path)
        with open(path, "rb") as f:
            f.seek(max(0, size - 65536))
            raw = f.read()
        raw_text = raw.decode("utf-8", "replace")
    except OSError:
        return ""
    noisy = [r.strip() for r in raw_text.splitlines() if r.strip()]
    clean = []
    for r in noisy:
        if len(r) > 240:                      # HTML / 大 JSON
            continue
        head = r[:24]
        if any(head.startswith(n) or r.startswith(n) for n in _NOISE_PREFIX):
            continue
        clean.append(r)
    rows = clean or noisy
    out = "\n".join(rows[-lines:])
    return out[-limit:]


# --------------------------------------------------------------------------- #
# 适配器：统一成"给文件 + 一句话 → 一条命令"
# --------------------------------------------------------------------------- #
class Adapter:
    key = ""
    label = ""
    can_dispatch = True

    def build(self, files, instruction, cwd):
        """返回 (命令行 list, 要喂给 stdin 的文字)。

        为什么指令走 stdin 而不是命令行参数：里面有换行 / 中文 / 引号 / 路径，
        而 Windows 上 .cmd 还要过一层 shell，参数会被**二次解析**，很容易炸。
        """
        raise NotImplementedError

    def describe(self):
        return self.label


class CliAdapter(Adapter):
    """**配置驱动的通用 Agent**：`cmd + args`，任务文字从 stdin 喂进去。

    2026-10-26 主人要的：设置里能自己加 Agent（Claude Code / Pi / 原生 GPT …），
    不需要的能删掉（「只打开」始终留着）。所以除了「只打开」，别的都走这一个类，
    命令怎么拼、要不要额外加目录，全看配置里那几个字段。

    配置字段（存在 `cfg["dispatch_agents"]`，一个 list）：
        key            唯一名字（也用来记住"上次选的谁"）
        label          按钮上显示的名字
        on             开没开（关掉的不会出现在那排按钮里）
        cmd            可执行名或完整路径（.cmd / .bat 会自动垫一层 shell）
        args           参数，空格分隔（带空格的路径自己加引号）
        add_dir_flag   额外目录用哪个参数传（codex 是 `--add-dir`；没有就留空）
    """

    def __init__(self, spec):
        self.spec = dict(spec)
        self.key = str(spec.get("key") or "agent")
        self.label = str(spec.get("label") or self.key)
        self.can_dispatch = True

    def build(self, files, instruction, cwd):
        # 工作目录靠 `Popen(cwd=...)` 给，不在命令行里重复一遍
        cmd = _wrap(self.spec.get("cmd") or self.key) + split_args(self.spec.get("args"))
        flag = str(self.spec.get("add_dir_flag") or "").strip()
        if flag:
            # ⚠️ codex 的 `-s workspace-write` 只允许访问 workdir（+ /tmp）。
            # 拖进来的文件分布在几个目录时，不在 cwd 里的那些它**根本读不到**，
            # 会满盘 `dir /s` 找 —— 表现就是「完全看不到我拖的东西」（2026-10-26）。
            seen = {os.path.normcase(cwd)}
            for f in files:
                d = f if os.path.isdir(f) else os.path.dirname(f)
                if not d or os.path.normcase(d) in seen:
                    continue
                seen.add(os.path.normcase(d))
                cmd += [flag, d]
        return cmd, self._prompt(files, instruction)

    @staticmethod
    def _prompt(files, instruction):
        rel = "\n".join("- " + f for f in files)
        return (f"我拖给你这些东西：\n{rel}\n\n"
                f"要做的事：{instruction}\n\n"
                f"（上面都是完整路径，直接按路径读；别递归扫描整个磁盘去找，"
                f"找不到就直说。做完用一两句话说明结果。）")


# 「只打开」：不派活，只把文件交给系统默认程序（用户想自己上手时用）。**始终保留。**
class OpenAdapter(Adapter):
    key = "open"
    label = "只打开"
    can_dispatch = False


OPEN_ADAPTER = OpenAdapter()

# 内置默认（老配置没有 `dispatch_agents` 时就用这两条，行为跟以前一模一样）
BUILTIN_SPECS = [
    {"key": "codex", "label": "Codex", "on": True, "cmd": "codex",
     "args": "exec -s workspace-write --skip-git-repo-check",
     "add_dir_flag": "--add-dir"},
    {"key": "dsh", "label": "DSH", "on": True, "cmd": DSH_CMD,
     "args": "--profile headless -", "add_dir_flag": ""},
]

# 自动检测用的一张表：本机装了什么就自动配上。
# ⚠️ 只收**参数能确定**的（任务文字必须能从 stdin 喂进去）。拿不准参数的别往里加，
# 不然自动配出来是个跑不通的命令，比不配更糟。
KNOWN_CLIS = [
    {"key": "codex", "label": "Codex", "exe": "codex",
     "args": "exec -s workspace-write --skip-git-repo-check", "add_dir_flag": "--add-dir"},
    # DSH 不在 PATH 里，只能认它固定的安装位置
    {"key": "dsh", "label": "DSH", "exe": DSH_CMD, "args": "--profile headless -",
     "add_dir_flag": ""},
]


def detect_clis(existing_keys=()):
    """扫一遍本机，返回 (找到了的 spec 列表, 没找到的 [(key, label), ...])。"""
    found, missed = [], []
    for item in KNOWN_CLIS:
        key = item["key"]
        if key in existing_keys:
            continue
        exe = item["exe"]
        path = shutil.which(exe) or (exe if os.path.isfile(exe) else "")
        if not path:
            missed.append((key, item["label"]))
            continue
        found.append({"key": key, "label": item["label"], "on": True,
                      "cmd": path if os.path.isabs(path) else exe,
                      "args": item["args"], "add_dir_flag": item["add_dir_flag"]})
    return found, missed


class Task:
    """一次派活。进程 + 输出文件 + 状态。"""

    __slots__ = ("tid", "agent", "files", "instruction", "cwd", "cmd", "proc",
                 "out_path", "started", "state", "code", "notified")

    def __init__(self, tid, agent, files, instruction, cwd, cmd, proc, out_path):
        self.tid = tid
        self.agent = agent
        self.files = files
        self.instruction = instruction
        self.cwd = cwd
        self.cmd = cmd
        self.proc = proc
        self.out_path = out_path
        self.started = time.time()
        self.state = "running"        # running / done / failed / cancelled
        self.code = None
        self.notified = False

    @property
    def elapsed(self):
        return time.time() - self.started


class DispatchExtension(QObject):
    """挂到 `pet.ext["dispatch"]`。拖放事件由 `PetWindow` 转发进来。"""

    def __init__(self, pet):
        super().__init__()
        self.pet = pet
        self.tasks = {}               # tid → Task
        self._seq = 0
        self._pending = []            # 刚拖进来、还没说要干什么的文件
        self._hint_shown = False
        self._timer = None
        self._hooked = False          # 「停止」按钮有没有挂到浮窗上
        os.makedirs(LOG_DIR, exist_ok=True)

    # ------------------------------------------------------------------ 生命周期
    def start(self):
        self._timer = QTimer(self)
        self._timer.setInterval(POLL_MS)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        return self

    def _hook_flyout(self, fly):
        """第一次拿到浮窗时把「停止」挂上。

        ⚠️ 和 chat 一样：`load_extensions` 是先 setup 完所有扩展再统一赋 `pet.ext`，
        `start()` 里拿不到 flyout（实测），所以延迟到第一次真正用它的时候。
        """
        if fly is None or self._hooked:
            return
        try:
            fly.set_stop_handler(self.stop_all)
            self._hooked = True
        except Exception:
            pass

    def stop_all(self):
        """「停止」按钮：把正在跑的全部掐掉（走了 cancel 的正规路径，会播报）。"""
        running = [t for t in self.tasks.values() if t.state == "running"]
        for t in running:
            self.cancel(t.tid)
        fly = self._flyout()
        if not running and fly is not None:
            fly.set_status("")
        self.pet.say("停下了" if running else "现在没有在跑的任务", seconds=2.6, again=True)

    def _flyout(self):
        return (getattr(self.pet, "ext", {}) or {}).get("flyout")

    def _chat(self):
        return (getattr(self.pet, "ext", {}) or {}).get("chat")

    # ------------------------------------------------------------------ Agent 列表
    def agent_specs(self):
        """当前配置的 Agent（老配置没有就补上内置两条，行为跟以前一样）。"""
        specs = self.pet.cfg.get("dispatch_agents")
        # 只在"根本没配过"时补默认。**空列表是用户故意删光的**（只剩「只打开」），
        # 不能再给他补回来，不然删了又自己长出来（2026-10-26 踩过）。
        if not isinstance(specs, list):
            specs = [dict(x) for x in BUILTIN_SPECS]
            self.pet.cfg["dispatch_agents"] = specs
        return specs

    def agents(self):
        """真正能用的适配器：开着的那些 + 「只打开」（**始终**在最后）。"""
        out = {}
        for spec in self.agent_specs():
            if not spec.get("on", True):
                continue
            ad = CliAdapter(spec)
            out[ad.key] = ad
        out["open"] = OPEN_ADAPTER
        return out

    def detect(self, existing_specs=None):
        """自动检测本机装了哪些 Agent，返回 (新发现, 没找到的)。"""
        specs = existing_specs if existing_specs is not None else self.agent_specs()
        return detect_clis({str(x.get("key") or "") for x in specs})

    def save_specs(self, specs):
        self.pet.cfg["dispatch_agents"] = list(specs)
        try:
            self.pet.save_config()
        except Exception:
            pass

    def _agent(self):
        agents = self.agents()
        key = self.pet.cfg.get("dispatch_agent") or next(iter(agents), "open")
        return agents.get(key) or agents.get("open") or OPEN_ADAPTER

    def set_agent(self, key):
        if key in self.agents():
            self.pet.cfg["dispatch_agent"] = key
            try:
                self.pet.save_config()
            except Exception:
                pass
            self._refresh_actions()

    # ------------------------------------------------------------------ 拖放
    @staticmethod
    def mime_paths(mime):
        """从拖放数据里取出本地文件路径（去重、保序、只要真实存在的）。"""
        out = []
        try:
            if mime.hasUrls():
                for url in mime.urls():
                    # ⚠️ `QUrl.toLocalFile()` 给的是**正斜杠**（C:/Users/…），
                    # 后面要当 cwd、要拼进命令行，统一转成系统原生分隔符。
                    p = os.path.normpath(url.toLocalFile() or "")
                    if p and os.path.exists(p) and p not in out:
                        out.append(p)
        except Exception:
            pass
        return out

    def can_accept(self, mime):
        if self.pet.cfg.get("passthrough"):
            return False          # 穿透状态下窗口根本收不到拖放，别给假希望
        return bool(self.mime_paths(mime))

    def on_drag_enter(self):
        """文件拖到身上了（还没松手）：给点反应，不然她一动不动像坏了。"""
        try:
            self.pet.press_t = 1.0
            if not self._hint_shown:
                self._hint_shown = True
                self.pet.say("给我吗？松开手就行", seconds=2.6, again=True)
        except Exception:
            pass

    def on_drop(self, paths):
        """松手了：记住文件，把浮窗打开，让她问"要我做什么"。"""
        files = [p for p in (paths or []) if os.path.exists(p)]
        if not files:
            return
        self._pending = files
        self._hint_shown = False
        self._open_panel(files)

    def _open_panel(self, files):
        fly = self._flyout()
        names = "、".join(os.path.basename(f) for f in files[:4])
        if len(files) > 4:
            names += f" 等 {len(files)} 个"
        self.pet.say(f"收到：{names}", seconds=3.2, again=True)

        if fly is None:
            self.pet.say("浮窗没起来，派活用不了（pet_ext/flyout.py）", seconds=4.0, again=True)
            return
        self._hook_flyout(fly)
        fly.set_title("派活")
        fly.set_subtitle("交给谁：")
        fly.set_mode("task")
        fly.set_status("")
        fly.set_send_handler(self._on_instruction)
        fly.set_clear_handler(self.clear_panel)
        fly.set_quick_actions(self._actions())
        fly.show(title="派活")
        fly.clear()          # 每次派活从空白开始，别把上次的输出和聊天记录堆在上面
        fly.add("note", f"收到 {len(files)} 个文件：{names}")
        for f in files[:6]:
            fly.add("note", "· " + os.path.basename(f))
        fly.add("her", "要我拿它们做什么？说一句就行（回车发送）。")
        fly.add("note", "上面那排选谁干活；「只打开」点了就直接打开，不用再说一句。")

    def _actions(self):
        cur = self._agent().key
        acts = []
        for key, ad in self.agents().items():
            # 第三项是"选中"标记：选中的那颗由浮窗画成强调色实底（比文字前加「· 」明显）
            # ⚠️ `clicked` 带一个 checked(bool) 参数，而且 PySide 会拿它去填 lambda 的
            # **第一个可选参数** —— 写 `lambda k=key: ...` 时 k 会变成 False，
            # `set_agent(False)` 静默什么都不做（主人 2026-10-26："选择按钮无法使用"）。
            # 项目和 ui_console 里的老写法都是 `lambda _=False, v=...`，这里照抄。
            acts.append((ad.label, (lambda _=False, k=key: self.pick_agent(k)), key == cur))
        return acts

    def pick_agent(self, key):
        """点那排 chip。

        选「只打开」时**不用再打一句话**：点了就立刻用系统默认程序把文件打开
        （主人 2026-10-26：「只打开应该点击了就直接打开，而不是还要发一句话」）。
        """
        self.set_agent(key)
        if key == "open" and self._pending:
            self.dispatch("open", "", self._pending)

    def _refresh_actions(self):
        fly = self._flyout()
        if fly is not None:
            fly.set_quick_actions(self._actions())

    def clear_panel(self):
        self._pending = []

    # ------------------------------------------------------------------ 派发
    def _on_instruction(self, text):
        text = (text or "").strip()
        if not text:
            return
        if not self._pending:
            fly = self._flyout()
            if fly is not None:
                fly.add("note", "没有待处理的文件了 —— 先把文件拖到桌宠身上。")
            return
        self.dispatch(self._agent().key, text, self._pending)

    @staticmethod
    def pick_cwd(files):
        """工作目录怎么定 —— 它决定 agent 在哪儿干活、能访问哪些地方。

        2026-10-26 主人问「在 codex/dsh 里要很久才同步我拖进去的内容」：
        - 拖**文件夹**时，原来 cwd 取的是它的**父目录**，agent 还得先自己"找进去"
          （日志里真见过 `dir /s /b C:\\...\\Temp\\笔记.txt` 在满盘搜）；
        - 拖的文件跨目录时，第一个之外的都在沙箱外，**根本读不到**。
        所以：单个路径就用它自己（文件夹）/ 它的目录（文件）；多个就用公共父目录。
        """
        if not files:
            return os.getcwd()
        dirs = []
        for f in files:
            d = f if os.path.isdir(f) else os.path.dirname(f)
            if d:
                dirs.append(d)
        if not dirs:
            return os.getcwd()
        if len(dirs) == 1:
            return dirs[0]
        try:
            common = os.path.commonpath(dirs)
        except ValueError:                     # 跨盘符，没有公共前缀
            return dirs[0]
        # 公共父目录要是只剩盘符根（`D:\`），agent 会在整个盘上翻 —— 太宽，退回第一个
        tail = common[len(os.path.splitdrive(common)[0]):].strip("\\/")
        return common if tail else dirs[0]

    def dispatch(self, agent_key, instruction, files=None):
        """真正起进程。返回 Task（失败返回 None）。"""
        files = list(files or self._pending)
        if not files:
            return None
        agents = self.agents()
        ad = agents.get(agent_key) or agents.get("open") or OPEN_ADAPTER
        fly = self._flyout()

        if not ad.can_dispatch:
            for f in files:
                self.open_path(f)
            if fly is not None:
                fly.add("note", f"已经帮你打开 {len(files)} 个文件，剩下的你自己来。")
            self._pending = []
            return None

        running = [t for t in self.tasks.values() if t.state == "running"]
        if len(running) >= MAX_RUNNING:
            if fly is not None:
                fly.add("note", f"已经有 {len(running)} 个在跑了，等一个跑完再来。")
            return None

        cwd = self.pick_cwd(files)
        self._seq += 1
        tid = time.strftime("%H%M%S") + f"-{self._seq}"
        out_path = os.path.join(LOG_DIR, f"{tid}-{ad.key}.log")
        try:
            cmd, feed = ad.build(files, instruction, cwd)
        except Exception as exc:
            # 配置里参数写坏了（引号不配对之类）不该把整个回调打崩
            if fly is not None:
                fly.set_status("")
                fly.add("note", f"命令没拼出来：{type(exc).__name__}: {exc}")
            return None

        # 先给个"马上就起"的反馈，别让人对着没反应的窗口猜（启动本身要十几秒）
        if fly is not None:
            fly.set_status(f"● 正在启动 {ad.label}…（它自己要加载一堆东西，十几秒很正常）")

        try:
            proc = self._spawn(cmd, cwd, out_path, feed)
        except FileNotFoundError:
            msg = f"找不到 {ad.label} 的命令（{cmd[0]}），是不是没装 / 没进 PATH？"
            if fly is not None:
                fly.set_status("")
                fly.add("note", msg)
            self.pet.say("找不到它的命令", seconds=3.5, again=True)
            return None
        except Exception as exc:
            if fly is not None:
                fly.set_status("")
                fly.add("note", f"起进程失败：{type(exc).__name__}: {exc}")
            return None

        task = Task(tid, ad.key, files, instruction, cwd, cmd, proc, out_path)
        self.tasks[tid] = task
        self._pending = []
        if fly is not None:
            # ⚠️ 用户这句**已经**被 `flyout._on_send()` 加进板子了（它先 add 再回调）。
            # 这里再 add 一次的话，浮窗里每条指令都显示两遍（2026-10-26 实测）。
            # 明确写出来"它收到了什么"，省得以为没喂进去（主人 2026-10-26 就怀疑过）。
            # 工作目录只报文件夹名 —— 完整路径动辄三行，把气泡撑爆（要看全的点按钮）
            folder = self._folder_label(cwd)
            fly.add("note", f"已交给 {ad.label}：{len(files)} 个文件 + 你这句话。"
                            f"它在「{folder}」里干活，跑完我把结果贴上来。")
            fly.set_status(f"● {ad.label} 已启动，正在跑…")
            fly.set_busy(False)
        self.pet.say(f"交给 {ad.label} 了，你忙你的", seconds=3.0, again=True)
        self._play_thinking()
        return task

    def _spawn(self, cmd, cwd, out_path, feed=""):
        """起进程，stdout / stderr 直接写文件（主线程不碰管道），指令从 stdin 喂进去。

        单独一个方法是为了测试时能换掉（不然每条用例都要真起 codex）。
        """
        f = open(out_path, "wb")
        try:
            creation = 0
            if sys.platform == "win32":
                # 别弹黑窗口（桌宠是 GUI 程序，弹一堆控制台窗口很吓人）
                creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            proc = subprocess.Popen(
                cmd, cwd=cwd, stdout=f, stderr=subprocess.STDOUT,
                stdin=subprocess.PIPE if feed else subprocess.DEVNULL,
                creationflags=creation, shell=False)
        finally:
            f.close()        # 子进程已经拿到句柄了，父进程这份可以关

        if feed:
            # 指令很短（几 KB），直接写不会被管道缓冲卡住；写完关掉让子进程看到 EOF
            try:
                proc.stdin.write(feed.encode("utf-8", "replace"))
                proc.stdin.close()
            except Exception:
                pass
        return proc

    def _poll(self):
        """定时看有没有跑完的（主线程，只做 `proc.poll()` 这种轻活）。"""
        for task in list(self.tasks.values()):
            if task.state != "running":
                continue
            try:
                code = task.proc.poll()
            except Exception as exc:      # 进程句柄没了 / 起进程时就出了岔子
                task.code = -1
                task.state = "failed"
                task.out_path = task.out_path
                self._announce(task, extra=f"看不了进程状态：{exc}")
                continue
            if code is None:
                continue
            task.code = code
            task.state = "done" if code == 0 else "failed"
            self._announce(task)
        self._tick_status()

    def _tick_status(self):
        """每 700ms 刷一次输入框上面那行状态。

        主人 2026-10-26：「接收太慢，而且我根本不知道成功没有」—— 回车之后除了
        「交给 Codex 了」就再没动静，几十秒里完全看不出它在跑还是卡死了。
        这里实时写：谁在跑、跑了多久、最后吐出来一句什么。
        """
        fly = self._flyout()
        if fly is None:
            return
        # ⚠️ 正在聊天时**不写**「● Codex 正在跑 · 正在读 xxx」那种派活状态行 ——
        # 糊在聊天框上面会让人以为她的回复卡住了（跑完会在聊天流里补一条结果）。
        # 但「停止」这颗按钮不能跟着消失：主人 2026-10-27 要的就是随时能掐掉任务。
        # 所以聊天模式下只留一行极短的「● 后台任务 · N 秒」+ 停止。
        chatting = getattr(fly, "mode", "") == "chat"
        running = [t for t in self.tasks.values() if t.state == "running"]
        if not running:
            fly.set_status("", stoppable=False)
            return
        t = max(running, key=lambda x: x.elapsed)
        if chatting:
            more = f"（共 {len(running)} 个）" if len(running) > 1 else ""
            fly.set_status(f"● 后台任务 · {int(t.elapsed)} 秒{more}", stoppable=True)
            return
        ad = self.agents().get(t.agent)
        label = ad.label if ad is not None else t.agent
        parts = [f"● {label} 正在跑 · {int(t.elapsed)} 秒"]
        if len(running) > 1:
            parts.append(f"另有 {len(running) - 1} 个")
        elif t.elapsed > 8:
            parts.append("（启动要十几秒，正常）")
        last = tail_text(t.out_path, lines=1, limit=42)
        if last:
            parts.append(last.strip().replace("\n", " "))
        text = " · ".join(parts)
        if len(text) > 56:
            text = text[:54] + "…"
        # stoppable=True：右边露「停止」（2026-10-27 主人要的，原来只能改代码掐任务）
        fly.set_status(text, stoppable=True)

    def _announce(self, task, extra=""):
        if task.notified:
            return
        task.notified = True
        ad = self.agents().get(task.agent)
        label = ad.label if ad is not None else task.agent
        fly = self._flyout()
        tail = tail_text(task.out_path)
        ok = task.state == "done"
        if task.state == "cancelled":
            head = "⏹ 停下了"
        else:
            head = "✅ 弄完了" if ok else f"⚠️ 出问题了（退出码 {task.code}）"
        if extra:
            head = f"{head}（{extra}）"
        if fly is not None:
            # ⚠️ 你**正在聊天**（板子可见 + 模式是 chat）→ 别打断：不弹窗、不换 chip、不碰状态行。
            # 尤其不能换成「再派一个」那颗 —— 它一点就 `clear()`，聊天记录全没。
            # 结果照样写进板子（就在聊天流里），下次打开也看得到。
            chatting = (getattr(fly, "mode", "") == "chat") and fly.visible
            if not chatting:
                fly.set_status("")              # 跑完了，状态行收起来
                # ⚠️ 窗口可能已经被关掉了（主人去干别的了）—— 跑完必须自己冒出来，
                # 否则"到底成功没有"永远是个问号（主人 2026-10-26 原话）。
                try:
                    if not fly.visible:
                        fly.show()
                except Exception:
                    pass
                # 从聊天切过来的：标题得跟着换，否则弹出一个叫「和她聊聊」的派活结果
                if getattr(fly, "mode", "") != "task":
                    fly.set_title("派活结果")
                    fly.set_subtitle("")
                    fly.set_mode("task")
            if chatting:
                # 不打断聊天，但**入口不能丢**：按钮跟着这条消息走，随聊天流一起滚上去。
                # （换成整块板子的 chip 就会把「再派一个」糊上来，一点清空聊天记录。）
                fly.add_with_actions(
                    "note", f"{head} · {label} · 用时 {task.elapsed:.0f} 秒",
                    [("输出文件", lambda _=False, p=task.out_path: self.open_path(p)),
                     (f"打开{self._folder_label(task.cwd)}",
                      lambda _=False, p=task.cwd: self.open_path(p))])
            else:
                fly.add("note", f"{head} · {label} · 用时 {task.elapsed:.0f} 秒")
            fly.add("her" if ok else "note", tail or "（它没有输出任何内容）")
            if not chatting:
                fly.set_quick_actions([
                    # ⚠️ 同上：第一个参数会被 checked(bool) 填掉，函数要拿的实际参数只能靠默认值
                    ("输出文件", lambda _=False, p=task.out_path: self.open_path(p)),
                    (f"打开{self._folder_label(task.cwd)}",
                     lambda _=False, p=task.cwd: self.open_path(p)),
                    ("再派一个", lambda _=False: self._open_panel(task.files)),
                ])
        if task.state == "cancelled":
            said = "停下了，看旁边"
        else:
            said = "弄完了，看旁边" if ok else "它说不行，看旁边"
        self.pet.say(said, seconds=4.0, again=True)
        self._play_done(ok)

    # ------------------------------------------------------------------ 杂项
    # 工作目录 → 给人看的短名字。Windows 上桌面文件夹叫 `Desktop`，
    # 直接显示会让人以为跑错了地方（主人 2026-10-27：「打开工作目录是桌面」——
    # 其实按设计就是桌面，因为文件本来就在桌面上，只是界面上没说清）。
    _FOLDER_ALIAS = {"Desktop": "桌面", "Downloads": "下载", "Documents": "文档",
                     "Pictures": "图片", "Music": "音乐", "Videos": "视频"}

    @classmethod
    def _folder_label(cls, path):
        """工作目录 → 短名字（桌面 / 下载 / 临时目录 / 项目名 / D:\\）。"""
        try:
            p = os.path.normpath(str(path or ""))
            name = os.path.basename(p)
            if not name:                       # 盘符根（D:\）
                drive = os.path.splitdrive(p)[0]
                return (drive + "\\") if drive else p
            _tmp = os.path.normpath(os.environ.get("TEMP") or "")
            if _tmp and p.lower().startswith(_tmp.lower()):
                return "临时"
            return cls._FOLDER_ALIAS.get(name, name)
        except Exception:
            return "工作目录"

    def open_path(self, path):
        """用系统默认程序打开文件 / 目录。"""
        try:
            if sys.platform == "win32":
                os.startfile(path)          # noqa: S606  这是本地可信路径
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
            return True
        except Exception as exc:
            fly = self._flyout()
            if fly is not None:
                fly.add("note", f"打不开：{exc}")
            return False

    def cancel(self, tid=None):
        """停掉任务（不给 tid 就全停）。"""
        for t in self.tasks.values():
            if t.state == "running" and (tid is None or t.tid == tid):
                try:
                    t.proc.kill()
                except Exception:
                    pass
                t.state = "cancelled"
                self._announce(t)

    def _play_thinking(self):
        try:
            from .anim import ANIM_SKIN
            if self.pet.skin != ANIM_SKIN:
                return
            _anim = (getattr(self.pet, "ext", {}) or {}).get("anim")
            if _anim is not None and "thinking" in (_anim.player.clips() or []):
                self.pet._play_anim_clip("thinking")
        except Exception:
            pass

    def _play_done(self, ok):
        try:
            from .anim import ANIM_SKIN
            if self.pet.skin != ANIM_SKIN:
                return
            _anim = (getattr(self.pet, "ext", {}) or {}).get("anim")
            clip = "wave" if ok else "curtsy"
            if _anim is not None and clip in (_anim.player.clips() or []):
                self.pet._play_anim_clip(clip)
        except Exception:
            pass


def setup(pet):
    return DispatchExtension(pet).start()
