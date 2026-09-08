# Bibliotecas de terceiros

Estes arquivos **não são do projeto**. São cópias literais de bibliotecas de
código aberto, servidas pelo próprio backend em vez de virem de um CDN.

## Por que estão aqui

Até a 1.5.0 o `index.html` carregava as duas de `unpkg.com` e
`cdn.jsdelivr.net`, com SRI e versão fixada — o que é a forma correta de usar um
CDN. O problema não era esse: é que **isto é um aplicativo desktop**. Depender
de rede em tempo de execução significava três coisas ruins:

1. o mapa e os gráficos não desenhavam na primeira abertura sem internet — e o
   Service Worker só ajuda a partir da segunda;
2. dois domínios de terceiro entravam na superfície de disponibilidade de um
   programa que roda inteiramente na máquina do cliente;
3. a CSP precisava autorizar `unpkg.com` e `cdn.jsdelivr.net` em `script-src`,
   ou seja, dois terceiros com permissão para executar código dentro de um app
   que trata nome, endereço e valores a receber dos clientes.

Com os arquivos locais, a CSP voltou a ser `script-src 'self'`.

## O que está aqui

| Pasta | Biblioteca | Versão | Licença |
|---|---|---|---|
| `leaflet/` | [Leaflet](https://leafletjs.com/) | 1.9.4 | BSD-2-Clause |
| `chartjs/` | [Chart.js](https://www.chartjs.org/) | 4.4.0 | MIT |

As duas licenças permitem redistribuição, inclusive em produto fechado, desde
que o aviso de copyright seja preservado — e ele está preservado: os cabeçalhos
originais continuam dentro dos próprios arquivos, que não foram editados.

`leaflet/images/` contém os PNGs de marcador e sombra que o `leaflet.css`
referencia por caminho relativo. Sem eles o mapa desenha sem os pinos.

## Procedência

Baixados das mesmas URLs fixadas que o `index.html` já usava, e conferidos
byte a byte contra os hashes SRI que estavam commitados no próprio HTML:

```
leaflet.css        sha384-sHL9NAb7lN7rfvG5lfHpm643Xkcjzp4jFvuavGOndn6pjVqS6ny56CAt3nsEVT4H
leaflet.js         sha384-cxOPjt7s7Iz04uaHJceBmS+qpjv2JkIHNVcuOrM+YHwZOmJGBXI00mdUXEq65HTH
chart.umd.min.js   sha384-e6nUZLBkQ86NJ6TVVKAeSaK8jWa3NhkYWZFomE39AvDbQWeie9PlQqM3pmYW5d1g
```

## Como atualizar

Não edite nada aqui à mão. Para subir de versão:

1. baixe da mesma origem, na versão nova;
2. confira o SRI publicado pelo distribuidor antes de commitar;
3. atualize a tabela acima e os hashes desta seção;
4. incremente `CACHE_NAME` em `frontend/sw.js` — senão a máquina do cliente
   continua servindo a versão anterior do cache;
5. rode `tests/test_contrato_da_interface.py`, que falha se alguma referência
   a CDN voltar ao HTML.

Estes arquivos **não** são cobertos pelo `npm audit` da CI, porque não passam
pelo `package.json`. É o preço de não ter etapa de build no frontend. Quem
atualizar precisa checar o aviso de segurança do projeto na mão.
