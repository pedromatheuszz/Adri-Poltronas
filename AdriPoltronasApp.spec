# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
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
        'database', 'security', 'asaas', 'config', 'validators',
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
    name='AdriPoltronasApp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
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
    name='AdriPoltronasApp',
)
