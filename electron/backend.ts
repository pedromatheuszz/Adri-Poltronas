/**
 * Ciclo de vida do backend Flask.
 *
 * O Python continua sendo o backend: ele detem o schema, as migrations, as
 * integracoes externas e a suite de testes. O Electron troca apenas o motor
 * de exibicao -- antes o WebView2 embutido pelo pywebview.
 */
import { spawn, ChildProcess } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { setTimeout as esperar } from 'node:timers/promises';
import { NOME_DO_HEADER, VARIAVEL_DE_AMBIENTE } from './capacidade';

/** A porta e fixa porque o redirect_uri do OAuth Microsoft esta registrado
 *  no Azure como http://localhost:5000/callback. Sortear porta quebraria o
 *  login do OneDrive. */
export const PORTA = 5000;
export const HOST = '127.0.0.1';
export const URL_APP = `http://${HOST}:${PORTA}/`;

/** Sonda de identidade. Nao e mais a propria pagina: uma pagina que responde
 *  so prova que ALGO escuta na porta, e o app adotava esse algo como se fosse
 *  o proprio backend. `/api/health` diz QUEM esta atendendo. */
const URL_SONDA = `${URL_APP}api/health`;

/** Marcador que `backend/servidor.py` imprime no stderr quando se recusa a
 *  subir sobre um banco em duvida. O texto que vem depois dele sao as
 *  instrucoes de recuperacao, e vao inteiras para a caixa de dialogo. */
const MARCADOR_FALHA_BANCO = '[ADRI-BANCO-FALHOU]';

const TIMEOUT_BOOT_MS = 30_000;
const INTERVALO_SONDA_MS = 250;
/** Margem para o Flask fechar conexoes antes de recorrer ao SIGKILL. */
const TIMEOUT_ENCERRAMENTO_MS = 5_000;

let processo: ChildProcess | null = null;

type RespostaDaSonda = {
  servico?: string;
  capacidade_exigida?: boolean;
  capacidade_aceita?: boolean;
};

/** O que a sonda encontrou na porta. */
export type EstadoDaPorta =
  | { situacao: 'livre' }
  | { situacao: 'nosso' }
  | { situacao: 'estranho' }
  | { situacao: 'recusou-capacidade' };

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

/**
 * Descobre o que ha na porta 5000.
 *
 * A versao anterior perguntava so "alguem responde?" e, em caso afirmativo,
 * apontava a janela para la. Qualquer servidor de qualquer outro projeto
 * herdava o aplicativo -- e tudo o que ele mandasse.
 */
export async function sondarPorta(token: string): Promise<EstadoDaPorta> {
  let resposta: Response;
  try {
    resposta = await fetch(URL_SONDA, {
      headers: { [NOME_DO_HEADER]: token },
      signal: AbortSignal.timeout(1_000),
    });
  } catch {
    return { situacao: 'livre' };
  }

  let corpo: RespostaDaSonda;
  try {
    corpo = (await resposta.json()) as RespostaDaSonda;
  } catch {
    // Respondeu, mas nao com o JSON da sonda: e outro servico.
    return { situacao: 'estranho' };
  }

  if (corpo.servico !== 'adri-poltronas') return { situacao: 'estranho' };
  if (corpo.capacidade_exigida && !corpo.capacidade_aceita) {
    // E um backend nosso, mas de uma instalacao com outro token. Adotar seria
    // abrir uma janela em que nenhuma chamada de API funciona.
    return { situacao: 'recusou-capacidade' };
  }
  return { situacao: 'nosso' };
}

export async function iniciarBackend(
  raizProjeto: string,
  empacotado: boolean,
  token: string,
  aoFalhar: (mensagem: string) => void,
): Promise<boolean> {
  // Uma instancia anterior pode ter deixado o Python orfao na porta.
  // Reaproveitar evita o segundo processo morrer com EADDRINUSE e a janela
  // ficar vazia -- mas so quando o que esta la e mesmo o nosso backend.
  const estadoInicial = await sondarPorta(token);
  if (estadoInicial.situacao === 'nosso') {
    console.log('[backend] ja havia um servidor em', URL_APP);
    return true;
  }
  if (estadoInicial.situacao === 'estranho') {
    aoFalhar(
      `A porta ${PORTA} ja esta em uso por outro programa.\n\n` +
        'O Adri Poltronas precisa dela para funcionar (o endereco de retorno ' +
        'do login da Microsoft aponta para essa porta).\n\n' +
        'Feche o outro programa e abra o aplicativo de novo.',
    );
    return false;
  }
  if (estadoInicial.situacao === 'recusou-capacidade') {
    aoFalhar(
      'Ha uma execucao anterior do Adri Poltronas ainda ativa em segundo plano.\n\n' +
        'Encerre o processo "AdriPoltronasBackend" pelo Gerenciador de Tarefas, ' +
        'ou reinicie o computador, e abra o aplicativo de novo.',
    );
    return false;
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
      [VARIAVEL_DE_AMBIENTE]: token,
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  processo.stdout?.on('data', (d: Buffer) => process.stdout.write(`[backend] ${d}`));

  // O stderr e acumulado a partir do marcador de falha de banco: e o unico
  // caminho pelo qual o operador recebe as instrucoes de recuperacao. Sem
  // isso ele veria "o servidor nao respondeu" e nao teria o que fazer com a
  // informacao.
  let instrucoesDeRecuperacao = '';
  processo.stderr?.on('data', (d: Buffer) => {
    const texto = d.toString();
    process.stderr.write(`[backend] ${texto}`);
    if (instrucoesDeRecuperacao) {
      instrucoesDeRecuperacao += texto;
    } else {
      const marcador = texto.indexOf(MARCADOR_FALHA_BANCO);
      if (marcador !== -1) {
        instrucoesDeRecuperacao = texto.slice(marcador + MARCADOR_FALHA_BANCO.length);
      }
    }
  });

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
      aoFalhar(instrucoesDeRecuperacao.trim() || saiuCedo);
      return false;
    }
    const estado = await sondarPorta(token);
    if (estado.situacao === 'nosso') return true;
    if (estado.situacao === 'recusou-capacidade') {
      // O backend subiu mas nao reconhece o token que acabamos de passar.
      // Abrir a janela aqui daria uma tela em que nada carrega.
      aoFalhar(
        'O servidor interno subiu, mas recusou a credencial do aplicativo.\n\n' +
          'Feche o aplicativo e abra novamente. Persistindo, apague o arquivo ' +
          '.capacidade da pasta de dados do aplicativo.',
      );
      return false;
    }
    await esperar(INTERVALO_SONDA_MS);
  }

  aoFalhar(
    instrucoesDeRecuperacao.trim() ||
      `O servidor interno nao respondeu em ${URL_APP} dentro de ${TIMEOUT_BOOT_MS / 1000}s.`,
  );
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
