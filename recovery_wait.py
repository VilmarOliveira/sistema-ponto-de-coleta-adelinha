"""Explain the existing resend limits without changing their enforcement."""
import math
from datetime import datetime, timedelta
from markupsafe import Markup


def recovery_wait_message(recent, current):
    latest = datetime.fromisoformat(recent['latest'])
    deadline = latest + timedelta(seconds=60)
    if recent['total'] >= 3:
        deadline = max(deadline, datetime.fromisoformat(recent['earliest']) + timedelta(minutes=15))
    seconds = max(1, math.ceil((deadline-current).total_seconds()))
    reason = ('Você atingiu o limite de solicitações de código.' if recent['total'] >= 3
              else 'Você solicitou um código há pouco.')
    return Markup('{} Aguarde <span data-recovery-wait="{}">{} segundos</span> para solicitar outro.').format(reason, seconds, seconds)
