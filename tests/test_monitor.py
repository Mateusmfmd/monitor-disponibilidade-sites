from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from monitor_disponibilidade.checker import check_url
from monitor_disponibilidade.cli import main
from monitor_disponibilidade.config import MonitorConfig, URLTarget, load_config
from monitor_disponibilidade.monitor import run_monitor
from monitor_disponibilidade.notifications import Notifier
from monitor_disponibilidade.storage import HistoryStore


class LocalHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - nome exigido pela biblioteca padrão
        if self.path == "/ok":
            body = b"ok"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/down":
            self.send_response(503)
            self.end_headers()
        elif self.path == "/slow":
            time.sleep(0.15)
            self.send_response(200)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # noqa: A002 - assinatura do servidor
        return


@pytest.fixture
def local_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def test_http_check_and_sqlite_history(local_server, tmp_path: Path):
    target = URLTarget(f"{local_server}/ok", "local ok")
    result = check_url(target, timeout=1, retries=0)
    assert result.available is True
    assert result.status_code == 200
    assert result.attempts == 1

    db = tmp_path / "history.db"
    with HistoryStore(db) as store:
        row_id = store.record(result)
        records = store.history(limit=5)
    assert row_id == 1
    assert records[0]["url"] == target.url
    assert records[0]["available"] is True


def test_retries_on_http_failure(local_server):
    result = check_url(URLTarget(f"{local_server}/down"), timeout=1, retries=2)
    assert result.available is False
    assert result.status_code == 503
    assert result.attempts == 3
    assert result.error == "HTTP 503"


def test_timeout_is_applied(local_server):
    result = check_url(URLTarget(f"{local_server}/slow"), timeout=0.01, retries=0)
    assert result.available is False
    assert result.attempts == 1
    assert result.error is not None


def test_simulation_never_opens_network(tmp_path: Path):
    # O endereço é deliberadamente inválido; simulação deve retornar sem tentar acessá-lo.
    config = MonitorConfig(
        urls=[URLTarget("http://nao-deve-ser-acessado.invalid")],
        database=tmp_path / "simulation.db",
        simulate=True,
    )
    report = run_monitor(config, notifier=Notifier())
    assert report.available is True
    assert report.results[0].status_code == 200
    assert report.notifications == []


def test_cli_json_and_history(local_server, tmp_path: Path, capsys):
    db = tmp_path / "cli.db"
    code = main(["check", "--url", f"{local_server}/ok", "--database", str(db), "--json"])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["up"] == 1
    assert output["results"][0]["available"] is True

    code = main(["history", "--database", str(db), "--json"])
    history = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len(history) == 1
    assert history[0]["url"].endswith("/ok")


def test_json_and_environment_precedence(tmp_path: Path, monkeypatch):
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps({"urls": ["http://json.invalid"], "timeout": 9, "retries": 1, "database": "json.db"}),
        encoding="utf-8",
    )
    monkeypatch.setenv("MONITOR_TIMEOUT", "2.5")
    monkeypatch.setenv("MONITOR_RETRIES", "4")
    config = load_config(config_file, overrides={"urls": ["http://cli.invalid"]})
    assert [item.url for item in config.urls] == ["http://cli.invalid"]
    assert config.timeout == 2.5
    assert config.retries == 4
    assert config.database == Path("json.db")


def test_no_notification_channel_is_configured_by_default():
    notifier = Notifier()
    assert notifier.configured is False
    assert notifier.notify(
        type("Down", (), {"available": False, "url": "http://local", "name": None,
                           "checked_at": "now", "attempts": 1, "status_code": 503,
                           "error": "HTTP 503"})()
    ) == []
