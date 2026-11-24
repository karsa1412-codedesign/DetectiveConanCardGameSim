"""Descarga de las cartas reales desde la lista oficial de cartas.

La web oficial incluye en cada carta sus datos en formato estructurado (atributo data
de la imagen). De ahí se sacan nivel, AP, LP, color, rasgos, texto de efecto, etc., sin
depender del diseño visual de la página. Las imágenes se guardan en la carpeta local
que elija el usuario y nunca se distribuyen con la app.

Es independiente de CardScraper: no comparte código con él.
"""
from __future__ import annotations

import html
import json
import re
import time
import urllib.request
from pathlib import Path
from typing import Callable

BASE = "https://www.takaratomy.co.jp/products/conan-cardgame"
LISTA = BASE + "/cardlist/"
IMAGENES = BASE + "/storage/card/"
AGENTE = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SimuladorConan/1.0 (proyecto de fans)"
PAUSA = 0.6   # segundos entre peticiones, para no cargar la web oficial

TIPOS = {"パートナー": "companero", "キャラ": "personaje", "イベント": "evento", "事件": "caso"}
COLORES = {"青": "azul", "赤": "rojo", "緑": "verde", "黄": "amarillo", "白": "blanco",
           "黒": "negro", "紫": "morado", "桃": "rosa", "ピンク": "rosa", "橙": "naranja"}

Progreso = Callable[[str, float], None]


class DescargaError(Exception):
    pass


def _get(url: str, binario: bool = False, intentos: int = 3):
    ultimo = None
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": AGENTE})
            with urllib.request.urlopen(req, timeout=30) as r:
                datos = r.read()
            return datos if binario else datos.decode("utf-8", "replace")
        except Exception as e:  # red caída, 5xx…
            ultimo = e
            time.sleep(1.5 * (i + 1))
    raise DescargaError(f"No se pudo descargar {url}: {ultimo}")


def listar_paquetes() -> list[tuple[str, str]]:
    """[(código, nombre)] de todas las colecciones publicadas."""
    pagina = _get(LISTA)
    out = []
    for cod, nombre in re.findall(r'<option value="([A-Z]{2}-?[A-Z0-9-]*)">([^<]+)', pagina):
        if (cod, nombre.strip()) not in out:
            out.append((cod, html.unescape(nombre.strip())))
    return out


def _cartas_de(pagina: str) -> list[dict]:
    return [json.loads(html.unescape(m)) for m in re.findall(r"<img src=\"[^\"]*\" data='([^']*)'", pagina)]


def descargar_paquete(codigo: str, progreso: Progreso | None = None) -> list[dict]:
    """Datos en bruto de todas las cartas de una colección (todas las páginas)."""
    url = f"{LISTA}?package={codigo}"
    primera = _get(url)
    m = re.search(r'data-last-page="(\d+)"', primera)
    ultima = int(m.group(1)) if m else 1
    cartas = _cartas_de(primera)
    for pag in range(2, ultima + 1):
        if progreso:
            progreso(f"{codigo}: página {pag} de {ultima}", pag / ultima)
        time.sleep(PAUSA)
        cartas += _cartas_de(_get(f"{url}&page={pag}"))
    vistos, unicas = set(), []
    for c in cartas:
        if c["card_num"] not in vistos:
            vistos.add(c["card_num"])
            unicas.append(c)
    return unicas


# ------------------------------------------------------------------ conversión

def _entero(v) -> int:
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return 0


def _colores(v: str | None) -> list[str]:
    if not v:
        return []
    out = []
    for parte in re.split(r"[,、/・\s]+", v):
        if parte in COLORES:
            out.append(COLORES[parte])
        else:  # «青赤» sin separador
            out += [COLORES[ch] for ch in parte if ch in COLORES]
    return list(dict.fromkeys(out))


def _palabras_clave(texto: str) -> dict:
    pc = {}
    if "〚迅速〛" in texto or "【迅速】" in texto:
        pc["rapidez"] = True
    if re.search(r"〚突撃〛|【突撃】", texto):
        pc["asalto"] = True
    if re.search(r"〚突撃\s*[\[［]キャラ[\]］]〛", texto):
        pc["asalto_personaje"] = True
    if re.search(r"〚突撃\s*[\[［]事件[\]］]〛", texto):
        pc["asalto_caso"] = True
    if "ブレット" in texto:
        pc["bala"] = True
    m = re.search(r"ミスリード\s*([0-9０-９]+)", texto)
    if m:
        pc["pista_falsa"] = int(m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))
    m = re.search(r"捜査\s*([0-9０-９]+)", texto)
    if m:
        pc["investigacion"] = int(m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))
    if "痕跡" in texto:
        pc["rastro"] = True
    return pc


