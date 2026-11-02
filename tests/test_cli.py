from __future__ import annotations

import signal

import uvicorn

from bili_live_danmaku.cli import GracefulServer


def test_graceful_server_first_and_second_interrupt(capsys, monkeypatch) -> None:
    server = GracefulServer(uvicorn.Config(lambda scope, receive, send: None))
    exit_codes: list[int] = []
    monkeypatch.setattr("bili_live_danmaku.cli.os._exit", exit_codes.append)

    server.handle_exit(signal.SIGINT, None)
    assert server.should_exit is True
    assert server.force_exit is False
    assert "🛑 收到退出信号，正在优雅关闭…" in capsys.readouterr().out

    server.handle_exit(signal.SIGINT, None)
    assert server.force_exit is True
    assert exit_codes == [130]
    output = capsys.readouterr().out
    assert "⚡ 再次收到退出信号，立即退出" in output
    assert "👋 Bili Live Danmaku 已退出" in output
