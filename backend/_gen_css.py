#!/usr/bin/env python3
"""Gera o style.css completo com suporte dark/light."""
import os

CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root, [data-theme="dark"] {
    --primary: #3b82f6;
    --primary-hover: #60a5fa;
    --bg-main: linear-gradient(-45deg, #080d1a, #0f172a, #04060d);
    --text-main: #f8fafc;
    --text-muted: #94a3b8;
    --glass-bg: rgba(30, 41, 59, 0.7);
    --glass-border: rgba(255, 255, 255, 0.08);
    --input-bg: rgba(15, 23, 42, 0.6);
    --card-hover-shadow: 0 20px 45px rgba(0, 0, 0, 0.45);
    --table-row-bg: rgba(30, 41, 59, 0.4);
    --table-row-hover: rgba(45, 59, 82, 0.85);
    --nav-tab-bg: rgba(30, 41, 59, 0.5);
    --nav-tab-active-bg: rgba(59, 130, 246, 0.2);
    --kbd-bg: rgba(255,255,255,0.08);
    --shadow-card: 0 15px 35px rgba(0, 0, 0, 0.2);
}

[data-theme="light"] {
    --primary: #2563eb;
    --primary-hover: #3b82f6;
    --bg-main: linear-gradient(-45deg, #f8fafc, #e2e8f0, #f1f5f9);
    --text-main: #1e293b;
    --text-muted: #64748b;
    --glass-bg: rgba(255, 255, 255, 0.85);
    --glass-border: rgba(0, 0, 0, 0.08);
    --input-bg: rgba(241, 245, 249, 0.8);
    --card-hover-shadow: 0 20px 45px rgba(0, 0, 0, 0.1);
    --table-row-bg: rgba(241, 245, 249, 0.6);
    --table-row-hover: rgba(226, 232, 240, 0.9);
    --nav-tab-bg: rgba(241, 245, 249, 0.7);
    --nav-tab-active-bg: rgba(37, 99, 235, 0.1);
    --kbd-bg: rgba(0,0,0,0.06);
    --shadow-card: 0 15px 35px rgba(0, 0, 0, 0.06);
}

* { margin: 0; padding: 0; box-sizing: border-box; font-family: 'Inter', sans-serif; }

body {
    background: var(--bg-main);
    background-size: 200% 200%;
    animation: gradientBG 20s ease infinite;
    color: var(--text-main);
    min-height: 100vh;
    padding: 1.5rem;
    position: relative;
    z-index: 1;
    transition: background 0.5s ease, color 0.5s ease;
}

@keyframes gradientBG { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }

body::before {
    content: '';
    position: fixed;
    top: 0; left: 0; width: 100vw; height: 100vh;
    background-image: linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
    background-size: 32px 32px;
    z-index: -2;
    pointer-events: none;
}

[data-theme="light"] body::before {
    background-image: linear-gradient(rgba(0,0,0,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(0,0,0,0.03) 1px, transparent 1px);
}

.container { max-width: 1200px; margin: 0 auto; animation: fadeIn 0.8s ease-out; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(20px); } to { opacity: 1; transform: translateY(0); } }

.tab-content { display: none; }
.tab-content.active { display: block; }

.main-header {
    display: flex; align-items: center; justify-content: space-between;
    gap: 1rem; margin-bottom: 1.5rem; padding: 1rem 1.5rem;
    background: var(--glass-bg); backdrop-filter: blur(16px);
    border: 1px solid var(--glass-border); border-radius: 20px;
}

.header-left h1 {
    font-size: 1.5rem; font-weight: 700;
    background: linear-gradient(135deg, var(--primary), #a78bfa);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text;
}

.header-right { display: flex; align-items: center; gap: 0.75rem; }
.header-logo { max-height: 48px; width: auto; object-fit: contain; border-radius: 12px; }

.btn-icon {
    width: 40px; height: 40px; border-radius: 12px;
    border: 1px solid var(--glass-border); background: var(--nav-tab-bg);
    color: var(--text-main); cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: all 0.3s ease; position: relative;
}
.btn-icon:hover { background: var(--primary); color: white; transform: translateY(-2px); }

.notif-badge {
    position: absolute; top: -4px; right: -4px; min-width: 18px; height: 18px;
    padding: 0 5px; background: #ef4444; color: white;
    font-size: 0.65rem; font-weight: 700; border-radius: 10px;
    display: flex; align-items: center; justify-content: center;
}

.nav-tabs {
    display: flex; gap: 0.5rem; margin-bottom: 1.5rem; padding: 0.4rem;
    background: var(--glass-bg); backdrop-filter: blur(16px);
    border: 1px solid var(--glass-border); border-radius: 16px; overflow-x: auto;
}

.nav-tab {
    flex: 1; min-width: 0; padding: 0.7rem 1rem;
    border: none; border-radius: 12px; background: transparent;
    color: var(--text-muted); font-weight: 600; font-size: 0.85rem;
    cursor: pointer; display: flex; align-items: center; justify-content: center;
    gap: 0.4rem; transition: all 0.3s ease; white-space: nowrap;
}
.nav-tab:hover { background: var(--nav-tab-bg); color: var(--text-main); }
.nav-tab.active { background: var(--nav-tab-active-bg); color: var(--primary); box-shadow: 0 2px 8px rgba(59, 130, 246, 0.15); }
.nav-tab svg { flex-shrink: 0; }

.card {
    background: var(--glass-bg); backdrop-filter: blur(16px);
    border: 1px solid var(--glass-border); border-radius: 24px;
    padding: 2rem; margin-bottom: 1.5rem;
    box-shadow: var(--shadow-card);
    transition: box-shadow 0.4s ease, border-color 0.4s ease, background 0.3s ease;
}
.card:hover { box-shadow: var(--card-hover-shadow); border-color: rgba(59, 130, 246, 0.3); }
.card-title { font-size: 1rem; font-weight: 700; color: var(--text-main); margin-bottom: 1rem; }

.dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
.card-metrica { display: flex; align-items: center; gap: 1rem; padding: 1.5rem; }
.metrica-icon { width: 48px; height: 48px; border-radius: 14px; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.metrica-info { display: flex; flex-direction: column; }
.metrica-valor { font-size: 1.5rem; font-weight: 700; color: var(--text-main); }
.metrica-label { font-size: 0.8rem; color: var(--text-muted); margin-top: 2px; }
.dashboard-charts { display: flex; gap: 1rem; margin-bottom: 1.5rem; }
.chart-card { flex: 1; min-width: 0; }
.chart-card canvas { max-height: 300px; }

.form-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 1.2rem; margin-bottom: 1.5rem; }
.input-group { display: flex; flex-direction: column; gap: 0.5rem; }
label { font-size: 0.85rem; font-weight: 600; color: var(--text-muted); margin-left: 4px; }

input, select, textarea {
    padding: 0.8rem 1rem; border-radius: 12px;
    border: 1px solid var(--glass-border); background: var(--input-bg);
    font-size: 0.95rem; color: var(--text-main);
    transition: all 0.3s ease; outline: none;
}
input::placeholder, textarea::placeholder { color: #475569; }
[data-theme="light"] input::placeholder, [data-theme="light"] textarea::placeholder { color: #94a3b8; }
input:focus, select:focus, textarea:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15); }
textarea { resize: vertical; font-family: inherit; }

select {
    cursor: pointer; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 24 24' fill='none' stroke='%2394a3b8' stroke-width='2'%3E%3Cpolyline points='6 9 12 15 18 9'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 12px center; padding-right: 36px;
}

.search-bar input {
    width: 100%; max-width: 400px;
    background-image: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="%2394a3b8" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>');
    background-repeat: no-repeat; background-position: 12px center; padding-left: 40px;
}

.btn {
    padding: 0.6rem 1.2rem; border: none; border-radius: 10px;
    font-weight: 600; font-size: 0.85rem; cursor: pointer;
    display: inline-flex; align-items: center; justify-content: center;
    gap: 0.5rem; transition: all 0.3s ease; color: white;
}
.btn-primary { background: linear-gradient(135deg, #2563eb, #3b82f6); box-shadow: 0 4px 15px rgba(37, 99, 235, 0.3); }
.btn-primary:hover { transform: translateY(-2px); box-shadow: 0 8px 25px rgba(37, 99, 235, 0.4); }
.btn-ia {
    padding: 0.2rem 0.5rem; border: 1px solid rgba(139, 92, 246, 0.4);
    border-radius: 6px; background: rgba(139, 92, 246, 0.15);
    color: #a78bfa; font-size: 0.7rem; font-weight: 600; cursor: pointer;
    transition: all 0.2s ease; margin-left: 6px;
}
.btn-ia:hover { background: rgba(139, 92, 246, 0.3); transform: scale(1.05); }

.btn-select-mode {
    background: var(--nav-tab-bg); border: 1px solid var(--glass-border);
    color: var(--text-main); padding: 0.6rem 1rem; border-radius: 10px;
    font-size: 0.85rem; font-weight: 600; cursor: pointer;
    display: inline-flex; align-items: center; gap: 0.5rem; transition: all 0.3s ease;
}
.btn-select-mode:hover { background: rgba(51, 65, 85, 0.5); transform: translateY(-2px); }
.btn-select-mode.ativo { background: linear-gradient(135deg, #2563eb, #3b82f6); color: white; border-color: #3b82f6; }

.btn-microsoft { background: linear-gradient(135deg, #2563eb, #3b82f6); }
.btn-microsoft.conectado { background: linear-gradient(135deg, #059669, #10b981); }
.btn-excel { background: rgba(51, 65, 85, 0.6); }
.btn-excel:not(:disabled):hover { background: linear-gradient(135deg, #059669, #10b981); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }

.btn.carregando { position: relative; pointer-events: none; }
.btn.carregando::before { content: ''; width: 16px; height: 16px; border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff; border-radius: 50%; animation: spin 0.7s linear infinite; flex-shrink: 0; }
@keyframes spin { to { transform: rotate(360deg); } }

table { width: 100%; border-collapse: separate; border-spacing: 0 6px; }
th { padding: 0.8rem 1rem; color: var(--text-muted); font-weight: 700; font-size: 0.75rem; text-transform: uppercase; }
td { padding: 0.8rem 1rem; background: var(--table-row-bg); transition: all 0.3s ease; }
tbody tr:hover td { background: var(--table-row-hover); }
td:first-child { border-top-left-radius: 12px; border-bottom-left-radius: 12px; }
td:last-child { border-top-right-radius: 12px; border-bottom-right-radius: 12px; }
th.col-checkbox, td.col-checkbox { display: none !important; width: 0; padding: 0; }
body.modo-selecao-ativo th.col-checkbox, body.modo-selecao-ativo td.col-checkbox { display: table-cell !important; width: 48px; padding: 0 0.6rem; text-align: center; }

.badge-entrega, .badge-retirada { display: inline-block; padding: 0.25rem 0.7rem; border-radius: 8px; font-size: 0.75rem; font-weight: 600; white-space: nowrap; }
.badge-entrega { background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }
.badge-retirada { background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
.badge-pendente { background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3); }
.badge-recebido { background: rgba(16,185,129,0.15); color: #10b981; border: 1px solid rgba(16,185,129,0.3); }
.badge-atrasado { background: rgba(239,68,68,0.15); color: #ef4444; border: 1px solid rgba(239,68,68,0.3); }
.badge-cancelado { background: rgba(100,116,139,0.15); color: #64748b; border: 1px solid rgba(100,116,139,0.3); }

.modal-overlay { position: fixed; inset: 0; z-index: 9999; display: flex; align-items: center; justify-content: center; background: rgba(0,0,0,0.6); backdrop-filter: blur(6px); opacity: 0; visibility: hidden; transition: all 0.3s ease; }
.modal-overlay.ativo { opacity: 1; visibility: visible; }
.modal-box { background: var(--glass-bg); backdrop-filter: blur(20px); border: 1px solid var(--glass-border); border-radius: 20px; padding: 2rem; max-width: 420px; width: 90%; text-align: center; transform: scale(0.85) translateY(20px); transition: transform 0.35s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.25s ease; opacity: 0; }
.modal-overlay.ativo .modal-box { transform: scale(1) translateY(0); opacity: 1; }
.modal-icon { width: 56px; height: 56px; margin: 0 auto 1rem; background: rgba(239,68,68,0.15); border-radius: 50%; display: flex; align-items: center; justify-content: center; border: 2px solid rgba(239,68,68,0.3); color: #ef4444; }
.modal-title { font-size: 1.1rem; font-weight: 700; margin-bottom: 0.5rem; }
.modal-msg { font-size: 0.9rem; color: var(--text-muted); margin-bottom: 1.5rem; line-height: 1.5; }
.modal-actions { display: flex; gap: 0.75rem; justify-content: center; }
.modal-btn { padding: 0.6rem 1.5rem; border: none; border-radius: 12px; font-weight: 600; font-size: 0.9rem; cursor: pointer; transition: all 0.25s ease; color: white; }
.modal-btn-cancelar { background: rgba(71, 85, 105, 0.8); }
.modal-btn-cancelar:hover { background: rgba(100, 116, 139, 0.9); }
.modal-btn-confirmar { background: linear-gradient(135deg, #dc2626, #ef4444); box-shadow: 0 4px 15px rgba(239,68,68,0.3); }
.modal-btn-confirmar:hover { transform: translateY(-2px); }

#toast { visibility: hidden; min-width: 280px; background: var(--glass-bg); backdrop-filter: blur(15px); border: 1px solid var(--glass-border); color: #fff; text-align: center; border-radius: 100px; padding: 14px 24px; position: fixed; z-index: 10000; bottom: 40px; left: 50%; transform: translate(-50%, 100px); font-weight: 500; font-size: 0.9rem; opacity: 0; transition: all 0.5s cubic-bezier(0.68, -0.55, 0.265, 1.55); }
#toast.show { visibility: visible; transform: translate(-50%, 0); opacity: 1; }

.filtro-dropdown { position: absolute; top: calc(100% + 8px); right: 0; min-width: 240px; background: var(--glass-bg); backdrop-filter: blur(20px); border: 1px solid var(--glass-border); border-radius: 16px; padding: 1rem; z-index: 100; opacity: 0; visibility: hidden; transform: translateY(-8px); transition: all 0.25s ease; box-shadow: 0 20px 50px rgba(0,0,0,0.3); }
.filtro-dropdown.ativo { opacity: 1; visibility: visible; transform: translateY(0); }
.filtro-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--glass-border); }
.filtro-header span { font-weight: 700; font-size: 0.85rem; }
.filtro-limpar { background: none; border: none; color: var(--primary); font-size: 0.8rem; font-weight: 600; cursor: pointer; padding: 0.2rem 0.5rem; border-radius: 6px; }
.filtro-limpar:hover { background: rgba(59,130,246,0.15); }
.filtro-section { margin-bottom: 0.75rem; }
.filtro-label { font-size: 0.7rem; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 0.4rem; letter-spacing: 0.05em; }
.filtro-option { display: flex; align-items: center; gap: 0.5rem; padding: 0.35rem 0.5rem; border-radius: 8px; cursor: pointer; }
.filtro-option:hover { background: rgba(255,255,255,0.05); }
.filtro-cidade-item { display: flex; align-items: center; gap: 0.5rem; padding: 0.3rem 0.5rem; border-radius: 6px; font-size: 0.8rem; cursor: pointer; }
.filtro-cidade-item:hover { background: rgba(255,255,255,0.05); }

.notificacoes-panel { position: fixed; top: 1rem; right: 1rem; width: 340px; max-height: 400px; background: var(--glass-bg); backdrop-filter: blur(20px); border: 1px solid var(--glass-border); border-radius: 16px; z-index: 9998; overflow: hidden; box-shadow: 0 20px 50px rgba(0,0,0,0.3); }
.notificacoes-header { display: flex; justify-content: space-between; align-items: center; padding: 1rem; border-bottom: 1px solid var(--glass-border); font-weight: 700; font-size: 0.9rem; }
.notif-close { background: none; border: none; color: var(--text-muted); font-size: 1.2rem; cursor: pointer; padding: 0.2rem; }
.notif-close:hover { color: var(--text-main); }
.notificacoes-lista { padding: 0.5rem; max-height: 340px; overflow-y: auto; }
.notificacao-item { padding: 0.75rem; border-radius: 10px; margin-bottom: 0.4rem; font-size: 0.85rem; color: var(--text-main); border-left: 3px solid var(--primary); background: rgba(255,255,255,0.03); }
.notificacao-item.notif-aviso { border-left-color: #f59e0b; }
.notificacao-item.notif-erro { border-left-color: #ef4444; }
.notificacao-item.notif-ok { border-left-color: #10b981; }
.notificacao-item small { display: block; color: var(--text-muted); font-size: 0.75rem; margin-top: 0.3rem; }

.keyboard-shortcuts-bar { position: fixed; bottom: 0; left: 0; right: 0; display: flex; justify-content: center; gap: 1.5rem; padding: 0.5rem 1rem; background: var(--glass-bg); backdrop-filter: blur(16px); border-top: 1px solid var(--glass-border); font-size: 0.7rem; color: var(--text-muted); z-index: 100; }
.keyboard-shortcuts-bar kbd { display: inline-block; padding: 0.15rem 0.4rem; background: var(--kbd-bg); border-radius: 4px; font-family: monospace; font-size: 0.7rem; border: 1px solid var(--glass-border); }

input[type="checkbox"] { appearance: none; -webkit-appearance: none; width: 16px; height: 16px; min-width: 16px; border: 1.5px solid rgba(255,255,255,0.3); border-radius: 4px; background: rgba(255,255,255,0.05); cursor: pointer; display: inline-block; vertical-align: middle; transition: all 0.2s ease; }
input[type="checkbox"]:checked { background-color: #2563eb; border-color: #3b82f6; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E"); background-size: 10px 10px; background-position: center; background-repeat: no-repeat; }
[data-theme="light"] input[type="checkbox"] { border-color: rgba(0,0,0,0.2); background: rgba(0,0,0,0.03); }
[data-theme="light"] input[type="checkbox"]:checked { background-color: #2563eb; border-color: #3b82f6; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E"); }

::-webkit-scrollbar { height: 6px; width: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #475569; border-radius: 10px; }
::-webkit-scrollbar-thumb:hover { background: #64748b; }

.historico-item { padding: 0.75rem 1rem; border-left: 3px solid var(--glass-border); margin-bottom: 0.5rem; border-radius: 0 10px 10px 0; background: rgba(255,255,255,0.02); }
.historico-item.h-criacao { border-left-color: #10b981; }
.historico-item.h-atualizacao { border-left-color: #3b82f6; }
.historico-item.h-exclusao { border-left-color: #ef4444; }
.historico-item.h-importacao { border-left-color: #8b5cf6; }
.historico-item.h-pagamento { border-left-color: #f59e0b; }
.historico-item strong { font-size: 0.85rem; }
.historico-item .h-detalhes { font-size: 0.8rem; color: var(--text-muted); margin-top: 0.25rem; }
.historico-item .h-data { font-size: 0.75rem; color: var(--text-muted); margin-top: 0.3rem; }

.regiao-item { display: flex; justify-content: space-between; align-items: center; padding: 0.75rem 1rem; margin-bottom: 0.4rem; border-radius: 10px; background: rgba(255,255,255,0.02); }
.regiao-item .regiao-nome { font-weight: 600; font-size: 0.9rem; }
.regiao-item .regiao-stats { display: flex; gap: 0.75rem; font-size: 0.8rem; color: var(--text-muted); }

.form-actions { margin-top: 1.5rem; display: flex; gap: 1rem; }
.btn-cancelar { background: #64748b; }
.btn-cancelar:hover { background: #475569; }
.input-group-obs { margin-top: 1rem; }
.obs-counter { font-size: 0.75rem; color: var(--text-muted); text-align: right; }

.modal-input { width: 100%; padding: 0.8rem 1rem; border-radius: 10px; border: 1px solid var(--glass-border); background: var(--input-bg); color: var(--text-main); font-size: 1rem; outline: none; margin-bottom: 1.5rem; box-sizing: border-box; }
.modal-input:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15); }

@keyframes fadeBtn { 0% { opacity: 0; transform: translateY(-4px); } 100% { opacity: 1; transform: translateY(0); } }
.btn-fade { animation: fadeBtn 0.3s ease both; }
@keyframes fadeTitle { 0% { opacity: 0; transform: translateX(-6px); } 100% { opacity: 1; transform: translateX(0); } }
.title-fade #formTitleText { animation: fadeTitle 0.3s ease both; }
.title-icon { stroke: var(--primary); transition: all 0.4s ease; }
.title-icon.editando { stroke: #60a5fa; animation: pulseIcon 2s ease-in-out infinite; }
@keyframes pulseIcon { 0%, 100% { transform: scale(1); } 50% { transform: scale(1.1); } }
body.modo-selecao-ativo tbody tr { animation: rowFadeIn 0.35s ease both; }
@keyframes rowFadeIn { from { opacity: 0.5; transform: translateX(-6px); } to { opacity: 1; transform: translateX(0); } }
body.saindo-selecao tbody tr { animation: rowFadeOut 0.3s ease both !important; }
@keyframes rowFadeOut { from { opacity: 1; transform: translateX(0); } to { opacity: 0.3; transform: translateX(8px); } }

@media (max-width: 768px) {
    body { padding: 1rem; }
    .dashboard-charts { flex-direction: column; }
    .nav-tabs { gap: 0.25rem; }
    .nav-tab { font-size: 0.75rem; padding: 0.5rem 0.7rem; }
    .keyboard-shortcuts-bar { display: none; }
    .notificacoes-panel { width: calc(100vw - 2rem); right: 1rem; }
}
""".strip()

if __name__ == '__main__':
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'frontend', 'css', 'style.css')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(CSS)
    print(f'Written {len(CSS)} chars to style.css')
