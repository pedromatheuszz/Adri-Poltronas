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
| ✅ | O tratamento de credenciais: Asaas, Microsoft, Gemini |
| ✅ | O banco local e os backups |
| ✅ | A cadeia de build e o instalador |
| ❌ | O aplicativo `.NET/Avalonia` (`dotnet/`) — exploração arquitetural, não distribuída |
| ❌ | A janela Qt (`qt-app/`) — interface alternativa, não distribuída |
| ❌ | Serviços de terceiros (Asaas, Microsoft Graph, ViaCEP, Nominatim) — relate a eles |

## Versões suportadas

| Versão | Situação |
|---|---|
| 1.1.x | Suportada |
| < 1.1 | Sem suporte |

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
- **Webhook do Asaas fail closed**: sem token configurado, ele recusa tudo.
- **Segredos fora do repositório e cifrados em repouso**: as chaves do Asaas
  e do Gemini vivem em `%APPDATA%\AdriPoltronas\.segredos`, protegidas por
  DPAPI. Uma chave em texto no `.env` é migrada automaticamente na próxima
  abertura.

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
- **Não há usuários nem permissões.** Quem abre o aplicativo pode tudo. A
  autenticação existente é o OAuth da Microsoft, que serve à integração com o
  OneDrive e foi indevidamente reaproveitada como identidade — está na lista
  de correções.
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
