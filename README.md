# Adri Poltronas

ERP desktop para uma fábrica de poltronas sob encomenda.

O sistema acompanha o ciclo completo de um pedido — do cadastro do cliente à
entrega e ao recebimento parcelado — numa aplicação que roda inteira na máquina
do escritório: sem servidor, sem mensalidade e sem depender de internet para o
trabalho do dia a dia.

```
Cliente  ──>  Pedido  ──>  Entrega agendada
                 │
                 └──>  Faturamento  ──>  Parcelas a receber  ──>  Pix / Boleto
```

---

## De que se trata

A Adri Poltronas fabrica sob encomenda: cada poltrona tem tecido, acabamento e
medida próprios, e existe um prazo combinado com o cliente. Um ERP genérico não
serve bem a isso — ou trata tudo como produto de prateleira, ou exige um módulo
de produção que a operação não usa.

Este software é feito para esse recorte. Ele responde às três perguntas que a
equipe faz todo dia:

| Pergunta | Onde é respondida |
|---|---|
| **O que foi vendido, por quanto e para quando?** | Pedidos |
| **O que precisa ser entregue hoje?** | Agenda de Entregas |
| **Quem deve, quanto e desde quando?** | Pagamentos |

O público é uma **equipe pequena de escritório** — duas a cinco pessoas — que
passa o dia inteiro na tela. Isso moldou tanto a interface (densa, calma, sem
animação decorativa) quanto a arquitetura (um executável, um banco em arquivo,
nenhuma infraestrutura para manter).

---

## Como o sistema funciona

Não é um site nem um app de nuvem. É um **aplicativo desktop que embute o
próprio servidor**:

```
┌──────────────────────── Aplicativo (Electron) ────────────────────────┐
│                                                                       │
│  Janela (Chromium)                     Processo filho (Python)        │
│  ┌───────────────────────┐             ┌────────────────────────┐     │
│  │  Interface            │   HTTP      │  Flask                 │     │
│  │  HTML + CSS + JS      │ ──────────> │  47 rotas /api/*       │     │
│  │  (sem framework)      │  127.0.0.1  │                        │     │
│  └───────────────────────┘  porta 5000 │  Regras de negócio     │     │
│                                        │  backend/erp/          │     │
│                                        └──────────┬─────────────┘     │
│                                                   │                   │
│                                          ┌────────▼────────┐          │
│                                          │  SQLite         │          │
│                                          │  %APPDATA%      │          │
│                                          └─────────────────┘          │
└───────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
        ViaCEP · Nominatim · Gemini · Microsoft Graph · Asaas
                  (opcionais — cada uma degrada sozinha)
```

O Electron abre a janela e sobe o Flask como processo filho. A interface é
servida pelo próprio backend em `http://127.0.0.1:5000` — **loopback apenas**,
nunca exposto na rede. Quando a janela fecha, o backend morre junto.

A porta 5000 é fixa de propósito: o `redirect_uri` do login Microsoft está
registrado no Azure apontando para ela.

**Por que sem framework de front-end.** A interface é HTML, CSS e JavaScript
direto, servidos pelo Flask. Não há build step, bundler nem `node_modules` em
produção — o que se lê no repositório é o que roda. Para uma equipe pequena
mantendo o sistema por anos, isso vale mais do que a ergonomia de um framework.

---

## Funcionalidades

### Dashboard
Visão executiva, só de leitura: total de clientes, entregas e retiradas,
cadastros dos últimos 30 dias, faturamento do mês com variação contra o mês
anterior, valor a receber, valor em atraso e ticket médio. Quatro gráficos
(receita mensal, entregas × retiradas, clientes por cidade, novos clientes) e
a lista dos últimos cadastros.

### Pedidos
O centro do dia a dia. Cada pedido registra cliente, **prazo de entrega**,
itens, desconto, frete e total. Os itens aceitam **descrição própria** — é onde
entram tecido, acabamento e medida de cada peça.

O pedido segue uma máquina de estados explícita:

```
rascunho ──> aberto ──> aprovado ──> faturado
    │           │           │
    └───────────┴───────────┴──> cancelado
```

- **rascunho** — sendo montado; itens entram e saem
- **aberto** — apresentado ao cliente, aguardando aceite
- **aprovado** — aceito; a produção começa e a entrega pode ser agendada
- **faturado** — parcelas emitidas. **Terminal**, porque a partir daí existe
  dinheiro cobrado do outro lado

