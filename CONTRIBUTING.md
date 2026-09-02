# Como trabalhar neste repositório

## Os dois ambientes

| Branch | O que é | Quem escreve nela |
|---|---|---|
| **`main`** | O software pronto. Tudo aqui está concluído, testado e instalável. Cada commit é uma versão que pode ir para a máquina do cliente. | Ninguém direto. Só recebe merge de `develop`. |
| **`develop`** | A cópia de desenvolvimento. É onde o trabalho em andamento se integra e convive antes de virar versão. | Só recebe merge de `feature/*`. |
| **`feature/*`** | Uma branch por funcionalidade. Nasce de `develop` e volta para ela. | Aqui é onde se programa. |

A regra que dá sentido a tudo: **se está na `main`, funciona.** Quem instalar o
que está na `main` recebe um sistema íntegro. É por isso que ela não recebe
trabalho pela metade, nem "vou terminar amanhã".

```
feature/nome-da-coisa  ──PR──>  develop  ──PR──>  main  ──tag──>  v1.2.0
      (programa aqui)          (integra)      (entrega)
```

## O ciclo de uma funcionalidade

**1. Nasce de `develop`, nunca da `main`**

```bash
git switch develop
git pull
git switch -c feature/nome-da-coisa
```

**2. Trabalha e commita**

Mensagem no formato `tipo: descrição` — `feat`, `fix`, `refactor`, `docs`,
`test`, `chore`, `perf`, `ci`. O corpo explica **por quê**, não o quê: o diff
já mostra o quê.

**3. Antes de abrir o PR, roda o que o CI roda**

```bash
python -m ruff check backend/ tests/ build.py
```

```bash
cd backend && python -m pytest ../tests -q
```

```bash
npm run typecheck && npm run build
```

O `ruff` é o que mais pega gente desprevenida: o job de teste do CI roda o
lint **antes** do pytest, então um import não usado reprova tudo sem a suíte
sequer começar. E o pytest roda de dentro de `backend/` no CI — rodar da raiz
pode esconder problema de caminho relativo.

Além disso, o CI reprova por coisas que não aparecem rodando os comandos acima:

| Verificação | Como reproduzir localmente |
|---|---|
| Cobertura mínima de 80% | `cd backend && python -m pytest ../tests --cov=. --cov-fail-under=80` |
| Vulnerabilidade em dependência Node | `npm audit --audit-level=high` |
| Vulnerabilidade em dependência Python | `pip-audit -r backend/requirements.txt --strict` |
| Segredo no histórico | `gitleaks detect --source . --redact` |
| Interface num navegador de verdade | `pip install pytest-playwright && playwright install chromium`, depois `cd backend && python -m pytest ../tests/test_e2e_interface.py` |

O job `instalador` só roda na `main` e em PR para ela: é ele que constrói o
PyInstaller e o NSIS. Um PR para `develop` não o exercita, então um problema de
empacotamento só aparece na promoção.

**4. Abre PR para `develop`**

```bash
gh pr create --base develop --title "..." --body "..."
```

O PR precisa dizer **o que mudou, por quê, e o que o revisor precisa saber**.
Decisão não óbvia merece parágrafo: quem revisa não estava na sua cabeça.

**5. Merge em `develop` quando os checks passarem**

## Quando promover para a `main`

Só quando a funcionalidade estiver **concluída e testada**. Na prática:

- [ ] Faz o que se propôs, ponta a ponta, exercitado na interface real — não
      só em teste
- [ ] Tem teste automatizado cobrindo a regra crítica, não apenas o caminho feliz
- [ ] `ruff`, `pytest`, `typecheck` e `build` verdes
- [ ] Os checks do CI passando no PR
- [ ] Se mexeu no schema: migration testada em banco vazio **e** em cópia do
      banco de produção
- [ ] Nada de `TODO`, código comentado ou "arruma depois" no diff

Faltando um item, o lugar é `develop`. Não a `main`.

```bash
gh pr create --base main --head develop --title "Entrega: ..."
```

