"""Orquestração da execução do monitor."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .checker import CheckResult, check_url
from .config import MonitorConfig
from .notifications import NotificationResult, Notifier
from .storage import HistoryStore


@dataclass
class RunReport:
    results: list[CheckResult]
    notifications: list[NotificationResult]

    @property
    def available(self) -> bool:
        return all(result.available for result in self.results)

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "total": len(self.results),
            "up": sum(result.available for result in self.results),
            "down": sum(not result.available for result in self.results),
            "results": [result.as_dict() for result in self.results],
            "notifications": [asdict(item) for item in self.notifications],
        }


def run_monitor(config: MonitorConfig, *, notifier: Notifier | None = None) -> RunReport:
    """Executa todas as URLs e registra o resultado final de cada uma."""
    config.validate(require_urls=True)
    notifier = notifier or Notifier(config.email, config.telegram)
    notifications: list[NotificationResult] = []
    results: list[CheckResult] = []
    with HistoryStore(config.database) as store:
        for target in config.urls:
            result = check_url(
                target,
                timeout=config.timeout,
                retries=config.retries,
                simulate=config.simulate,
            )
            store.record(result)
            results.append(result)
            # Simulação é deliberadamente sem efeitos colaterais: não dispara alertas.
            if not config.simulate:
                notifications.extend(notifier.notify(result))
    return RunReport(results=results, notifications=notifications)
