// =============================================================================
// Adri Poltronas - Offline Module (IndexedDB + Sync)
// =============================================================================

var OfflineManager = (function() {
  'use strict';

  var DB_NAME = 'AdriPoltronasOffline';
  var DB_VERSION = 1;
  var db = null;
  var dbReady = null; // Promise que resolve quando DB está pronto
  var isOnline = navigator.onLine;

  // ===========================================================================
  // Inicialização
  // ===========================================================================
  function init() {
    console.log('[Offline] Inicializando...');
    dbReady = openDatabase();
    setupEventListeners();
    updateOnlineStatus();
    registerServiceWorker();
  }

  // Aguardar DB estar pronto
  async function aguardarDB() {
    if (dbReady) await dbReady;
    return db;
  }

  // ===========================================================================
  // IndexedDB
  // ===========================================================================
  function openDatabase() {
    return new Promise(function(resolve, reject) {
      var request = indexedDB.open(DB_NAME, DB_VERSION);

      request.onupgradeneeded = function(event) {
        var database = event.target.result;

        // Store para operações pendentes de sincronização
        if (!database.objectStoreNames.contains('pending-sync')) {
          var store = database.createObjectStore('pending-sync', {
            keyPath: 'id',
            autoIncrement: true
          });
          store.createIndex('action', 'action', { unique: false });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }

        // Store para cache de clientes
        if (!database.objectStoreNames.contains('cached-clients')) {
          database.createObjectStore('cached-clients', { keyPath: 'id' });
        }

        // Store para cache de configurações
        if (!database.objectStoreNames.contains('app-cache')) {
          database.createObjectStore('app-cache', { keyPath: 'key' });
        }
      };

      request.onsuccess = function(event) {
        db = event.target.result;
        console.log('[Offline] IndexedDB aberto com sucesso');
        resolve(db);
      };

      request.onerror = function(event) {
        console.error('[Offline] Erro ao abrir IndexedDB:', event.target.error);
        reject(event.target.error);
      };
    });
  }

  // ===========================================================================
  // Salvar operação pendente
  // ===========================================================================
  async function savePendingAction(action, dados) {
    await aguardarDB();
    return new Promise(function(resolve, reject) {
      if (!db) {
        reject(new Error('IndexedDB nao inicializado'));
        return;
      }

      var tx = db.transaction('pending-sync', 'readwrite');
      var store = tx.objectStore('pending-sync');

      var item = {
        action: action, // 'create', 'update', 'delete'
        dados: dados,
        timestamp: new Date().toISOString()
      };

      var request = store.add(item);

      request.onsuccess = function() {
        console.log('[Offline] Operacao pendente salva:', action, dados.nome || dados.id);
        updatePendingCount();
        resolve(request.result);
      };

      request.onerror = function() {
        console.error('[Offline] Erro ao salvar operacao pendente');
        reject(request.error);
      };
    });
  }

  // ===========================================================================
  // Obter operações pendentes
  // ===========================================================================
  async function getPendingActions() {
    await aguardarDB();
    return new Promise(function(resolve, reject) {
      if (!db) {
        reject(new Error('IndexedDB nao inicializado'));
        return;
      }

      var tx = db.transaction('pending-sync', 'readonly');
      var store = tx.objectStore('pending-sync');
      var request = store.getAll();

      request.onsuccess = function() {
        resolve(request.result);
      };

      request.onerror = function() {
        reject(request.error);
      };
    });
  }

  // ===========================================================================
  // Remover operação pendente
  // ===========================================================================
  async function removePendingAction(id) {
    await aguardarDB();
    return new Promise(function(resolve, reject) {
      if (!db) {
        reject(new Error('IndexedDB nao inicializado'));
        return;
      }

      var tx = db.transaction('pending-sync', 'readwrite');
      var store = tx.objectStore('pending-sync');
      var request = store.delete(id);

      request.onsuccess = function() {
        updatePendingCount();
        resolve();
      };

      request.onerror = function() {
        reject(request.error);
      };
    });
  }

  // ===========================================================================
  // Contar pendências
  // ===========================================================================
  async function getPendingCount() {
    await aguardarDB();
    return new Promise(function(resolve, reject) {
      if (!db) {
        resolve(0);
        return;
      }

      var tx = db.transaction('pending-sync', 'readonly');
      var store = tx.objectStore('pending-sync');
      var request = store.count();

      request.onsuccess = function() {
        resolve(request.result);
      };

      request.onerror = function() {
        resolve(0);
      };
    });
  }

  // ===========================================================================
  // Cache de clientes
  // ===========================================================================
  async function cacheClientes(clientes) {
    await aguardarDB();
    return new Promise(function(resolve, reject) {
      if (!db) {
        reject(new Error('IndexedDB nao inicializado'));
        return;
      }

      var tx = db.transaction('cached-clients', 'readwrite');
      var store = tx.objectStore('cached-clients');

      clientes.forEach(function(cliente) {
        store.put(cliente);
      });

      tx.oncomplete = function() {
        console.log('[Offline] Clientes cacheados:', clientes.length);
        resolve();
      };

      tx.onerror = function() {
        reject(tx.error);
      };
    });
  }

  async function getCachedClientes() {
    await aguardarDB();
    return new Promise(function(resolve, reject) {
      if (!db) {
        reject(new Error('IndexedDB nao inicializado'));
        return;
      }

      var tx = db.transaction('cached-clients', 'readonly');
      var store = tx.objectStore('cached-clients');
      var request = store.getAll();

      request.onsuccess = function() {
        resolve(request.result);
      };

      request.onerror = function() {
        reject(request.error);
      };
    });
  }

  // ===========================================================================
  // Sincronização automática
  // ===========================================================================
  async function syncPendingActions() {
    if (!navigator.onLine) {
      console.log('[Offline] Sem conexao, sincronizacao adiada');
      return;
    }

    var pending = await getPendingActions();
    if (pending.length === 0) {
      console.log('[Offline] Nenhuma operacao pendente');
      return;
    }

    console.log('[Offline] Sincronizando', pending.length, 'operacoes...');
    showSyncIndicator('Sincronizando ' + pending.length + ' operacoes...');

    var sincronizados = 0;
    var erros = 0;

    for (var i = 0; i < pending.length; i++) {
      var item = pending[i];
      try {
        var response;
        var dados = item.dados;

        if (item.action === 'create') {
          response = await fetch('/api/clientes', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
          });
        } else if (item.action === 'update') {
          response = await fetch('/api/clientes/' + dados.id, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados)
          });
        } else if (item.action === 'delete') {
          response = await fetch('/api/clientes/' + dados.id, {
            method: 'DELETE'
          });
        }

        if (response && response.ok) {
          await removePendingAction(item.id);
          sincronizados++;
        } else {
          erros++;
          console.error('[Offline] Erro ao sincronizar item:', item.id);
        }
      } catch (e) {
        erros++;
        console.error('[Offline] Erro ao sincronizar:', e);
      }
    }

    var mensagem = 'Sincronizacao concluida: ' + sincronizados + ' enviados';
    if (erros > 0) {
      mensagem += ', ' + erros + ' erros';
    }

    showSyncIndicator(mensagem);
    updatePendingCount();

    // Recarregar lista de clientes
    if (typeof carregarClientes === 'function') {
      carregarClientes();
    }

    return { sincronizados: sincronizados, erros: erros };
  }

  // ===========================================================================
  // Event Listeners (online/offline)
  // ===========================================================================
  function setupEventListeners() {
    window.addEventListener('online', function() {
      console.log('[Offline] Conexao restaurada');
      isOnline = true;
      updateOnlineStatus();
      showSyncIndicator('Conexao restaurada! Sincronizando...');

      // Aguardar um pouco antes de sincronizar
      setTimeout(function() {
        syncPendingActions();
      }, 1000);
    });

    window.addEventListener('offline', function() {
      console.log('[Offline] Conexao perdida');
      isOnline = false;
      updateOnlineStatus();
      showSyncIndicator('Voce esta offline. As alteracoes serao sincronizadas quando voltar online.');
    });

    // Escutar mensagens do Service Worker
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('message', function(event) {
        if (event.data.type === 'SYNC_START') {
          showSyncIndicator(event.data.mensagem);
        } else if (event.data.type === 'SYNC_COMPLETE') {
          showSyncIndicator(event.data.mensagem);
          updatePendingCount();
          if (typeof carregarClientes === 'function') {
            carregarClientes();
          }
        }
      });
    }
  }

  // ===========================================================================
  // UI - Status Online/Offline
  // ===========================================================================
  function updateOnlineStatus() {
    var indicator = document.getElementById('onlineStatus');
    if (!indicator) return;

    if (isOnline) {
      indicator.className = 'online-status online';
      indicator.innerHTML = '<span class="status-dot"></span> Online';
      indicator.title = 'Conexao ativa - dados sincronizados';
    } else {
      indicator.className = 'online-status offline';
      indicator.innerHTML = '<span class="status-dot"></span> Offline';
      indicator.title = 'Sem conexao - dados serao sincronizados depois';
    }
  }

  function updatePendingCount() {
    getPendingCount().then(function(count) {
      var badge = document.getElementById('pendingBadge');
      if (badge) {
        if (count > 0) {
          badge.style.display = 'flex';
          badge.textContent = count;
          badge.title = count + ' operacao(oes) pendente(s)';
        } else {
          badge.style.display = 'none';
        }
      }
    });
  }

  function showSyncIndicator(mensagem) {
    var indicator = document.getElementById('syncIndicator');
    if (!indicator) return;

    indicator.textContent = mensagem;
    indicator.classList.add('show');

    setTimeout(function() {
      indicator.classList.remove('show');
    }, 4000);
  }

  // ===========================================================================
  // Service Worker Registration
  // ===========================================================================
  function registerServiceWorker() {
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.register('/sw.js')
        .then(function(registration) {
          console.log('[Offline] Service Worker registrado:', registration.scope);

          // Verificar atualizações
          registration.addEventListener('updatefound', function() {
            var newWorker = registration.installing;
            if (newWorker) {
              newWorker.addEventListener('statechange', function() {
                if (newWorker.state === 'activated') {
                  showSyncIndicator('App atualizado! Recarregue para ver as mudancas.');
                }
              });
            }
          });
        })
        .catch(function(error) {
          console.error('[Offline] Erro ao registrar SW:', error);
        });
    }
  }

  // ===========================================================================
  // API Pública
  // ===========================================================================
  return {
    init: init,
    savePendingAction: savePendingAction,
    getPendingActions: getPendingActions,
    removePendingAction: removePendingAction,
    getPendingCount: getPendingCount,
    cacheClientes: cacheClientes,
    getCachedClientes: getCachedClientes,
    syncPendingActions: syncPendingActions,
    isOnline: function() { return isOnline; }
  };
})();

// Inicializar quando DOM estiver pronto
document.addEventListener('DOMContentLoaded', function() {
  OfflineManager.init();
});
