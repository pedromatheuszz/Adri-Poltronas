// =============================================================================
// Adri Poltronas - Service Worker (PWA Offline)
// =============================================================================

// IMPORTANTE: incremente CACHE_NAME sempre que o HTML, o CSS ou o JS mudarem.
// O handler de `activate` apaga todo cache cujo nome nao esteja nesta lista, e
// e isso que expurga a versao anterior da maquina do usuario.
const CACHE_NAME = 'adri-poltronas-v8';

// Assets proprios: precache obrigatorio. Sao servidos pelo backend local,
// entao addAll() so falha aqui se algo estiver de fato errado no bundle.
const PRECACHE_ASSETS = [
  '/',
  '/css/tokens.css',
  '/css/style.css',
  '/js/app.js',
  '/js/offline.js',
  '/manifest.json'
];

// Bibliotecas de CDN: precache pelo melhor esforco, FORA do addAll().
//
// cache.addAll() e atomico -- uma URL que falha rejeita a promise inteira e
// derruba o install. Com as URLs de CDN na lista obrigatoria, abrir o app uma
// primeira vez sem internet deixava o PWA sem nenhum asset cacheado, inclusive
// os locais. Aqui cada uma e tentada isoladamente e a falha e tolerada.
//
// Estas entradas servem apenas ao modo offline: como o handler de fetch nao
// intercepta outra origem, elas nao sao lidas no fluxo normal.
const PRECACHE_EXTERNOS = [
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js',
  'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js'
];


async function precachearExternos(cache) {
  await Promise.allSettled(
    PRECACHE_EXTERNOS.map(function(url) {
      return fetch(url, { mode: 'cors' })
        .then(function(resposta) {
          if (resposta.ok) return cache.put(url, resposta);
        })
        .catch(function() {
          console.warn('[SW] Precache externo indisponivel:', url);
        })
    })
  );
}

// =============================================================================
// Install - Precache de assets estáticos
// =============================================================================
self.addEventListener('install', function(event) {
  console.log('[SW] Instalando...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(async function(cache) {
        console.log('[SW] Precaching assets');
        await cache.addAll(PRECACHE_ASSETS);
        await precachearExternos(cache);
      })
      .then(function() {
        return self.skipWaiting();
      })
  );
});

// =============================================================================
// Activate - Limpeza de caches antigos
// =============================================================================
self.addEventListener('activate', function(event) {
  console.log('[SW] Ativando...');
  event.waitUntil(
    caches.keys()
      .then(function(cacheNames) {
        return Promise.all(
          cacheNames
            .filter(function(name) {
              // Nao esta na lista -> vai embora. E isso que remove o
              // 'adri-api-v1' das maquinas que ja rodaram a versao anterior.
              return name !== CACHE_NAME;
            })
            .map(function(name) {
              console.log('[SW] Removendo cache antigo:', name);
              return caches.delete(name);
            })
        );
      })
      .then(function() {
        return self.clients.claim();
      })
  );
});

// =============================================================================
// Fetch - Estratégias de cache
// =============================================================================
self.addEventListener('fetch', function(event) {
  const url = new URL(event.request.url);

  // Ignorar requisições não-GET
  if (event.request.method !== 'GET') return;

  // Requisicoes de OUTRA ORIGEM passam direto, sem interceptacao.
  //
  // Os tiles do OpenStreetMap e os icones do Leaflet caiam aqui e eram
  // reemitidos por `fetch()` dentro do worker. No WebView2 que embalava o app
  // ate a migracao para o Electron, esse `fetch()` falhava para tais hosts: a
  // estrategia caia no catch e resolvia para `undefined`, e
  // `respondWith(undefined)` vira erro de rede -- mapa cinza e marcadores
  // quebrados, sem nenhuma violacao de CSP para dar pista.
  //
  // O motor mudou, mas a regra fica: nao interceptar devolve essas requisicoes
  // ao carregamento nativo do navegador, e cachear recurso de terceiro nunca
  // trouxe beneficio -- sao respostas opacas, que `cache.put` recusa.
  if (url.origin !== self.location.origin) return;

  // Respostas de API NAO sao cacheadas.
  //
  // O Cache Storage vive em disco e sem cifragem. Cachear tudo sob /api/
  // gravava ali /api/clientes (nome, CEP e endereco de todos os clientes),
  // /api/pagamentos e ate /api/clientes/backup/sqlite -- o banco inteiro --
  // sem nunca expirar. O que o app precisa offline (a lista de clientes) ja
  // vive no IndexedDB, gerenciado pelo OfflineManager, entao o cache de API
  // custava privacidade sem entregar nada em troca.
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(apenasRede(event.request));
    return;
  }

  // O documento HTML vai por Network First, e nao por Stale-While-Revalidate.
  //
  // O SWR devolve a copia em cache primeiro e so revalida depois: o usuario
  // ficava permanentemente uma versao atras, vendo markup antigo mesmo com o
  // servidor ja respondendo o novo. Como o HTML e servido de '/' (sem hash nem
  // query de versao), nao havia nada que invalidasse a entrada.
  // Offline continua funcionando pelo fallback de cache.
  if (event.request.mode === 'navigate' ||
      (event.request.destination === 'document') ||
      (event.request.headers.get('accept') || '').includes('text/html')) {
    event.respondWith(
      networkFirstDocument(event.request, CACHE_NAME)
    );
    return;
  }

  // Para assets estáticos: Stale-While-Revalidate
  event.respondWith(
    staleWhileRevalidate(event.request, CACHE_NAME)
  );
});

