"""API central para licenças do Adri Poltronas.

Execute atrás de HTTPS com PostgreSQL persistente. Clientes só podem consultar
uma conta usando o segredo aleatório daquela conta; comandos administrativos
exigem o token que fica exclusivamente na máquina do desenvolvedor.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import threading
from datetime import datetime, timedelta, timezone

import psycopg
from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix
from psycopg.rows import dict_row

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024
# Render termina TLS em um proxy e informa o endereço do cliente em
# X-Forwarded-For. Só confiamos em um salto e apenas no ambiente Render.
if os.environ.get("RENDER_EXTERNAL_URL"):
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
DATABASE_URL = os.environ.get("DATABASE_URL", "")
ADMIN_TOKEN = os.environ.get("LICENSE_ADMIN_TOKEN", "")
ID_RE = re.compile(r"^[A-Za-z0-9-]{1,64}$")
INSTALLATION_ID_RE = re.compile(r"^[0-9a-f]{64}$")
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
    # Chave malformada tem de impedir o servico de subir, e nao aparecer na
    # primeira sincronizacao de um cliente.
    _carregar_chave_de_assinatura()
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                license_id VARCHAR(64) PRIMARY KEY,
                client_secret_hash CHAR(64) NOT NULL,
                installation_id VARCHAR(64),
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
        # Migração idempotente para as contas já existentes no Neon.
        conn.execute(
            "ALTER TABLE licenses ADD COLUMN IF NOT EXISTS installation_id VARCHAR(64)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS license_installations (
                installation_id VARCHAR(64) PRIMARY KEY,
                trial_license_id VARCHAR(64),
                trial_ip_hash CHAR(64),
                trial_started_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
        """)
        conn.execute(
            "ALTER TABLE license_installations ADD COLUMN IF NOT EXISTS trial_ip_hash CHAR(64)"
        )
        conn.execute(
            "ALTER TABLE license_installations ADD COLUMN IF NOT EXISTS trial_started_at TIMESTAMPTZ"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS ix_licenses_installation_id "
            "ON licenses (installation_id)"
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS license_sync_rate_limits (
                ip_hash CHAR(64) NOT NULL,
                window_start TIMESTAMPTZ NOT NULL,
                request_count INTEGER NOT NULL,
                PRIMARY KEY (ip_hash, window_start)
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


# -----------------------------------------------------------------------------
# Assinatura da resposta
#
# O aplicativo roda inteiro na maquina do cliente, e a URL deste servico e
# configuravel la. Sem assinatura, qualquer servidor que responda `"paid"` --
# ou uma edicao no cache local -- libera o uso. Com ela, so quem tem a chave
# PRIVADA produz uma resposta que o aplicativo aceita, e a chave privada so
# existe aqui.
#
# `LICENSE_SIGNING_KEY` e a semente Ed25519 (32 bytes) em base64, gerada por
# `gerar_chave_de_assinatura.py`. Ausente, o servico responde sem `prova`,
# como antes: e o que permite publicar esta versao ANTES de os aplicativos
# passarem a exigir a assinatura. Presente e malformada, o servico se recusa a
# subir -- assinar com uma chave que ninguem consegue conferir trancaria todos
# os clientes sem aviso.
# -----------------------------------------------------------------------------
PREFIXO_DA_ASSINATURA = b"adri-licenca-v1."
VERSAO_DA_PROVA = 1
_chave_de_assinatura = None
_chave_de_assinatura_lida = False


def _b64url(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode("ascii")


def _carregar_chave_de_assinatura():
    """A chave privada, ou None quando o servico ainda nao assina."""
    global _chave_de_assinatura, _chave_de_assinatura_lida
    if _chave_de_assinatura_lida:
        return _chave_de_assinatura

    bruta = (os.environ.get("LICENSE_SIGNING_KEY") or "").strip()
    if not bruta:
        app.logger.warning(
            "LICENSE_SIGNING_KEY ausente: respostas de licenca saem SEM assinatura.")
        _chave_de_assinatura, _chave_de_assinatura_lida = None, True
        return None

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    try:
        semente = base64.b64decode(bruta, validate=True)
        if len(semente) != 32:
            raise ValueError("tamanho")
        chave = Ed25519PrivateKey.from_private_bytes(semente)
    except Exception as erro:
        raise RuntimeError(
            "LICENSE_SIGNING_KEY precisa ser uma semente Ed25519 de 32 bytes em "
            "base64 (gere com gerar_chave_de_assinatura.py)."
        ) from erro
    _chave_de_assinatura, _chave_de_assinatura_lida = chave, True
    return chave


def _assinar_registro(record: dict, installation_id: str) -> str:
    """
    Prova de que ESTE servico afirmou este estado, para esta conta, nesta
    instalacao, neste instante. Vazio quando nao ha chave configurada.

    Formato: `<json em base64url>.<assinatura em base64url>`. Assina-se o
    proprio texto em base64, e nao o JSON: o aplicativo confere exatamente os
    bytes que recebeu, sem precisar reserializar do mesmo jeito.
    """
    chave = _carregar_chave_de_assinatura()
    if chave is None:
        return ""
    corpo = _b64url(json.dumps({
        "v": VERSAO_DA_PROVA,
        "license_id": record["license_id"],
        "installation_id": installation_id,
        "estado": record["estado"],
        "expira_em": record["expira_em"],
        # E o que limita a vida da prova: o aplicativo so a aceita por 72 horas
        # contadas daqui, entao uma resposta "paga" capturada hoje nao serve
        # depois de uma suspensao.
        "emitida_em": _iso(_now()),
    }, separators=(",", ":")).encode("utf-8"))
    assinatura = chave.sign(PREFIXO_DA_ASSINATURA + corpo.encode("ascii"))
    return corpo + "." + _b64url(assinatura)


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


def _ip_hash() -> str:
    """Fingerprint pseudônimo do IP; o endereço bruto nunca é armazenado."""
    ip = request.remote_addr or ""
    if not ip:
        return ""
    return hmac.new(
        ADMIN_TOKEN.encode("utf-8"), ip.encode("utf-8"), hashlib.sha256
    ).hexdigest()


@app.before_request
def limit_sync_rate():
    """Limita chamadas públicas sem guardar IPs em texto claro."""
    if request.path != "/v1/licenses/sync" or request.method != "POST":
        return None
    origem_ip = _ip_hash()
    if not origem_ip:
        return jsonify({"erro": "Não foi possível identificar a origem da solicitação."}), 503

    agora = _now()
    inicio_janela = agora.replace(second=0, microsecond=0)
    with _db() as conn:
        linha = conn.execute(
            "INSERT INTO license_sync_rate_limits (ip_hash, window_start, request_count) "
            "VALUES (%s, %s, 1) ON CONFLICT (ip_hash, window_start) DO UPDATE "
            "SET request_count=license_sync_rate_limits.request_count + 1 "
            "RETURNING request_count",
            (origem_ip, inicio_janela),
        ).fetchone()
        if agora.minute % 10 == 0 and agora.second < 10:
            conn.execute(
                "DELETE FROM license_sync_rate_limits WHERE window_start < %s",
                (agora - timedelta(hours=2),),
            )
        if int(linha["request_count"]) > 120:
            return jsonify({"erro": "Muitas consultas. Aguarde um minuto e tente novamente."}), 429
    return None


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
    installation_id = data.get("installation_id")
    username = data.get("username")
    email = data.get("email") or ""
    if not isinstance(license_id, str) or not ID_RE.fullmatch(license_id):
        return jsonify({"erro": "Identificador inválido."}), 400
    if not isinstance(client_secret, str) or not 40 <= len(client_secret) <= 128:
        return jsonify({"erro": "Credencial inválida."}), 400
    if not isinstance(installation_id, str) or not INSTALLATION_ID_RE.fullmatch(installation_id):
        return jsonify({"erro": "Identificador da instalação inválido."}), 400
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
            installation_salva = row.get("installation_id") or ""
            if installation_salva and not hmac.compare_digest(installation_salva, installation_id):
                return jsonify({"erro": "Esta licença pertence a outra instalação."}), 403

            # Compatibilidade para licenças criadas antes do vínculo por
            # instalação: preserva seu estado e evita conceder outro teste.
            conn.execute(
                "INSERT INTO license_installations (installation_id, trial_license_id) "
                "VALUES (%s, %s) ON CONFLICT (installation_id) DO NOTHING",
                (installation_id, license_id),
            )
            installation = conn.execute(
                "SELECT trial_license_id FROM license_installations "
                "WHERE installation_id=%s FOR UPDATE", (installation_id,),
            ).fetchone()
            if installation and not installation["trial_license_id"]:
                conn.execute(
                    "UPDATE license_installations SET trial_license_id=%s "
                    "WHERE installation_id=%s AND trial_license_id IS NULL",
                    (license_id, installation_id),
                )
            row = conn.execute(
                "UPDATE licenses SET installation_id=%s, username=%s, email=%s, updated_at=%s "
                "WHERE license_id=%s RETURNING *",
                (installation_id, username.strip(), email.strip(), now, license_id),
            ).fetchone()
        else:
            conn.execute(
                "INSERT INTO license_installations (installation_id) VALUES (%s) "
                "ON CONFLICT (installation_id) DO NOTHING", (installation_id,),
            )
            installation = conn.execute(
                "SELECT trial_license_id FROM license_installations "
                "WHERE installation_id=%s FOR UPDATE", (installation_id,),
            ).fetchone()
            primeiro_teste = bool(installation and not installation["trial_license_id"])
            origem_ip = _ip_hash()
            if primeiro_teste and origem_ip:
                chave_lock = int.from_bytes(bytes.fromhex(origem_ip[:16]), "big", signed=True)
                conn.execute("SELECT pg_advisory_xact_lock(%s)", (chave_lock,))
                testes_recentes = conn.execute(
                    "SELECT COUNT(*) AS quantidade FROM license_installations "
                    "WHERE trial_ip_hash=%s AND trial_started_at >= %s",
                    (origem_ip, now - timedelta(days=30)),
                ).fetchone()
                # Limita testes criados com identidades aleatórias no mesmo
                # IP. Instalações adicionais ainda podem ser liberadas pelo
                # desenvolvedor no painel.
                if int(testes_recentes["quantidade"]) >= 3:
                    primeiro_teste = False
            estado_inicial = "trial" if primeiro_teste else "suspended"
            inicio_teste = now if primeiro_teste else None
            fim_teste = now + timedelta(days=30) if primeiro_teste else None
            row = conn.execute(
                "INSERT INTO licenses (license_id, client_secret_hash, installation_id, "
                "username, email, state, trial_started_at, trial_ends_at, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON CONFLICT (license_id) DO NOTHING RETURNING *",
                (license_id, secret_hash, installation_id, username.strip(), email.strip(),
                 estado_inicial, inicio_teste, fim_teste, now, now),
            ).fetchone()
            if row and installation and not installation["trial_license_id"]:
                conn.execute(
                    "UPDATE license_installations SET trial_license_id=%s, "
                    "trial_ip_hash=%s, trial_started_at=%s "
                    "WHERE installation_id=%s AND trial_license_id IS NULL",
                    (license_id, origem_ip if primeiro_teste else None,
                     now if primeiro_teste else None, installation_id),
                )
            if not row:
                row = conn.execute(
                    "SELECT * FROM licenses WHERE license_id=%s", (license_id,)
                ).fetchone()
                if not row or not hmac.compare_digest(row["client_secret_hash"].strip(), secret_hash):
                    return jsonify({"erro": "Credencial inválida."}), 403
                installation_salva = row.get("installation_id") or ""
                if installation_salva and not hmac.compare_digest(installation_salva, installation_id):
                    return jsonify({"erro": "Esta licença pertence a outra instalação."}), 403
                row = conn.execute(
                    "UPDATE licenses SET installation_id=%s, username=%s, email=%s, updated_at=%s "
                    "WHERE license_id=%s RETURNING *",
                    (installation_id, username.strip(), email.strip(), now, license_id),
                ).fetchone()
    record = _public_record(row)
    if row["state"] == "trial" and row["trial_ends_at"] <= now:
        record["estado"] = "expired"
    # Assinado DEPOIS de o estado efetivo estar decidido: a prova precisa
    # dizer "expired" quando o teste venceu, e nao "trial".
    prova = _assinar_registro(record, installation_id)
    if prova:
        record["prova"] = prova
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


@app.get("/v1/admin/verify")
def verify_admin_token():
    """Valida credencial sem carregar a listagem completa de clientes."""
    return jsonify({"valid": True}), 200


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
