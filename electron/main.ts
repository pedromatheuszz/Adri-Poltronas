/**
 * Processo principal do Electron.
 *
 * Substitui o pywebview: antes a janela era um WebView2 hospedado pelo
 * proprio processo Python. Aqui o Electron abre a janela, e o Flask segue
 * como backend em processo separado.
 */
import { app, BrowserWindow, dialog, shell } from 'electron';
import { join } from 'node:path';
import { iniciarBackend, pararBackend, URL_APP } from './backend';

const LARGURA_PADRAO = 1100;
const ALTURA_PADRAO = 760;
const LARGURA_MINIMA = 900;
const ALTURA_MINIMA = 600;

const raizProjeto = join(__dirname, '..');
let janela: BrowserWindow | null = null;
let encerrando = false;

function criarJanela(): BrowserWindow {
  const nova = new BrowserWindow({
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
    },
  });

  // Só exibe quando ha conteudo pintado.
  nova.once('ready-to-show', () => nova.show());

  // Links externos (boleto do Asaas, arquivo no OneDrive) abrem no navegador
  // do sistema; dentro do app eles virariam uma janela sem barra de endereco.
  nova.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://')) void shell.openExternal(url);
    return { action: 'deny' };
  });

  // Navegacao para fora da origem local tambem vai para o navegador.
  nova.webContents.on('will-navigate', (evento, url) => {
    if (!url.startsWith(URL_APP)) {
      evento.preventDefault();
      if (url.startsWith('https://')) void shell.openExternal(url);
    }
  });

  return nova;
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
    const subiu = await iniciarBackend(raizProjeto, app.isPackaged, mostrarErroEEncerrar);
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
