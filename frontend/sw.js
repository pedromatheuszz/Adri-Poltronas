// =============================================================================
// Adri Poltronas - Service Worker (PWA Offline)
// =============================================================================

const CACHE_NAME = 'adri-poltronas-v1';
const CACHE_API = 'adri-api-v1';

// Assets estáticos para cache imediato durante install
const PRECACHE_ASSETS = [
  '/',
  '/css/style.css',
  '/js/app.js',
  '/js/offline.js',
  '/manifest.json',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css',
  'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'
];

// =============================================================================
// Install - Precache de assets estáticos
// =============================================================================
self.addEventListener('install', function(event) {
  console.log('[SW] Instalando...');
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(function(cache) {
        console.log('[SW] Precaching assets');
        return cache.addAll(PRECACHE_ASSETS);
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
              return name !== CACHE_NAME && name !== CACHE_API;
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

  // Estratégia para APIs: Network First com fallback para cache
  if (url.pathname.startsWith('/api/')) {
    // Não cachear chamadas de login/auth
    if (url.pathname.includes('/api/auth/')) return;

    event.respondWith(
      networkFirstStrategy(event.request, CACHE_API)
    );
    return;
  }

  // Para assets estáticos: Stale-While-Revalidate
  event.respondWith(
    staleWhileRevalidate(event.request, CACHE_NAME)
  );
});

// =============================================================================
// Estratégia Network First (para APIs)
// =============================================================================
async function networkFirstStrategy(request, cacheName) {
  try {
    const networkResponse = await fetch(request);

    // Se sucesso, cachear a resposta
    if (networkResponse.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
    }

    return networkResponse;
  } catch (error) {
    // Se falhar, tentar cache
    const cachedResponse = await caches.match(request);
    if (cachedResponse) {
      return cachedResponse;
    }

    // Se não tem cache, retornar resposta offline para APIs
    return new Response(
      JSON.stringify({
        offline: true,
        mensagem: 'Voce esta offline. Os dados podem nao estar atualizados.',
        dados: []
      }),
      {
        headers: { 'Content-Type': 'application/json' },
        status: 200
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
    .catch(function() {
      // Se falhar e não tem cache, retorna null
      return cachedResponse;
    });

  // Retorna cache imediatamente se disponível, senão espera network
  return cachedResponse || fetchPromise;
}

// =============================================================================
// Push Notifications (futuro)
// =============================================================================

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
