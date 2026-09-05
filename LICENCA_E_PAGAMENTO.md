# Licença de uso e pagamento

Como funciona o período de teste, como o pagamento é confirmado, e o que
precisa ser configurado antes de entregar o aplicativo a um cliente.

---

## O que o cliente vê

**Nos primeiros 30 dias**, o sistema funciona por inteiro. A topbar mostra
`Periodo de teste: N dias restantes`, discreto — e com destaque na última
semana.

**Depois dos 30 dias**, a tela é substituída por um painel com o valor
(R$ 1.500,00) e o botão *Pagar com Pix*. Nenhum dado aparece: os números do
Dashboard sem dados carregados são os zeros escritos no HTML, e mostrá-los
seria informar errado com ar de informação certa.

**Ao clicar em Pagar**, o app gera uma cobrança Pix no Mercado Pago e mostra o
QR Code e o copia-e-cola. A cada 5 segundos ele pergunta ao Mercado Pago se o
pagamento entrou. Assim que entra, o painel some sozinho e os dados carregam —
sem reabrir o app, sem digitar código nenhum.

Se o app for fechado com o Pix na tela, a cobrança fica lembrada: a próxima
abertura retoma a espera sem pedir para gerar outra.

---

## O que você precisa configurar

O aplicativo só consegue cobrar se souber falar com a **sua** conta do Mercado
Pago. Uma variável, guardada cifrada:

| Nome | O que é |
|---|---|
| `MP_ACCESS_TOKEN` | O **Access Token** da sua aplicação no Mercado Pago. |

Não é a *Public Key* — essa serve para tokenizar cartão no navegador. Criar
cobrança e consultar status são operações de servidor, e ambas usam o Access
Token.

### Como gravar, sem o token passar por lugar nenhum

Na máquina onde o app vai rodar:

```bash
python -c "import sys,getpass; sys.path.insert(0,'backend'); import segredos; print('gravado:', segredos.gravar({'MP_ACCESS_TOKEN': getpass.getpass('Token MP: ')}))"
```

O comando pede o token sem exibir na tela, cifra com DPAPI e grava em
`%APPDATA%\AdriPoltronas\.segredos`. Nunca cole um Access Token em chat, em
commit ou em arquivo de texto.

### Testar sem mover dinheiro

Use o Access Token de **Credenciais de teste** (aba *Testes* no painel do
Mercado Pago). Ele exercita a API inteira e nenhum centavo se move.

> Atenção: desde 2024 o token de teste **também** começa com `APP_USR-`. O
> prefixo não distingue mais os dois ambientes — o que distingue é de qual aba
> do painel ele veio.

### Sem configurar

O app não quebra: o botão de pagar responde
*"Pagamento indisponível: o Mercado Pago não está configurado nesta
instalação."* O bloqueio continua valendo — só não há como pagar por dentro do
aplicativo.

---

## Onde o estado da licença mora

Em **dois lugares**, e a reconciliação pega sempre o lado mais restritivo:

| Lugar | Sobrevive a |
|---|---|
| `%APPDATA%\AdriPoltronas\.licenca`, cifrado com DPAPI | restaurar um backup antigo do banco |
| Tabela `licenca` no SQLite | apagar o arquivo do perfil |

A instalação mais **antiga** dos dois vale; a marca d'água mais **nova** vale;
e se qualquer um dos dois disser "paga", está paga.

**O relógio.** Atrasar o relógio do Windows congela a contagem em vez de
revertê-la: `visto_em` guarda a data mais adiantada já observada e nunca
retrocede.

---

## O que este controle não faz

O aplicativo roda inteiro na máquina do cliente — backend, banco e interface.
Quem tem administrador ali contorna qualquer bloqueio escrito no código. **Não
existe forma honesta de impedir isso sem um servidor do vendedor no meio**, e
este projeto não tem um.

O que o desenho alcança é outra coisa, e essa sim é alcançável: tornar o
contorno **deliberado**. Ninguém perde o acesso por engano, ninguém estende o
prazo sem perceber que está fazendo isso, e o caminho honesto — pagar — é o
mais fácil de todos.

**O token na máquina do cliente** é o outro limite. A verificação automática
exige o Access Token da sua conta, e ele dá acesso total a ela. Cifrado com
DPAPI, fica preso àquela conta do Windows e não pode ser copiado para outra
máquina; não fica protegido de quem tem administrador ali.

A forma correta de fechar isso é um endpoint seu que responda apenas *"esta
licença está paga?"*. O app perguntaria a ele em vez de ao Mercado Pago, e
nenhuma credencial sua sairia da sua casa. Enquanto esse endpoint não existe,
a recomendação prática é **usar um token de aplicação dedicada à licença**, e
não o token principal da conta — assim, se ele vazar, o estrago fica contido e
a revogação não derruba mais nada.

---

## Mudando o preço

Um lugar só: `VALOR_DA_LICENCA_CENTAVOS`, em `backend/licenca.py`. Em centavos,
mesma convenção do resto do financeiro (`erp/core/dinheiro.py`). R$ 1.500,00 é
`150000`.

O prazo do teste fica ao lado, em `DIAS_DE_TESTE`.
