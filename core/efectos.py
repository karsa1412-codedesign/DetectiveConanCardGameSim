"""Ejecución de habilidades y efectos (reglamento p. 14, 21-25).

El Motor hereda de esta clase. Aquí está una función por cada regla de efecto
(«_ef_<op>») y por cada cosa que un efecto puede hacer a una carta («_hacer_<accion>»),
además de:
  · las condiciones de los iconos y de las frases («_cumple»),
  · los filtros de cartas («_encaja»),
  · la cola de habilidades disparadas y la pila de ejecuciones («_procesar»),
  · el uso de 【宣言】 («_a_declarar») y las decisiones del jugador («_a_elegir»),
  · los efectos permanentes, recalculados tras cada paso («_recalcular»).

Cuando un paso necesita que alguien elija (objetivos, sí/no, una opción, aplicar algo a
mano), deja una Pendiente «efecto» con los datos para que la interfaz haga el foco en las
cartas válidas.
"""
from __future__ import annotations

from itertools import combinations

from . import acciones as A
from . import habilidades as H
from .cartas import EVENTO, PERSONAJE, PISTA_FALSA
from .estado import (ACTIVO, ATURDIDO, DORMIDO, HASTA_AURA, HASTA_CONTACTO, HASTA_TURNO, Carta, Disparo,
                     Ejecucion, Mod, Pendiente)

MAX_ESCENA = 5


