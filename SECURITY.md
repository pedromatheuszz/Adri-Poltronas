# Segurança

## Como relatar uma vulnerabilidade

**Não abra uma issue pública.** Uma issue neste repositório é visível para
qualquer pessoa, e uma falha descrita ali fica disponível antes de existir
correção.

Use um destes canais:

1. **Preferido** — [Security Advisories](https://github.com/pedromatheuszz/Adri-Poltronas/security/advisories/new),
   na aba *Security* do repositório. O relato fica privado até a publicação.
2. E-mail para o mantenedor, listado no perfil do GitHub.

Inclua, na medida do possível: a versão afetada, o passo a passo para
reproduzir, o impacto que você enxerga e qualquer prova de conceito.

**Resposta em até 7 dias.** Este é um projeto de um mantenedor só — o prazo é
o que dá para sustentar honestamente, não o de uma equipe dedicada.

## O que está no escopo

| | |
|---|---|
| ✅ | O backend Flask (`backend/`) e as APIs que ele expõe |
| ✅ | O processo principal do Electron (`electron/`) e a configuração da janela |
| ✅ | O tratamento de credenciais: Microsoft, Gemini, Mercado Pago |
| ✅ | O banco local e os backups |
| ✅ | A cadeia de build e o instalador |
| ❌ | O aplicativo `.NET/Avalonia` (`dotnet/`) — exploração arquitetural, não distribuída |
| ❌ | A janela Qt (`qt-app/`) — interface alternativa, não distribuída |
| ❌ | Serviços de terceiros (Microsoft Graph, ViaCEP, Nominatim, Mercado Pago) — relate a eles |

## Versões suportadas

| Versão | Situação |
|---|---|
| 1.5.x | Suportada |
| < 1.5 | Sem suporte |

## O modelo de ameaça, e seus limites

Ser franco sobre o que o produto **não** protege vale mais do que uma lista de
boas intenções. O Adri Poltronas é um aplicativo desktop de um único
computador, e isso define o que é defensável:

### O que é tratado

- **A API local não responde a estranhos.** O backend escuta em
  `127.0.0.1:5000`, e loopback não é privado: qualquer processo da máquina e
  qualquer página aberta no navegador do usuário alcançam essa porta. Toda
  requisição precisa apresentar um segredo que só o aplicativo conhece
  (`backend/capacidade.py`).
- **DNS rebinding.** O nome do host é validado contra a lista de apelidos de
  loopback, em vez de ser inferido do próprio cabeçalho `Host`.
- **Login e autorização locais.** A API de negócio exige cookie de sessão
  `HttpOnly` e conta ativa. Senhas locais são armazenadas como hashes bcrypt;
  novas contas exigem ao menos 12 caracteres. O perfil é conferido no servidor:
  só o desenvolvedor pode administrar contas e períodos de teste.
- **Tokens da Microsoft cifrados em repouso**, com DPAPI no Windows.
- **Trilha de auditoria append-only**, protegida por gatilhos no banco, com
  valores sensíveis removidos.
- **Janela isolada**: `contextIsolation`, sandbox, sem integração com Node,
  navegação externa bloqueada.
- **Rotas externas limitadas.** Desde a 1.5.0 não há webhook: a verificação
  do pagamento da licença é feita perguntando ao Mercado Pago, de dentro para
  fora. `/callback` recebe o retorno OAuth e `/api/health` identifica o
  backend; nenhuma delas devolve dados de negócio. Ambas continuam restritas
  ao host de loopback.
- **Segredos fora do repositório e cifrados em repouso**: o `MP_ACCESS_TOKEN`
  e a `GEMINI_API_KEY` vivem em `%APPDATA%\AdriPoltronas\.segredos`,
  protegidos por DPAPI. Uma chave em texto no `.env` é migrada automaticamente
  na próxima abertura, e a cópia em texto claro é descartada depois que o cofre
  é relido e conferido.
- **Allowlist Microsoft, quando configurada.** `ADRI_CONTAS_AUTORIZADAS`
  restringe quais contas Microsoft podem vincular o OneDrive. Isso não cria
  login local nem concede perfil no ERP.

### O que **não** é tratado — e por quê

- **Outro processo rodando como o mesmo usuário.** Ele já pode abrir o banco
  SQLite diretamente, ler o `.env` e o arquivo de capacidade. Nenhum controle
  dentro do aplicativo muda isso; quem defende essa fronteira é o sistema
  operacional.
- **As chaves cifradas não resistem a código rodando como você.** O DPAPI
  protege contra outra conta do Windows e contra o arquivo sair da máquina;
  um processo executando com a sua identidade pode simplesmente pedir que ele
  decifre. É a mesma fronteira do arquivo de capacidade.
- **Banco e backups não são cifrados em repouso.** O arquivo contém nome,
  endereço e CEP de clientes reais. Um disco sem BitLocker, roubado, entrega
  tudo. Cifrar exigiria SQLCipher e uma chave que o usuário teria de digitar a
  cada abertura — uma decisão de produto que ainda não foi tomada.
- **O limite de confiança é o usuário do Windows.** As permissões locais
  impedem que uma conta comum use a área de desenvolvedor pela API do
  aplicativo, mas não protegem os arquivos contra outro processo executado
  pela mesma conta do Windows. Uma pessoa com essa identidade pode ler ou
  alterar o banco diretamente.

- **A licença central é uma barreira comercial, não inviolável.** O servidor
  central guarda os estados de teste/pagamento e o ERP consulta a API por HTTPS.
  O estado local dá até 72 horas de operação offline após validação. O dono do
  computador ainda controla o executável local e pode adulterá-lo; não se deve
  prometer proteção contra engenharia reversa.
- **O token administrativo da licença não vai aos clientes.** Só o backend da
  máquina do vendedor deve receber `ADRI_LICENCA_ADMIN_TOKEN`. Os clientes
  autenticam sua própria consulta com um segredo aleatório por conta, cujo hash
  fica no serviço central.
- **O aplicativo não é assinado digitalmente.** O Windows exibe o aviso do
  SmartScreen na instalação.
- **Vários computadores compartilhando a mesma base** não são suportados. O
  SQLite em pasta de rede corrompe.

### Contas e perfis

- Na primeira execução, o operador cria a conta de desenvolvedor. Não existe
  senha padrão ou credencial de desenvolvedor embutida no código.
- Usuários podem criar a própria conta; o cadastro público só aceita o perfil
  comum. Administrador e desenvolvedor são criados ou gerenciados pelo
  desenvolvedor.
- Usuário e administrador acessam as áreas comuns. A área de desenvolvedor e
  o controle de contas/períodos de teste são exclusivos do perfil
  desenvolvedor, com checagem repetida no backend.
- A conexão Microsoft é opcional e serve à integração com o OneDrive. Ela não
  substitui o login local nem altera o perfil local.

## Se você encontrou um segredo neste repositório

O `gitleaks` roda em cada push, mas nenhuma varredura é perfeita. Se você achar
uma chave em algum commit, relate pelo canal privado acima **e considere-a
comprometida**: um segredo que entrou no histórico do Git continua acessível
mesmo depois de removido do último commit. A correção é rotacionar a chave, não
apagar o arquivo.
