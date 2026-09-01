# Janela Qt — interface alternativa

Segunda interface do Adri Poltronas, em C++/Qt 6, sobre o **mesmo backend
Flask** que a janela do Electron.

Não substitui a interface web: as duas podem rodar ao mesmo tempo. Quem abrir
primeiro sobe o processo Python; a segunda detecta a porta ocupada e
reaproveita o servidor em vez de tentar subir outro.

## O que ela cobre

| Recurso | Qt | Electron (web) |
|---------|-----|----------------|
| Métricas do dashboard | ✅ | ✅ |
| Listar / buscar clientes | ✅ | ✅ |
| Cadastrar / editar / excluir cliente | ✅ | ✅ |
| Entregas, pagamentos, relatórios | ❌ | ✅ |
| Mapa de clientes | ❌ | ✅ |
| Exportação para o OneDrive | ❌ | ✅ |

O que ficou de fora depende de Leaflet, gráficos e do fluxo OAuth do OneDrive —
sem equivalente direto em Qt Widgets, e que teria de ser reimplementado do
zero em vez de reaproveitado.

## Arquitetura

```
main.cpp            sobe o backend, aplica o tema, abre a janela
ProcessoBackend     ciclo de vida do Flask (equivalente a electron/backend.ts)
ClienteApi          cliente HTTP de /api/clientes e /api/dashboard
ModeloClientes      QAbstractTableModel da lista
JanelaPrincipal     cartões de métrica, busca e tabela
DialogoCliente      formulário de cadastro/edição
```

Nenhuma dessas classes toca o SQLite. Validação, migrations e regras de
negócio continuam só no Python — duas UIs, um backend, uma fonte de verdade.
Há testes que garantem isso (`tests/test_qt.py`, na raiz do projeto).

## Pré-requisitos

- Qt 6.8+ com MinGW (`aqt install-qt windows desktop 6.8.3 win64_mingw`)
- Toolchain MinGW (`aqt install-tool windows desktop tools_mingw1310`)
- CMake 3.21+

## Compilar

Pela raiz do projeto, com o caminho do Qt no ambiente:

```bash
set QT_PREFIX_PATH=C:\Users\<voce>\Qt\6.8.3\mingw_64
set QT_CXX_COMPILER=C:\Users\<voce>\Qt\Tools\mingw1310_64\bin\g++.exe
set QT_MAKE_PROGRAM=C:\Users\<voce>\Qt\Tools\mingw1310_64\bin\mingw32-make.exe

python build.py qt      # configure + build + ctest
make qt                 # equivalente
```

Ou direto pelo CMake:

```bash
cd qt-app
cmake -G "MinGW Makefiles" -S . -B build -DCMAKE_PREFIX_PATH=<qt>/mingw_64
cmake --build build -j 4
ctest --test-dir build --output-on-failure
```

## Executar

O executável precisa das DLLs do Qt no `PATH`:

```bash
set PATH=%QT_PREFIX_PATH%\bin;%PATH%
qt-app\build\AdriPoltronasQt.exe
```

`--empacotado` faz o programa procurar o backend em `backend/` ao lado do
executável, no mesmo layout que o electron-builder produz — é o modo usado
quando a janela Qt é distribuída junto do backend do PyInstaller.

## Testes

`ctest` roda três binários de QtTest (17 casos):

| Binário | Cobre |
|---------|-------|
| `test_cliente_api` | parsing do JSON da API e montagem/codificação das URLs |
| `test_modelo_clientes` | colunas, cores por tipo e limites de índice |
| `test_processo_backend` | porta, entrypoint e nome do executável empacotado |

> Os padrões do projeto pedem GoogleTest para C++. Aqui a escolha foi QtTest:
> ele já vem com o Qt (`Qt6::Test`, sem download extra), integra com o `ctest`
> e conhece os tipos do Qt — `QCOMPARE` sobre um `QString` ou `QColor` mostra
> o valor real na falha, o que o gtest não faz sem matchers próprios.
