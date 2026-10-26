# -*- coding: utf-8 -*-
"""等旧桌宠进程退出后重新启动它（给「重启桌宠」按钮用）。

为什么必须单独一个进程来干这件事：
1. 桌宠自己 `quit()` 之后事件循环就没了，`QTimer.singleShot` 根本不会触发；
2. 立刻启动新进程会被**单实例锁**拦住（`QLocalServer` 那个名字还没释放）。

所以菜单里点「重启」时，这里先起这个助手，助手 `WaitForSingleObject` 等旧进程
真的退了、再等 0.6 秒让管道名释放，然后才启动新的。
"""
import ctypes
import os
import subprocess
import sys
import tempfile
import time

SYNCHRONIZE = 0x00100000
CREATE_NEW_PROCESS_GROUP = 0x00000200


def log(msg):
    """写一行到 %TEMP%\\dafeiyu-relaunch.log（重启出问题时唯一的线索）。"""
    try:
        path = os.path.join(tempfile.gettempdir(), "dafeiyu-relaunch.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{time.strftime('%H:%M:%S')}] {msg}\n")
    except OSError:
        pass


def wait_gone(pid, timeout_ms=20000):
    """等那个进程退出（拿不到句柄就当它已经没了）。"""
    try:
        k32 = ctypes.windll.kernel32
    except AttributeError:          # 非 Windows：直接按时间等
        time.sleep(1.0)
        return
    handle = k32.OpenProcess(SYNCHRONIZE, False, int(pid))
    if not handle:
        log(f"OpenProcess({pid}) 失败 —— 当成已经退出了")
        time.sleep(0.5)
        return
    try:
        k32.WaitForSingleObject(handle, int(timeout_ms))
        log(f"旧进程 {pid} 已退出")
    finally:
        k32.CloseHandle(handle)


def main():
    if len(sys.argv) < 4:
        log(f"参数不够：{sys.argv}")
        print("用法: _relaunch.py <pid> <目标脚本> <工作目录> [python]")
        return 2
    pid = sys.argv[1]
    target = sys.argv[2]
    cwd = sys.argv[3]
    py = sys.argv[4] if len(sys.argv) > 4 else sys.executable

    log(f"接到重启请求：pid={pid} target={target} py={py}")
    wait_gone(pid)
    time.sleep(1.2)                 # 单实例的管道名 + 配置落盘，都要一点时间
    child_log = os.path.join(tempfile.gettempdir(), "dafeiyu-relaunch-child.log")
    # ⚠️ 只等固定时间不够：旧进程退出后 Qt 还要清理一阵，这几秒里新进程会被
    # **单实例锁**拦住然后静默退出（return 0、没有任何输出，实测踩过）。
    # 所以起完看它 4 秒内有没有退出，退出了就等一会儿再试。
    for attempt in range(1, 5):
        try:
            fh = open(child_log, "ab")
        except OSError:
            fh = subprocess.DEVNULL
        try:
            p = subprocess.Popen([py, "-u", target], cwd=cwd,
                                 creationflags=CREATE_NEW_PROCESS_GROUP,
                                 stdout=fh, stderr=subprocess.STDOUT)
        except Exception as exc:
            log(f"第 {attempt} 次启动失败：{type(exc).__name__}: {exc}")
            time.sleep(1.5)
            continue
        finally:
            try:
                if fh not in (None, subprocess.DEVNULL):
                    fh.close()
            except OSError:
                pass
        try:
            code = p.wait(timeout=4.0)
        except subprocess.TimeoutExpired:
            log(f"第 {attempt} 次启动成功（pid={p.pid} 活着）")
            return 0
        log(f"第 {attempt} 次启动后 {code} 就退出了（多半被单实例拦），1.6 秒后再试")
        time.sleep(1.6)
    log("重试 4 次都没起来 —— 手动双击 启动开发版.bat 吧")
    return 1


if __name__ == "__main__":
    sys.exit(main())
