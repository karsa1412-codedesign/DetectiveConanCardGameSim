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
        j = motor.j(a.jugador)
        ap = motor.irrupcion_valida(j, c, motor._propio_contacto(j)) or c.defn.irrupcion_ap
        return tx("a_irrupcion", carta=n(a.uid), ap=ap)
    if isinstance(a, A.FinTurno):
        return tx("a_fin_turno")
    if isinstance(a, A.Declarar):
        return describir_declarar(tx, motor, a)
    if isinstance(a, A.Elegir):
        d = motor.p.pendiente.datos if motor.p.pendiente else {}
        if a.uids:
            return ", ".join(f"«{n(u)}»" for u in a.uids)
        if d.get("modo") == "opcion":
            return d["opciones"][a.opcion]
        if d.get("modo") == "manual":
            return tx("ef_hecho")
        if d.get("modo") == "si_no":
            return tx("ef_si") if a.opcion else tx("ef_no")
        return tx("ef_confirmar")
    return type(a).__name__


# ------------------------------------------------------------------ habilidades

def _lineas(texto: str) -> list[str]:
    """Líneas de habilidad, uniendo las opciones «・» a su línea (como core.habilidades)."""
    out: list[str] = []
    for l in (texto or "").splitlines():
        if not l.strip():
            continue
        if out and l.lstrip().startswith(("・", "•", "(上から", "（上から")):
            out[-1] += " " + l.strip()
        else:
            out.append(l.strip())
    return out


def linea_hab(defn, indice: int, idioma: str) -> str:
    """Texto traducido de la habilidad nº indice (o el japonés si la traducción no cuadra)."""
    ja = _lineas(defn.texto.get("ja", ""))
    trad = _lineas(defn.texto.get(idioma) or defn.texto.get("es") or "")
    if len(trad) == len(ja) and 0 <= indice < len(trad):
        return trad[indice]
    return ja[indice] if 0 <= indice < len(ja) else ""


def _corto(texto: str, n: int = 90) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= n else texto[:n - 1] + "…"


def describir_declarar(tx: Textos, motor, a: A.Declarar) -> str:
    c = motor.p.carta(a.uid)
    return tx("a_declarar", carta=c.defn.nombre_en(tx.idioma), hab=_corto(linea_hab(c.defn, a.indice, tx.idioma)))


def _rango(tx: Textos, minimo: int, maximo: int) -> str:
    if minimo == maximo:
        return tx("ef_rango_exacto", n=maximo)
    return tx("ef_rango_hasta", n=maximo)


def describir_efecto(tx: Textos, datos: dict) -> str:
    """Instrucción para el jugador según lo que pide el efecto pendiente."""
    modo = datos["modo"]
    if modo == "manual":
        return tx("ef_manual")
    if modo == "si_no":
        return tx("ef_inspiracion") if datos.get("inspiracion") else tx("ef_pregunta")
    if modo == "opcion":
        return tx("ef_opcion")
    rango = _rango(tx, datos["min"], datos["max"])
    tras = datos.get("tras")
    if tras == "descartar":
        return tx("ef_elegir_mano", rango=rango)
    if tras == "cambio":
        return tx("ef_elegir_cambio")
    if tras == "tomar":
        return tx("ef_elegir_vistas", rango=rango, resto=tx("ef_resto_fondo"))
    det = datos.get("detalle", {})
    acc = datos.get("accion", "")
    if acc == "mod":
        valor = det.get("valor", 0)
        clave = "acc_mod_contacto" if det.get("hasta") == "contacto" else "acc_mod"
        accion = tx(clave, campo={"ap": "AP", "lp": "LP", "nivel": "Nv."}.get(det.get("campo"), ""),
                    valor=f"{valor:+d}")
    elif acc == "dar_claves":
        accion = tx("acc_dar_claves", claves=", ".join(tx("clave_" + k) for k in det.get("claves", {})))
    else:
        accion = tx("acc_" + acc) if ("acc_" + acc) in tx.t else tx("acc_otro")
    return tx("ef_elegir", rango=rango, que=tx("ef_tipo_" + det.get("tipo", "carta")), accion=accion)
