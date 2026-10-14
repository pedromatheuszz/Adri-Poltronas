# API central de licenças

Serviço separado do ERP. O ERP continua com o banco SQLite local; este serviço
guarda somente o identificador da licença, nome/e-mail da conta do software e
estado do teste/pagamento. Nenhum cadastro de clientes, pedidos ou financeiro
do ERP é enviado para cá.

## Opção A: Hospedagem 100% Gratuita (Neon.tech + Render.com)

Esta é a opção mais rápida e simples, sem necessidade de alugar servidor nem registrar domínio de imediato.

### 1. Criar o Banco PostgreSQL Gratuito no Neon (https://neon.tech)
1. Crie uma conta gratuita no Neon e clique em **Create Project** (ou **Create Database**).
2. Escolha um nome (ex: `adri-licencas`).
3. O Neon exibirá a **Connection String** pronta (com `sslmode=require`). Copie esse valor:
   `postgresql://usuario:senha@ep-xyz.neon.tech/neondb?sslmode=require`

### 2. Publicar a API Gratuitamente no Render (https://render.com)
1. Crie uma conta no Render e clique em **New +** > **Web Service**.
2. Conecte o repositório Git ou faça deploy desta pasta.
3. Se fizer deploy por Dockerfile:
   - O Render usará o `Dockerfile` existente automaticamente.
   Se fizer deploy por Python nativo:
   - **Root Directory**: `licensing-service`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn --workers 2 --threads 4 --timeout 30 app:app`
4. Na aba **Environment**, adicione as seguintes variáveis:
   - `DATABASE_URL`: a connection string copiada do Neon.
   - `LICENSE_ADMIN_TOKEN`: token aleatório de 64 caracteres (gere com `python -c "import secrets; print(secrets.token_hex(32))"`).
5. O Render fornecerá uma URL pública gratuita com HTTPS, ex:
   `https://adri-licencas.onrender.com`
6. Acesse `https://adri-licencas.onrender.com/health` no navegador. A resposta esperada é:
   `{"service":"adri-licensing","status":"ok"}`

---

## Opção B: Publicar em Servidor Próprio com Docker Compose

É necessário um servidor Linux com Docker Compose, um domínio próprio e acesso
ao DNS. O domínio precisa apontar para o IP do servidor; as portas TCP 80 e 443
(e UDP 443 para HTTP/3) precisam estar liberadas. O Caddy emite e renova o
certificado HTTPS automaticamente.

1. Copie esta pasta para o servidor.
2. Copie `.env.example` para `.env` e preencha o domínio e dois segredos
   aleatórios diferentes. Para cada segredo, gere 32 bytes com:

   ```sh
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

3. Suba a aplicação:

   ```sh
   docker compose up -d --build
   docker compose ps
   ```

4. Confira `https://SEU_DOMINIO/health`. A resposta esperada contém
   `{"status":"ok"}`.
5. Faça backup periódico do volume Docker `license_db` e mantenha a chave de
   administração em um cofre de senhas.

O banco PostgreSQL usa volume persistente. Não remova o volume durante uma
atualização. Para atualizar, copie a nova versão do código e execute novamente
`docker compose up -d --build`.

## Configurar o ERP

Nas configurações `.env` do backend local, configure:

```dotenv
ADRI_LICENCA_API_URL=https://SEU_DOMINIO
ADRI_LICENCA_ADMIN_TOKEN=TOKEN_ADMINISTRATIVO
```

O token administrativo fica **somente** no computador do desenvolvedor. Se
inserido temporariamente no `.env` do usuário, o backend migra esse segredo
para `%APPDATA%\AdriPoltronas\.segredos`, cifrado com DPAPI, na inicialização.
Também pode ser injetado pelo ambiente do processo. Não o inclua no
repositório, instalador, JavaScript, computador do cliente ou arquivo
`.env.example`.

Nas instalações dos clientes, configure somente `ADRI_LICENCA_API_URL`. Sem o
token administrativo, a instalação ainda sincroniza a própria licença, mas não
pode listar contas nem executar comandos administrativos.

Após configurar a URL, reinicie o software. A conta do cliente aparece na aba
Desenvolvedor depois que o computador dele entrar no sistema e sincronizar com
a internet. A liberação de pagamento no painel é propagada no próximo contato
do aplicativo, que consulta a API a cada 30 segundos. Uma licença validada
recentemente continua funcionando offline por até 72 horas.

## API e estados

- `POST /v1/licenses/sync`: cliente consulta a licença usando um ID e segredo
  aleatórios próprios. A primeira sincronização inicia um período de 30 dias.
- `GET /v1/admin/licenses`: lista as contas; exige `Bearer` com o token admin.
- `POST /v1/admin/licenses/{id}`: ação `paid`, `trial_30_days` ou `suspend`;
  exige o token admin. `paid` libera permanentemente até uma suspensão manual.
- `GET /health`: prontidão do serviço e do banco.

O tráfego público deve usar HTTPS. A API guarda hash SHA-256 do segredo de cada
conta, nunca o segredo em texto puro. A chave administrativa é comparada sem
comparação de prefixo e não é devolvida nas respostas. O dono da máquina do
cliente controla o software local, então nenhuma barreira comercial embarcada
no aplicativo impede adulteração deliberada do executável ou do relógio.

O identificador de conta é criado uma vez no SQLite de cada instalação. Apagar
esse banco apaga também a identidade local; o produto não usa um cadastro de
conta hospedado. Mantenha backups do servidor e do banco local conforme a
política de suporte da empresa.
