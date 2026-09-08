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
- **Tokens da Microsoft cifrados em repouso**, com DPAPI no Windows.
- **Trilha de auditoria append-only**, protegida por gatilhos no banco, com
  valores sensíveis removidos.
- **Janela isolada**: `contextIsolation`, sandbox, sem integração com Node,
  navegação externa bloqueada.
- **Nenhuma rota chega de fora.** Desde a 1.5.0 não há webhook: a
  verificação do pagamento da licença é feita perguntando ao Mercado Pago, de
  dentro para fora. O conjunto de rotas isentas das regras de tráfego local
  está vazio.
- **Segredos fora do repositório e cifrados em repouso**: o `MP_ACCESS_TOKEN`
  e a `GEMINI_API_KEY` vivem em `%APPDATA%\AdriPoltronas\.segredos`,
  protegidos por DPAPI. Uma chave em texto no `.env` é migrada automaticamente
  na próxima abertura, e a cópia em texto claro é descartada depois que o cofre
  é relido e conferido.
- **Allowlist de contas, quando configurada.** `ADRI_CONTAS_AUTORIZADAS`
  restringe quais contas Microsoft destravam a base. Vazia, qualquer conta
  entra — ver a limitação correspondente abaixo.

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
- **Não há papéis nem permissões.** Quem abre o aplicativo pode tudo:
  faturar, restaurar backup e baixar o banco completo exigem exatamente a
  mesma permissão que listar clientes. A autenticação é o OAuth da Microsoft,
  que serve à integração com o OneDrive e foi reaproveitada como identidade.
  Desde a 1.5.1 é possível restringir *quais* contas entram
  (`ADRI_CONTAS_AUTORIZADAS`), o que fecha o caso do colaborador que conecta a
  conta pessoal — mas continua sendo um único nível de privilégio. Identidade
  local própria e separação por papéis seguem na lista de correções.

- **O controle de licença é local, e um controle local é contornável.** O
  estado vive em arquivo cifrado por DPAPI e na tabela `licenca`, reconciliados
  sempre pelo lado mais restritivo, com marca-d'água monotônica contra recuo do
  relógio. Isso resiste a acidente e a tentativa casual, não a alguém decidido
  a editar o próprio banco.
- **O aplicativo não é assinado digitalmente.** O Windows exibe o aviso do
  SmartScreen na instalação.
- **Vários computadores compartilhando a mesma base** não são suportados. O
  SQLite em pasta de rede corrompe.

## Se você encontrou um segredo neste repositório

O `gitleaks` roda em cada push, mas nenhuma varredura é perfeita. Se você achar
uma chave em algum commit, relate pelo canal privado acima **e considere-a
comprometida**: um segredo que entrou no histórico do Git continua acessível
mesmo depois de removido do último commit. A correção é rotacionar a chave, não
apagar o arquivo.