O **faturamento** é a transição que gera efeito real: emite N parcelas e marca
o pedido, tudo numa transação só. Se a emissão da segunda parcela falhar, a
primeira volta atrás e o pedido continua aprovado — não fica pedido faturado
com cobrança pela metade.

O rateio não perde nem inventa centavo: R$ 100,00 em 3 vira 33,34 + 33,33 +
33,33, com a sobra na primeira parcela, para o total conferir já no primeiro
vencimento.

### Produtos
Catálogo enxuto dos modelos: código, descrição, unidade e preço de venda. É
meio para o pedido, não um fim. Produto usado em pedido é **inativado**, nunca
apagado — o pedido antigo não pode perder a referência.

### Clientes
Cadastro com busca no servidor, filtros por tipo e cidade, importação em lote
(CSV, JSON e XLSX, até 5.000 linhas, com detecção de duplicados) e exportação.
A exclusão é lógica: o cliente sai das listas, o histórico permanece.

### Agenda de Entregas
Agrupada por dia, com **Hoje** e **Atrasadas** em destaque — é a tela que a
equipe olha de manhã. Cada entrega pode nascer de um pedido aprovado, herdando
cliente e prazo, e o número do pedido leva de volta a ele.

Situações: `Pendente` → `Em andamento` → `Concluída`, ou `Cancelada`.

### Pagamentos
Lançamentos com status (Pendente, Recebido, Atrasado, Cancelado), forma de
pagamento e vencimento. As parcelas geradas pelo faturamento aparecem aqui, e
de cada uma é possível **emitir cobrança Pix ou boleto** pelo Asaas, com QR
Code e "copia e cola" na própria tela.

### Mapa
Os clientes plotados sobre o OpenStreetMap, com marcadores distinguindo entrega
de retirada. A geocodificação é cacheada localmente, então o custo é pago uma
vez por máquina.

### Relatórios
Consultas filtradas por tipo, cidade e período, com prévia na tela, exportação
em CSV ou XLSX e um recorte de desempenho por região.

### Notificações
Seis alertas derivados dos dados, sem tabela própria — recalculados a cada
consulta:

| Alerta | Prioridade |
|---|---|
| Entrega atrasada | Crítica |
| Entrega hoje | Alta |
| Pagamento atrasado | Alta |
| Entrega nos próximos 3 dias | Média |
| Pagamento vence hoje | Média |
| Cliente sem movimento há 90 dias | Baixa |

O estado de "lida" é persistido; o fato em si continua valendo.

### Modo offline
A interface abre e a lista de clientes continua legível sem rede, servida do
IndexedDB. Cadastro, edição e exclusão de clientes entram numa fila e são
sincronizados quando a conexão volta.

---

## APIs e serviços integrados

Todas as integrações são **opcionais e degradam sozinhas**: sem chave ou sem
rede, o recurso correspondente se desliga e o resto do sistema segue.

| Serviço | Para quê | Credencial |
|---|---|---|
| **Microsoft Graph** | Envia a planilha de clientes para o OneDrive. Login OAuth 2.0 com PKCE, sem client secret; o token é renovado em silêncio via `refresh_token`. | App registrado no Azure (já configurado) |
| **Asaas** | Emite cobrança Pix e boleto e recebe a confirmação por webhook. Suporta sandbox e produção. | `ASAAS_API_KEY` + `ASAAS_WEBHOOK_TOKEN` |
| **ViaCEP** | Preenche endereço a partir do CEP. | Não precisa |
| **Google Gemini** | Sugere o bairro quando o ViaCEP não resolve. | `GEMINI_API_KEY` |
| **Nominatim / OpenStreetMap** | Converte endereço em coordenada para o mapa. Respeita o limite de 1 requisição por segundo. | Não precisa |

No front-end, **Leaflet** desenha o mapa e **Chart.js** os gráficos, ambos
carregados de CDN com verificação de integridade (SRI).

### A API interna

47 rotas sob `/api/`, servidas em loopback:

| Grupo | Rotas | O que cobre |
|---|---|---|
| `pedidos` | 10 | CRUD, itens e as quatro transições de estado |
| `pagamentos` | 10 | Lançamentos, métricas, cobrança Asaas e webhook |
| `clientes` | 8 | CRUD, importação em lote, mapa e backup |
| `produtos` | 4 | Catálogo |
| `auth` · `entregas` · `notificacoes` | 3 cada | Sessão Microsoft, agenda, alertas |
| `dashboard` · `relatorios` | 2 cada | Indicadores e consultas |
| `excel` · `ia` | 1 cada | OneDrive e sugestão de bairro |

