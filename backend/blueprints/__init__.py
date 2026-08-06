# backend/blueprints/__init__.py
"""Pacote de blueprints Flask."""
from .auth import auth_bp
from .clientes import clientes_bp
from .pagamentos import pagamentos_bp
from .webhook import webhook_bp
from .relatorios import relatorios_bp
from .ia import ia_bp
from .entregas import entregas_bp
from .dashboard import dashboard_bp
from .notificacoes import notificacoes_bp
from .excel import excel_bp

__all__ = [
    'auth_bp',
    'clientes_bp',
    'pagamentos_bp',
    'webhook_bp',
    'relatorios_bp',
    'ia_bp',
    'entregas_bp',
    'dashboard_bp',
    'notificacoes_bp',
    'excel_bp',
]