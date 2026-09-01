/**
 * Ciclo de vida do backend Flask.
 *
 * O Python continua sendo o backend: ele detem o schema, as migrations, a
 * integracao com o Asaas e a suite de testes. O Electron troca apenas o motor
 * de exibicao -- antes o WebView2 embutido pelo pywebview.
 */
import { spawn, ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout as esperar } from 'node:timers/promises';

/** A porta e fixa porque o redirect_uri do OAuth Microsoft esta registrado
 *  no Azure como http://localhost:5000/callback. Sortear porta quebraria o
 *  login do OneDrive. */
export const PORTA = 5000;
export const HOST = '127.0.0.1';
export const URL_APP = `http://${HOST}:${PORTA}/`;

/** A sonda de disponibilidade e a propria pagina: se ela responde, o Flask
 *  subiu e serviu o shell. */
const URL_SONDA = URL_APP;

const TIMEOUT_BOOT_MS = 30_000;
const INTERVALO_SONDA_MS = 250;
/** Margem para o Flask fechar conexoes antes de recorrer ao SIGKILL. */
const TIMEOUT_ENCERRAMENTO_MS = 5_000;

let processo: ChildProcess | null = null;

/**
 * Como iniciar o backend, conforme empacotado ou nao.
 *
 * Empacotado: PyInstaller gera `AdriPoltronasBackend.exe`, copiado para
 * `resources/backend` pelo electron-builder.
 * Desenvolvimento: o interpretador do sistema roda `backend/servidor.py`.
 */
function comandoDoBackend(raizProjeto: string, empacotado: boolean): {
  comando: string;
  argumentos: string[];
  diretorio: string;
} {
  if (empacotado) {
    const exe = join(process.resourcesPath, 'backend', 'AdriPoltronasBackend.exe');
    return { comando: exe, argumentos: [], diretorio: join(process.resourcesPath, 'backend') };
  }
  const python = process.platform === 'win32' ? 'python' : 'python3';
  return {
    comando: python,
    argumentos: [join(raizProjeto, 'backend', 'servidor.py')],
    diretorio: raizProjeto,
  };
}

/** True quando o Flask ja responde. Qualquer status serve: o que importa e
 *  ter alguem escutando, e nao o corpo da resposta. */
async function servidorNoAr(): Promise<boolean> {
  try {
    const resposta = await fetch(URL_SONDA, {
      signal: AbortSignal.timeout(1_000),
    });
    return resposta.status > 0;
  } catch {
    return false;
  }
}

export async function iniciarBackend(
  raizProjeto: string,
  empacotado: boolean,
  aoFalhar: (mensagem: string) => void,
): Promise<boolean> {
  // Uma instancia anterior (ou outro app) pode ja estar na porta. Reaproveitar
  // evita a segunda instancia morrer com EADDRINUSE e a janela ficar vazia.
  if (await servidorNoAr()) {
    console.log('[backend] ja havia um servidor em', URL_APP);
    return true;
  }

  const { comando, argumentos, diretorio } = comandoDoBackend(raizProjeto, empacotado);
  if (empacotado && !existsSync(comando)) {
    aoFalhar(`Backend nao encontrado em ${comando}`);
    return false;
  }

  processo = spawn(comando, argumentos, {
    cwd: diretorio,
    // O backend herda o ambiente; ADRI_DB_PATH e afins continuam valendo.
    env: {
      ...process.env,
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  processo.stdout?.on('data', (d: Buffer) => process.stdout.write(`[backend] ${d}`));
  processo.stderr?.on('data', (d: Buffer) => process.stderr.write(`[backend] ${d}`));

  let saiuCedo: string | null = null;
  processo.on('exit', (codigo, sinal) => {
    if (codigo !== 0 && codigo !== null) saiuCedo = `Backend encerrou com codigo ${codigo}`;
    else if (sinal) saiuCedo = `Backend encerrado por ${sinal}`;
    processo = null;
  });
  processo.on('error', (erro) => {
    saiuCedo = `Nao foi possivel iniciar o backend: ${erro.message}`;
  });

  const limite = Date.now() + TIMEOUT_BOOT_MS;
  while (Date.now() < limite) {
    if (saiuCedo) {
      aoFalhar(saiuCedo);
      return false;
    }
    if (await servidorNoAr()) return true;
    await esperar(INTERVALO_SONDA_MS);
  }

  aoFalhar(`O servidor interno nao respondeu em ${URL_APP} dentro de ${TIMEOUT_BOOT_MS / 1000}s.`);
  return false;
}

/** Encerra o backend. Sem isso o processo Python sobrevive ao fechamento da
 *  janela e a proxima abertura encontra a porta ocupada. */
export async function pararBackend(): Promise<void> {
  const atual = processo;
  if (!atual || atual.exitCode !== null) return;

  atual.kill();
  const limite = Date.now() + TIMEOUT_ENCERRAMENTO_MS;
  while (Date.now() < limite && atual.exitCode === null) {
    await esperar(100);
  }
  if (atual.exitCode === null) atual.kill('SIGKILL');
  processo = null;
}