def convertir(c: dict) -> dict:
    """Pasa los datos oficiales al formato de carta del simulador."""
    texto = c.get("feature") or ""
    extras = [c.get(k) for k in ("cut_in", "hirameki", "henso") if c.get(k)]
    completo = "\n".join([texto, *extras]).strip()
    irr = None
    if c.get("cut_in"):
        m = re.search(r"AP\s*[＋+]\s*([0-9０-９]+)", c["cut_in"])
        if m:
            irr = int(m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789")))
    rasgos = [r for k in ("category1", "category2", "category3") if c.get(k)
              for r in re.split(r"[,、]", c[k]) if r]
    paquete = (c.get("package") or "").split(" ")[0]
    d = {
        "id": c["card_num"],
        "id_regla": c.get("card_id") or c["card_num"],
        "nombre": {"ja": c.get("title") or ""},
        "tipo": TIPOS.get(c.get("type"), "personaje"),
        "colores": _colores(c.get("color")),
        "nivel": _entero(c.get("cost")),
        "ap": _entero(c.get("ap")),
        "lp": _entero(c.get("lp")),
        "rasgos_ja": rasgos,
        "nivel_caso": [_entero(c.get("difficulty_first")), _entero(c.get("difficulty_second"))],
        "palabras_clave": _palabras_clave(completo),
        "irrupcion_ap": irr,
        "disfraz": bool(c.get("henso")),
        "inspiracion": bool(c.get("hirameki")),
        "mr": (c.get("rarity") or "").upper().startswith("MR"),
        "texto": {"ja": completo},
        "rareza": c.get("rarity") or "",
        "paquete": paquete,
        "imagen": c.get("main_thumb") or f"{c['card_num']}.jpg",
        "imagen_url": IMAGENES + c["main_path"] if c.get("main_path") else "",
        "limite": _entero(c.get("rcp_sameid_limit")) or 3,
    }
    return d


# ------------------------------------------------------------------ catálogo local

class CatalogoLocal:
    """datos/cartas.json: todas las cartas descargadas, con sus traducciones."""

    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)
        self.datos = {"version": 1, "fuente": LISTA, "paquetes": {}, "cartas": []}
        if self.ruta.exists():
            self.datos = json.loads(self.ruta.read_text(encoding="utf-8"))

    @property
    def cartas(self) -> list[dict]:
        return self.datos["cartas"]

    def paquetes(self) -> dict:
        return self.datos.setdefault("paquetes", {})

    def integrar(self, codigo: str, nombre: str, nuevas: list[dict]):
        """Añade o actualiza cartas conservando las traducciones ya hechas."""
        por_id = {c["id"]: c for c in self.cartas}
        for n in nuevas:
            vieja = por_id.get(n["id"])
            if vieja:
                for campo in ("nombre", "texto"):
                    for idioma, valor in vieja.get(campo, {}).items():
                        if idioma != "ja" and n[campo].get("ja") == vieja[campo].get("ja"):
                            n[campo][idioma] = valor
                vieja.clear()
                vieja.update(n)
            else:
                self.cartas.append(n)
                por_id[n["id"]] = n
        self.paquetes()[codigo] = {"nombre": nombre, "cartas": len(nuevas),
                                   "descargado": time.strftime("%Y-%m-%d %H:%M")}

    def guardar(self):
        self.ruta.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.ruta.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.datos, ensure_ascii=False, indent=0), encoding="utf-8")
        tmp.replace(self.ruta)


def descargar_imagenes(cartas: list[dict], carpeta: Path, progreso: Progreso | None = None,
                       parar: Callable[[], bool] = lambda: False) -> int:
    """Baja las imágenes que falten a carpeta/<colección>/<id>.jpg. Devuelve cuántas bajó."""
    carpeta = Path(carpeta)
    pendientes = []
    for c in cartas:
        if not c.get("imagen_url"):
            continue
        destino = carpeta / (c.get("paquete") or "otros") / c["imagen"]
        if not destino.exists():
            pendientes.append((c, destino))
    hechas = 0
    for i, (c, destino) in enumerate(pendientes):
        if parar():
            break
        if progreso:
            progreso(f"Imagen {i + 1} de {len(pendientes)}: {c['id']}", (i + 1) / max(1, len(pendientes)))
        destino.parent.mkdir(parents=True, exist_ok=True)
        datos = _get(c["imagen_url"], binario=True)
        tmp = destino.with_suffix(".part")
        tmp.write_bytes(datos)
        tmp.replace(destino)
        hechas += 1
        time.sleep(PAUSA / 2)
    return hechas
