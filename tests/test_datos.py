"""Pruebas de conversión de cartas oficiales, traducción (sin conectar a DeepL) e importación de mazos."""
import json
from pathlib import Path

from core.cartas import Catalogo, CartaDef, Mazo
from datos.descarga import convertir
from datos.traduccion import Glosario, Traductor, restaurar

DATOS = Path(__file__).resolve().parent.parent / "datos"

OFICIAL = {"id": 162, "card_id": "0092", "title": "江戸川コナン", "card_num": "D01003",
           "package": "CT-D01 Case-StartDeck 01 江戸川コナン", "color": "青", "type": "キャラ", "rarity": "D",
           "cost": "4", "ap": "4000", "lp": "1", "category1": "探偵,毛利探偵事務所,少年探偵団",
           "category2": None, "category3": None, "difficulty_first": None, "difficulty_second": None,
           "feature": "【宣言】【ターン1】〚このキャラ以外のキャラを1枚スリープさせる〛：カードを1枚引く。〚迅速〛",
           "cut_in": "【カットイン】AP＋2000（コンタクト中に手札からリムーブして使う）",
           "hirameki": "【ヒラメキ】（証拠からリムーブされるときに発動する）カードを1枚引く。", "henso": None,
           "main_thumb": "D01003.jpg", "main_path": "123.jpg", "rcp_sameid_limit": 3}


def test_convertir_carta_oficial():
    c = convertir(OFICIAL)
    assert c["id"] == "D01003" and c["id_regla"] == "0092" and c["tipo"] == "personaje"
    assert c["colores"] == ["azul"] and (c["nivel"], c["ap"], c["lp"]) == (4, 4000, 1)
    assert c["irrupcion_ap"] == 2000 and c["inspiracion"] and c["palabras_clave"].get("rapidez")
    assert c["rasgos_ja"] == ["探偵", "毛利探偵事務所", "少年探偵団"] and c["paquete"] == "CT-D01"
    d = CartaDef.desde_dict(c)
    assert d.id_regla == "0092" and d.limite == 3


def test_colores_multiples():
    for valor, esperado in (("青,黒", ["azul", "negro"]), ("青緑", ["azul", "verde"])):
        assert convertir({**OFICIAL, "color": valor})["colores"] == esperado


def test_glosario_protege_iconos_y_nombres():
    g = Glosario(DATOS / "glosario", "es")
    xml = g.proteger(OFICIAL["feature"], lambda s: s)
    assert "<x>[Declarar]</x>" in xml and "<x>«Rapidez»</x>" in xml
    assert "<x>«</x>このキャラ" in xml      # el coste se traduce, pero queda entre «»
    assert restaurar("<x>[Declarar]</x> Roba <x>«</x>1 carta<x>»</x>.<br/>Fin") == "[Declarar] Roba «1 carta».\nFin"
    assert "<x>Conan Edogawa</x>" in g.proteger("江戸川コナンを選ぶ", lambda s: s)


class FalsoDeepL:
    def __init__(self):
        self.llamadas = 0

    def traducir(self, textos, destino):
        self.llamadas += 1
        return [f"[{destino}]" + t for t in textos]


def test_traductor_cachea_y_no_repite(tmp_path):
    base = tmp_path / "datos"
    (base / "glosario").mkdir(parents=True)
    for f in (DATOS / "glosario").iterdir():
        (base / "glosario" / f.name).write_bytes(f.read_bytes())
    cartas = [convertir(OFICIAL), convertir({**OFICIAL, "card_num": "D01003P"})]   # paralela: mismo texto
    cli = FalsoDeepL()
    tr = Traductor(base, "ca", cli)
    assert tr.pendiente(cartas) > 0
    assert tr.traducir_catalogo(cartas)
    assert cartas[0]["texto"]["ca"] == cartas[1]["texto"]["ca"]
    assert cartas[0]["nombre"]["ca"] == "Conan Edogawa"         # del glosario, sin DeepL
    llamadas = cli.llamadas
    tr2 = Traductor(base, "ca", cli)                            # nueva sesión: lee la caché
    assert tr2.pendiente(cartas) == 0
    tr2.traducir_catalogo(cartas)
    assert cli.llamadas == llamadas


def test_importar_y_exportar_texto():
    from gui.mazos import mazo_a_texto, texto_a_mazo
    cat = Catalogo.cargar(DATOS / "cartas_demo.json")
    m, avisos = texto_a_mazo("# Prueba\nCompañero: DEMO-P01\nCaso: DEMO-C01\n3 DEMO-A01\nDEMO-A02 x2\n1x DEMO-A03\n9 NOEXISTE", cat.por_id)
    assert m.nombre == "Prueba" and m.companero == "DEMO-P01" and m.caso == "DEMO-C01"
    assert m.cartas == {"DEMO-A01": 3, "DEMO-A02": 2, "DEMO-A03": 1} and len(avisos) == 1
    m2, _ = texto_a_mazo(mazo_a_texto(m), cat.por_id)
    assert m2.cartas == m.cartas and m2.companero == m.companero


def test_limite_por_id_de_reglas():
    base = convertir(OFICIAL)
    paralela = {**base, "id": "D01003P"}
    comp = {**base, "id": "P1", "id_regla": "P1", "tipo": "companero"}
    caso = {**base, "id": "C1", "id_regla": "C1", "tipo": "caso"}
    relleno = [{**base, "id": f"R{i}", "id_regla": f"R{i}"} for i in range(13)]
    cat = Catalogo([CartaDef.desde_dict(d) for d in [base, paralela, comp, caso, *relleno]])
    cartas = {"D01003": 2, "D01003P": 2, **{f"R{i}": 3 for i in range(12)}}
    errores = Mazo("x", "P1", "C1", cartas).validar(cat)
    assert any("0092" in e for e in errores)      # 2 + 2 versiones paralelas = 4 > 3


def test_mazos_oficiales_bien_formados():
    for f in ("CT-D10.json", "CT-D11.json"):
        d = json.loads((DATOS / "mazos" / f).read_text(encoding="utf-8"))
        assert sum(d["cartas"].values()) == 40 and d["companeros_alternativos"]


def test_correcciones_manuales_mandan_y_se_conservan(tmp_path):
    base = tmp_path / "datos"
    (base / "glosario").mkdir(parents=True)
    for f in (DATOS / "glosario").iterdir():
        (base / "glosario" / f.name).write_bytes(f.read_bytes())
    cartas = [convertir(OFICIAL), convertir({**OFICIAL, "card_num": "D01003P"})]
    tr = Traductor(base, "es", FalsoDeepL())
    tr.traducir_catalogo(cartas)
    ja = OFICIAL["feature"] + "\n" + OFICIAL["cut_in"] + "\n" + OFICIAL["hirameki"]
    tr.corregir("textos", ja, "Texto corregido")
    tr.corregir("nombres", "江戸川コナン", "Conan")          # manda sobre el glosario
    tr.aplicar(cartas)
    assert all(c["texto"]["es"] == "Texto corregido" and c["nombre"]["es"] == "Conan" for c in cartas)
    tr2 = Traductor(base, "es", FalsoDeepL())               # se conserva y DeepL no lo pisa
    tr2.traducir_catalogo(cartas)
    assert cartas[0]["texto"]["es"] == "Texto corregido" and tr2.es_manual("textos", ja)
    tr2.restablecer("textos", ja)
    tr2.restablecer("nombres", "江戸川コナン")
    tr2.aplicar(cartas)
    assert cartas[0]["texto"]["es"].startswith("[ES]") and cartas[0]["nombre"]["es"] == "Conan Edogawa"
