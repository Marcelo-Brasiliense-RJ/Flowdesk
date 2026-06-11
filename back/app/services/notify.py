"""Notificações por e-mail (best-effort, opcional).

Usado para avisar quando um job agendado falha. Sem SMTP_HOST configurado no
.env, vira no-op silencioso. O envio roda numa thread para nunca atrasar nem
derrubar o runtime.
"""
from __future__ import annotations

import smtplib
import threading
from email.message import EmailMessage

from ..config import settings


def _recipients() -> list[str]:
    return [e.strip() for e in settings.notify_emails.split(",") if e.strip()]


def notify_job_failure(project_name: str, stage_name: str, execution_id: str, stderr: str) -> None:
    """Dispara e-mail de falha de job agendado, se SMTP estiver configurado."""
    if not settings.smtp_host or not _recipients():
        return

    def _send() -> None:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[FlowDesk] Falha no job agendado: {project_name} / {stage_name}"
            msg["From"] = settings.smtp_from
            msg["To"] = ", ".join(_recipients())
            msg.set_content(
                "Uma execução agendada falhou.\n\n"
                f"Automação: {project_name}\n"
                f"Etapa: {stage_name}\n"
                f"Execução: {execution_id}\n\n"
                f"Erro (final):\n{(stderr or '')[-1500:]}\n\n"
                "Veja os detalhes em Logs / Monitor no FlowDesk."
            )
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as s:
                s.starttls()
                if settings.smtp_user:
                    s.login(settings.smtp_user, settings.smtp_password)
                s.send_message(msg)
        except Exception:
            # nunca derrubar o runtime por falha de notificação
            pass

    threading.Thread(target=_send, daemon=True).start()
