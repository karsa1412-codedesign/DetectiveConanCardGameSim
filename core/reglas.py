"""Motor de reglas de Detective Conan Card Game (reglamento oficial Ver. 2.6).

El motor no sabe nada de la interfaz: recibe acciones, comprueba que sean legales,
modifica la partida y anota lo ocurrido en partida.log. Con la misma semilla y las
mismas acciones, la partida se reproduce idéntica.

Las páginas citadas (p. N) son las del reglamento.
"""
from __future__ import annotations

import random
from itertools import combinations

from . import acciones as A
from . import habilidades as H
from .efectos import EfectosMixin
from .cartas import (ASALTO, ASALTO_CASO, ASALTO_PERSONAJE, BALA, CASO, COMPANERO, EVENTO,
                     PERSONAJE, PISTA_FALSA, RAPIDEZ, Catalogo, Mazo)
from .estado import (ACTIVO, ATURDIDO, DORMIDO, HASTA_CONTACTO, HASTA_TURNO, Carta, Contacto,
                     Jugador, Mod, Partida, Pendiente)

MAX_ESCENA = 5        # p. 8
MANO_INICIAL = 5      # p. 9
FILE_PARA_RESOLUCION = 7  # p. 13


class ReglaError(Exception):
    """La acción no está permitida por el reglamento en este momento."""


# ---------------------------------------------------------------- creación

def nueva_partida(cat: Catalogo, mazo0: Mazo, mazo1: Mazo, semilla: int | None = None,
                  primero: int | None = None, arriba: dict | None = None) -> "Motor":
    """arriba = {jugador: [ids]} fija el orden del mazo sin barajar (para el tutorial):
    la primera carta de la lista es la primera que se roba; el resto sigue el orden del mazo."""
    semilla = random.randrange(2**31) if semilla is None else semilla
    rng = random.Random(semilla)
    uid = iter(range(1, 10_000))
    jugadores = []
    p = Partida(jugadores=jugadores, primero=0, semilla=semilla, rng=rng)
    for idx, mz in enumerate((mazo0, mazo1)):
        errores = mz.validar(cat)
        if errores:
            raise ReglaError(f"Mazo {idx + 1} no válido: " + " ".join(errores))
        comp = Carta(next(uid), cat[mz.companero], idx)
        caso = Carta(next(uid), cat[mz.caso], idx)
        j = Jugador(idx, comp, caso)
        for cid in mz.lista():
            c = Carta(next(uid), cat[cid], idx)
            j.mazo.append(c)
        for c in [comp, caso, *j.mazo]:
            p.registrar(c)
        if arriba and idx in arriba:
            resto = list(j.mazo)
            primeras = []
            for cid in arriba[idx]:
                c = next((x for x in resto if x.defn.id == cid), None)
                if c is None:
                    raise ReglaError(f"El mazo {idx + 1} no tiene suficientes copias de {cid}.")
                resto.remove(c)
                primeras.append(c)
            j.mazo = list(reversed(resto)) + list(reversed(primeras))  # el final es la parte de arriba
        else:
            rng.shuffle(j.mazo)
        jugadores.append(j)
    # p. 9: se sortea quién empieza
    p.primero = rng.randrange(2) if primero is None else primero
    p.activo = p.primero
    m = Motor(p)
    m._log(f"Empieza el jugador {p.primero + 1}.")
    for j in jugadores:
        m._robar(j, MANO_INICIAL)
    p.pendiente = Pendiente("mulligan", p.primero)
    return m


