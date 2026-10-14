"""API central para licenças do Adri Poltronas.

Execute atrás de HTTPS com PostgreSQL persistente. Clientes só podem consultar
uma conta usando o segredo aleatório daquela conta; comandos administrativos
exigem o token que fica exclusivamente na máquina do desenvolvedor.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import threading
from datetime import datetime, timedelta, timezone

import psycopg
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from psycopg.rows import dict_row

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_TOKEN = os.environ.get("LICENSE_ADMIN_TOKEN", "")
ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
_schema_ready = False
_schema_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(value: datetime | None) -> str:
    return value.isoformat().replace("+00:00", "Z") if value else ""


def _db():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL não configurada")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=15)


def _schema() -> None:
    token = os.environ.get("LICENSE_ADMIN_TOKEN", "")
    if len(token) < 40:
        raise RuntimeError("LICENSE_ADMIN_TOKEN precisa ter ao menos 40 caracteres.")
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                license_id VARCHAR(64) PRIMARY KEY,
                client_secret_hash CHAR(64) NOT NULL,
                username VARCHAR(80) NOT NULL DEFAULT '',
                email VARCHAR(254) NOT NULL DEFAULT '',
                state VARCHAR(16) NOT NULL CHECK (state IN ('trial', 'paid', 'suspended')),
                trial_started_at TIMESTAMPTZ,
                trial_ends_at TIMESTAMPTZ,
                paid_at TIMESTAMPTZ,
                suspended_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)


@app.before_request
def initialize_schema():
    # Cria a tabela por demanda; impede iniciar sem banco e deixa a prontidão
    # do contêiner refletir se a persistência pode ser alcançada.
    global _schema_ready
    if not _schema_ready:
        with _schema_lock:
            if not _schema_ready:
                _schema()
                _schema_ready = True


def _public_record(row: dict) -> dict:
    now = _now()
    return {
        "license_id": row["license_id"],
        "username": row["username"],
        "email": row["email"],
        "estado": row["state"],
        "inicio_em": _iso(row["trial_started_at"]),
        "expira_em": _iso(row["trial_ends_at"]),
        "pago_em": _iso(row["paid_at"]),
        "atualizado_em": _iso(row["updated_at"]),
        "dias_restantes": max((row["trial_ends_at"].date() - now.date()).days, 0)
        if row["state"] == "trial" and row["trial_ends_at"] else None,
    }


@app.get("/health")
def health():
    try:
        with _db() as conn:
            conn.execute("SELECT 1")
        return jsonify({"status": "ok", "service": "adri-licensing"}), 200
    except Exception as err:
        app.logger.warning("Falha na sonda de saúde do banco: %s", err)
        return jsonify({"status": "degraded", "erro": "Banco de dados indisponível."}), 503


@app.post("/v1/licenses/sync")
def sync_license():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"erro": "JSON inválido."}), 400
    license_id = data.get("license_id")
    client_secret = data.get("client_secret")
    username = data.get("username")
    email = data.get("email") or ""
    if not isinstance(license_id, str) or not ID_RE.fullmatch(license_id):
        return jsonify({"erro": "Identificador inválido."}), 400
    if not isinstance(client_secret, str) or not 40 <= len(client_secret) <= 128:
        return jsonify({"erro": "Credencial inválida."}), 400
    if not isinstance(username, str) or not username.strip() or len(username) > 80:
        return jsonify({"erro": "Nome inválido."}), 400
    if not isinstance(email, str) or len(email) > 254:
        return jsonify({"erro": "E-mail inválido."}), 400

    secret_hash = hashlib.sha256(client_secret.encode("utf-8")).hexdigest()
    now = _now()
    with _db() as conn:
        row = conn.execute("SELECT * FROM licenses WHERE license_id = %s", (license_id,)).fetchone()
        if row:
            if not hmac.compare_digest(row["client_secret_hash"].strip(), secret_hash):
                return jsonify({"erro": "Credencial inválida."}), 403
            row = conn.execute(
                "UPDATE licenses SET username=%s, email=%s, updated_at=%s "
                "WHERE license_id=%s RETURNING *",
                (username.strip(), email.strip(), now, license_id),
            ).fetchone()
        else:
            row = conn.execute(
                "INSERT INTO licenses (license_id, client_secret_hash, username, email, "
                "state, trial_started_at, trial_ends_at, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,'trial',%s,%s,%s,%s) "
                "ON CONFLICT (license_id) DO NOTHING RETURNING *",
                (license_id, secret_hash, username.strip(), email.strip(), now,
                 now + timedelta(days=30), now, now),
            ).fetchone()
            if not row:
                row = conn.execute(
                    "SELECT * FROM licenses WHERE license_id=%s", (license_id,)
                ).fetchone()
                if not row or not hmac.compare_digest(row["client_secret_hash"].strip(), secret_hash):
                    return jsonify({"erro": "Credencial inválida."}), 403
                row = conn.execute(
                    "UPDATE licenses SET username=%s, email=%s, updated_at=%s "
                    "WHERE license_id=%s RETURNING *",
                    (username.strip(), email.strip(), now, license_id),
                ).fetchone()
    record = _public_record(row)
    if row["state"] == "trial" and row["trial_ends_at"] <= now:
        record["estado"] = "expired"
    return jsonify(record), 200


def _admin_autorizado() -> bool:
    token = os.environ.get("LICENSE_ADMIN_TOKEN", "")
    header = request.headers.get("Authorization", "")
    apresentado = header[7:] if header.startswith("Bearer ") else ""
    return bool(token and len(token) >= 40
                and hmac.compare_digest(apresentado, token))


@app.before_request
def admin_guard():
    if request.path.startswith("/v1/admin/") and not _admin_autorizado():
        return jsonify({"erro": "Acesso negado."}), 401


@app.get("/v1/admin/licenses")
def list_licenses():
    with _db() as conn:
        rows = conn.execute("SELECT * FROM licenses ORDER BY updated_at DESC").fetchall()
    result = []
    now = _now()
    for row in rows:
        item = _public_record(row)
        if row["state"] == "trial" and row["trial_ends_at"] <= now:
            item["estado"] = "expired"
        result.append(item)
    return jsonify({"contas": result}), 200


@app.post("/v1/admin/licenses/<license_id>")
def update_license(license_id: str):
    if not ID_RE.fullmatch(license_id):
        return jsonify({"erro": "Identificador inválido."}), 400
    data = request.get_json(silent=True)
    action = data.get("acao") if isinstance(data, dict) else None
    now = _now()
    with _db() as conn:
        row = conn.execute("SELECT * FROM licenses WHERE license_id=%s FOR UPDATE", (license_id,)).fetchone()
        if not row:
            return jsonify({"erro": "Conta ainda não sincronizada pelo computador do cliente."}), 404
        if action == "paid":
            row = conn.execute(
                "UPDATE licenses SET state='paid', paid_at=%s, suspended_at=NULL, updated_at=%s "
                "WHERE license_id=%s RETURNING *", (now, now, license_id),
            ).fetchone()
        elif action == "trial_30_days":
            row = conn.execute(
                "UPDATE licenses SET state='trial', trial_started_at=%s, trial_ends_at=%s, "
                "paid_at=NULL, suspended_at=NULL, updated_at=%s WHERE license_id=%s RETURNING *",
                (now, now + timedelta(days=30), now, license_id),
            ).fetchone()
        elif action == "suspend":
            row = conn.execute(
                "UPDATE licenses SET state='suspended', suspended_at=%s, updated_at=%s "
                "WHERE license_id=%s RETURNING *", (now, now, license_id),
            ).fetchone()
        else:
            return jsonify({"erro": "Ação inválida."}), 400
    return jsonify(_public_record(row)), 200


@app.errorhandler(Exception)
def handle_error(error):
    if isinstance(error, HTTPException):
        return error
    app.logger.error("Erro interno da API de licenças: %s", type(error).__name__)
    return jsonify({"erro": "Serviço de licenças temporariamente indisponível."}), 503


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080)
