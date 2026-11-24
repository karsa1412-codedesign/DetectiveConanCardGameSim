"""Textos de la interfaz por idioma y descripción legible de las acciones."""
from __future__ import annotations

import json
from pathlib import Path

from core import acciones as A


class Textos:
    def __init__(self, carpeta: Path, idioma: str = "es"):
        self.carpeta = carpeta
        self.cambiar(idioma)

    def idiomas(self) -> list[str]:
        return sorted(p.stem for p in self.carpeta.glob("*.json"))

    def cambiar(self, idioma: str):
        base = json.loads((self.carpeta / "es.json").read_text(encoding="utf-8"))
        ruta = self.carpeta / f"{idioma}.json"
        if ruta.exists():
            base.update(json.loads(ruta.read_text(encoding="utf-8")))
        self.idioma, self.t = idioma, base

    def __call__(self, clave: str, **kw) -> str:
        return self.t.get(clave, clave).format(**kw)


def describir(tx: Textos, motor, a: A.Accion) -> str:
    def n(uid):
        return motor.p.carta(uid).defn.nombre_en(tx.idioma)
    if isinstance(a, A.Mulligan):
        mano = motor.j(a.jugador).mano
        if not a.uids:
            return tx("a_mulligan_quedar")
        if len(a.uids) == len(mano):
            return tx("a_mulligan_todo")
        return tx("a_mulligan_una", carta=n(a.uids[0]))
    if isinstance(a, A.JugarCarta):
        if a.retirar is not None:
            return tx("a_jugar_cambio", carta=n(a.uid), sale=n(a.retirar))
        return tx("a_jugar", carta=n(a.uid))
    if isinstance(a, A.SiguientePista):
        return tx("a_pista")
    if isinstance(a, A.NoJugar):
        return tx("a_no_jugar")
    if isinstance(a, A.Asistir):
        return tx("a_asistir")
    if isinstance(a, A.ResolverCaso):
        return tx("a_resolver")
    if isinstance(a, A.Deducir):
        return tx("a_deducir", carta=n(a.uid), lp=motor.p.carta(a.uid).lp)
    if isinstance(a, A.PistaFalsa):
        if not a.uids:
            return tx("a_pista_falsa_no")
        return tx("a_pista_falsa", cartas=", ".join(f"«{n(u)}»" for u in a.uids))
    if isinstance(a, A.Atacar):
        if a.objetivo is None:
            return tx("a_atacar_caso", carta=n(a.atacante))
        return tx("a_atacar", carta=n(a.atacante), objetivo=n(a.objetivo))
    if isinstance(a, A.Guardia):
        if a.uid is None:
            return tx("a_guardia_no")
        return tx("a_guardia", carta=n(a.uid), ap=motor.p.carta(a.uid).ap)
    if isinstance(a, A.Contactar):
        if a.uid is None:
            return tx("a_contacto_pasar")
        c = motor.p.carta(a.uid)
        if a.modo == "disfraz":
            return tx("a_disfraz", carta=n(a.uid))
        return tx("a_irrupcion", carta=n(a.uid), ap=c.defn.irrupcion_ap)
    if isinstance(a, A.FinTurno):
        return tx("a_fin_turno")
    return type(a).__name__
