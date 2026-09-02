/**
 * Segredo que separa o aplicativo de qualquer outro cliente da porta 5000.
 *
 * O Flask escuta em loopback, e loopback nao e privado: qualquer processo da
 * maquina -- e qualquer pagina aberta no navegador do usuario -- alcanca
 * 127.0.0.1:5000. Sem este token, um `GET /api/clientes` de um curl qualquer
 * devolvia a lista completa de clientes, com nome, endereco e CEP.
 *
 * O fluxo:
 *   1. aqui o token e lido (ou criado) no perfil do usuario;
 *   2. `iniciarBackend` o passa ao processo Python por variavel de ambiente;
 *   3. `main.ts` injeta o cabecalho em todas as requisicoes da sessao da janela;
 *   4. o Flask recusa, com 403, tudo que chegar sem ele.
 *
 * Por que persistido, e nao sorteado a cada execucao: quando o Electron morre
 * sem levar o Python junto, a proxima abertura encontra a porta ocupada pelo
 * backend orfao. Com token por execucao, esse orfao so aceitaria o segredo
 * anterior e o aplicativo nao teria como se recuperar sozinho.
 *
 * O limite honesto da protecao esta documentado em `backend/capacidade.py`:
 * o arquivo mora ao lado do banco SQLite, entao um processo rodando como o
 * mesmo usuario ja poderia ler os dados direto. O que o token fecha e o vetor
 * real de um servico em loopback -- quem chuta a porta 5000 as cegas.
 */
import { randomBytes } from 'node:crypto';
import { chmodSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

export const NOME_DO_HEADER = 'X-Adri-Capacidade';
export const VARIAVEL_DE_AMBIENTE = 'ADRI_API_TOKEN';

const NOME_DO_ARQUIVO = '.capacidade';
const NOME_DA_PASTA = 'AdriPoltronas';
const BYTES_DO_TOKEN = 32;

/**
 * Le o token do perfil do usuario, criando-o na primeira execucao.
 *
 * `pastaAppData` vem de `app.getPath('appData')` -- passado como argumento em
 * vez de importado para que este modulo continue testavel fora do Electron.
 */
export function obterToken(pastaAppData: string): string {
  const pasta = join(pastaAppData, NOME_DA_PASTA);
  const caminho = join(pasta, NOME_DO_ARQUIVO);

  try {
    const existente = readFileSync(caminho, 'utf8').trim();
    if (existente) return existente;
  } catch {
    // Primeira execucao, ou arquivo removido pelo usuario. Segue e cria.
  }

  const token = randomBytes(BYTES_DO_TOKEN).toString('hex');
  try {
    mkdirSync(pasta, { recursive: true });
    writeFileSync(caminho, token, { encoding: 'utf8', mode: 0o600 });
    // No Windows o chmod so mexe no atributo somente-leitura; a protecao real
    // vem da ACL do perfil. Repetir aqui cobre o caso de o arquivo ja existir
    // com permissao frouxa de uma versao anterior.
    chmodSync(caminho, 0o600);
  } catch (erro) {
    // Perfil somente-leitura nao pode impedir o app de abrir: o token da
    // execucao continua valendo em memoria, so nao sobrevive ao fechamento.
    console.warn('[capacidade] nao foi possivel gravar o token:', erro);
  }
  return token;
}