O contrato está em [API_STANDARD.md](API_STANDARD.md): sem envelope, erro
sempre na chave `erro`, e rotas sob `/api/` nunca devolvem HTML.

---

## Dados e segurança

**11 tabelas** em SQLite, com Alembic como único dono do schema (7 revisions).
O banco vive em `%APPDATA%\AdriPoltronas\adri_poltronas.db`.

```
clientes ──┬── pedidos ── pedido_itens ── produtos
           ├── pagamentos           │
           ├── entregas_agendadas ──┘
           ├── historico
           └── clientes_asaas

auditoria_eventos · notificacoes_lidas · sessao
```

**Backup automático.** Uma cópia antes de cada migration — a única operação que
reescreve estrutura — e uma por dia. Usa a API online do SQLite, então a cópia é
íntegra mesmo com o aplicativo aberto, e é descartada se não passar no
`integrity_check`: cópia parcial dá falsa segurança. Ficam em
`%APPDATA%\AdriPoltronas\backups\`, com rotação separada por motivo (10 de
pré-migração, 7 diárias).

**Trilha de auditoria** append-only, protegida por triggers que recusam `UPDATE`
e `DELETE`. Cada operação grava valores anteriores e novos, com identificação de
quem fez e id de correlação. Campos sensíveis são redigidos antes de gravar.

**Credenciais em repouso** são cifradas com DPAPI do Windows quando disponível,
e com Fernet (AES-128-CBC + HMAC-SHA256) como alternativa. O token e o
refresh_token da Microsoft nunca ficam em texto claro.

**Superfície de ataque.** O servidor escuta apenas em loopback. Toda resposta
carrega CSP, `X-Content-Type-Options`, `X-Frame-Options` e `Referrer-Policy`.
Requisições que alteram estado verificam `Origin`/`Referer`. O webhook do Asaas
compara o token em tempo constante e recusa quando não configurado. Há rate
limit por endpoint.

**Registros empresariais não são apagados** — são inativados, cancelados ou
estornados. Cliente excluído vira inativo; produto em uso vira inativo; pedido
faturado só se desfaz por estorno.

---

## Começando

Pré-requisitos: **Windows**, **Python 3.10–3.12** e **Node.js 22**.

```powershell
python -m pip install -r backend/requirements.txt
npm ci
npm start
```

O primeiro `npm start` aplica as migrations e cria o banco. Para trabalhar com
um banco isolado, defina `ADRI_DB_PATH`.

As credenciais opcionais vão num `.env` em `%APPDATA%\AdriPoltronas\`, criado
automaticamente no primeiro boot a partir de [.env.example](.env.example). O que
faltar apenas desliga o recurso correspondente, e o log do boot diz o quê.

### Gerar o instalador

```powershell
npm run dist
```

Empacota o backend com PyInstaller e a janela com electron-builder, produzindo
um instalador NSIS. Detalhes em [BUILD_GUIDE.md](BUILD_GUIDE.md).

---

## Desenvolvimento

### Ambientes

| Branch | O que é |
|---|---|
| `main` | O software pronto: concluído, testado e instalável. Cada tag é uma versão. |
| `develop` | A cópia de desenvolvimento, onde o trabalho em andamento se integra. |
| `feature/*` | Uma branch por funcionalidade; nasce de `develop` e volta para ela. |

**Se está na `main`, funciona.** O fluxo completo e o checklist de promoção
estão em [CONTRIBUTING.md](CONTRIBUTING.md).

### Qualidade

**520 testes** e 85% de cobertura, cobrindo regras de negócio, API, segurança,
validação, migrations e contratos do front-end. O CI reprova abaixo de 80%.

```powershell
python -m ruff check backend tests build.py
cd backend; python -m pytest ../tests -q
npm run typecheck
npm run build
```

O `ruff` roda **antes** do pytest no CI — um import não usado reprova a suíte
sem ela começar. E o CI executa os testes de dentro de `backend/`, então rodar
da raiz pode esconder problema de caminho relativo.

### Estrutura

```
backend/
  app.py              Composição do Flask, middleware, CSP, sessão
  servidor.py         Ponto de entrada: backup, migrations, servidor
  blueprints/         Adaptadores HTTP, sem regra de negócio
  erp/
    core/             Auditoria, contexto, backup, dinheiro em centavos
    comercial/        Pedido: estados, repositório e regras
    financeiro/       Conciliação de pagamentos
  migrations/         Alembic — o único dono do schema
frontend/
  css/tokens.css      Design system: cor, tipografia, espaço, sombra
  css/style.css       Componentes e layout
  js/app.js           Núcleo da interface
  js/comercial.js     Pedidos, Produtos e Entregas
  js/offline.js       Fila de sincronização e cache
electron/             Processo principal (TypeScript)
tests/                435 testes
```

Código novo de domínio entra em `backend/erp/`, por módulo de negócio. Os
blueprints permanecem como adaptadores; contratos existentes não são removidos
sem migração e testes.

---

## Estado atual e limites conhecidos

O que está descrito acima existe e funciona. O que **ainda não existe**, para
não gerar expectativa errada:

- **Estoque, compras e contas a pagar.** O sistema cobre a venda, não a
  aquisição.
- **Ordem de produção.** Não há etapas de oficina, apontamento nem ficha
  técnica. O prazo do pedido é o único controle de fabricação.
- **Nota fiscal.** Nenhuma emissão fiscal — e o cadastro de cliente ainda não
  tem CPF/CNPJ, telefone nem e-mail.
- **Usuários e permissões.** Não há login próprio do ERP: a autenticação usa a
  sessão OAuth da Microsoft, o que é conceitualmente errado — integração não
  deveria definir identidade de usuário. Na prática, criar cliente, produto ou
  pedido exige estar conectado ao OneDrive.
- **Webhook do Asaas inalcançável pela internet.** O servidor é loopback, e
  nenhum servidor externo alcança esse endereço. Quem cobre isso é a
  conciliação ativa: o sistema pergunta ao Asaas o estado das cobranças em
  aberto ao abrir a aba de Pagamentos e no botão "Conciliar com o Asaas". O
  webhook continua no lugar para quem tiver infraestrutura para recebê-lo.
- **Executável sem assinatura digital.** O SmartScreen alerta na instalação.
- **Banco e backups não são cifrados em repouso.** O arquivo contém nome,
  endereço e CEP de clientes reais; um disco sem BitLocker, perdido ou
  roubado, entrega tudo. Ver [PRIVACIDADE.md](PRIVACIDADE.md).
- **Exclusão de cliente é lógica, não física.** O registro sai das telas e das
  exportações, mas permanece no banco e nos backups — o histórico, os
  pagamentos e a auditoria apontam para ele. Um pedido de exclusão sob a LGPD
  não é atendido pela tela de exclusão.
- **Um computador por empresa.** Não há arquitetura para várias máquinas
  compartilharem a mesma base; SQLite em pasta de rede corrompe.
- **Listagens sem paginação.** A tela de clientes baixa e renderiza todos os
  registros. Adequado para os milhares de hoje, não para dezenas de milhares.

O caminho pretendido está em
[docs/ERP_DIAGNOSTICO_E_ROADMAP.md](docs/ERP_DIAGNOSTICO_E_ROADMAP.md).

---

## Documentação

- [Como trabalhar neste repositório](CONTRIBUTING.md) — fluxo de branches e critérios de entrega
- [Registro de mudanças](CHANGELOG.md) — o que entrou em cada versão
- [Segurança](SECURITY.md) — como relatar falha, e o modelo de ameaça com seus limites
- [Dados pessoais e LGPD](PRIVACIDADE.md) — o que é guardado, por quanto tempo e o que sai da máquina
- [Padrão da API](API_STANDARD.md) — contrato das rotas
- [Build e desenvolvimento](BUILD_GUIDE.md) — empacotamento e instalador
- [Diagnóstico e roadmap ERP](docs/ERP_DIAGNOSTICO_E_ROADMAP.md) — estado e evolução
- [Decisões de arquitetura](docs/adr/) — o que foi decidido, e o que foi descartado junto
- [Code signing](docs/code-signing.md) — assinatura do executável
- [Aplicativo .NET/Avalonia](dotnet/README.md) — exploração arquitetural, banco próprio, não distribuída
- [Licença](LICENSE) — software proprietário; o código é público para consulta
