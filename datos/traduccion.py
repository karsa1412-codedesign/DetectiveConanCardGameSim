"""Traducción de nombres, rasgos y textos de efecto con DeepL.

- Una clave de DeepL por idioma (opcional) y una clave general para el resto.
- Los iconos del juego (【登場時】, 〚突撃〛…) no se mandan a DeepL: se sustituyen por el
  término fijo del glosario del idioma, protegido con etiquetas que DeepL no toca.
- Los nombres propios se pueden fijar en datos/glosario/nombres_<idioma>.csv (ja;traducción).
- Cada texto japonés se traduce una sola vez por idioma y se guarda en
  datos/traducciones/<idioma>.json: las reimpresiones y versiones paralelas no gastan cuota.
"""
from __future__ import annotations

import csv
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

DEEPL_IDIOMAS = {"es": "ES", "ca": "CA", "en": "EN-GB", "fr": "FR", "it": "IT", "pt": "PT-PT", "de": "DE"}
LOTE = 40                # textos por petición
LOTE_CARACTERES = 20000  # tope aproximado por petición


class TraduccionError(Exception):
    pass


# ------------------------------------------------------------------ DeepL

class ClienteDeepL:
    def __init__(self, clave: str):
        clave = (clave or "").strip()
        if not clave:
            raise TraduccionError("Falta la clave de DeepL.")
        self.clave = clave
        self.base = "https://api-free.deepl.com/v2" if clave.endswith(":fx") else "https://api.deepl.com/v2"

    def _pedir(self, ruta: str, datos: list[tuple[str, str]] | None = None):
        cuerpo = urllib.parse.urlencode(datos).encode() if datos is not None else None
        req = urllib.request.Request(self.base + ruta, data=cuerpo,
                                     headers={"Authorization": f"DeepL-Auth-Key {self.clave}"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            motivos = {403: "clave no válida", 456: "cuota de caracteres agotada este mes",
                       429: "demasiadas peticiones; prueba en un rato", 400: "petición no válida"}
            raise TraduccionError(f"DeepL respondió {e.code}: {motivos.get(e.code, e.reason)}") from e
        except OSError as e:
            raise TraduccionError(f"No se pudo conectar con DeepL: {e}") from e

    def uso(self) -> tuple[int, int]:
        d = self._pedir("/usage")
        return int(d.get("character_count", 0)), int(d.get("character_limit", 0))

    def idiomas_destino(self) -> set[str]:
        return {x["language"].upper() for x in self._pedir("/languages?type=target")}

    def traducir(self, textos: list[str], destino: str) -> list[str]:
        datos = [("text", t) for t in textos]
        datos += [("source_lang", "JA"), ("target_lang", destino), ("tag_handling", "xml"),
                  ("ignore_tags", "x"), ("preserve_formatting", "1")]
        r = self._pedir("/translate", datos)
        return [t["text"] for t in r["translations"]]


# ------------------------------------------------------------------ glosarios

def _cargar_csv(ruta: Path) -> dict[str, str]:
    out = {}
    if ruta.exists():
        with open(ruta, encoding="utf-8-sig", newline="") as f:
            for fila in csv.reader(f, delimiter=";"):
                if len(fila) >= 2 and fila[0].strip() and not fila[0].startswith("#"):
                    out[fila[0].strip()] = fila[1].strip()
    return out


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _desesc(t: str) -> str:
    return t.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


class Glosario:
    """Términos fijos de juego (iconos) y nombres propios de un idioma."""

    def __init__(self, carpeta: Path, idioma: str, respaldo: Path | None = None):
        """carpeta: glosario del usuario; respaldo: glosario de serie del programa."""
        def buscar(nombre):
            for c in (carpeta, respaldo):
                if c is not None and (c / nombre).exists():
                    return c / nombre
            return carpeta / nombre
        datos = json.loads(buscar("terminos.json").read_text(encoding="utf-8"))
        self.iconos: dict[str, str] = datos["iconos"].get(idioma, datos["iconos"]["es"])
        self.claves: dict[str, str] = datos["claves"].get(idioma, datos["claves"]["es"])
        self.plantillas: dict[str, str] = datos["plantillas"].get(idioma, datos["plantillas"]["es"])
        self.nombres = _cargar_csv(buscar(f"nombres_{idioma}.csv"))

    def nombre(self, ja: str) -> str | None:
        return self.nombres.get(ja)

    def proteger(self, texto: str, traducir_nombre: Callable[[str], str]) -> str:
        """Convierte el japonés en XML para DeepL con los términos fijos ya puestos."""
        fijos: list[str] = []

        def fijo(valor: str) -> str:
            fijos.append(valor)
            return f"\x00{len(fijos) - 1}\x00"

        def icono(m):
            tok = m.group(0)
            if tok in self.iconos:
                return fijo(self.iconos[tok])
            interior = tok[1:-1]
            mm = re.fullmatch(r"FILE\s*([0-9０-９]+)", interior)
            if mm:
                return fijo(self.plantillas["file"].format(n=_num(mm.group(1))))
            mm = re.fullmatch(r"ターン\s*([0-9０-９]+)", interior)
            if mm:
                return fijo(self.plantillas["turno"].format(n=_num(mm.group(1))))
            mm = re.fullmatch(r"([0-9０-９]+)枚以上", interior)
            if mm:
                return fijo(self.plantillas["o_mas"].format(n=_num(mm.group(1))))
            mm = re.fullmatch(r"パートナー(.+)", interior)
            if mm and mm.group(1) in self.claves:
                return fijo(self.plantillas["companero"].format(color=self.claves[mm.group(1)]))
            if interior in self.claves:   # 【黒】 = tu Caso es de ese color
                return fijo(self.plantillas["caso_color"].format(color=self.claves[interior]))
            mm = re.fullmatch(r"事件(.+)", interior)
            if mm:   # 【事件青＆黒】, 【事件YAIBA】: color o rasgo del Caso
                partes = [self.claves.get(x) or traducir_nombre(x) for x in re.split(r"[＆&]", mm.group(1))]
                return fijo(self.plantillas["caso_color"].format(color=self.plantillas.get("y", " y ").join(partes)))
            mm = re.fullmatch(r"絆(.+)", interior)
            if mm:   # 【絆工藤新一】: Vínculo con ese nombre
                return fijo(self.plantillas["vinculo"].format(x=traducir_nombre(mm.group(1))))
            return tok

        def clave(m):
            interior = m.group(1)
            if interior in self.claves:
                return fijo(f"«{self.claves[interior]}»")
            mm = re.fullmatch(r"(ミスリード|捜査)\s*([0-9０-９]+|[XＸ])", interior)
            if mm:
                n = mm.group(2) if mm.group(2) in "XＸ" else _num(mm.group(2))
                return fijo(f"«{self.claves[mm.group(1)]} {'X' if n in ('X', 'Ｘ') else n}»")
            mm = re.fullmatch(r"突撃\s*[［\[](キャラ|事件)[］\]]", interior)
            if mm:
                return fijo(f"«{self.claves['突撃' + mm.group(1)]}»")
            mm = re.fullmatch(r"特徴\s*[［\[](.+?)[］\]]", interior)
            if mm:
                return fijo(self.plantillas["rasgo"].format(x=traducir_nombre(mm.group(1))))
            mm = re.fullmatch(r"(?:カード名)?\s*[［\[](.+?)[］\]]", interior)
            if mm:
                return fijo(self.plantillas["nombre"].format(x=traducir_nombre(mm.group(1))))
            return "\x01" + interior + "\x02"   # coste u otra frase: se traduce dentro de «»

        t = re.sub(r"【[^】]+】", icono, texto)
        t = re.sub(r"〚([^〛]+)〛", clave, t)
        for ja in sorted(self.nombres, key=len, reverse=True):
            if ja in t:
                t = t.replace(ja, fijo(self.nombres[ja]))
        t = _esc(t)
        t = t.replace("\x01", "<x>«</x>").replace("\x02", "<x>»</x>")
        t = re.sub(r"\x00(\d+)\x00", lambda m: f"<x>{_esc(fijos[int(m.group(1))])}</x>", t)
        return t.replace("\n", "<br/>")


def _num(s: str) -> int:
    return int(s.translate(str.maketrans("０１２３４５６７８９", "0123456789")))


def restaurar(xml: str) -> str:
    t = re.sub(r"<br\s*/?>", "\n", xml)
    t = re.sub(r"</?x>", "", t)
    t = _desesc(t)
    t = re.sub(r"[ \t]+\n", "\n", t)
    return re.sub(r" {2,}", " ", t).strip()


# ------------------------------------------------------------------ traductor del catálogo

class Traductor:
    def __init__(self, base_datos: Path, idioma: str, cliente, datos_programa: Path | None = None):
        if idioma not in DEEPL_IDIOMAS:
            raise TraduccionError(f"Idioma no previsto: {idioma}")
        self.idioma = idioma
        self.destino = DEEPL_IDIOMAS[idioma]
        self.cliente = cliente
        self.glosario = Glosario(base_datos / "glosario", idioma,
                                 datos_programa / "glosario" if datos_programa else None)
        self.ruta_cache = base_datos / "traducciones" / f"{idioma}.json"
        # «manual»: correcciones hechas a mano; mandan sobre el glosario y sobre DeepL
        self.cache: dict = {"nombres": {}, "rasgos": {}, "textos": {},
                            "manual": {"nombres": {}, "rasgos": {}, "textos": {}}}
        if self.ruta_cache.exists():
            self.cache.update(json.loads(self.ruta_cache.read_text(encoding="utf-8")))
        for tipo in ("nombres", "rasgos", "textos"):
            self.cache.setdefault("manual", {}).setdefault(tipo, {})
        self.enviados = 0

    def guardar_cache(self):
        self.ruta_cache.parent.mkdir(parents=True, exist_ok=True)
        self.ruta_cache.write_text(json.dumps(self.cache, ensure_ascii=False, indent=0), encoding="utf-8")

    # --- piezas
    def _lotes(self, items: list[str]):
        lote, tam = [], 0
        for it in items:
            if lote and (len(lote) >= LOTE or tam + len(it) > LOTE_CARACTERES):
                yield lote
                lote, tam = [], 0
            lote.append(it)
            tam += len(it)
        if lote:
            yield lote

    def _traducir_lista(self, tipo: str, originales: list[str], preparar, progreso, parar, base, peso):
        pendientes = [o for o in dict.fromkeys(originales) if o and o not in self.cache[tipo]]
        hechos = 0
        for lote in self._lotes(pendientes):
            if parar():
                return False
            xml = [preparar(o) for o in lote]
            self.enviados += sum(len(x) for x in xml)
            for o, t in zip(lote, self.cliente.traducir(xml, self.destino)):
                self.cache[tipo][o] = restaurar(t)
            hechos += len(lote)
            self.guardar_cache()
            if progreso:
                progreso(f"{tipo}: {hechos} de {len(pendientes)}", base + peso * hechos / max(1, len(pendientes)))
        return True

    def _manual(self, tipo: str, ja: str) -> str | None:
        return self.cache["manual"][tipo].get(ja)

    def nombre(self, ja: str) -> str:
        return self._manual("nombres", ja) or self.glosario.nombre(ja) or self.cache["nombres"].get(ja) or ja

    # --- correcciones a mano
    def traduccion_actual(self, tipo: str, ja: str) -> str:
        """Lo que se muestra ahora para ese texto japonés (manual > glosario > DeepL)."""
        if tipo == "textos":
            return self._manual("textos", ja) or self.cache["textos"].get(ja, "")
        if tipo == "rasgos":
            return self._manual("rasgos", ja) or self._nombre_o_rasgo(ja)
        return self.nombre(ja) if (self._manual("nombres", ja) or self.glosario.nombre(ja)
                                   or ja in self.cache["nombres"]) else ""

    def es_manual(self, tipo: str, ja: str) -> bool:
        return ja in self.cache["manual"][tipo]

    def corregir(self, tipo: str, ja: str, valor: str):
        """Guarda una corrección. Afecta a todas las cartas con ese mismo texto japonés."""
        valor = valor.strip()
        if not valor:
            self.restablecer(tipo, ja)
            return
        self.cache["manual"][tipo][ja] = valor
        self.guardar_cache()

    def restablecer(self, tipo: str, ja: str):
        """Quita la corrección y vuelve a la traducción del glosario o de DeepL."""
        self.cache["manual"][tipo].pop(ja, None)
        self.guardar_cache()

    def pendiente(self, cartas: list[dict]) -> int:
        """Caracteres japoneses que aún faltan por traducir (estimación de cuota)."""
        n = sum(len(x) for x in {c["nombre"]["ja"] for c in cartas} if x not in self.cache["nombres"]
                and not self.glosario.nombre(x))
        n += sum(len(x) for x in {r for c in cartas for r in c.get("rasgos_ja", [])}
                 if x not in self.cache["rasgos"] and not self.glosario.nombre(x))
        n += sum(len(x) for x in {c["texto"].get("ja", "") for c in cartas} if x and x not in self.cache["textos"])
        return n

    def traducir_catalogo(self, cartas: list[dict], progreso=None, parar=lambda: False) -> bool:
        """Traduce lo que falte y lo escribe en cada carta. Devuelve False si se interrumpe."""
        nombres = [c["nombre"]["ja"] for c in cartas if not self.glosario.nombre(c["nombre"]["ja"])]
        rasgos = [r for c in cartas for r in c.get("rasgos_ja", []) if not self.glosario.nombre(r)]
        ok = self._traducir_lista("nombres", nombres, _esc, progreso, parar, 0.0, 0.1)
        ok = ok and self._traducir_lista("rasgos", rasgos, _esc, progreso, parar, 0.1, 0.05)
        textos = [c["texto"].get("ja", "") for c in cartas]
        ok = ok and self._traducir_lista("textos", textos, lambda t: self.glosario.proteger(t, self._nombre_o_rasgo),
                                         progreso, parar, 0.15, 0.85)
        self.aplicar(cartas)
        return ok

    def _nombre_o_rasgo(self, ja: str) -> str:
        return (self._manual("rasgos", ja) or self._manual("nombres", ja) or self.glosario.nombre(ja)
                or self.cache["nombres"].get(ja) or self.cache["rasgos"].get(ja) or ja)

    def aplicar(self, cartas: list[dict]):
        """Copia a cada carta lo que ya esté traducido (sin llamar a DeepL)."""
        for c in cartas:
            ja = c["nombre"]["ja"]
            nom = self._manual("nombres", ja) or self.glosario.nombre(ja) or self.cache["nombres"].get(ja)
            if nom:
                c["nombre"][self.idioma] = nom
            else:
                c["nombre"].pop(self.idioma, None)
            tja = c["texto"].get("ja", "")
            t = self._manual("textos", tja) or self.cache["textos"].get(tja)
            if t:
                c["texto"][self.idioma] = t
            else:
                c["texto"].pop(self.idioma, None)
            if c.get("rasgos_ja"):
                c.setdefault("rasgos", {})[self.idioma] = [self._nombre_o_rasgo(r) for r in c["rasgos_ja"]]
