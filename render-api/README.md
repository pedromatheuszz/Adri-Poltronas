# Render API wrapper

Este serviço administrativo é separado da API de licenças (`licensing-service`).
Ele consulta e inicia deploys na conta Render; por isso exige uma chave Render
e um segredo JWT fortes, configurados como variáveis privadas do serviço.

No desenvolvimento dentro deste repositório, o wrapper lê a chave canônica
`KEY_RENDER` do `.env` na raiz. Assim, não mantenha uma segunda cópia da chave
em `render-api/.env`. Esse arquivo local contém o `JWT_SECRET` do wrapper.
Para um deploy independente, configure `RENDER_API_KEY` e `JWT_SECRET` como
variáveis privadas do serviço. Não publique `.env`, tokens JWT ou chaves Render.
A aplicação se recusa a iniciar se não encontrar uma chave Render válida em
`KEY_RENDER` ou `RENDER_API_KEY`, ou se o segredo JWT tiver menos de 32 caracteres.

Os endpoints `/services`, `/deploy` e `/deploys/{id}` aceitam apenas JWTs
assinados para o emissor e audiência deste serviço, com `role=admin` e validade
máxima de 60 minutos. Não use um JWT genérico nem exponha o wrapper sem HTTPS.

Para instalar e iniciar, use o diretório `render-api` como raiz do serviço,
instale `requirements.txt` e execute `uvicorn app:app --host 0.0.0.0 --port
$PORT`. A chave Render deve ter somente as permissões que o wrapper precisa.
