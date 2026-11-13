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
   - **Start Command**: `gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 30 app:app`

   > O `--bind 0.0.0.0:$PORT` é obrigatório: o Render só conversa com a
   > porta da variável `PORT`, e o gunicorn sozinho escuta em
   > `127.0.0.1:8000` — sem o bind, o deploy sobe e a URL responde 502
   > para sempre. (O Dockerfile já faz o bind; esse aviso vale só para o
   > caminho Python.)
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

## Assinar as respostas (fecha o contorno da licença)

Sem assinatura, o aplicativo acredita em qualquer servidor para o qual
`ADRI_LICENCA_API_URL` aponte e no que estiver gravado no cache local — basta
um servidor falso respondendo `"paid"`, ou uma linha de SQL no banco do
cliente. Com assinatura, o serviço assina (Ed25519) o estado, a validade, a
conta, a instalação e o instante da resposta, e o aplicativo só aceita o que
confere com a chave pública embutida nele.

A exigência fica **desligada** enquanto a chave pública não estiver no código.
Ative nesta ordem — inverter os passos 2 e 4 tranca os clientes do lado de
fora, porque o aplicativo passaria a exigir uma assinatura que o serviço ainda
não emite:

1. Gere o par, uma única vez, no computador do fornecedor:
   `python licensing-service/gerar_chave_de_assinatura.py`
2. Configure a linha `LICENSE_SIGNING_KEY=...` nas variáveis de ambiente do
   serviço (aba **Environment** do Render, ou o `.env` do Docker Compose) e
   publique. É a chave **privada**: quem a tiver emite licenças válidas. Não
   vai para o repositório nem para nenhuma instalação de cliente.
3. Confirme que o serviço passou a assinar: a resposta de
   `/v1/licenses/sync` ganha o campo `prova`.
4. Cole a linha `CHAVE_PUBLICA_DA_CENTRAL = "..."` em
   `backend/licenca_remota.py`, gere o instalador e distribua. A chave
   pública não é segredo.

A partir da versão com a chave pública, uma resposta sem assinatura válida é
ignorada, o cache só libera o uso a partir da prova assinada (as colunas de
texto servem apenas para lembrar uma recusa), a prova copiada de outro
computador não vale e a janela offline de 72 horas conta do instante em que o
servidor respondeu. Instalações antigas, sem a chave, continuam funcionando
como antes.

Limites: atrasar o relógio do Windows ainda estica a janela offline, e quem
altera o executável altera também a chave embutida. Trocar o par invalida as
provas já emitidas — os aplicativos com a chave antiga deixam de reconhecer o
serviço até serem atualizados.

## API e estados

- `POST /v1/licenses/sync`: cliente consulta a licença usando um ID e segredo
  aleatórios próprios e o identificador estável da instalação Windows. A
  primeira conta da instalação recebe 30 dias; novas contas começam suspensas
  até o desenvolvedor liberar o teste ou o pagamento. A central limita a três
  novas instalações em teste por IP a cada 30 dias; guarda apenas um hash
  pseudônimo do endereço, nunca o IP em texto.
- `GET /v1/admin/verify`: valida a credencial administrativa sem devolver
  dados de clientes; exige o mesmo `Bearer` privado.
- `GET /v1/admin/licenses`: lista as contas; exige `Bearer` com o token admin.
- `POST /v1/admin/licenses/{id}`: ação `paid`, `trial_30_days` ou `suspend`;
  exige o token admin. `paid` libera permanentemente até uma suspensão manual.
- `GET /health`: prontidão do serviço e do banco.

O tráfego público deve usar HTTPS. A API guarda hash SHA-256 do segredo de cada
conta, nunca o segredo em texto puro. A chave administrativa é comparada sem
comparação de prefixo e não é devolvida nas respostas. O dono da máquina do
cliente controla o software local, então nenhuma barreira comercial embarcada
no aplicativo impede adulteração deliberada do executável ou do relógio.

O identificador de conta é criado no SQLite. O serviço central vincula cada
licença à instalação Windows e conserva o direito ao primeiro teste em uma
tabela própria: apagar ou recriar o banco local não reinicia os 30 dias. Copiar
um banco licenciado para outro computador não transfere a licença; a troca de
computador exige atendimento manual do fornecedor. Mantenha backups do servidor
e do banco local conforme a política de suporte da empresa.

O cliente espera até 90 segundos pela sincronização para acomodar a inicialização
de instâncias Render gratuitas. A primeira validação exige internet; somente
uma licença já validada pode usar a janela offline de até 72 horas.
