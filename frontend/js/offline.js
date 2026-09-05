// =============================================================================
// Adri Poltronas - Offline Module (IndexedDB + Sync)
// =============================================================================

var OfflineManager = (function() {
  'use strict';

  var DB_NAME = 'AdriPoltronasOffline';
  // v2 acrescenta a fila de erros (`dead-letter`) e os campos `uuid`/`idLocal`
  // nas pendencias. Ver o bloco "A fila" abaixo.
  var DB_VERSION = 2;
  var db = null;
  var dbReady = null; // Promise que resolve quando DB está pronto
  var isOnline = navigator.onLine;

  // Um item que falha por validacao (4xx) nunca vai passar; um que falha por
  // erro do servidor (5xx) pode passar depois. O teto existe para o segundo
  // caso -- sem ele, um item problematico era reenviado a cada reconexao,
  // indefinidamente.
  var MAX_TENTATIVAS_SYNC = 5;

  // Guarda de concorrencia: o evento `online` e uma chamada manual podiam
  // disparar duas sincronizacoes ao mesmo tempo e duplicar POSTs de criacao.
  var sincronizacaoEmCurso = false;

  // A sincronizacao dependia so do evento `online`. Ele nao dispara quando o
  // navegador acha que ha rede mas o backend esta fora, nem quando a maquina
  // acorda de suspensao com a conexao ja de pe -- e a fila ficava parada com
  // o operador achando que tinha sincronizado.
  var INTERVALO_TENTATIVA_MS = 60000;
  var temporizadorTentativa = null;

  // ===========================================================================
  // A fila
  //
  // Cada pendencia carrega:
  //
  //   uuid     identificador da OPERACAO, gerado uma vez, no momento em que
  //            ela entra na fila -- nao a cada tentativa de envio. Vai no
  //            cabecalho `Idempotency-Key`, e e o que permite ao servidor
  //            distinguir "nao recebi" de "recebi e a resposta se perdeu".
  //            Sem ele, reenviar uma criacao criava um segundo cliente.
  //
  //   idLocal  para criacoes, o id temporario negativo com que o cliente
  //            aparece no cache enquanto nao ha id real. Antes ele nao era
  //            guardado na fila, e por isso nada ligava a criacao pendente ao
  //            registro que o operador estava vendo na tela. Tres defeitos
  //            saiam dai:
  //
  //              - editar o cliente recem-criado enfileirava um PUT contra o
  //                id negativo, que o servidor respondia com 404 e a fila
  //                descartava em silencio: a edicao sumia;
  //              - excluir o cliente temporario limpava o cache e deixava a
  //                criacao na fila, entao ele reaparecia ao sincronizar;
  //              - depois de criado com id real, nada remapeava as operacoes
  //                seguintes.
  // ===========================================================================
  function novoUuid() {
    if (window.crypto && typeof window.crypto.randomUUID === 'function') {
      return window.crypto.randomUUID();
    }
    // Fallback para motores sem randomUUID. Nao precisa de qualidade
    // criptografica: e um identificador de operacao local, nao um segredo.
    return 'op-' + Date.now().toString(36) + '-' +
           Math.random().toString(36).slice(2, 10);
  }

  // ===========================================================================
  // Inicialização
  // ===========================================================================
  function init() {
    console.log('[Offline] Inicializando...');
    dbReady = openDatabase();
    setupEventListeners();
    escutarServiceWorker();
    updateOnlineStatus();
    registerServiceWorker();
    updatePendingCount();
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

        // Fila de erros. Uma pendencia que o servidor recusou de forma
        // definitiva (4xx) ou que esgotou as tentativas vinha sendo APAGADA:
        // o trabalho do operador desaparecia sem deixar rastro nem aviso.
        // Agora ela sai da fila de envio e vai para ca, onde pode ser
        // consultada, reenviada ou descartada com conhecimento de causa.
        if (!database.objectStoreNames.contains('dead-letter')) {
          var falhas = database.createObjectStore('dead-letter', {
            keyPath: 'id',
            autoIncrement: true
          });
          falhas.createIndex('timestamp', 'timestamp', { unique: false });
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
  async function savePendingAction(action, dados, idLocal) {
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
        // Copia rasa: `dados` e mutado pelo chamador logo depois (para
        // receber o id temporario, por exemplo), e a fila precisa guardar o
        // que foi enfileirado, nao o que o objeto virou.
        dados: Object.assign({}, dados),
        uuid: novoUuid(),
        idLocal: (typeof idLocal === 'number') ? idLocal : null,
        tentativas: 0,
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
  // Compactacao: operacoes sobre um cliente que ainda nao existe no servidor
  //
  // Enquanto o id e temporario, nao ha o que enviar separadamente -- o
  // servidor nem conhece o registro. Entao a edicao e absorvida pela criacao
  // pendente, e a exclusao simplesmente cancela a criacao.
  //
  // Antes, os dois casos viravam requisicoes contra o id negativo: o PUT
  // tomava 404 e era descartado (a edicao sumia), e o DELETE nao removia a
  // criacao (o cliente excluido reaparecia na proxima sincronizacao).
  // ===========================================================================
  async function mesclarNaCriacaoPendente(idLocal, dados) {
    var pendencia = await encontrarCriacaoPendente(idLocal);
    if (!pendencia) return false;
    pendencia.dados = Object.assign({}, pendencia.dados, dados);
    delete pendencia.dados.id; // o id temporario nunca vai para o servidor
    await atualizarPendingAction(pendencia);
    console.log('[Offline] Edicao absorvida pela criacao pendente', idLocal);
    return true;
  }

  async function cancelarCriacaoPendente(idLocal) {
    var pendencia = await encontrarCriacaoPendente(idLocal);
    if (!pendencia) return false;
    await removePendingAction(pendencia.id);
    console.log('[Offline] Criacao pendente cancelada', idLocal);
    return true;
  }

  async function encontrarCriacaoPendente(idLocal) {
    var pendentes = await getPendingActions();
    for (var i = 0; i < pendentes.length; i++) {
      if (pendentes[i].action === 'create' && pendentes[i].idLocal === idLocal) {
        return pendentes[i];
      }
    }
    return null;
  }

  // ===========================================================================
  // Remapeamento: o id temporario vira o id real depois da criacao
  // ===========================================================================
  async function remapearPendencias(idLocal, idReal) {
    if (typeof idLocal !== 'number' || typeof idReal !== 'number') return;
    var pendentes = await getPendingActions();
    for (var i = 0; i < pendentes.length; i++) {
      var item = pendentes[i];
      if (item.idLocal !== idLocal && item.dados.id !== idLocal) continue;
      item.dados = Object.assign({}, item.dados, { id: idReal });
      item.idLocal = null;
      await atualizarPendingAction(item);
      console.log('[Offline] Pendencia remapeada:', idLocal, '->', idReal);
    }

    // O cache tambem: senao a tela continua mostrando o id negativo e a
    // proxima edicao volta a apontar para um registro que nao existe mais.
    var cache = await getCachedClientes();
    var alvo = cache.filter(function(c) { return c.id === idLocal; })[0];
    if (alvo) {
      await removerDoCache(idLocal);
      alvo.id = idReal;
      delete alvo._offline;
      await cacheClientes([alvo]);
    }
  }

  async function removerDoCache(id) {
    await aguardarDB();
    return new Promise(function(resolve) {
      if (!db) { resolve(); return; }
      var tx = db.transaction('cached-clients', 'readwrite');
      tx.objectStore('cached-clients').delete(id);
      tx.oncomplete = function() { resolve(); };
      tx.onerror = function() { resolve(); };
    });
  }

  // ===========================================================================
  // Fila de erros (dead-letter)
  //
  // Uma pendencia recusada de forma definitiva (4xx) ou que esgotou as
  // tentativas vinha sendo APAGADA: o trabalho do operador desaparecia sem
  // rastro e sem aviso. Agora sai da fila de envio e vem para ca, onde pode
  // ser vista, reenviada ou descartada com conhecimento de causa.
  // ===========================================================================
  async function moverParaFilaDeErros(item, motivo) {
    await aguardarDB();
    await new Promise(function(resolve) {
      if (!db) { resolve(); return; }
      var tx = db.transaction('dead-letter', 'readwrite');
      tx.objectStore('dead-letter').add({
        action: item.action,
        dados: item.dados,
        uuid: item.uuid,
        motivo: motivo,
        tentativas: item.tentativas || 0,
        enfileiradoEm: item.timestamp,
        timestamp: new Date().toISOString()
      });
      tx.oncomplete = function() { resolve(); };
      tx.onerror = function() { resolve(); };
    });
    await removePendingAction(item.id);
    console.error('[Offline] Pendencia movida para a fila de erros:', motivo, item);
  }

  async function getDeadLetters() {
    await aguardarDB();
    return new Promise(function(resolve) {
      if (!db) { resolve([]); return; }
      var pedido = db.transaction('dead-letter', 'readonly')
                     .objectStore('dead-letter').getAll();
      pedido.onsuccess = function() { resolve(pedido.result); };
      pedido.onerror = function() { resolve([]); };
    });
  }

  async function descartarDeadLetter(id) {
    await aguardarDB();
    return new Promise(function(resolve) {
      if (!db) { resolve(); return; }
      var tx = db.transaction('dead-letter', 'readwrite');
      tx.objectStore('dead-letter').delete(id);
      tx.oncomplete = function() { resolve(); };
      tx.onerror = function() { resolve(); };
    });
  }

  async function reenviarDeadLetter(id) {
    var falhas = await getDeadLetters();
    var alvo = falhas.filter(function(f) { return f.id === id; })[0];
    if (!alvo) return false;
    await savePendingAction(alvo.action, alvo.dados, null);
    await descartarDeadLetter(id);
    return syncPendingActions();
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
  // Atualizar operação pendente (persiste o contador de tentativas)
  // ===========================================================================
  async function atualizarPendingAction(item) {
    await aguardarDB();
    return new Promise(function(resolve, reject) {
      if (!db) { reject(new Error('IndexedDB nao inicializado')); return; }
      var tx = db.transaction('pending-sync', 'readwrite');
      var request = tx.objectStore('pending-sync').put(item);
      request.onsuccess = function() { resolve(); };
      request.onerror = function() { reject(request.error); };
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

  async function sincronizarCache(clientes) {
    // Substitui o conteudo do cache pela lista do servidor.
    //
    // `cacheClientes` so faz put(): um cliente criado offline (id negativo)
    // continuava no IndexedDB depois de sincronizado com o id real -- e
    // aparecia duplicado na tela -- enquanto clientes excluidos no servidor
    // nunca sumiam do cache.
    //
    // Com pendencias ainda na fila, porem, o servidor NAO e a verdade
    // completa: as alteracoes locais ainda nao chegaram nele. Nesse caso a
    // poda e adiada para nao apagar o que o usuario acabou de registrar.
    var pendentes = await getPendingCount();
    if (pendentes > 0) {
      return cacheClientes(clientes);
    }

    await aguardarDB();
    return new Promise(function(resolve, reject) {
      if (!db) { reject(new Error('IndexedDB nao inicializado')); return; }
      var tx = db.transaction('cached-clients', 'readwrite');
      var store = tx.objectStore('cached-clients');
      store.clear();
      clientes.forEach(function(cliente) { store.put(cliente); });
      tx.oncomplete = function() {
        console.log('[Offline] Cache sincronizado:', clientes.length);
        resolve();
      };
      tx.onerror = function() { reject(tx.error); };
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
  // O `Idempotency-Key` e o que torna o reenvio seguro. Ele identifica a
  // OPERACAO, e nao a tentativa: o mesmo valor vai em todos os reenvios, e o
  // servidor devolve a resposta que ja deu em vez de executar de novo. Sem
  // ele, um POST cuja resposta se perdeu no caminho de volta -- indistinguivel,
  // daqui, de um POST que nunca chegou -- criava um segundo cliente identico.
  function cabecalhos(item, comCorpo) {
    var h = { 'Idempotency-Key': item.uuid || '' };
    if (comCorpo) h['Content-Type'] = 'application/json';
    return h;
  }

  async function enviarPendencia(item) {
    var dados = item.dados;
    if (item.action === 'create') {
      return fetch('/api/clientes', {
        method: 'POST',
        headers: cabecalhos(item, true),
        body: JSON.stringify(dados)
      });
    }
    if (item.action === 'update') {
      return fetch('/api/clientes/' + dados.id, {
        method: 'PUT',
        headers: cabecalhos(item, true),
        body: JSON.stringify(dados)
      });
    }
    if (item.action === 'delete') {
      return fetch('/api/clientes/' + dados.id, {
        method: 'DELETE',
        headers: cabecalhos(item, false)
      });
    }
    return null;
  }

  async function syncPendingActions() {
    if (sincronizacaoEmCurso) {
      console.log('[Offline] Sincronizacao ja em andamento');
      return;
    }
    sincronizacaoEmCurso = true;
    try {
      return await _sincronizar();
    } finally {
      sincronizacaoEmCurso = false;
    }
  }

  async function _sincronizar() {
    var pending = await getPendingActions();
    if (pending.length === 0) {
      console.log('[Offline] Nenhuma operacao pendente');
      return { sincronizados: 0, descartados: 0, adiados: 0 };
    }

    console.log('[Offline] Sincronizando', pending.length, 'operacoes...');
    showSyncIndicator('Sincronizando ' + pending.length + ' operacoes...');

    var sincronizados = 0;
    var descartados = 0;
    var adiados = 0;

    for (var i = 0; i < pending.length; i++) {
      var item = pending[i];
      var response;

      try {
        response = await enviarPendencia(item);
      } catch (e) {
        // Falha de REDE: o backend esta fora do ar. Nao e culpa do payload,
        // entao nao consome tentativa -- e nao adianta tentar os proximos.
        console.warn('[Offline] Backend indisponivel, sincronizacao adiada:', e);
        adiados = pending.length - i;
        break;
      }

      if (response && response.ok) {
        // Criacao: o id real chega na resposta, e as operacoes seguintes da
        // fila ainda apontam para o id temporario negativo. Sem este
        // remapeamento, a proxima delas vai contra um id que nao existe --
        // era assim que a edicao feita logo apos criar offline sumia.
        if (item.action === 'create' && item.idLocal !== null) {
          var corpo = await response.json().catch(function() { return {}; });
          if (typeof corpo.id === 'number') {
            await remapearPendencias(item.idLocal, corpo.id);
          }
        }
        await removePendingAction(item.id);
        sincronizados++;
        continue;
      }

      if (response && response.status >= 400 && response.status < 500) {
        // Erro permanente (validacao, id inexistente): reenviar nunca vai
        // mudar o resultado. Sai da fila de envio -- mas para a fila de
        // erros, nao para o lixo: apagar em silencio fazia o trabalho do
        // operador desaparecer sem que ninguem soubesse.
        await moverParaFilaDeErros(item, 'Recusado pelo servidor (' + response.status + ')');
        descartados++;
        continue;
      }

      // Erro do servidor (5xx) ou action desconhecida: pode passar depois.
      item.tentativas = (item.tentativas || 0) + 1;
      if (item.tentativas >= MAX_TENTATIVAS_SYNC) {
        await moverParaFilaDeErros(
          item, 'Excedeu ' + MAX_TENTATIVAS_SYNC + ' tentativas de envio');
        descartados++;
      } else {
        await atualizarPendingAction(item);
        adiados++;
      }
    }

    var mensagem = 'Sincronizacao concluida: ' + sincronizados + ' enviados';
    if (descartados > 0) mensagem += ', ' + descartados + ' com erro (ver pendencias)';
    if (adiados > 0) mensagem += ', ' + adiados + ' adiados';

    showSyncIndicator(mensagem);
    updatePendingCount();

    if (typeof carregarClientes === 'function') {
      carregarClientes();
    }

    return { sincronizados: sincronizados, descartados: descartados, adiados: adiados };
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

    // O evento `online` nao cobre tudo. Ele nao dispara quando o navegador
    // acha que ha rede mas o backend esta fora, nem quando a maquina acorda
    // de suspensao com a conexao ja de pe. Nesses casos a fila ficava parada
    // com o operador achando que tinha sincronizado.
    //
    // Voltar a aba e o momento mais provavel de o operador ir conferir, e um
    // relogio de um minuto cobre o resto sem custo perceptivel: sem pendencia
    // na fila, `syncPendingActions` sai na primeira linha.
    document.addEventListener('visibilitychange', function() {
      if (!document.hidden) tentarSincronizar();
    });
    temporizadorTentativa = setInterval(tentarSincronizar, INTERVALO_TENTATIVA_MS);
  }

  async function tentarSincronizar() {
    if (sincronizacaoEmCurso) return;
    var pendentes = await getPendingCount();
    if (pendentes > 0) syncPendingActions();
  }

  function escutarServiceWorker() {
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

    // O rotulo precisa de um elemento proprio (.online-rotulo). Como texto
    // solto ele nao podia ser alvo de seletor nenhum: nem a barra lateral
    // recolhida nem a regra de <=480px conseguiam escode-lo, e a palavra
    // vazava do indicador circular.
    var conectado = isOnline;
    indicator.className = 'online-status ' + (conectado ? 'online' : 'offline');
    indicator.innerHTML = '<span class="status-dot" aria-hidden="true"></span>'
      + '<span class="online-rotulo">' + (conectado ? 'Online' : 'Offline') + '</span>';
    indicator.title = conectado
      ? 'Conexao ativa - dados sincronizados'
      : 'Sem conexao - dados serao sincronizados depois';
  }

  function updatePendingCount() {
    getPendingCount().then(function(count) {
      var badge = document.getElementById('pendingBadge');
      if (badge) {
        if (count > 0) {
          badge.hidden = false;
          badge.textContent = count;
          badge.title = count + ' operacao(oes) pendente(s)';
        } else {
          badge.hidden = true;
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
              // `controller` nulo significa que NAO havia service worker
              // controlando esta pagina -- ou seja, primeira instalacao. O
              // `updatefound` dispara igual nos dois casos, entao sem esta
              // checagem a primeira abertura do app anunciava "App
              // atualizado! Recarregue" sem nada ter sido atualizado, e
              // pedindo ao operador uma acao que nao servia para nada.
              var eraAtualizacao = !!navigator.serviceWorker.controller;
              newWorker.addEventListener('statechange', function() {
                if (newWorker.state === 'activated' && eraAtualizacao) {
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
    sincronizarCache: sincronizarCache,
    getCachedClientes: getCachedClientes,
    syncPendingActions: syncPendingActions,
    // Compactacao das operacoes sobre cliente que ainda so existe localmente.
    mesclarNaCriacaoPendente: mesclarNaCriacaoPendente,
    cancelarCriacaoPendente: cancelarCriacaoPendente,
    // Fila de erros: o que o servidor recusou continua visivel e recuperavel.
    getDeadLetters: getDeadLetters,
    descartarDeadLetter: descartarDeadLetter,
    reenviarDeadLetter: reenviarDeadLetter,
    isOnline: function() { return isOnline; }
  };
})();

// Inicializar quando DOM estiver pronto
document.addEventListener('DOMContentLoaded', function() {
  OfflineManager.init();
});
