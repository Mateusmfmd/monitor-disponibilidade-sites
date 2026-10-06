"""Canais opcionais de alerta; por padrão nenhum acesso externo é feito."""

from __future__ import annotations

import json
import smtplib
import ssl
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import EmailMessage

from .checker import CheckResult
from .config import EmailConfig, TelegramConfig


@dataclass
class NotificationResult:
    channel: str
    sent: bool
    error: str | None = None


class Notifier:
    """Envia alertas somente para canais presentes na configuração."""

    def __init__(self, email: EmailConfig | None = None, telegram: TelegramConfig | None = None):
        self.email = email
        self.telegram = telegram

    @property
    def configured(self) -> bool:
        return self.email is not None or self.telegram is not None

    @staticmethod
    def message_for(result: CheckResult) -> str:
        label = result.name or result.url
        return (
            f"Alerta de indisponibilidade: {label}\n"
            f"URL: {result.url}\n"
            f"Verificado em: {result.checked_at}\n"
            f"Tentativas: {result.attempts}\n"
            f"Status HTTP: {result.status_code or 'sem resposta'}\n"
            f"Erro: {result.error or 'falha desconhecida'}"
        )

    def notify(self, result: CheckResult) -> list[NotificationResult]:
        """Tenta cada canal configurado e devolve o resultado individual."""
        if result.available:
            return []
        message = self.message_for(result)
        outcomes: list[NotificationResult] = []
        if self.email is not None:
            try:
                self._send_email(message)
                outcomes.append(NotificationResult("email", True))
            except Exception as exc:  # alerta não deve esconder o resultado do monitor
                outcomes.append(NotificationResult("email", False, f"{type(exc).__name__}: {exc}"))
        if self.telegram is not None:
            try:
                self._send_telegram(message)
                outcomes.append(NotificationResult("telegram", True))
            except Exception as exc:  # alerta não deve esconder o resultado do monitor
                outcomes.append(NotificationResult("telegram", False, f"{type(exc).__name__}: {exc}"))
        return outcomes

    def _send_email(self, body: str) -> None:
        if self.email is None:
            return
        message = EmailMessage()
        message["Subject"] = "Alerta de indisponibilidade"
        message["From"] = self.email.sender
        message["To"] = ", ".join(self.email.recipients)
        message.set_content(body)
        context = ssl.create_default_context()
        with smtplib.SMTP(self.email.host, self.email.port, timeout=10) as smtp:
            if self.email.starttls:
                smtp.starttls(context=context)
            if self.email.username:
                smtp.login(self.email.username, self.email.password or "")
            smtp.send_message(message)

    def _send_telegram(self, body: str) -> None:
        if self.telegram is None:
            return
        endpoint = f"https://api.telegram.org/bot{self.telegram.bot_token}/sendMessage"
        payload = urllib.parse.urlencode(
            {"chat_id": self.telegram.chat_id, "text": body}
        ).encode("utf-8")
        request = urllib.request.Request(endpoint, data=payload, method="POST")
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Telegram HTTP {response.status}")
