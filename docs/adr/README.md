# Registros de decisão de arquitetura (ADR)

Uma decisão de arquitetura é aquela cara de reverter. Este diretório guarda as
que foram tomadas, o que se sabia na hora e o que foi descartado junto.

O valor não está na decisão — essa já está no código. Está no **contexto e nas
alternativas**: daqui a um ano, quem encontrar `adri_poltronas_dotnet.db` e
achar estranho vai querer saber se aquilo foi pensado ou aconteceu por acaso.
Sem o registro, a resposta honesta é "ninguém lembra", e a tendência é desfazer
a decisão sem saber o que ela evitava.

## Índice

| # | Decisão | Status |
|---|---|---|
| [0001](0001-dono-do-banco-e-o-backend-python.md) | O dono do banco é o backend Python | aceito |

## Quando escrever um

Quando a resposta a "por que assim?" não estiver no diff. Em geral:

- escolher entre duas arquiteturas possíveis;
- aceitar um custo permanente em troca de outra coisa;
- decidir **não** fazer algo que parece óbvio;
- reverter uma decisão anterior — nesse caso o ADR novo referencia o antigo,
  que passa a "substituído" em vez de sumir.

Correção de defeito, refatoração e ajuste de interface não viram ADR. A
mensagem de commit já é o lugar disso.

## Formato

Status, data, contexto (o problema, com evidência), decisão, alternativas
consideradas **e por que foram descartadas**, consequências — as boas e as
ruins — e como reverter.

A seção de alternativas é a que costuma faltar e a que mais se lê depois.
