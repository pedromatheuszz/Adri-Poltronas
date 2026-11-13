/** Ponte minima entre a interface e os controles nativos da janela. */
import { contextBridge, ipcRenderer } from 'electron';

contextBridge.exposeInMainWorld('controlesJanela', {
  minimizar: (): Promise<void> => ipcRenderer.invoke('janela:minimizar'),
  alternarMaximizada: (): Promise<void> => ipcRenderer.invoke('janela:alternar-maximizada'),
  fechar: (): Promise<void> => ipcRenderer.invoke('janela:fechar'),
  aoAlterarEstadoMaximizado: (callback: (maximizada: boolean) => void): (() => void) => {
    const listener = (_evento: Electron.IpcRendererEvent, maximizada: boolean) => callback(maximizada);
    ipcRenderer.on('janela:estado-maximizada', listener);
    return () => ipcRenderer.removeListener('janela:estado-maximizada', listener);
  },
});
