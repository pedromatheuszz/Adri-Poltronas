/**
 * Processo principal do Electron.
 *
 * Substitui o pywebview: antes a janela era um WebView2 hospedado pelo
 * proprio processo Python. Aqui o Electron abre a janela, e o Flask segue
 * como backend em processo separado.
 */
import { app, BrowserWindow, dialog, ipcMain, session, shell } from 'electron';
import { join } from 'node:path';
import { iniciarBackend, pararBackend, URL_APP } from './backend';
import { NOME_DO_HEADER, obterToken } from './capacidade';

const LARGURA_PADRAO = 1100;
const ALTURA_PADRAO = 760;
const LARGURA_MINIMA = 900;
const ALTURA_MINIMA = 600;

const raizProjeto = join(__dirname, '..');
let janela: BrowserWindow | null = null;
let encerrando = false;

function pertenceAoApp(url: string): boolean {
  try {
    return new URL(url).origin === new URL(URL_APP).origin;
  } catch {
    return false;
  }
}

function abrirExternoSeguro(url: string): void {
  try {
    if (new URL(url).protocol === 'https:') void shell.openExternal(url);
  } catch {
    // URLs malformadas e protocolos locais nunca saem do aplicativo.
  }
}

function validarOrigemDaJanela(evento: Electron.IpcMainInvokeEvent): BrowserWindow {
  const frame = evento.senderFrame;
  const origem = frame?.url;
  if (!origem || frame !== evento.sender.mainFrame || new URL(origem).origin !== new URL(URL_APP).origin) {
    throw new Error('Origem da janela invalida.');
  }
  const origemJanela = BrowserWindow.fromWebContents(evento.sender);
  if (!origemJanela || origemJanela !== janela) {
    throw new Error('Janela nao autorizada.');
  }
  return origemJanela;
}

function registrarControlesDaJanela(): void {
  ipcMain.handle('janela:minimizar', (evento) => {
    validarOrigemDaJanela(evento).minimize();
  });
  ipcMain.handle('janela:alternar-maximizada', (evento) => {
    const alvo = validarOrigemDaJanela(evento);
    if (alvo.isMaximized()) alvo.unmaximize();
    else alvo.maximize();
  });
  ipcMain.handle('janela:fechar', (evento) => {
    validarOrigemDaJanela(evento).close();
  });
}

function publicarEstadoDaJanela(alvo: BrowserWindow): void {
  const publicar = () => {
    if (!alvo.isDestroyed() && !alvo.webContents.isDestroyed()) {
      alvo.webContents.send('janela:estado-maximizada', alvo.isMaximized());
    }
  };
  alvo.on('maximize', publicar);
  alvo.on('unmaximize', publicar);
  alvo.webContents.on('did-finish-load', publicar);
}

function criarJanela(): BrowserWindow {
  const nova = new BrowserWindow({
    frame: false,
    width: LARGURA_PADRAO,
    height: ALTURA_PADRAO,
    minWidth: LARGURA_MINIMA,
    minHeight: ALTURA_MINIMA,
    title: 'Adri Poltronas',
    // Cor de fundo da janela antes do primeiro paint. Acompanha
    // `--cor-fundo` do tema claro (tokens.css): com o azul-escuro anterior,
    // a abertura piscava escuro antes de a interface clara aparecer.
    backgroundColor: '#F2EEE7',
    show: false,
    autoHideMenuBar: true,
    icon: join(raizProjeto, 'icone_sistema.ico'),
    webPreferences: {
      // A pagina vem do proprio backend por HTTP e nao precisa de nenhuma
      // ponte para o Node. Manter o isolamento fecha a porta para que um XSS
      // no frontend alcance o sistema de arquivos.
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      preload: join(__dirname, 'preload.js'),
    },
  });

  // Só exibe quando ha conteudo pintado.
  nova.once('ready-to-show', () => nova.show());
  publicarEstadoDaJanela(nova);

  // Links externos (arquivo no OneDrive, cobranca da licenca) abrem no
  // navegador do sistema; dentro do app eles virariam uma janela sem barra de
  // endereco.
  nova.webContents.setWindowOpenHandler(({ url }) => {
    abrirExternoSeguro(url);
    return { action: 'deny' };
  });

  // Navegacao para fora da origem local tambem vai para o navegador.
  nova.webContents.on('will-navigate', (evento, url) => {
    if (!pertenceAoApp(url)) {
      evento.preventDefault();
      abrirExternoSeguro(url);
    }
  });

  return nova;
}

/**
 * Carimba o token de capacidade em toda requisicao que sai para o backend.
 *
 * Precisa rodar antes do primeiro `loadURL`: o Flask recusa com 403 tudo que
 * chegue sem o cabecalho, inclusive a pagina inicial. O filtro limita a
 * injecao a origem local -- o token nao pode vazar para o Mercado Pago, o ViaCEP
 * ou qualquer outro destino que a pagina consulte.
 */
function injetarCapacidade(token: string): void {
  // O filtro por padrao de URL do webRequest segue a sintaxe de match pattern
  // do Chromium, que nao contempla porta -- `http://127.0.0.1:5000/*` nao e um
  // padrao valido e o filtro deixaria de casar. Escuta-se tudo e compara-se a
  // origem aqui, que e explicito e nao depende dessa sutileza.
  session.defaultSession.webRequest.onBeforeSendHeaders(
    { urls: ['<all_urls>'] },
    (detalhes, prosseguir) => {
      if (!pertenceAoApp(detalhes.url)) {
        // Nunca para fora: o token nao pode vazar para o Mercado Pago, o
        // ViaCEP ou qualquer outro destino que a pagina consulte.
        prosseguir({ requestHeaders: detalhes.requestHeaders });
        return;
      }
      prosseguir({
        requestHeaders: { ...detalhes.requestHeaders, [NOME_DO_HEADER]: token },
      });
    },
  );
}

function mostrarErroEEncerrar(mensagem: string): void {
  dialog.showErrorBox('Adri Poltronas', mensagem);
  encerrando = true;
  void pararBackend().finally(() => app.exit(1));
}

// Segunda instancia apenas foca a janela existente: duas instancias
// disputariam a porta 5000 e o mesmo arquivo SQLite.
if (!app.requestSingleInstanceLock()) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (janela) {
      if (janela.isMinimized()) janela.restore();
      janela.focus();
    }
  });

  app.whenReady().then(async () => {
    registrarControlesDaJanela();
    // O token precisa existir ANTES do backend subir (ele o recebe por
    // variavel de ambiente) e antes da primeira navegacao (a propria pagina
    // inicial ja e recusada sem ele).
    const capacidade = obterToken(app.getPath('appData'));
    injetarCapacidade(capacidade);

    const subiu = await iniciarBackend(raizProjeto, app.isPackaged, capacidade, mostrarErroEEncerrar);
    if (!subiu) return;

    janela = criarJanela();
    await janela.loadURL(URL_APP);

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        janela = criarJanela();
        void janela.loadURL(URL_APP);
      }
    });
  });

  app.on('window-all-closed', () => app.quit());

  // O backend precisa morrer junto: senao o processo Python sobrevive a
  // janela e a proxima abertura encontra a porta ocupada.
  app.on('before-quit', (evento) => {
    if (encerrando) return;
    evento.preventDefault();
    encerrando = true;
    void pararBackend().finally(() => app.exit(0));
  });
}
