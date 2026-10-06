"""Verificação de URLs sem dependências externas."""

from __future__ import annotations

import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from .config import URLTarget


@dataclass(frozen=True)
class CheckResult:
    """Resultado de uma URL depois de todas as tentativas."""

    url: str
    name: str | None
    checked_at: str
    available: bool
    status_code: int | None
    response_time_ms: float | None
    attempts: int
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_url(target: URLTarget, *, timeout: float, retries: int, simulate: bool = False) -> CheckResult:
    """Verifica uma URL. ``retries`` é o número de tentativas adicionais."""

    if simulate:
        return CheckResult(
            url=target.url,
            name=target.name,
            checked_at=_now(),
            available=True,
            status_code=200,
            response_time_ms=0.0,
            attempts=1,
            error=None,
        )

    last_code: int | None = None
    last_error: str | None = None
    last_elapsed: float | None = None
    total_attempts = retries + 1
    request = urllib.request.Request(
        target.url,
        headers={"User-Agent": "monitor-disponibilidade-sites/1.0"},
        method="GET",
    )
    for attempt in range(1, total_attempts + 1):
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                last_elapsed = (time.monotonic() - started) * 1000
                last_code = response.getcode()
            if last_code is not None and 200 <= last_code < 400:
                return CheckResult(
                    url=target.url,
                    name=target.name,
                    checked_at=_now(),
                    available=True,
                    status_code=last_code,
                    response_time_ms=round(last_elapsed or 0.0, 2),
                    attempts=attempt,
                )
            last_error = f"HTTP {last_code}" if last_code is not None else "Resposta sem status"
        except urllib.error.HTTPError as exc:
            last_elapsed = (time.monotonic() - started) * 1000
            last_code = exc.code
            last_error = f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_elapsed = (time.monotonic() - started) * 1000
            reason = getattr(exc, "reason", exc)
            last_error = f"{type(reason).__name__}: {reason}"
        if attempt < total_attempts:
            continue

    return CheckResult(
        url=target.url,
        name=target.name,
        checked_at=_now(),
        available=False,
        status_code=last_code,
        response_time_ms=round(last_elapsed, 2) if last_elapsed is not None else None,
        attempts=total_attempts,
        error=last_error or "Falha desconhecida",
    )