class Motor(EfectosMixin):
    Error = ReglaError
    OPS_MANUALES = ("robar", "a_mano", "a_descarte", "al_fondo_mazo", "a_file", "activar",
                    "dormir", "aturdir", "ap+1000", "ap-1000", "prueba+1", "prueba-1",
                    "barajar")

    def __init__(self, partida: Partida):
        self.p = partida

    # ------------------------------------------------------------ utilidades

    def _log(self, texto: str):
        self.p.log.append(texto)

    def j(self, idx: int) -> Jugador:
        return self.p.jugadores[idx]

    def nombre(self, c: Carta) -> str:
        return c.defn.nombre_en("es")

    def nivel_caso(self, j: Jugador) -> int:
        primero, segundo = j.caso.defn.nivel_caso
        return primero if j.idx == self.p.primero else segundo

    def _sacar_mazo(self, j: Jugador) -> Carta | None:
        """Saca la carta de arriba. Si el mazo se vacía, recicla al momento (p. 20)."""
        if not j.mazo:
            self._reciclar(j)
            if not j.mazo:
                return None
        c = j.mazo.pop()
        if not j.mazo:
            self._reciclar(j)
        return c

    def _reciclar(self, j: Jugador):
        """«Refresh» (p. 20)."""
        if self.p.ganador is not None:
            return
        if not j.descarte:
            self._fin(self.p.rival(j.idx), f"El jugador {j.idx + 1} se queda sin mazo ni descarte.")
            return
        for c in j.descarte:
            c.limpiar()
        j.mazo = j.descarte
        j.descarte = []
        self.p.rng.shuffle(j.mazo)
        self._log(f"Jugador {j.idx + 1} recicla su descarte como mazo; el rival gana 1 Prueba.")
        rival = self.j(self.p.rival(j.idx))
        rival.rastro_descubierto = True  # 痕跡 (p. 25): el rival ha reciclado
        self._ganar_pruebas(rival, 1)

    def _robar(self, j: Jugador, n: int):
        for _ in range(n):
            c = self._sacar_mazo(j)
            if c is None:
                return
            j.mano.append(c)

    def _ganar_pruebas(self, j: Jugador, n: int):
        ganadas = 0
        for _ in range(n):
            c = self._sacar_mazo(j)
            if c is None:
                break
            c.limpiar()
            j.pruebas.append(c)
            ganadas += 1
        if ganadas:
            self._log(f"Jugador {j.idx + 1} gana {ganadas} Prueba(s): ahora tiene {len(j.pruebas)}.")

    def _fin(self, ganador: int, motivo: str):
        if self.p.ganador is None:
            self.p.ganador = ganador
            self.p.motivo = motivo
            self.p.fase = "terminada"
            self.p.pendiente = None
            self._log(f"FIN: gana el jugador {ganador + 1}. {motivo}")

    def _activar(self, c: Carta):
        # p. 6: una carta aturdida se queda dormida en lugar de activarse
        c.estado = DORMIDO if c.estado == ATURDIDO else ACTIVO

    def _recien_llegado(self, c: Carta) -> bool:
        """«Estado de presentación» (名乗り状態, p. 15)."""
        return c.turno_entrada == self.p.turno

    def _color_ok(self, j: Jugador, c: Carta) -> bool:
        """p. 12: la carta debe compartir color con tu Caso; una de dos colores, ambos."""
        colores = set(c.defn.colores)
        return bool(colores) and colores <= set(j.caso.defn.colores)

    def _retirar_de_escena(self, c: Carta):
        j = self.j(c.dueno)
        if c in j.escena:
            j.escena.remove(c)
        for d in c.debajo:
            d.limpiar()
            j.descarte.append(d)
        c.debajo.clear()
        c.limpiar()
        # p. 26: una MR que sale de escena en turno rival va a la zona de Compañero
        if c.defn.mr and self.p.activo != c.dueno:
            j.zona_companero.append(c)
            self._log(f"{self.nombre(c)} (MR) pasa a la zona de Compañero.")
        else:
            j.descarte.append(c)
            self._log(f"{self.nombre(c)} se retira de escena.")
        self._disparar(H.SALIDA, c)     # 【現場リムーブ時】

    def _entrar(self, j: Jugador, c: Carta, retirar: int | None):
        if c.defn.tipo == EVENTO:
            self._log(f"Jugador {j.idx + 1} juega el Evento {self.nombre(c)}.")
            self._usar_evento(j, c)
            return
        if len(j.escena) >= MAX_ESCENA:
            sale = self.p.carta(retirar) if retirar is not None else None
            if sale is None or sale not in j.escena:
                raise ReglaError("La escena está llena: elige un Personaje para el Cambio.")
            self._log(f"Cambio: sale {self.nombre(sale)}.")
            self._retirar_de_escena(sale)
        elif retirar is not None:
            raise ReglaError("El Cambio solo se permite con la escena llena (p. 12).")
        c.limpiar()
        self._poner_en_escena(j, c)

    def _poner_en_escena(self, j: Jugador, c: Carta):
        """Entrada en escena por cualquier vía; dispara 【登場時】 y 【疾風】."""
        if c.defn.mr:
            # p. 26: al entrar una MR, la MR anterior se retira
            for vieja in [x for x in j.escena + j.zona_companero if x.defn.mr]:
                if vieja in j.zona_companero:
                    j.zona_companero.remove(vieja)
                    vieja.limpiar()
                    j.descarte.append(vieja)
                    self._log(f"{self.nombre(vieja)} (MR) se retira.")
                else:
                    self._retirar_de_escena(vieja)
        c.turno_entrada = self.p.turno
        j.escena.append(c)
        if self.entra_dormido(c):
            c.estado = DORMIDO
        self._log(f"Jugador {j.idx + 1} pone en escena a {self.nombre(c)} "
                  f"(nivel {c.defn.nivel}, AP {c.ap}, LP {c.lp}).")
        j.entradas_turno += 1
        self._disparar(H.ENTRADA, c)
        if j.entradas_turno == 1:
            self._disparar(H.RAFAGA, c)   # 【疾風】: el primero en entrar este turno

    def _puede_jugar(self, j: Jugador, c: Carta, limite: int) -> str | None:
        if c not in j.mano:
            return "La carta no está en tu mano."
        if c.defn.tipo not in (PERSONAJE, EVENTO):
            return "Solo se juegan Personajes y Eventos."
        if c.defn.nivel > limite:
            return f"Nivel {c.defn.nivel} mayor que las cartas en FILE ({limite})."
        if not self._color_ok(j, c):
            return "La carta no comparte color con tu Caso."
        return None

    # ------------------------------------------------------------ turno

    def _empezar_turno(self, idx: int):
        p = self.p
        p.turno += 1
        p.activo = idx
        j = self.j(idx)
        j.jugo_mano = j.uso_pista = j.sin_pista = False
        for x in p.jugadores:
            x.entradas_turno = 0
        p.usos.clear()
        p.fase = "automatica"
        self._log(f"— Turno {p.turno}: jugador {idx + 1} —")
        # p. 10, fase automática
        if j.companero_en_file:
            j.companero_en_file = False
        j.companero.estado = ACTIVO
        for c in j.escena:
            self._activar(c)
        self._robar(j, 1)
        for _ in range(1 if p.turno == 1 else 2):
            if p.ganador is not None:
                return
            c = self._sacar_mazo(j)
            if c is None:
                break
            c.limpiar()
            j.file.append(c)
        if p.ganador is None:
            p.fase = "principal"

    def _terminar_turno(self):
        j = self.j(self.p.activo)
        self.p.fase = "final"
        self._log(f"Fin del turno del jugador {j.idx + 1}.")
        for c in list(j.escena):
            self._disparar(H.DISPARO, c, H.EV_FIN_TURNO)
        if self.efectos_en_curso():
            self.p.diferida = ("fin_turno", None)
        else:
            self._cerrar_turno()

    def _cerrar_turno(self):
        for jug in self.p.jugadores:
            for c in jug.escena + [jug.companero]:
                c.mods = [m for m in c.mods if m.hasta not in (HASTA_TURNO, f"fin_turno_de:{self.p.activo}")]
        self._empezar_turno(self.p.rival(self.p.activo))

    # ------------------------------------------------------------ API pública

    def aplicar(self, a: A.Accion):
        p = self.p
        if p.ganador is not None:
            raise ReglaError("La partida ha terminado.")
        if isinstance(a, A.Manual):
            self._manual(a)
            self._recalcular()
            return
        if isinstance(a, A.Rendirse):   # no hace falta que sea su turno
            self._log(f"El jugador {a.jugador + 1} se rinde.")
            self.p.contacto = None
            self._fin(self.p.rival(a.jugador), f"El jugador {a.jugador + 1} se ha rendido.")
            return
        if a.jugador != p.quien_decide():
            raise ReglaError(f"Ahora decide el jugador {p.quien_decide() + 1}.")
        self._aplicar(a)
        self._procesar()

    def _aplicar(self, a: A.Accion):
        p = self.p
        pend = p.pendiente
        if pend:
            manejador = {
                "mulligan": (A.Mulligan, self._a_mulligan),
                "pista_jugar": ((A.JugarCarta, A.NoJugar), self._a_pista_jugar),
                "pista_falsa": (A.PistaFalsa, self._a_pista_falsa),
                "guardia": (A.Guardia, self._a_guardia),
                "contacto": (A.Contactar, self._a_contactar),
                "efecto": (A.Elegir, self._a_elegir_motor),
            }[pend.tipo]
            if not isinstance(a, manejador[0]):
                raise ReglaError(f"Se espera una respuesta de tipo «{pend.tipo}».")
            return manejador[1](a)
        if p.fase != "principal":
            raise ReglaError("Solo se actúa en la fase principal.")
        if self.efectos_en_curso():
            raise ReglaError("Primero hay que terminar de resolver los efectos.")
        fn = {
            A.JugarCarta: self._a_jugar, A.SiguientePista: self._a_siguiente_pista,
            A.Asistir: self._a_asistir, A.ResolverCaso: self._a_resolver,
            A.Deducir: self._a_deducir, A.Atacar: self._a_atacar, A.FinTurno: self._a_fin_turno,
            A.Declarar: self._a_declarar,
        }.get(type(a))
        if fn is None:
            raise ReglaError("Acción no disponible en este momento.")
        fn(a)

    def legales(self) -> list[A.Accion]:
        """Todas las acciones que el reglamento permite ahora mismo (sin las manuales)."""
        p = self.p
        if p.ganador is not None:
            return []
        q = p.quien_decide()
        j = self.j(q)
        pend = p.pendiente
        out: list[A.Accion] = []
        if pend:
            if pend.tipo == "efecto":
                return self.legales_efecto()
            if pend.tipo == "mulligan":
                out.append(A.Mulligan(q, ()))
                out.append(A.Mulligan(q, tuple(c.uid for c in j.mano)))
                out += [A.Mulligan(q, (c.uid,)) for c in j.mano]
            elif pend.tipo == "pista_jugar":
                out.append(A.NoJugar(q))
                out += self._jugadas(j, j.cartas_file)
            elif pend.tipo == "pista_falsa":
                cand = pend.datos["candidatos"]
                for n in range(len(cand) + 1):
                    out += [A.PistaFalsa(q, tuple(x)) for x in combinations(cand, n)]
            elif pend.tipo == "guardia":
                out.append(A.Guardia(q, None))
                out += [A.Guardia(q, c.uid) for c in self._guardias(j)]
            elif pend.tipo == "contacto":
                out.append(A.Contactar(q, None))
                mio = self._propio_contacto(j)
                for c in j.mano:
                    if self.irrupcion_valida(j, c, mio) is not None and not self._sin_irrupcion(j):
                        out.append(A.Contactar(q, c.uid, "irrupcion"))
                    if c.defn.disfraz and c.defn.tipo == PERSONAJE:
                        out.append(A.Contactar(q, c.uid, "disfraz"))
            return out
        if p.fase != "principal" or self.efectos_en_curso():
            return []
        if not j.jugo_mano and not j.uso_pista:
            out += self._jugadas(j, j.cartas_file)
        if j.file and not j.sin_pista:
            out.append(A.SiguientePista(q))
        out += [A.Declarar(q, c.uid, h.indice) for c, h in self.declarables(j)]
        comp = j.companero
        if not j.companero_en_file and comp.estado == ACTIVO:
            out.append(A.Asistir(q))
            out.append(A.Deducir(q, comp.uid))
            if j.caso_resuelto:
                out.append(A.ResolverCaso(q))
        rival = self.j(p.rival(q))
        for c in j.escena:
            if c.estado != ACTIVO:
                continue
            if self._puede_deducir(c):
                out.append(A.Deducir(q, c.uid))
            obligados = self._obligados(c)
            if self._puede_atacar(c, personaje=True):
                out += [A.Atacar(q, c.uid, t.uid) for t in rival.escena if self._objetivo_valido(c, t)
                        and (not obligados or t in obligados)]
            if self._puede_atacar(c, personaje=False) and rival.pruebas and not c.marca("sin_accion_caso") \
                    and not obligados:
                out.append(A.Atacar(q, c.uid, None))
        out.append(A.FinTurno(q))
        return out

    def _jugadas(self, j: Jugador, limite: int) -> list[A.Accion]:
        out = []
        vistos = set()
        for c in j.mano:
            if self._puede_jugar(j, c, limite) is not None:
                continue
            if c.defn.tipo == PERSONAJE and len(j.escena) >= MAX_ESCENA:
                out += [A.JugarCarta(j.idx, c.uid, s.uid) for s in j.escena]
            else:
                if c.defn.id in vistos:   # copias idénticas: basta una opción
                    continue
                vistos.add(c.defn.id)
                out.append(A.JugarCarta(j.idx, c.uid))
        return out

    def _puede_deducir(self, c: Carta) -> bool:
        return c.estado == ACTIVO and (not self._recien_llegado(c) or self.tiene(c, RAPIDEZ))

    def _objetivo_valido(self, atacante: Carta, t: Carta) -> bool:
        """p. 16: se elige un Personaje rival dormido o aturdido (o el que permita una habilidad)."""
        if t.estado in (DORMIDO, ATURDIDO):
            return True
        return any(self._encaja(t, f, atacante, atacante.dueno, {}) for f in self.objetivos_extra(atacante))

    def _obligados(self, atacante: Carta) -> list:
        """Personajes rivales que hay que elegir si se pueden elegir («必ず指定する»)."""
        rival = self.j(self.p.rival(atacante.dueno))
        return [t for t in rival.escena if t.marca("provocar") and self._objetivo_valido(atacante, t)
                and self._puede_atacar(atacante, personaje=True)]

    def _guardias(self, j: Jugador) -> list:
        return [c for c in j.escena if c.estado == ACTIVO or (c.estado == DORMIDO and c.marca("guardia_dormido"))]

    def _propio_contacto(self, j: Jugador) -> Carta | None:
        ct = self.p.contacto
        if ct is None:
            return None
        a = self.p.carta(ct.atacante)
        return a if a.dueno == j.idx else self.p.carta(ct.defensor)

    def _sin_irrupcion(self, j: Jugador) -> bool:
        rival = self.j(self.p.rival(j.idx))
        return any(c.marca("sin_irrupcion_rival") for c in rival.escena)

    def _puede_atacar(self, c: Carta, personaje: bool) -> bool:
        if c.estado != ACTIVO:
            return False
        if not self._recien_llegado(c):
            return True
        return (self.tiene(c, RAPIDEZ) or self.tiene(c, ASALTO) or
                self.tiene(c, ASALTO_PERSONAJE if personaje else ASALTO_CASO))

    # ------------------------------------------------------------ preparación

    def _a_mulligan(self, a: A.Mulligan):
        j = self.j(a.jugador)
        devolver = [self.p.carta(u) for u in a.uids]
        if any(c not in j.mano for c in devolver) or len(set(a.uids)) != len(a.uids):
            raise ReglaError("Solo puedes devolver cartas de tu mano.")
        if devolver:
            for c in devolver:
                j.mano.remove(c)
                j.mazo.append(c)
            self.p.rng.shuffle(j.mazo)
            self._robar(j, len(devolver))
            self._log(f"Jugador {j.idx + 1} cambia {len(devolver)} carta(s) de su mano.")
        else:
            self._log(f"Jugador {j.idx + 1} se queda su mano.")
        j.mulligan_hecho = True
        otro = self.j(self.p.rival(j.idx))
        if not otro.mulligan_hecho:
            self.p.pendiente = Pendiente("mulligan", otro.idx)
        else:
            self.p.pendiente = None
            self._log("Se revelan Casos y Compañeros. ¡Empieza la partida!")
            self._empezar_turno(self.p.primero)

    # ------------------------------------------------------------ fase principal

    def _a_jugar(self, a: A.JugarCarta):
        j = self.j(a.jugador)
        c = self.p.carta(a.uid)
        if j.jugo_mano:
            raise ReglaError("Ya has jugado una carta de la mano este turno.")
        if j.uso_pista:
            raise ReglaError("Tras Siguiente pista ya no puedes jugar de la mano este turno.")
        err = self._puede_jugar(j, c, j.cartas_file)
        if err:
            raise ReglaError(err)
        j.mano.remove(c)
        try:
            self._entrar(j, c, a.retirar)
        except ReglaError:
            j.mano.append(c)
            raise
        j.jugo_mano = True

    def _a_siguiente_pista(self, a: A.SiguientePista):
        j = self.j(a.jugador)
        if j.sin_pista:
            raise ReglaError("Un efecto impide usar Siguiente pista este turno.")
        if not j.file:
            raise ReglaError("No hay cartas en FILE.")
        c = j.file.pop()
        j.mano.append(c)
        j.uso_pista = True
        self._log(f"Jugador {j.idx + 1} usa Siguiente pista: coge la carta de arriba de FILE "
                  f"y puede jugar una carta de nivel ≤ {j.cartas_file}.")
        self.p.pendiente = Pendiente("pista_jugar", j.idx, {"limite": j.cartas_file})

    def _a_pista_jugar(self, a):
        j = self.j(a.jugador)
        if isinstance(a, A.NoJugar):
            self.p.pendiente = None
            self._log(f"Jugador {j.idx + 1} no juega carta.")
            return
        c = self.p.carta(a.uid)
        err = self._puede_jugar(j, c, j.cartas_file)
        if err:
            raise ReglaError(err)
        j.mano.remove(c)
        try:
            self._entrar(j, c, a.retirar)
        except ReglaError:
            j.mano.append(c)
            raise
        self.p.pendiente = None

    def _companero_listo(self, j: Jugador):
        if j.companero_en_file:
            raise ReglaError("El Compañero está en FILE.")
        if j.companero.estado != ACTIVO:
            raise ReglaError("El Compañero no está activo.")

    def _a_asistir(self, a: A.Asistir):
        j = self.j(a.jugador)
        self._companero_listo(j)
        j.companero.estado = DORMIDO
        j.companero_en_file = True
        self._log(f"Jugador {j.idx + 1}: el Compañero Asiste y va a FILE ({j.cartas_file} cartas).")
        if not j.caso_resuelto and j.cartas_file >= FILE_PARA_RESOLUCION:
            j.caso_resuelto = True
            self._log(f"¡El Caso del jugador {j.idx + 1} pasa a Resolución!")
            self._disparar(H.CASO_RESOLUCION, j.caso)

    def _a_resolver(self, a: A.ResolverCaso):
        j = self.j(a.jugador)
        self._companero_listo(j)
        if not j.caso_resuelto:
            raise ReglaError("El Caso todavía no está en Resolución.")
        j.companero.estado = DORMIDO
        necesarias = self.nivel_caso(j)
        self._log(f"Jugador {j.idx + 1} intenta Resolver el caso: {len(j.pruebas)}/{necesarias} Pruebas.")
        if len(j.pruebas) >= necesarias:
            self._fin(j.idx, "Caso resuelto.")

    def _a_deducir(self, a: A.Deducir):
        j = self.j(a.jugador)
        c = self.p.carta(a.uid)
        if c is j.companero:
            self._companero_listo(j)
        elif c in j.escena:
            if not self._puede_deducir(c):
                raise ReglaError("Este Personaje no puede Deducir ahora (dormido o recién llegado).")
        else:
            raise ReglaError("Solo deducen tu Compañero o tus Personajes en escena.")
        c.estado = DORMIDO
        self._log(f"Jugador {j.idx + 1} Deduce con {self.nombre(c)} (LP {c.lp}).")
        if c is not j.companero:
            self._disparar(H.DISPARO, c, H.EV_DEDUCE)
            self._disparar(H.DISPARO, c, H.EV_DEDUCE_O_ACCION)
        rival = self.j(self.p.rival(j.idx))
        cand = [x.uid for x in rival.escena if x.estado == ACTIVO and self.tiene(x, PISTA_FALSA)]
        if cand:
            self._esperar(Pendiente("pista_falsa", rival.idx, {"actor": c.uid, "candidatos": cand}))
        else:
            self._resolver_deduccion(j, c, 0)

    def _a_pista_falsa(self, a: A.PistaFalsa):
        pend = self.p.pendiente
        if any(u not in pend.datos["candidatos"] for u in a.uids):
            raise ReglaError("Solo Personajes activos con Pista falsa.")
        rebaja = 0
        for u in a.uids:
            x = self.p.carta(u)
            x.estado = DORMIDO
            rebaja += self.valor_clave(x, PISTA_FALSA)
        actor = self.p.carta(pend.datos["actor"])
        self.p.pendiente = None
        if a.uids:
            self._log(f"Pista falsa: LP −{rebaja} para esta Deducción.")
        self._resolver_deduccion(self.j(actor.dueno), actor, rebaja)

    def _resolver_deduccion(self, j: Jugador, actor: Carta, rebaja: int):
        lp = actor.lp - rebaja
        if lp > 0:
            self._ganar_pruebas(j, lp)
        else:
            self._log("LP 0 o menos: no se gana ninguna Prueba.")

    def _a_atacar(self, a: A.Atacar):
        j = self.j(a.jugador)
        rival = self.j(self.p.rival(j.idx))
        c = self.p.carta(a.atacante)
        if c not in j.escena:
            raise ReglaError("El atacante debe estar en tu escena.")
        if a.objetivo is None:
            if not self._puede_atacar(c, personaje=False):
                raise ReglaError("Este Personaje no puede hacer Acción ahora.")
            if not rival.pruebas:
                raise ReglaError("No se puede atacar a un Caso sin Pruebas (p. 16).")
            if c.marca("sin_accion_caso"):
                raise ReglaError("Este Personaje no puede hacer Acción contra el Caso.")
            desc = "el Caso rival"
        else:
            t = self.p.carta(a.objetivo)
            if not self._puede_atacar(c, personaje=True):
                raise ReglaError("Este Personaje no puede hacer Acción ahora.")
            if t not in rival.escena or not self._objetivo_valido(c, t):
                raise ReglaError("El objetivo debe ser un Personaje rival dormido o aturdido.")
            desc = self.nombre(t)
        obligados = self._obligados(c)
        if obligados and (a.objetivo is None or self.p.carta(a.objetivo) not in obligados):
            raise ReglaError(f"Debes elegir a {self.nombre(obligados[0])} como objetivo.")
        c.estado = DORMIDO
        self._log(f"Jugador {j.idx + 1}: {self.nombre(c)} (AP {c.ap}) hace Acción contra {desc}.")
        self._disparar(H.DISPARO, c, H.EV_ACCION)
        self._disparar(H.DISPARO, c, H.EV_DEDUCE_O_ACCION)
        self._disparar(H.DISPARO, c, H.EV_ACCION_CASO if a.objetivo is None else H.EV_ACCION_PERSONAJE)
        guardias = [x for x in self._guardias(rival) if x.uid != a.objetivo]
        if guardias and not self.tiene(c, BALA):
            self._esperar(Pendiente("guardia", rival.idx, {"atacante": c.uid, "objetivo": a.objetivo}))
        else:
            self._sin_guardia(c, a.objetivo)

    def _a_guardia(self, a: A.Guardia):
        pend = self.p.pendiente
        atacante = self.p.carta(pend.datos["atacante"])
        rival = self.j(a.jugador)
        if a.uid is None:
            self.p.pendiente = None
            self._log("El rival no Guarda.")
            self._sin_guardia(atacante, pend.datos["objetivo"])
            return
        g = self.p.carta(a.uid)
        if g not in self._guardias(rival):
            raise ReglaError("Solo guarda un Personaje activo de tu escena.")
        g.estado = DORMIDO
        self.p.pendiente = None
        self._log(f"{self.nombre(g)} Guarda.")
        self._disparar(H.DISPARO, g, H.EV_GUARDIA)
        self._iniciar_contacto(atacante, g)

    def _sin_guardia(self, atacante: Carta, objetivo: int | None):
        if objetivo is not None:
            self._iniciar_contacto(atacante, self.p.carta(objetivo))
            return
        # p. 19: Acción al Caso no guardada
        j = self.j(atacante.dueno)
        rival = self.j(self.p.rival(j.idx))
        if rival.pruebas:
            quitada = rival.pruebas.pop()
            rival.descarte.append(quitada)
            self._log(f"Jugador {rival.idx + 1} pierde 1 Prueba ({self.nombre(quitada)}).")
            if any(h.clase == H.INSPIRACION for h in H.habilidades(quitada.defn)):
                self._log(f"¡Inspiración de {self.nombre(quitada)}! Su dueño decide si la aplica.")
                self._disparar(H.INSPIRACION, quitada, opcional=True)
            elif quitada.defn.inspiracion:
                self._log(f"¡Inspiración de {self.nombre(quitada)}! Su dueño puede aplicar el efecto (manual).")
        self._ganar_pruebas(j, 1)

    def _iniciar_contacto(self, atacante: Carta, defensor: Carta):
        a_j, d_j = atacante.dueno, defensor.dueno
        # p. 17: actúa primero quien tenga menos AP; con empate, el jugador no activo
        if atacante.ap < defensor.ap:
            orden = [a_j, d_j]
        else:
            orden = [d_j, a_j]
        self.p.contacto = Contacto(atacante.uid, defensor.uid, orden, 0, {a_j: False, d_j: False})
        self._log(f"Contacto: {self.nombre(atacante)} (AP {atacante.ap}) contra "
                  f"{self.nombre(defensor)} (AP {defensor.ap}).")
        for c, otro in ((atacante, defensor), (defensor, atacante)):
            self._disparar(H.DISPARO, c, H.EV_CONTACTO)
            if otro.ap > c.ap:
                self._disparar(H.DISPARO, c, H.EV_CONTACTO_MAYOR)
        self._esperar(Pendiente("contacto", orden[0]))

    def _a_contactar(self, a: A.Contactar):
        ct = self.p.contacto
        j = self.j(a.jugador)
        if a.uid is not None:
            c = self.p.carta(a.uid)
            if c not in j.mano:
                raise ReglaError("La carta debe estar en tu mano.")
            propio = ct.atacante if self.p.carta(ct.atacante).dueno == j.idx else ct.defensor
            mio = self.p.carta(propio)
            if a.modo == "irrupcion":
                valor = self.irrupcion_valida(j, c, mio)
                if valor is None or self._sin_irrupcion(j):
                    raise ReglaError("Esta carta no tiene Irrupción o ahora no se puede usar.")
                j.mano.remove(c)
                j.descarte.append(c)
                mio.mods.append(Mod("ap", valor, HASTA_CONTACTO))
                self._log(f"Irrupción de {self.nombre(c)}: {self.nombre(mio)} AP +{valor} "
                          f"(ahora {mio.ap}).")
                self._efecto_irrupcion(j, c, mio)
            elif a.modo == "disfraz":
                if not (c.defn.disfraz and c.defn.tipo == PERSONAJE):
                    raise ReglaError("Esta carta no tiene Disfraz.")
                # p. 18: el nuevo hereda estado y efectos; el original va al fondo del mazo
                j.mano.remove(c)
                pos = j.escena.index(mio)
                c.estado, c.turno_entrada = mio.estado, mio.turno_entrada
                c.mods, c.debajo = mio.mods, mio.debajo
                mio.mods, mio.debajo = [], []
                j.escena[pos] = c
                mio.limpiar()
                j.mazo.insert(0, mio)
                if propio == ct.atacante:
                    ct.atacante = c.uid
                else:
                    ct.defensor = c.uid
                self._log(f"Disfraz: {self.nombre(c)} sustituye a {self.nombre(mio)} (AP {c.ap}).")
                self._disparar(H.ENTRADA_DISFRAZ, c)
            else:
                raise ReglaError("Modo de Contacto desconocido.")
            ct.actuo[j.idx] = True
        else:
            self._log(f"Jugador {j.idx + 1} pasa en el Contacto.")
        primero, segundo = ct.orden
        self.p.pendiente = None
        if ct.paso == 0:
            ct.paso = 1
            self._esperar(Pendiente("contacto", segundo))
        elif ct.paso == 1 and not ct.actuo[primero] and ct.actuo[segundo]:
            ct.paso = 2
            self._esperar(Pendiente("contacto", primero))
        elif self.efectos_en_curso():
            self.p.diferida = ("resolver_contacto", None)   # p. 17: los efectos van antes
        else:
            self._resolver_contacto()

    def _resolver_contacto(self):
        ct = self.p.contacto
        atk, dfn = self.p.carta(ct.atacante), self.p.carta(ct.defensor)
        self.p.pendiente = None
        self.p.contacto = None
        self._log(f"Comparación de AP: {atk.ap} contra {dfn.ap}.")
        if atk.ap >= dfn.ap:
            self._retirar_de_escena(dfn)
            if atk in self.j(atk.dueno).escena:
                self._disparar(H.DISPARO, atk, H.EV_GANA_CONTACTO)
            for x in list(self.j(atk.dueno).escena):
                self._disparar(H.DISPARO, x, H.EV_RIVAL_RETIRADO)
        else:
            self._log("No ocurre nada.")
        for c in (atk, dfn):
            c.mods = [m for m in c.mods if m.hasta != HASTA_CONTACTO]

    def _a_fin_turno(self, a: A.FinTurno):
        self._terminar_turno()

    def _a_elegir_motor(self, a: A.Elegir):
        self._a_elegir(a)

    # ------------------------------------------------------------ herramientas manuales

    def _manual(self, a: A.Manual):
        """Mueve o cambia cartas a mano para aplicar efectos no automatizados.
        Solo sobre cartas propias: tus cartas nunca van a zonas del rival (p. 8)."""
        j = self.j(a.jugador)
        op = a.op
        if op not in self.OPS_MANUALES:
            raise ReglaError(f"Operación manual desconocida: {op}")
        if op == "robar":
            self._robar(j, 1)
        elif op == "barajar":
            self.p.rng.shuffle(j.mazo)
        elif op == "prueba+1":
            self._ganar_pruebas(j, 1)
        elif op == "prueba-1":
            if j.pruebas:
                j.descarte.append(j.pruebas.pop())
        else:
            c = self.p.carta(a.uid)
            if c.dueno != j.idx and op not in ("dormir", "aturdir", "activar", "ap+1000", "ap-1000"):
                raise ReglaError("Solo puedes mover tus propias cartas.")
            dueno = self.j(c.dueno)
            if op == "activar":
                c.estado = ACTIVO
            elif op == "dormir":
                c.estado = DORMIDO if c.estado != ATURDIDO else ATURDIDO
            elif op == "aturdir":
                c.estado = ATURDIDO
            elif op in ("ap+1000", "ap-1000"):
                c.mods.append(Mod("ap", 1000 if op == "ap+1000" else -1000, HASTA_TURNO))
            else:
                self._quitar_de_zona(dueno, c)
                c.limpiar()
                if op == "al_fondo_mazo":
                    dueno.mazo.insert(0, c)
                else:
                    {"a_mano": dueno.mano, "a_descarte": dueno.descarte, "a_file": dueno.file}[op].append(c)
        self._log(f"[manual] Jugador {j.idx + 1}: {op}" +
                  (f" sobre {self.nombre(self.p.carta(a.uid))}" if a.uid else ""))

    def _quitar_de_zona(self, j: Jugador, c: Carta):
        for zona in (j.mano, j.escena, j.file, j.pruebas, j.descarte, j.mazo, j.zona_companero):
            if c in zona:
                if zona is j.escena:
                    for d in c.debajo:
                        d.limpiar()
                        j.descarte.append(d)
                    c.debajo.clear()
                zona.remove(c)
                return
        raise ReglaError("Esa carta no se puede mover.")

    # ------------------------------------------------------------ información visible

    def vista(self, para: int) -> dict:
        """Lo que ve un jugador: su mano sí, la del rival solo el número (para el modo en línea)."""
        def carta(c, visible=True):
            if not visible:
                return {"oculta": True}
            return {"uid": c.uid, "id": c.defn.id, "nombre": self.nombre(c), "estado": c.estado,
                    "ap": c.ap, "lp": c.lp, "nivel": c.defn.nivel}
        out = {"turno": self.p.turno, "activo": self.p.activo, "fase": self.p.fase,
               "ganador": self.p.ganador, "jugadores": []}
        for j in self.p.jugadores:
            yo = j.idx == para
            out["jugadores"].append({
                "mano": [carta(c, yo) for c in j.mano],
                "escena": [carta(c) for c in j.escena],
                "mazo": len(j.mazo), "file": j.cartas_file, "pruebas": len(j.pruebas),
                "descarte": [carta(c) for c in j.descarte],
                "companero": carta(j.companero), "companero_en_file": j.companero_en_file,
                "caso": carta(j.caso), "resolucion": j.caso_resuelto,
            })
        return out