Depois do merge, marque a versão — é o que permite voltar a um ponto
conhecido quando algo der errado na máquina do cliente:

```bash
git switch main && git pull
git tag -a v1.2.0 -m "v1.2.0 - resumo do que entrou"
git push origin v1.2.0
```

Atualize também o `version` do `package.json` no mesmo commit.

## O que nunca entra no repositório

O `.gitignore` já cobre, mas vale saber por quê: **o repositório é público.**

- `backup/` e qualquer `*.db` — contêm nome, endereço e CEP de clientes reais
- `.env`, `*.key`, `*.pem` — as credenciais vivem em `%APPDATA%\AdriPoltronas\`
- `dist/`, `dist-instalador/`, `build/`, `node_modules/` — artefatos

Antes do primeiro `git add` de qualquer coisa nova, confira:

```bash
git status --porcelain | grep -iE "\.db|\.env|\.key|backup/"
```

Se retornar alguma linha, **pare**. Um arquivo commitado e enviado fica no
histórico para sempre, mesmo removido depois.

## Banco de dados

Alembic é o único dono do schema. Toda mudança é uma migration **aditiva** —
coluna nova é anulável ou tem default, e nada é removido sem uma versão de
compatibilidade antes.

O backup é automático: uma cópia antes de cada migration e uma por dia, em
`%APPDATA%\AdriPoltronas\backups\`. Ainda assim, teste a migration numa cópia
do banco real antes de promover para a `main`.

## Pendências conhecidas

- **Autenticação do ERP usa o OAuth da Microsoft.** Criar cliente, produto ou
  pedido exige estar conectado ao OneDrive, o que é conceitualmente errado —
  integração não deveria definir identidade de usuário. Na prática isso
  significa que a fila offline não consegue sincronizar sem uma sessão da
  Microsoft ativa: as alterações vão para a fila de erros com 401. Resolver
  exige autenticação local própria, independente de integração.
- **Não há usuários nem permissões.** Quem abre o aplicativo pode tudo.
- **Releases são publicadas por tag.** `git push origin vX.Y.Z` dispara o
  workflow `release.yml`, que constrói o instalador, gera o checksum e publica.
  A tag precisa casar com a `version` do `package.json` — o workflow reprova se
  divergirem.
- **`main` não está protegida pelo GitHub.** A tabela acima diz que ninguém
  grava direto nela — hoje isso é combinado, não regra: um `git push origin
  main` acidental passa. Ver "Proteger a `main`" abaixo.
- **`pagamentos.valor` ainda é `REAL`, ao lado de `valor_centavos`.** As
  escritas e todas as leituras financeiras já usam a coluna inteira; `valor`
  segue sendo gravado para não quebrar consumidor externo. Removê-la é o
  passo final da transição.
- **Listagens não têm paginação.** A tela de clientes baixa e renderiza todos.
  Adequado para os milhares de registros de hoje; não para dezenas de milhares.
- **Um computador por empresa.** SQLite em pasta de rede corrompe. Compartilhar
  a base entre máquinas exigiria API central e banco servidor.

## Proteger a `main`

Enquanto isso não estiver feito, a regra "ninguém grava direto na `main`" é
apenas um acordo. Em
[Settings → Branches](https://github.com/pedromatheuszz/Adri-Poltronas/settings/branches),
crie um ruleset para `main` com:

- **Require a pull request before merging**
- **Require status checks to pass** — marque todos: `test (3.10)`,
  `test (3.11)`, `test (3.12)`, `electron`, `qt`, `dotnet`, `security` e
  `instalador`
- **Block force pushes**

## Autoria dos commits

O e-mail do autor fica visível para sempre no histórico de um repositório
público. Para usar o endereço de encaminhamento do GitHub em vez do pessoal:

```bash
git config user.email "SEU_ID+SEU_USUARIO@users.noreply.github.com"
```

O número do ID está em
[Settings → Emails](https://github.com/settings/emails). Isso vale para os
commits **novos** — reescrever o histórico já publicado é outra operação, e
muda o hash de todos os commits.
