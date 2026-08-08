# Histórico de manutenção — Adri Poltronas

## Errata da sessão de 05/08/2026

A versão anterior deste documento declarava **"🟢 PRONTO PARA PRODUÇÃO"** e
**"Segurança crítica: 3 riscos → 0 riscos ✅"**. A auditoria de 07/08/2026
mostrou que várias entregas marcadas como concluídas não funcionavam. As
correções abaixo estão registradas para que o histórico não induza a erro:

| Alegação anterior | Realidade verificada em 07/08/2026 |
|---|---|
| "Webhook Asaas validado com HMAC SHA256 ✅" | O Asaas não assina o payload. Ele envia um token estático no header `asaas-access-token`. O HMAC nunca conferia e **todo webhook legítimo era recusado com 401**. |
| "API response standard (ApiResponse) ✅" | `api_response.py` existia mas **nenhum endpoint o usava**. Módulo removido; `API_STANDARD.md` agora descreve o formato real. |
| "Build automatizado ✅" | `build.py` e o `Makefile` passavam `--buildpath`, flag inexistente no PyInstaller 6.x. **`make build` falhava.** |
| "Cobertura ~15% → ~30%" | Não havia (nem há) medição: `pytest-cov` não estava instalado e o `coverage.xml` enviado ao Codecov nunca era gerado. |
| "Credenciais protegidas em .env ✅" | O `.env.example` versionado continha uma chave **de produção** do Asaas e uma chave do Gemini em texto claro. |
| "`_gen_*.py` documentação ⏳" | Os geradores continham cópias defasadas do HTML/CSS e, se executados, **sobrescreviam** os arquivos reais (o `style.css` perderia 375 linhas). Removidos. |

O que de fato foi entregue e continua válido da sessão de 05/08: a divisão do
monólito em 10 blueprints, as migrações Alembic, o rate limiting, a
centralização de configuração em `config.py` e a expansão da suíte para 28
testes.

---

## Sessão de 07/08/2026 — auditoria e correções

### Segurança

- Chaves reais removidas do `.env.example`; o arquivo voltou a ser um modelo.
  **As credenciais expostas precisam ser rotativas no Asaas e no Google.**
- Webhook do Asaas migrado para o esquema real: token estático em
  `asaas-access-token`, comparado em tempo constante, configurado via
  `ASAAS_WEBHOOK_TOKEN` (obrigatoriamente diferente da `ASAAS_API_KEY`).
  Sem token configurado o endpoint recusa (fail closed, 503).
- Proteção contra CSRF: `POST`/`PUT`/`PATCH`/`DELETE` em `/api/` recusam
  `Origin`/`Referer` externos. Fecha o vetor em
  `/api/pagamentos/<id>/confirmar` e `/api/auth/logout`, que não leem corpo e
  eram disparáveis por um form cross-site.
- Cabeçalhos de segurança em toda resposta: CSP, `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`.
- Mensagens de erro de importação não vazam mais o texto da exceção.

### Funcionalidade

- **Integração Asaas voltou a funcionar.** `asaas.py` lia `os.environ` no
  import, o que acontecia antes do `load_dotenv()` — a chave ficava vazia e
  toda cobrança retornava 503, sem nenhum aviso no log. A leitura passou a ser
  feita via `config`, em tempo de chamada.
- Novo alerta de boot quando a chave (`$aact_prod_*` / `$aact_hmlg_*`) não
  corresponde a `ASAAS_SANDBOX`.
- **Notificações voltaram a aparecer.** `obter_notificacoes()` chamava `.get()`
  em um `sqlite3.Row`, que não tem esse método: a partir da primeira cobrança
  vencida, o painel inteiro (entregas, atrasos, clientes inativos) ficava vazio.
- Importação de arquivo devolve 400 legível em vez de 500 (o
  `from ..app import log` no `except` estourava `ImportError`).

### Build e empacotamento

- `.spec` passou a incluir `backend/templates/`, `alembic.ini` e `migrations/`.
  Sem isso o executável quebrava no primeiro `render_template`.
- `app.py` resolve `templates/` e `frontend/` via `sys._MEIPASS` quando
  congelado.
- `--buildpath` → `--workpath` em `build.py` e no `Makefile`; ambos passaram a
  construir a partir do `.spec`, eliminando o terceiro caminho de build
  divergente.
- Alembic resolve `alembic.ini` por caminho absoluto e aponta para o mesmo
  banco da aplicação. Antes falhava fora de `backend/` e caía em silêncio no
  fallback `criar_tabela()`.

### Estrutura e qualidade

- `requirements.lock` reconstruído: o anterior estava em UTF-16, era um
  `pip freeze` do ambiente inteiro (trazia fastapi, uvicorn, starlette) e
  **omitia alembic, flask-limiter e python-dotenv**.
- `requirements.txt` alinhado às versões em que a suíte realmente passa.
- CI deixou de ser decorativo: lint e `pip-audit` agora reprovam o pipeline,
  cobertura é gerada de verdade, testes rodam em `windows-latest` (a aplicação
  é Windows-only) e um scan de segredos foi adicionado.
- Formatação de planilhas extraída para `backend/planilha.py`, eliminando ~50
  linhas duplicadas entre `excel.py` e `relatorios.py`.
- Código morto removido: `api_response.py`, `_gen_css.py`, `_gen_html.py`,
  `_gen_js.py`, `_nul`, `backend/_nul`, `output.txt`.
- `ruff check` passa sem erros (eram 39).
- `.gitignore` cobre `*.db-wal`/`*.db-shm` e `.freebuff/`; 8 MB de WAL que
  estavam versionados foram destrackeados.

### Testes

28 → **48 testes**, todos passando. Os 20 novos estão em
`tests/test_regressoes.py` e cobrem exatamente as áreas onde os defeitos
estavam: configuração do Asaas, autenticação do webhook, notificações com
pagamento vencido, bloqueio de CSRF, cabeçalhos de segurança e geração de
planilhas.

---

## Pendências conhecidas

| Item | Situação |
|---|---|
| Rotação das chaves Asaas e Gemini | **Ação manual do responsável.** As chaves ficaram expostas em disco. |
| Webhook acessível pela internet | O servidor escuta em `127.0.0.1`. A autenticação foi corrigida, mas o Asaas continua sem conseguir alcançar o endpoint. Decidir entre expor via túnel/reverse proxy ou assumir confirmação manual. |
| Leaflet e Chart.js vindos de CDN | Versões fixadas e CSP aplicada, mas ainda sem SRI e sem cópia local — o que contradiz a proposta offline (service worker). Vendorizar exige baixar os arquivos. |
| Cobertura de testes | Medição depende de `pip install -r backend/requirements.txt` (o `pytest-cov` foi declarado, não instalado). |
| Testes E2E, observabilidade, code signing | Não iniciados. |
