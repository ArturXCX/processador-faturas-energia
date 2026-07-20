"""
Execução do processamento em thread separada, comunicando-se com a GUI por uma
fila de eventos (a GUI faz polling com `after`, mantendo a janela responsiva).
"""
from __future__ import annotations

import queue
import threading

from ..core import controller
from ..core.controller import Job


class ProcessWorker:
    """Roda controller.processar_jobs em background e publica eventos na fila."""

    def __init__(self, jobs: list[Job]):
        self.jobs = jobs
        self.fila: queue.Queue = queue.Queue()
        self._cancelar = threading.Event()
        self._thread: threading.Thread | None = None

    # ── controle ──────────────────────────────────────────────────────────
    def iniciar(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def cancelar(self):
        self._cancelar.set()

    def ativo(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    # ── interno ───────────────────────────────────────────────────────────
    def _run(self):
        def progresso(feito, total, nome, forn, ok, msg):
            self.fila.put(("progresso", (feito, total, nome, forn, ok, msg)))

        try:
            res = controller.processar_jobs(
                self.jobs, progresso=progresso, cancelar=self._cancelar.is_set)
            self.fila.put(("concluido", res))
        except Exception as e:  # noqa: BLE001
            self.fila.put(("falha", e))

    def eventos(self):
        """Drena e devolve todos os eventos pendentes (chamada pela GUI)."""
        out = []
        try:
            while True:
                out.append(self.fila.get_nowait())
        except queue.Empty:
            pass
        return out