// =============================================================================
// Estratégia Network First (para o documento HTML)
// =============================================================================
async function networkFirstDocument(request, cacheName) {
  try {
    const networkResponse = await fetch(request);
    if (networkResponse.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  } catch (error) {
    // Offline: serve a ultima versao boa. Cai para '/' porque a navegacao pode
    // ter vindo de uma URL que nunca foi cacheada.
    const cachedResponse = await caches.match(request) || await caches.match('/');
    if (cachedResponse) {
      return cachedResponse;
    }
    // Sem cache algum: devolve HTML, nunca JSON (isso quebraria a pagina).
    return new Response(
      '<!doctype html><meta charset="utf-8">' +
      '<title>Adri Poltronas - Offline</title>' +
      '<body style="font-family:sans-serif;background:#0f172a;color:#f8fafc;' +
      'display:flex;align-items:center;justify-content:center;height:100vh;margin:0">' +
      '<div style="text-align:center"><h2>Voce esta offline</h2>' +
      '<p>Reabra o aplicativo quando a conexao voltar.</p></div>',
      { headers: { 'Content-Type': 'text/html; charset=utf-8' }, status: 503 }
    );
  }
}

// =============================================================================
// Somente rede (para APIs)
//
// Sem leitura nem escrita no Cache Storage. Quando a rede falha, devolve um
// envelope offline que o app ja sabe interpretar.
// =============================================================================
async function apenasRede(request) {
  try {
    return await fetch(request);
  } catch (error) {
    // Status 503 e o header, e nao 200.
    //
    // Com 200 o `fetch` do app RESOLVIA com sucesso, entao `tentarBackend`
    // nunca marcava `semBackend` e o caminho de cache offline jamais rodava:
    // `carregarClientes` seguia adiante, tentava filtrar um objeto como se
    // fosse lista e estourava. Resultado visivel: tabela vazia com "Erro ao
    // carregar clientes" -- enquanto os dados estavam intactos no IndexedDB.
    //
    // O header e o sinal explicito: distingue "a rede caiu aqui no worker"
    // de um 503 legitimo vindo do backend.
    return new Response(
      JSON.stringify({
        offline: true,
        mensagem: 'Voce esta offline. Os dados podem nao estar atualizados.',
        dados: []
      }),
      {
        headers: {
          'Content-Type': 'application/json',
          'X-Adri-Offline': '1'
        },
        status: 503
      }
    );
  }
}

// =============================================================================
// Estratégia Stale-While-Revalidate (para assets)
// =============================================================================
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);

  // Fetch em background para atualizar cache
  const fetchPromise = fetch(request)
    .then(function(networkResponse) {
      if (networkResponse.ok) {
        cache.put(request, networkResponse.clone());
      }
      return networkResponse;
    })
    .catch(function(erro) {
      // Havendo copia em cache, ela serve. Sem ela, o erro PRECISA subir:
      // devolver `cachedResponse` (que aqui e `undefined`) fazia
      // respondWith() abortar a requisicao de forma opaca, sem erro
      // legivel no console -- exatamente o que escondia a falha do mapa.
      if (cachedResponse) return cachedResponse;
      throw erro;
    });

  // Retorna cache imediatamente se disponível, senão espera network
  return cachedResponse || fetchPromise;
}

// =============================================================================
// Push Notifications (futuro)
// =============================================================================
self.addEventListener('push', function(event) {
  if (event.data) {
    const data = event.data.json();
    event.waitUntil(
      self.registration.showNotification(data.titulo || 'Adri Poltronas', {
        body: data.mensagem || 'Nova notificacao',
        icon: '/Design-sem-nome-8-1024x1024.png',
        badge: '/Design-sem-nome-8-1024x1024.png',
        vibrate: [200, 100, 200]
      })
    );
  }
});

self.addEventListener('notificationclick', function(event) {
  event.notification.close();
  event.waitUntil(
    self.clients.openWindow('/')
  );
});
