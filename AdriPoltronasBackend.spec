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
    ],
    hiddenimports=[
        'database', 'notificacoes_db', 'security', 'asaas', 'config', 'validators',
        'blueprints', 'migrations_manager',
        'openpyxl', 'openpyxl.utils', 'et_xmlfile',
        'alembic', 'alembic.config', 'alembic.command',
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
