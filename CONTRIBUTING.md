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

- **`gitleaks` vermelho no CI.** Falha desde antes do repositório entrar no
  git. O passo de dependências vulneráveis já passa; o de varredura de
  segredos ainda não. Diagnosticar exige ler o log do job.
- **Autenticação do ERP usa o OAuth da Microsoft.** Criar cliente, produto ou
  pedido exige estar conectado ao OneDrive, o que é conceitualmente errado —
  integração não deveria definir identidade de usuário.