class EfectosMixin:
    """Se mezcla con Motor (core/reglas.py)."""

    # ------------------------------------------------------------ consultas

    def habs(self, c: Carta) -> tuple:
        """Habilidades de una carta, incluidas las de los Eventos fijados a ella (p. 23)."""
        propias = H.habilidades(c.defn)
        fijadas = tuple(h for d in c.debajo if d.defn.tipo == EVENTO
                        for h in H.habilidades(d.defn) if h.fijada)
        return tuple(h for h in propias if not h.fijada) + fijadas

    def hab(self, c: Carta, indice: int) -> H.Habilidad | None:
        for h in self.habs(c):
            if h.indice == indice:
                return h
        return None

    def tiene(self, c: Carta, clave: str) -> bool:
        return clave in self.claves(c)

    def valor_clave(self, c: Carta, clave: str) -> int:
        v = self.claves(c).get(clave, 0)
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    def claves(self, c: Carta) -> dict:
        """Palabras clave que tiene ahora la carta (impresas, condicionadas y dadas por efectos)."""
        habs = self.habs(c)
        if habs:
            out = {}
            for h in habs:
                if h.clase == H.CLAVE and self._cumple(h.condiciones, c.dueno, c, {}):
                    out.update(h.claves)
        else:
            out = dict(c.defn.palabras_clave)
        out.update(c.claves_extra())
        return out

    def rasgos(self, c: Carta) -> list:
        return list(c.defn.rasgos_ja) + list(c.defn.rasgos) + c.rasgos_extra()

    def nombre_ja(self, c: Carta) -> str:
        return c.defn.nombre.get("ja") or c.defn.nombre_en("es")

    @staticmethod
    def _mismo_nombre(nombre: str, buscado: str) -> bool:
        return nombre == buscado or nombre.split("（")[0] == buscado

    def _zona_de(self, c: Carta) -> str:
        j = self.j(c.dueno)
        for nombre in ("escena", "mano", "descarte", "pruebas", "file", "mazo", "zona_companero"):
            if c in getattr(j, nombre):
                return nombre
        if c is j.caso:
            return "caso"
        if c is j.companero:
            return "companero"
        return "otra"

    # ------------------------------------------------------------ filtros (p. 22)

    def _encaja(self, c: Carta, f: dict, fuente: Carta | None, jugador: int, ctx: dict) -> bool:
        d = c.defn
        tipo = f.get("tipo", "carta")
        if tipo == "personaje" and d.tipo != PERSONAJE:
            return False
        if tipo == "evento" and d.tipo != EVENTO:
            return False
        if f.get("no_esta") and fuente is not None and c is fuente:
            return False
        nombre = self.nombre_ja(c)
        if "nombres" in f or "rasgos" in f:
            ok_n = any(self._mismo_nombre(nombre, n) for n in f.get("nombres", []))
            ok_r = any(r in self.rasgos(c) for r in f.get("rasgos", []))
            if not (ok_n or ok_r):
                return False
        if any(self._mismo_nombre(nombre, n) for n in f.get("no_nombres", [])):
            return False
        if "colores" in f and not set(f["colores"]) & set(d.colores):
            return False
        if "sin_colores" in f and not set(d.colores) - set(f["sin_colores"]):
            return False
        nivel = c.nivel
        if "nivel_max" in f and nivel > f["nivel_max"]:
            return False
        if "nivel_min" in f and nivel < f["nivel_min"]:
            return False
        if "niveles" in f and nivel not in f["niveles"]:
            return False
        if f.get("nivel_max_file") and nivel > self.j(jugador).cartas_file:
            return False
        if "ap_max" in f and c.ap > f["ap_max"]:
            return False
        if "ap_min" in f and c.ap < f["ap_min"]:
            return False
        if f.get("ap_max_esta") and fuente is not None and c.ap > fuente.ap:
            return False
        if "lp" in f and c.lp != f["lp"]:
            return False
        if "lp_min" in f and c.lp < f["lp_min"]:
            return False
        if "estado" in f and c.estado != f["estado"]:
            return False
        if f.get("irrupcion") and not (d.irrupcion_ap is not None or
                                       any(h.clase == H.IRRUPCION for h in H.habilidades(d))):
            return False
        return True

    # ------------------------------------------------------------ condiciones (p. 24)

    def _cumple(self, conds, jugador: int, fuente: Carta | None, ctx: dict) -> bool:
        return all(self._cond(c, jugador, fuente, ctx) for c in conds or ())

    def _cond(self, c: tuple, jugador: int, fuente: Carta | None, ctx: dict) -> bool:
        p = self.p
        j = self.j(jugador)
        r = self.j(p.rival(jugador))
        tipo = c[0]
        if tipo == "companero_color":
            return set(c[1]) <= set(j.companero.defn.colores)
        if tipo == "caso_colores":
            return set(c[1]) <= set(j.caso.defn.colores)
        if tipo == "caso_rasgo":
            return c[1] in self.rasgos(j.caso) or c[1] in self.nombre_ja(j.caso)
        if tipo == "caso_solo_colores":
            return set(j.caso.defn.colores) <= set(c[1])
        if tipo == "vinculo":
            return any(self._mismo_nombre(self.nombre_ja(x), c[1]) for x in j.escena)
        if tipo == "file":
            return j.cartas_file >= c[1]
        if tipo == "file_max":
            return j.cartas_file <= c[1]
        if tipo == "debajo":
            return fuente is not None and len(fuente.debajo) >= c[1]
        if tipo == "resolucion":
            return j.caso_resuelto == c[1]
        if tipo == "turno":
            return (p.activo == jugador) == (c[1] == "propio")
        if tipo in ("hay_en_escena", "no_hay_en_escena"):
            lado = j if c[1] == "propio" else r
            excluir = len(c) > 4 and c[4]
            n = sum(1 for x in lado.escena if self._encaja(x, c[2], fuente, jugador, ctx)
                    and not (excluir and x is fuente))
            minimo = c[3] if len(c) > 3 else 1
            return (n >= minimo) if tipo == "hay_en_escena" else n == 0
        if tipo == "pruebas":
            return len((j if c[1] == "propio" else r).pruebas) >= c[2]
        if tipo == "mano":
            return len(j.mano) >= c[1] if c[2] == "min" else len(j.mano) <= c[1]
        if tipo == "en_descarte":
            return sum(1 for x in j.descarte if self._encaja(x, c[1], fuente, jugador, ctx)) >= c[2]
        if tipo == "rastro":
            return j.rastro_descubierto == c[1]
        if tipo == "hecho":
            return bool(ctx.get("hecho"))
        if tipo == "hecho_nombre":
            u = ctx.get("ultima")
            return u is not None and self._encaja(p.carta(u), c[1], fuente, jugador, ctx)
        if tipo == "hecho_nivel":
            u = ctx.get("ultima")
            return u is not None and p.carta(u).nivel >= c[1]
        if tipo == "por_efecto":
            return fuente is not None and fuente.por_efecto
        if tipo == "revelada":
            u = ctx.get("revelada")
            return u is not None and self._encaja(p.carta(u), c[1], fuente, jugador, ctx)
        if tipo == "objetivo_irrupcion":
            u = ctx.get("objetivo")
            return u is not None and self._encaja(p.carta(u), c[1], fuente, jugador, ctx)
        return True   # condición que el intérprete no reconoce: no bloquea

    # ------------------------------------------------------------ disparos y cola (p. 22)

    def _disparar(self, clase: str, c: Carta, evento: str = "", ctx: dict | None = None,
                  opcional: bool = False):
        """Añade a la cola las habilidades de c de esa clase cuyas condiciones se cumplen."""
        for h in self.habs(c):
            if h.clase != clase or (evento and h.evento != evento):
                continue
            if not self._cumple(h.condiciones, c.dueno, c, ctx or {}):
                continue
            if h.limite is not None and self.p.usos.get((c.uid, h.indice), 0) >= h.limite:
                continue
            self.p.cola.append(Disparo(c.uid, h.indice, c.dueno, dict(ctx or {}), opcional))
            self._log(f"Se dispara una habilidad de {self.nombre(c)}.")

    def _esperar(self, pend: Pendiente):
        """Deja una decisión básica para cuando se hayan resuelto los efectos pendientes."""
        if self.p.cola or self.p.pila:
            self.p.diferida = ("pendiente", pend)
        else:
            self.p.pendiente = pend

    def efectos_en_curso(self) -> bool:
        return bool(self.p.cola or self.p.pila)

    def _procesar(self):
        """Resuelve pasos hasta que alguien tenga que decidir o no quede nada."""
        p = self.p
        for _ in range(10_000):
            self._recalcular()
            if p.ganador is not None or p.pendiente is not None:
                return
            if p.pila:
                e = p.pila[-1]
                if e.i >= len(e.pasos):
                    p.pila.pop()
                    self._fin_ejecucion(e)
                    continue
                paso = e.pasos[e.i]
                e.i += 1
                fuente = p.carta(e.fuente)
                if not self._cumple(paso.get("si"), e.jugador, fuente, e.ctx):
                    continue
                fn = getattr(self, "_ef_" + paso["op"], None)
                if fn is None:
                    self._ef_manual(e, {"op": "manual", "texto": str(paso)})
                else:
                    fn(e, paso)
                continue
            if p.cola:
                # p. 22: primero las del jugador del turno
                d = next((x for x in p.cola if x.jugador == p.activo), p.cola[0])
                p.cola.remove(d)
                self._iniciar_disparo(d)
                continue
            if p.diferida:
                tipo, dato = p.diferida
                p.diferida = None
                if tipo == "pendiente":
                    p.pendiente = dato
                elif tipo == "fin_turno":
                    self._cerrar_turno()
                elif tipo == "resolver_contacto":
                    self._resolver_contacto()
                continue
            return

    def _iniciar_disparo(self, d: Disparo):
        c = self.p.carta(d.uid)
        h = self.hab(c, d.indice)
        if h is None:
            return
        if h.limite is not None:
            k = (c.uid, h.indice)
            if self.p.usos.get(k, 0) >= h.limite:
                return
            self.p.usos[k] = self.p.usos.get(k, 0) + 1
        pasos = list(h.pasos)
        if d.opcional:
            pasos = [{"op": "preguntar", "texto": "【ヒラメキ】"}] + [dict(x, si=list(x.get("si", [])) + [("hecho",)])
                                                                   for x in pasos]
        self._log(f"Se resuelve la habilidad de {self.nombre(c)}.")
        self.p.pila.append(Ejecucion(c.uid, d.jugador, pasos, self._titulo(c, h),
                                     ctx=dict(d.ctx, hecho=True, indice=h.indice)))

    def _titulo(self, c: Carta, h: H.Habilidad) -> str:
        return f"{self.nombre(c)} · {h.texto}"

    def _fin_ejecucion(self, e: Ejecucion):
        """Al terminar: las cartas vistas vuelven al mazo y el Evento usado va a su sitio."""
        j = self.j(e.jugador)
        for u in e.ctx.pop("vistas", []):
            j.mazo.append(self.p.carta(u))     # sin elegir: vuelven arriba en el mismo orden
        if e.ctx.get("reveladas"):
            self._ef_fin_revelar(e, {})
        ev = e.ctx.get("evento")
        if ev is not None:
            c = self.p.carta(ev)
            if not e.ctx.get("fijado"):
                c.limpiar()
                self.j(c.dueno).descarte.append(c)

    # ------------------------------------------------------------ elecciones

    def _pedir(self, e: Ejecucion, quien: int, datos: dict):
        datos = dict(datos, fuente=e.fuente, titulo=e.titulo, indice=e.ctx.get("indice"))
        self.p.pendiente = Pendiente("efecto", quien, datos)
        e.ctx["espera"] = datos

    def _a_elegir(self, a: A.Elegir):
        p = self.p
        pend = p.pendiente
        if not p.pila:
            raise self.Error("No hay ningún efecto en curso.")
        e = p.pila[-1]
        d = pend.datos
        modo = d["modo"]
        if modo == "elegir":
            uids = tuple(a.uids)
            if len(set(uids)) != len(uids) or any(u not in d["opciones"] for u in uids):
                raise self.Error("Esa carta no se puede elegir para este efecto.")
            if not d["min"] <= len(uids) <= d["max"]:
                raise self.Error(f"Elige entre {d['min']} y {d['max']} cartas.")
            p.pendiente = None
            getattr(self, "_tras_" + d["tras"])(e, d, [p.carta(u) for u in uids])
        elif modo in ("si_no", "opcion", "manual", "numero"):
            n = len(d.get("opciones", [])) or 2
            if modo in ("si_no", "manual"):
                n = 2
            if not 0 <= a.opcion < n:
                raise self.Error("Opción no válida.")
            p.pendiente = None
            getattr(self, "_tras_" + d["tras"])(e, d, a.opcion)
        self._procesar()

    def legales_efecto(self) -> list:
        d = self.p.pendiente.datos
        q = self.p.pendiente.jugador
        if d["modo"] == "elegir":
            ops, out = d["opciones"], []
            for n in range(d["min"], d["max"] + 1):
                combos = list(combinations(ops, n))
                out += [A.Elegir(q, tuple(x)) for x in combos[:60]]
            return out
        if d["modo"] in ("si_no",):
            return [A.Elegir(q, (), 1), A.Elegir(q, (), 0)]
        if d["modo"] == "manual":
            return [A.Elegir(q, (), 1)]
        return [A.Elegir(q, (), i) for i in range(len(d["opciones"]))]

    # ------------------------------------------------------------ pasos (una función por regla)

    def _quien(self, e: Ejecucion, paso: dict) -> int:
        return self.p.rival(e.jugador) if paso.get("quien") == "rival" else e.jugador

    def _ef_manual(self, e: Ejecucion, paso: dict):
        """Lo que el intérprete no entiende: se muestra y el jugador lo aplica a mano."""
        self._pedir(e, e.jugador, {"modo": "manual", "texto": paso["texto"], "tras": "nada"})

    def _tras_nada(self, e, d, valor):
        pass

    def _ef_robar(self, e, paso):
        j = self.j(self._quien(e, paso))
        self._robar(j, paso["n"])
        self._log(f"Jugador {j.idx + 1} roba {paso['n']} carta(s).")

    def _ef_robar_fondo(self, e, paso):
        j = self.j(e.jugador)
        for _ in range(paso["n"]):
            if j.mazo:
                j.mano.append(j.mazo.pop(0))

    def _ef_robar_hasta(self, e, paso):
        j = self.j(e.jugador)
        if len(j.mano) < paso["n"]:
            self._robar(j, paso["n"] - len(j.mano))

    def _ef_todas(self, e, paso):
        for j in self.p.jugadores:
            for c in list(j.escena):
                self._hacer(e, paso, c)

    def _ef_file_a_mano(self, e, paso):
        j = self.j(e.jugador)
        for _ in range(min(paso["n"], len(j.file))):
            j.mano.append(j.file.pop())
        e.ctx["hecho"] = True

    def _ef_ganar_pruebas(self, e, paso):
        self._ganar_pruebas(self.j(self._quien(e, paso)), paso["n"])

    def _ef_moler(self, e, paso):
        j = self.j(self._quien(e, paso))
        for _ in range(paso["n"]):
            c = self._sacar_mazo(j)
            if c is None:
                break
            c.limpiar()
            j.descarte.append(c)
        self._log(f"Jugador {j.idx + 1} retira {paso['n']} carta(s) de arriba del mazo.")

    def _ef_barajar(self, e, paso):
        self.p.rng.shuffle(self.j(e.jugador).mazo)

    def _ef_ganar(self, e, paso):
        self._fin(e.jugador, f"Efecto de {self.nombre(self.p.carta(e.fuente))}.")

    def _ef_ver_mano_rival(self, e, paso):
        r = self.j(self.p.rival(e.jugador))
        self._log("Mano del rival: " + ", ".join(self.nombre(c) for c in r.mano) if r.mano else "La mano rival está vacía.")

    def _ef_sin_pista(self, e, paso):
        self.j(e.jugador).sin_pista = True

    def _ef_preguntar(self, e, paso):
        self._pedir(e, e.jugador, {"modo": "si_no", "texto": paso.get("texto", ""), "tras": "preguntar",
                                   "inspiracion": paso.get("texto") == "【ヒラメキ】"})

    def _tras_preguntar(self, e, d, valor):
        e.ctx["hecho"] = bool(valor)

    def _ef_modo(self, e, paso):
        e.ctx["modo_paso"] = paso
        self._pedir(e, e.jugador, {"modo": "opcion", "texto": "", "tras": "modo",
                                   "opciones": [o["texto"] for o in paso["opciones"]]})

    def _tras_modo(self, e, d, valor):
        paso = e.ctx.pop("modo_paso")
        e.pasos[e.i:e.i] = list(paso["opciones"][valor]["pasos"])

    # -- mano
    def _ef_descartar_mano(self, e, paso):
        q = self._quien(e, paso)
        j = self.j(q)
        f = paso.get("filtro")
        ops = [c for c in j.mano if f is None or self._encaja(c, f, None, q, e.ctx)]
        n = min(paso["n"], len(ops))
        e.ctx["hecho"] = n > 0 or paso["n"] == 0
        if n == 0:
            return
        if len(ops) == n:
            self._tras_descartar(e, {}, ops)
            return
        self._pedir(e, q, {"modo": "elegir", "opciones": [c.uid for c in ops], "min": n, "max": n,
                           "texto": f"Retira {n} carta(s) de la mano.", "tras": "descartar", "zona": "mano"})

    def _tras_descartar(self, e, d, cartas):
        for c in cartas:
            j = self.j(c.dueno)
            j.mano.remove(c)
            j.descarte.append(c)
            self._log(f"Jugador {j.idx + 1} retira {self.nombre(c)} de la mano.")
        e.ctx["hecho"] = bool(cartas)

    # -- la propia carta
    def _ef_esta(self, e, paso):
        c = self.p.carta(e.fuente)
        self._hacer(e, paso, c)

    def _ef_ultima(self, e, paso):
        u = e.ctx.get("ultima")
        if u is not None:
            self._hacer(e, paso, self.p.carta(u))

    def _ef_poner_debajo_esta(self, e, paso):
        c = self.p.carta(e.fuente)
        self._poner_debajo(self.j(e.jugador), c, paso["n"])

    def _ef_quitar_debajo_esta(self, e, paso):
        c = self.p.carta(e.fuente)
        j = self.j(c.dueno)
        for _ in range(min(paso["n"], len(c.debajo))):
            d = c.debajo.pop()
            d.limpiar()
            j.descarte.append(d)

    # -- costes
    def _ef_voltear_pruebas(self, e, paso):
        j = self.j(e.jugador)
        abajo = [c for c in j.pruebas if not c.boca_arriba]
        if paso.get("o_mas") and len(abajo) > paso["n"]:
            ops = [str(k) for k in range(paso["n"], len(abajo) + 1)]
            self._pedir(e, e.jugador, {"modo": "opcion", "opciones": ops, "tras": "voltear",
                                       "texto": "¿Cuántas Pruebas pones boca arriba?"})
            e.ctx["voltear_min"] = paso["n"]
            return
        self._voltear(e, j, paso["n"])

    def _tras_voltear(self, e, d, valor):
        self._voltear(e, self.j(e.jugador), e.ctx.pop("voltear_min") + valor)

    def _voltear(self, e, j, n):
        hechas = 0
        for c in reversed(j.pruebas):
            if hechas >= n:
                break
            if not c.boca_arriba:
                c.boca_arriba = True
                hechas += 1
        e.ctx["coste_n"] = hechas
        self._log(f"Jugador {j.idx + 1} pone {hechas} Prueba(s) boca arriba.")

    def _ef_perder_pruebas_nivel(self, e, paso):
        j = self.j(e.jugador)
        for _ in range(min(self.nivel_caso(j), len(j.pruebas))):
            j.descarte.append(j.pruebas.pop())

    def _ef_perder_file(self, e, paso):
        j = self.j(e.jugador)
        for _ in range(min(paso["n"], len(j.file))):
            c = j.file.pop()
            j.descarte.append(c)

    # -- mirar / revelar el mazo
    def _ef_mirar(self, e, paso):
        j = self.j(e.jugador)
        vistas = []
        for _ in range(min(paso["n"], len(j.mazo))):
            vistas.append(j.mazo.pop())
        e.ctx["vistas"] = [c.uid for c in vistas]
        self._log(f"Jugador {j.idx + 1} mira las {len(vistas)} primeras cartas de su mazo.")

    def _ef_tomar_vistas(self, e, paso):
        vistas = [self.p.carta(u) for u in e.ctx.get("vistas", [])]
        ops = [c for c in vistas if self._encaja(c, paso["filtro"], None, e.jugador, e.ctx)]
        e.ctx["resto"] = paso["resto"]
        maximo = min(paso["max"], len(ops))
        if maximo == 0:
            self._tras_tomar(e, {}, [])
            return
        self._pedir(e, e.jugador, {"modo": "elegir", "opciones": [c.uid for c in ops], "min": min(paso["min"], maximo),
                                   "max": maximo, "texto": "Elige qué cartas añades a la mano.",
                                   "tras": "tomar", "zona": "vistas",
                                   "vistas": [c.uid for c in vistas]})

    def _tras_tomar(self, e, d, cartas):
        j = self.j(e.jugador)
        vistas = [self.p.carta(u) for u in e.ctx.pop("vistas", [])]
        for c in cartas:
            j.mano.append(c)
            self._log(f"Jugador {j.idx + 1} añade {self.nombre(c)} a la mano.")
        resto = [c for c in vistas if c not in cartas]
        for c in resto:
            if e.ctx.get("resto") == "descarte":
                j.descarte.append(c)
            else:
                j.mazo.insert(0, c)
        e.ctx["hecho"] = bool(cartas)
        e.ctx["ultima"] = cartas[-1].uid if cartas else None

    def _ef_revelar_hasta(self, e, paso):
        j = self.j(e.jugador)
        reveladas = e.ctx.setdefault("reveladas", [])
        while j.mazo:
            c = j.mazo.pop()
            if self._encaja(c, paso["filtro"], None, e.jugador, e.ctx):
                self._log(f"Jugador {j.idx + 1} revela {self.nombre(c)}.")
                e.ctx["hecho"], e.ctx["ultima"] = True, c.uid
                if paso["destino"] == "mano":
                    j.mano.append(c)
                else:
                    self._entrar_por_efecto(e, c)
                return
            reveladas.append(c.uid)
        e.ctx["hecho"] = False
        self._log("No sale ninguna carta que cumpla la condición.")

    def _ef_fin_revelar(self, e, paso):
        j = self.j(e.jugador)
        for u in e.ctx.pop("reveladas", []):
            j.mazo.insert(0, self.p.carta(u))
        self.p.rng.shuffle(j.mazo)

    def _ef_revelar(self, e, paso):
        j = self.j(e.jugador)
        if j.mazo:
            c = j.mazo[-1]
            e.ctx["revelada"] = c.uid
            self._log(f"Jugador {j.idx + 1} revela {self.nombre(c)}.")

    def _ef_revelada_destino(self, e, paso):
        u = e.ctx.get("revelada")
        if u is None or (paso.get("otra") and e.ctx.get("revelada_movida")):
            return
        j = self.j(e.jugador)
        c = self.p.carta(u)
        if c not in j.mazo:
            return
        j.mazo.remove(c)
        {"mano": j.mano, "descarte": j.descarte}.get(paso["destino"], None)
        if paso["destino"] == "fondo":
            j.mazo.insert(0, c)
        elif paso["destino"] == "mano":
            j.mano.append(c)
        else:
            j.descarte.append(c)
        e.ctx["revelada_movida"] = True
        e.ctx["hecho"] = True

    # -- elegir cartas (con foco en la interfaz)
    def candidatos(self, e: Ejecucion, paso: dict) -> list[Carta]:
        zona, lado = paso["zona"]
        yo = e.jugador
        jugadores = {"propio": [yo], "rival": [self.p.rival(yo)], "ambos": [yo, self.p.rival(yo)]}[lado]
        fuente = self.p.carta(e.fuente)
        out = []
        for idx in jugadores:
            j = self.j(idx)
            if zona == "escena":
                cartas = j.escena
            elif zona == "pruebas":
                cartas = j.pruebas
            elif zona == "pruebas_arriba":
                cartas = [c for c in j.pruebas if c.boca_arriba]
            elif zona == "pruebas_abajo":
                cartas = [c for c in j.pruebas if not c.boca_arriba]
            else:
                cartas = getattr(j, zona)
            for c in cartas:
                if idx != yo and c.marca("intocable"):
                    continue    # «相手の能力や効果によって選ばれない»
                if zona.startswith("pruebas") or self._encaja(c, paso["filtro"], fuente, yo, e.ctx):
                    if paso.get("accion") == "usar" and c.defn.tipo != EVENTO:
                        continue
                    if paso.get("accion") == "entrar" and c.defn.tipo != PERSONAJE:
                        continue
                    out.append(c)
        return out

    def _ef_elegir(self, e, paso):
        ops = self.candidatos(e, paso)
        maximo = min(paso["max"], len(ops))
        minimo = min(paso["min"], maximo)
        e.ctx["paso_elegir"] = paso
        if maximo == 0:
            e.ctx["hecho"] = False
            self._log("No hay ninguna carta válida para el efecto.")
            return
        if minimo == maximo == len(ops) and paso["zona"][1] != "ambos" and paso.get("accion") != "mod_o":
            self._tras_elegir(e, {}, ops)    # no hay nada que decidir
            return
        detalle = {k: paso[k] for k in ("campo", "valor", "claves", "hasta", "tipo") if k in paso}
        detalle["tipo"] = paso["filtro"].get("tipo", "carta")
        self._pedir(e, e.jugador, {"modo": "elegir", "opciones": [c.uid for c in ops], "min": minimo,
                                   "max": maximo, "texto": "", "tras": "elegir", "zona": paso["zona"][0],
                                   "accion": paso.get("accion", ""), "detalle": detalle})

    def _tras_elegir(self, e, d, cartas):
        paso = e.ctx.pop("paso_elegir")
        e.ctx["hecho"] = bool(cartas)
        e.ctx["ultima"] = cartas[-1].uid if cartas else None
        if paso.get("accion") == "mod_o" and cartas:
            e.ctx["mod_o"] = (paso, [c.uid for c in cartas])
            self._pedir(e, e.jugador, {"modo": "opcion", "tras": "mod_o", "texto": "",
                                       "opciones": [f"{o['campo'].upper()} {o['valor']:+d}" for o in paso["opciones"]]})
            return
        for c in cartas:
            self._hacer(e, paso, c)
            for extra in paso.get("despues", []):
                self._hacer(e, extra, c)

    def _tras_mod_o(self, e, d, valor):
        paso, uids = e.ctx.pop("mod_o")
        o = paso["opciones"][valor]
        for u in uids:
            self._hacer(e, {"accion": "mod", "campo": o["campo"], "valor": o["valor"], "hasta": "turno"},
                        self.p.carta(u))

    # ------------------------------------------------------------ lo que se hace a una carta

    def _hacer(self, e: Ejecucion, paso: dict, c: Carta):
        fn = getattr(self, "_hacer_" + paso["accion"], None)
        if fn is None:
            self._ef_manual(e, {"texto": str(paso)})
            return
        fn(e, paso, c)

    def _hacer_dormir(self, e, paso, c):
        if c in self.j(c.dueno).escena and c.estado == ACTIVO:
            c.estado = DORMIDO
            self._log(f"{self.nombre(c)} se duerme.")

    def _hacer_aturdir(self, e, paso, c):
        if c in self.j(c.dueno).escena:
            c.estado = ATURDIDO
            self._log(f"{self.nombre(c)} queda aturdido.")

    def _hacer_activar(self, e, paso, c):
        if c in self.j(c.dueno).escena or c is self.j(c.dueno).companero:
            c.estado = ACTIVO
            self._log(f"{self.nombre(c)} se activa.")

    def _hacer_retirar(self, e, paso, c):
        j = self.j(c.dueno)
        if c in j.escena:
            self._retirar_de_escena(c)
            return
        zona = self._zona_de(c)
        if zona in ("mano", "pruebas", "zona_companero", "file", "mazo"):
            getattr(j, zona).remove(c)
            c.limpiar()
            j.descarte.append(c)
            self._log(f"{self.nombre(c)} va a la zona de retiradas.")

    def _hacer_fondo_mazo(self, e, paso, c):
        j = self.j(c.dueno)
        zona = self._zona_de(c)
        if zona == "otra" or zona in ("caso", "companero"):
            return
        self._quitar_de_zona(j, c)
        c.limpiar()
        j.mazo.insert(0, c)
        self._log(f"{self.nombre(c)} va al fondo del mazo.")

    def _hacer_a_mano(self, e, paso, c):
        j = self.j(c.dueno)
        zona = self._zona_de(c)
        if zona in ("otra", "caso", "companero", "mano"):
            return
        self._quitar_de_zona(j, c)
        c.limpiar()
        j.mano.append(c)
        self._log(f"{self.nombre(c)} va a la mano de su dueño.")

    def _hacer_a_zona_companero(self, e, paso, c):
        j = self.j(c.dueno)
        if self._zona_de(c) in ("otra", "caso", "companero"):
            return
        self._quitar_de_zona(j, c)
        c.limpiar()
        j.zona_companero.append(c)
        self._log(f"{self.nombre(c)} pasa a la zona de Compañero.")

    def _hacer_a_pruebas(self, e, paso, c):
        j = self.j(c.dueno)
        if self._zona_de(c) not in ("otra", "caso", "companero"):
            self._quitar_de_zona(j, c)
        c.limpiar()
        c.boca_arriba = True
        j.pruebas.append(c)
        if e.ctx.get("evento") == c.uid:
            e.ctx["fijado"] = True     # ya no va a la zona de retiradas
        self._log(f"{self.nombre(c)} pasa a las Pruebas boca arriba.")

    def _hacer_entrar(self, e, paso, c):
        j = self.j(e.jugador)
        if c.dueno != j.idx or c.defn.tipo != PERSONAJE:
            return
        self._quitar_de_zona(j, c)
        self._entrar_por_efecto(e, c, paso.get("dormido", False))

    def _hacer_usar(self, e, paso, c):
        """Usar un Evento de la mano gracias a un efecto (no cuenta como jugar de la mano)."""
        j = self.j(c.dueno)
        if c not in j.mano:
            return
        j.mano.remove(c)
        self._log(f"Jugador {j.idx + 1} usa el Evento {self.nombre(c)}.")
        self._usar_evento(j, c)

    def _hacer_mod(self, e, paso, c):
        valor = paso["valor"] * (e.ctx.get("coste_n", 0) if paso.get("por_coste") else 1)
        hasta = {"turno": HASTA_TURNO, "contacto": HASTA_CONTACTO}.get(paso.get("hasta"), HASTA_TURNO)
        if self._zona_de(c) not in ("escena", "companero"):
            return
        c.mods.append(Mod(paso["campo"], valor, hasta))
        self._log(f"{self.nombre(c)}: {paso['campo'].upper()} {valor:+d}.")

    def _hacer_dar_claves(self, e, paso, c):
        if self._zona_de(c) != "escena":
            return
        for k, v in paso["claves"].items():
            c.mods.append(Mod("clave:" + k, v, HASTA_TURNO))
        self._log(f"{self.nombre(c)} gana: {', '.join(paso['claves'])}.")

    def _hacer_marcar(self, e, paso, c):
        if self._zona_de(c) != "escena":
            return
        hasta = f"fin_turno_de:{self.p.rival(e.jugador)}" if paso.get("hasta") == "turno_rival" else HASTA_TURNO
        c.mods.append(Mod("marca:" + paso["marca"], 1, hasta))
        self._log(f"{self.nombre(c)} atrae las Acciones rivales.")

    def _hacer_boca_arriba(self, e, paso, c):
        c.boca_arriba = True

    def _hacer_boca_abajo(self, e, paso, c):
        c.boca_arriba = False

    def _hacer_debajo_esta(self, e, paso, c):
        destino = self.p.carta(e.fuente)
        j = self.j(c.dueno)
        if c is destino or self._zona_de(c) in ("otra", "caso", "companero"):
            return
        if c in j.escena:
            j.escena.remove(c)
            for d in c.debajo:           # p. 23: lo que tenía debajo se retira
                d.limpiar()
                j.descarte.append(d)
            c.debajo.clear()
        else:
            self._quitar_de_zona(j, c)
        c.limpiar()
        destino.debajo.append(c)
        self._log(f"{self.nombre(c)} queda debajo de {self.nombre(destino)}.")

    def _hacer_poner_debajo(self, e, paso, c):
        quien = self.p.rival(e.jugador) if paso.get("de") == "rival" else e.jugador
        self._poner_debajo(self.j(quien), c, paso["n"])

    def _poner_debajo(self, j, c, n):
        for _ in range(n):
            x = self._sacar_mazo(j)
            if x is None:
                break
            x.limpiar()
            c.debajo.append(x)
        self._log(f"Se fijan {n} carta(s) boca abajo en {self.nombre(c)}.")

    def _hacer_fijar_evento(self, e, paso, c):
        ev = self.p.carta(e.fuente)
        if ev.defn.tipo != EVENTO or self._zona_de(c) != "escena":
            return
        c.debajo.append(ev)
        e.ctx["fijado"] = True
        self._log(f"{self.nombre(ev)} queda fijado a {self.nombre(c)}.")

    def _hacer_mod_o(self, e, paso, c):
        pass   # se resuelve en _tras_elegir

    # ------------------------------------------------------------ entrar y usar por efecto

    def _entrar_por_efecto(self, e, c: Carta, dormido: bool = False):
        j = self.j(c.dueno)
        if len(j.escena) >= MAX_ESCENA:
            # p. 12: con la escena llena hay que retirar uno (Cambio)
            e.ctx["entrar_pendiente"] = (c.uid, dormido)
            self._pedir(e, j.idx, {"modo": "elegir", "opciones": [x.uid for x in j.escena], "min": 1, "max": 1,
                                   "texto": "Escena llena: elige el Personaje que sale (Cambio).",
                                   "tras": "cambio", "zona": "escena"})
            return
        self._colocar(j, c, dormido)

    def _tras_cambio(self, e, d, cartas):
        uid, dormido = e.ctx.pop("entrar_pendiente")
        self._retirar_de_escena(cartas[0])
        c = self.p.carta(uid)
        self._colocar(self.j(c.dueno), c, dormido)

    def _colocar(self, j, c: Carta, dormido: bool):
        c.limpiar()
        c.por_efecto = True
        self._poner_en_escena(j, c)
        if dormido:
            c.estado = DORMIDO

    def _usar_evento(self, j, c: Carta):
        """Resuelve el texto de un Evento; después va a la zona de retiradas (o queda fijado)."""
        pasos = []
        for h in self.habs(c):
            if h.clase == H.EVENTO_EFECTO:
                if self._cumple(h.condiciones, j.idx, c, {}):
                    pasos += list(h.pasos)
                else:
                    self._log("La condición del Evento no se cumple: no tiene efecto (p. 21).")
        if not H.habilidades(c.defn):
            texto = c.defn.texto_en("es")
            if texto:
                pasos.append({"op": "manual", "texto": texto})
        self.p.pila.append(Ejecucion(c.uid, j.idx, pasos, self.nombre(c) + " · " + (c.defn.texto.get("ja") or ""),
                                     ctx={"evento": c.uid, "hecho": True}))

    # ------------------------------------------------------------ 【宣言】 (p. 14)

    def declarables(self, j) -> list:
        """(carta, habilidad) que el jugador puede declarar ahora mismo."""
        p = self.p
        if p.fase != "principal" or p.pendiente or p.contacto or self.efectos_en_curso() or p.activo != j.idx:
            return []
        out = []
        fuentes = list(j.escena) + [j.caso] + list(j.zona_companero)
        for c in fuentes:
            for h in self.habs(c):
                if h.clase == H.DECLARAR and self._puede_declarar(j, c, h) is None:
                    out.append((c, h))
        return out

    def _puede_declarar(self, j, c: Carta, h) -> str | None:
        p = self.p
        if c in j.zona_companero and not (h.zona_companero or c.defn.mr):
            return "Esa habilidad no se puede declarar desde la zona de Compañero."
        if c not in j.escena and c is not j.caso and c not in j.zona_companero:
            return "La carta no está en tu escena."
        if not self._cumple(h.condiciones, j.idx, c, {}):
            return "No se cumplen las condiciones de los iconos de la habilidad."
        if not self._cumple(h.declarable_si, j.idx, c, {}):
            return "No se cumple la condición para declararla."
        if h.limite is not None and p.usos.get((c.uid, h.indice), 0) >= h.limite:
            return "Ya has usado esta habilidad las veces permitidas este turno."
        if h.coste_dormir and (c not in j.escena or c.estado != ACTIVO):
            return "El coste pide dormir a este Personaje y no está activo (p. 14)."
        return self._coste_posible(j, c, h.coste)

    def _coste_posible(self, j, c: Carta, coste: list) -> str | None:
        """p. 14: el coste se paga entero o la habilidad no se puede usar."""
        for paso in coste:
            op = paso["op"]
            if op == "descartar_mano":
                f = paso.get("filtro")
                if sum(1 for x in j.mano if f is None or self._encaja(x, f, None, j.idx, {})) < paso["n"]:
                    return "No tienes suficientes cartas en la mano para el coste."
            elif op == "moler" and len(j.mazo) < paso["n"]:
                return "No tienes suficientes cartas en el mazo para el coste."
            elif op == "voltear_pruebas" and sum(1 for x in j.pruebas if not x.boca_arriba) < paso["n"]:
                return "No tienes suficientes Pruebas boca abajo para el coste."
            elif op == "perder_pruebas_nivel" and len(j.pruebas) < self.nivel_caso(j):
                return "No tienes suficientes Pruebas para el coste."
            elif op == "perder_file" and len(j.file) < paso["n"]:
                return "No tienes suficientes cartas en FILE para el coste."
            elif op == "quitar_debajo_esta" and len(c.debajo) < paso["n"]:
                return "No hay suficientes cartas fijadas para el coste."
            elif op == "esta" and c not in j.escena and paso.get("accion") in ("fondo_mazo", "retirar"):
                return "La carta debe estar en escena para pagar el coste."
            elif op == "elegir":
                e = Ejecucion(c.uid, j.idx, [])
                if len(self.candidatos(e, paso)) < paso["min"]:
                    return "No tienes suficientes Personajes para pagar el coste."
            elif op == "manual":
                pass     # coste que el jugador pagará a mano
        return None

    def _a_declarar(self, a: A.Declarar):
        j = self.j(a.jugador)
        c = self.p.carta(a.uid)
        h = self.hab(c, a.indice)
        if h is None or h.clase != H.DECLARAR:
            raise self.Error("Esa carta no tiene esa habilidad 【宣言】.")
        if self.p.pendiente or self.efectos_en_curso() or self.p.contacto:
            raise self.Error("No se puede declarar en medio de otro efecto o acción (p. 14).")
        err = self._puede_declarar(j, c, h)
        if err:
            raise self.Error(err)
        self.p.usos[(c.uid, h.indice)] = self.p.usos.get((c.uid, h.indice), 0) + 1
        self._log(f"Jugador {j.idx + 1} declara la habilidad de {self.nombre(c)}.")
        if h.coste_dormir:
            c.estado = DORMIDO
        self.p.pila.append(Ejecucion(c.uid, j.idx, list(h.coste) + list(h.pasos), self._titulo(c, h),
                                     ctx={"hecho": True, "indice": h.indice}))

    # ------------------------------------------------------------ 【カットイン】

    def irrupcion_valida(self, j, c: Carta, mio: Carta) -> int | None:
        """AP que suma la Irrupción de c sobre mio, o None si no se puede usar."""
        habs = [h for h in H.habilidades(c.defn) if h.clase == H.IRRUPCION]
        if not habs:
            return c.defn.irrupcion_ap
        h = habs[0]
        if not self._cumple(h.condiciones, j.idx, c, {}):
            return None
        if not h.irrupcion:
            return c.defn.irrupcion_ap
        solo = h.irrupcion.get("solo")
        if solo is not None and not self._encaja(mio, solo, None, j.idx, {}):
            return None
        alt = h.irrupcion.get("alt")
        if alt and alt[0] and self._encaja(mio, alt[0], None, j.idx, {}):
            return alt[1]
        return h.irrupcion["ap"]

    def _efecto_irrupcion(self, j, c: Carta, mio: Carta):
        for h in H.habilidades(c.defn):
            if h.clase == H.IRRUPCION and h.pasos:
                self.p.pila.append(Ejecucion(c.uid, j.idx, list(h.pasos), self._titulo(c, h),
                                             ctx={"hecho": True, "objetivo": mio.uid, "indice": h.indice}))

    # ------------------------------------------------------------ permanentes

    def _recalcular(self):
        """Efectos permanentes de las cartas en escena (se rehacen siempre desde cero)."""
        for j in self.p.jugadores:
            for c in j.escena + [j.companero]:
                if any(m.hasta == HASTA_AURA for m in c.mods):
                    c.mods = [m for m in c.mods if m.hasta != HASTA_AURA]
        for j in self.p.jugadores:
            for c in list(j.escena):
                for h in self.habs(c):
                    if h.clase != H.CONTINUA or not self._cumple(h.condiciones, j.idx, c, {}):
                        continue
                    for op in h.continuas:
                        if not self._cumple(op.get("si"), j.idx, c, {}):
                            continue
                        self._aura(j, c, op)

    def _aura(self, j, c: Carta, op: dict):
        tipo = op["op"]
        if tipo == "mod_esta":
            c.mods.append(Mod(op["campo"], op["valor"], HASTA_AURA))
        elif tipo == "claves_esta":
            for k, v in op["claves"].items():
                c.mods.append(Mod("clave:" + k, v, HASTA_AURA))
        elif tipo == "rasgos_esta":
            for r in op["rasgos"]:
                c.mods.append(Mod("rasgo:" + r, 1, HASTA_AURA))
        elif tipo == "mod_aura":
            for x in j.escena:
                if self._encaja(x, op["filtro"], c, j.idx, {}):
                    x.mods.append(Mod(op["campo"], op["valor"], HASTA_AURA))
        elif tipo in ("intocable", "objetivo_extra", "sin_accion_caso", "guardia_dormido",
                      "sin_irrupcion_rival", "entra_dormido"):
            c.mods.append(Mod("marca:" + tipo, 1, HASTA_AURA))

    def objetivos_extra(self, c: Carta) -> list:
        """Filtros de «このキャラは相手の現場にいる…を指定してアクションできる»."""
        out = []
        for h in self.habs(c):
            if h.clase == H.CONTINUA and self._cumple(h.condiciones, c.dueno, c, {}):
                out += [op["filtro"] for op in h.continuas if op["op"] == "objetivo_extra"]
        return out

    def entra_dormido(self, c: Carta) -> bool:
        return any(op["op"] == "entra_dormido" for h in self.habs(c) if h.clase == H.CONTINUA
                   for op in h.continuas)
