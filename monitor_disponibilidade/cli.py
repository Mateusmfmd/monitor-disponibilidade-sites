"""Interface de linha de comando do monitor."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from typing import Sequence

from .config import ConfigError, load_config
from .monitor import run_monitor
from .storage import HistoryStore


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", help="arquivo JSON de configuração")
    parser.add_argument("--database", "--db", dest="database", help="arquivo SQLite")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="monitor-disponibilidade",
        description="Verifica URLs, grava histórico SQLite e alerta apenas se configurado.",
    )
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check", help="executa uma verificação")
    _add_common(check)
    check.add_argument("--url", action="append", help="URL; pode ser repetida")
    check.add_argument("--timeout", type=float, help="timeout em segundos")
    check.add_argument("--retries", type=int, help="tentativas adicionais")
    check.add_argument("--simulate", action="store_true", help="não acessa a rede; simula HTTP 200")
    check.add_argument("--no-alerts", action="store_true", help="desabilita alertas nesta execução")
    check.add_argument("--json", action="store_true", dest="as_json", help="imprime o relatório como JSON")

    history = subparsers.add_parser("history", help="mostra verificações já registradas")
    _add_common(history)
    history.add_argument("--url", help="filtra uma URL")
    history.add_argument("--limit", type=int, default=20, help="quantidade máxima de registros")
    history.add_argument("--json", action="store_true", dest="as_json", help="imprime como JSON")
    return parser


def _config_for_check(args: argparse.Namespace):
    overrides = {
        "urls": args.url,
        "timeout": args.timeout,
        "retries": args.retries,
        "database": args.database,
        "simulate": True if args.simulate else None,
    }
    return load_config(args.config, overrides=overrides)


def _run_check(args: argparse.Namespace) -> int:
    config = _config_for_check(args)
    if args.no_alerts:
        config.email = None
        config.telegram = None
    report = run_monitor(config)
    if args.as_json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        for result in report.results:
            state = "UP" if result.available else "DOWN"
            status = result.status_code if result.status_code is not None else "-"
            elapsed = f"{result.response_time_ms:.2f} ms" if result.response_time_ms is not None else "-"
            detail = f"; erro={result.error}" if result.error else ""
            print(f"{state} {result.url} (HTTP {status}, {elapsed}, tentativas={result.attempts}{detail})")
        sent = sum(item.sent for item in report.notifications)
        print(f"Resumo: {report.as_dict()['up']} UP, {report.as_dict()['down']} DOWN; alertas enviados={sent}")
    return 0 if report.available else 1


def _run_history(args: argparse.Namespace) -> int:
    config = load_config(args.config, overrides={"database": args.database})
    with HistoryStore(config.database) as store:
        records = store.history(url=args.url, limit=args.limit)
    if args.as_json:
        print(json.dumps(records, ensure_ascii=False, indent=2))
    else:
        if not records:
            print("Nenhum registro encontrado.")
        for item in records:
            state = "UP" if item["available"] else "DOWN"
            print(
                f"#{item['id']} {state} {item['url']} em {item['checked_at']} "
                f"(HTTP {item['status_code'] or '-'}, tentativas={item['attempts']})"
            )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    # Permite a forma curta `monitor-disponibilidade --url ...`.
    if args_list and args_list[0] not in {"check", "history", "-h", "--help"}:
        args_list.insert(0, "check")
    parser = build_parser()
    args = parser.parse_args(args_list)
    if args.command is None:
        parser.print_help()
        return 0
    try:
        return _run_check(args) if args.command == "check" else _run_history(args)
    except (ConfigError, OSError, sqlite3.Error) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
