"""Modelos e carregamento de configuração do monitor."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


class ConfigError(ValueError):
    """Erro de configuração informado ao usuário."""


@dataclass(frozen=True)
class URLTarget:
    """URL que será monitorada, com nome opcional para relatórios."""

    url: str
    name: str | None = None

    @classmethod
    def from_value(cls, value: Any) -> "URLTarget":
        if isinstance(value, str):
            url = value.strip()
            name = None
        elif isinstance(value, dict):
            url = str(value.get("url", "")).strip()
            name_value = value.get("name")
            name = str(name_value).strip() if name_value else None
        else:
            raise ConfigError("Cada URL deve ser uma string ou um objeto com a chave 'url'.")
        if not url:
            raise ConfigError("Uma URL vazia foi informada.")
        return cls(url=url, name=name)


@dataclass(frozen=True)
class EmailConfig:
    """Configuração mínima para envio via SMTP."""

    host: str
    port: int
    sender: str
    recipients: tuple[str, ...]
    username: str | None = None
    password: str | None = None
    starttls: bool = True


@dataclass(frozen=True)
class TelegramConfig:
    """Configuração do Bot API do Telegram."""

    bot_token: str
    chat_id: str


@dataclass
class MonitorConfig:
    """Configuração consolidada do monitor."""

    urls: list[URLTarget]
    timeout: float = 10.0
    retries: int = 2
    database: Path = Path("monitor.db")
    simulate: bool = False
    email: EmailConfig | None = None
    telegram: TelegramConfig | None = None

    def validate(self, *, require_urls: bool = True) -> None:
        if require_urls and not self.urls:
            raise ConfigError("Nenhuma URL configurada. Use --url ou a chave 'urls'.")
        if self.timeout <= 0:
            raise ConfigError("O timeout deve ser maior que zero.")
        if self.retries < 0:
            raise ConfigError("O número de retries não pode ser negativo.")
        for target in self.urls:
            if not target.url.startswith(("http://", "https://")):
                raise ConfigError(f"URL sem esquema http/https: {target.url}")


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "sim", "on"}:
        return True
    if text in {"0", "false", "no", "não", "nao", "off"}:
        return False
    raise ConfigError(f"Valor booleano inválido: {value}")


def _as_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field} deve ser um número inteiro.") from exc


def _as_float(value: Any, field: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{field} deve ser um número.") from exc


def _list_from(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return list(value)
    raise ConfigError("A lista de URLs/destinatários deve ser uma lista ou texto separado por vírgulas.")


def _env_first(*names: str) -> str | None:
    for name in names:
        value = os.getenv(name)
        if value is not None and value != "":
            return value
    return None


def _notification_config(raw: dict[str, Any]) -> tuple[EmailConfig | None, TelegramConfig | None]:
    notifications = raw.get("notifications") or {}
    if not isinstance(notifications, dict):
        raise ConfigError("'notifications' deve ser um objeto JSON.")

    email_raw = notifications.get("email", raw.get("email"))
    if email_raw is not None and not isinstance(email_raw, dict):
        raise ConfigError("'notifications.email' deve ser um objeto JSON.")
    telegram_raw = notifications.get("telegram", raw.get("telegram"))
    if telegram_raw is not None and not isinstance(telegram_raw, dict):
        raise ConfigError("'notifications.telegram' deve ser um objeto JSON.")

    email_enabled = _as_bool(
        _env_first("MONITOR_EMAIL_ENABLED")
        if _env_first("MONITOR_EMAIL_ENABLED") is not None
        else (email_raw or {}).get("enabled"),
        default=email_raw is not None,
    )
    email_host = _env_first("MONITOR_EMAIL_HOST") or (email_raw or {}).get("host")
    email_sender = _env_first("MONITOR_EMAIL_FROM", "MONITOR_EMAIL_SENDER") or (email_raw or {}).get("sender", (email_raw or {}).get("from"))
    email_recipients = _env_first("MONITOR_EMAIL_TO", "MONITOR_EMAIL_RECIPIENTS") or (email_raw or {}).get("recipients", (email_raw or {}).get("to"))
    email = None
    if email_enabled and email_host and email_sender and email_recipients:
        email = EmailConfig(
            host=str(email_host),
            port=_as_int(_env_first("MONITOR_EMAIL_PORT") or (email_raw or {}).get("port", 587), "email.port"),
            sender=str(email_sender),
            recipients=tuple(str(item).strip() for item in _list_from(email_recipients) if str(item).strip()),
            username=_env_first("MONITOR_EMAIL_USERNAME") or (email_raw or {}).get("username"),
            password=_env_first("MONITOR_EMAIL_PASSWORD") or (email_raw or {}).get("password"),
            starttls=_as_bool(
                _env_first("MONITOR_EMAIL_STARTTLS")
                if _env_first("MONITOR_EMAIL_STARTTLS") is not None
                else (email_raw or {}).get("starttls"),
                default=True,
            ),
        )
        if not email.recipients:
            email = None

    token = _env_first("MONITOR_TELEGRAM_BOT_TOKEN") or (telegram_raw or {}).get("bot_token", (telegram_raw or {}).get("token"))
    chat_id = _env_first("MONITOR_TELEGRAM_CHAT_ID") or (telegram_raw or {}).get("chat_id")
    telegram_enabled = _as_bool(
        _env_first("MONITOR_TELEGRAM_ENABLED")
        if _env_first("MONITOR_TELEGRAM_ENABLED") is not None
        else (telegram_raw or {}).get("enabled"),
        default=telegram_raw is not None,
    )
    telegram = TelegramConfig(str(token), str(chat_id)) if telegram_enabled and token and chat_id else None
    return email, telegram


def load_config(config_path: str | Path | None = None, *, overrides: dict[str, Any] | None = None) -> MonitorConfig:
    """Carrega JSON, aplica ambiente e por fim valores explícitos de CLI.

    Variáveis de ambiente são opcionais e têm precedência sobre o JSON;
    ``overrides`` representa os argumentos da linha de comando e tem a maior
    precedência. Segredos nunca têm valores padrão.
    """

    selected_path = config_path or os.getenv("MONITOR_CONFIG")
    raw: dict[str, Any] = {}
    if selected_path:
        path = Path(selected_path)
        try:
            with path.open("r", encoding="utf-8") as stream:
                loaded = json.load(stream)
        except FileNotFoundError as exc:
            raise ConfigError(f"Arquivo de configuração não encontrado: {path}") from exc
        except json.JSONDecodeError as exc:
            raise ConfigError(f"JSON inválido em {path}: {exc}") from exc
        if not isinstance(loaded, dict):
            raise ConfigError("A configuração JSON deve ser um objeto.")
        raw.update(loaded)

    env_urls = _env_first("MONITOR_URLS", "MONITOR_URL")
    values = dict(raw)
    if env_urls is not None:
        values["urls"] = _list_from(env_urls)
    if _env_first("MONITOR_TIMEOUT") is not None:
        values["timeout"] = _env_first("MONITOR_TIMEOUT")
    if _env_first("MONITOR_RETRIES") is not None:
        values["retries"] = _env_first("MONITOR_RETRIES")
    if _env_first("MONITOR_DATABASE", "MONITOR_DB") is not None:
        values["database"] = _env_first("MONITOR_DATABASE", "MONITOR_DB")
    if _env_first("MONITOR_SIMULATE") is not None:
        values["simulate"] = _env_first("MONITOR_SIMULATE")

    for key, value in (overrides or {}).items():
        if value is not None:
            values[key] = value

    url_values = _list_from(values.get("urls"))
    urls = [URLTarget.from_value(value) for value in url_values]
    email, telegram = _notification_config(values)
    config = MonitorConfig(
        urls=urls,
        timeout=_as_float(values.get("timeout", 10.0), "timeout"),
        retries=_as_int(values.get("retries", 2), "retries"),
        database=Path(values.get("database", "monitor.db")),
        simulate=_as_bool(values.get("simulate", False)),
        email=email,
        telegram=telegram,
    )
    return config
