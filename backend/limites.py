"""
Limites de requisicao por rota.

Por que este modulo existe separado de `app.py`
-----------------------------------------------
O limitador nascia dentro de `app.py`, e `app.py` importa os blueprints no
final do arquivo. Um blueprint que quisesse limitar uma rota propria teria de
fazer `from app import limiter` -- import circular que so funciona por acidente
da ordem das linhas. Com o objeto aqui, quem precisa dele importa este modulo,
e `app.py` faz o `init_app`.

O que o limite defende, e o que nao defende
-------------------------------------------
Nao ha atacante remoto de quem se defender: `_exigir_host_de_loopback` ja
recusa qualquer requisicao que nao venha de 127.0.0.1, e a capacidade recusa
quem nao apresenta o token. Todo o trafego legitimo vem de um IP so -- o
proprio aplicativo. Na pratica, portanto, o limite se aplica ao app.

Ate a 1.3.0 o teto era `200 por minuto` e `50 por segundo`. Numa rajada de 250
GET sequenciais, 124 receberam 429: uma sincronizacao da fila offline com
muitas operacoes acumuladas, ou uma importacao seguida de recarga da lista,
batia no teto e o operador via falhas sem causa aparente.

O teto padrao agora existe contra loop acidental -- um `setInterval` de 50 ms
que ninguem parou --, e nao contra ataque. Quem precisa de limite apertado sao
as rotas que gastam cota de TERCEIRO: cada chamada delas custa dinheiro ou
credito fora daqui, e nenhuma e disparada em rajada pelo uso normal.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Alto de proposito: barra o loop acidental sem atrapalhar rajada legitima.
LIMITE_PADRAO = "2000 per minute"

# Gemini: cota diaria de terceiro, e a sugestao de bairro e disparada por
# digitacao no formulario.
LIMITE_IA = "20 per minute"

# Cada chamada pode criar uma cobranca real no Asaas. A idempotencia ja impede
# cobranca duplicada; isto impede a rajada que a exercitaria.
LIMITE_EMISSAO_DE_COBRANCA = "20 per minute"

# Roda sozinha a cada 20 minutos desde a 1.3.1, e uma rodada consulta N
# cobrancas em aberto. Clique manual acima disso e dedo nervoso, nao trabalho.
LIMITE_CONCILIACAO = "10 per minute"

# Upload ao OneDrive: cota do Microsoft Graph, e o arquivo e grande.
LIMITE_ONEDRIVE = "10 per minute"

limiter = Limiter(
    get_remote_address,
    default_limits=[LIMITE_PADRAO],
    storage_uri="memory://",
)
