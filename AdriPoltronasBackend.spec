# -*- mode: python ; coding: utf-8 -*-
#
# Empacota o *backend* -- so o Flask, sem janela.
#
# A janela agora e do Electron (electron-builder gera o instalador). Este .spec
# produz `dist/AdriPoltronasBackend/`, que o electron-builder copia para
# `resources/backend` via `extraResources` no package.json. O executavel e
# console=True de proposito: o Electron le stdout/stderr do filho para
# diagnosticar falhas de inicializacao, e nada aqui abre GUI.


a = Analysis(
    ['backend/servidor.py'],
    pathex=['backend'],
    binaries=[],
    # O destino de cada entrada precisa casar com o que app.py e
    # migrations_manager.py procuram dentro de sys._MEIPASS.
    datas=[
        ('frontend', 'frontend'),
        ('backend/templates', 'templates'),
        ('backend/alembic.ini', '.'),
        ('backend/migrations', 'migrations'),
        # `config.VERSAO_DO_APP` le a versao daqui. Sem o arquivo no bundle, o
        # app instalado se identificaria como "desconhecida" na sonda que o
        # Electron usa para decidir se o servidor na porta e mesmo o dele.
        ('package.json', '.'),
    ],
    hiddenimports=[
        'database', 'notificacoes_db', 'security', 'asaas', 'config', 'validators',
        'blueprints', 'migrations_manager', 'capacidade', 'microsoft', 'planilha',
        'openpyxl', 'openpyxl.utils', 'et_xmlfile',
        'alembic', 'alembic.config', 'alembic.command',
        # `alembic/env.py` chama `logging.config.fileConfig`. O PyInstaller nao
        # enxerga isso -- o import esta dentro do env.py, que e carregado como
        # script em tempo de execucao, nao importado estaticamente.
        #
        # Sem estes dois, TODA migration falhava no app empacotado com
        # "No module named 'logging.config'", e o backend caia no schema de
        # emergencia em silencio. O instalador nunca era construido pelo CI, e
        # o defeito so aparecia na maquina de quem instalasse.
        'logging.config', 'logging.handlers',
        'win32crypt',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='AdriPoltronasBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # console=True: o processo e filho do Electron e reporta por stdout/stderr.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['icone_sistema.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AdriPoltronasBackend',
)
