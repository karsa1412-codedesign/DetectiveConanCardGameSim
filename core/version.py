"""Versión de la app y origen de las actualizaciones.

Para publicar una versión nueva: sube VERSION aquí y sube el cambio a la rama main.
GitHub Actions compila el instalador, crea la etiqueta v<VERSION> y lo publica;
las apps instaladas lo detectan al arrancar.
"""
VERSION = "0.11.0"

# Repositorio de GitHub donde se publican las versiones («usuario/repositorio»).
# Vacío = no se buscan actualizaciones. Se puede cambiar en config.ini, sección [actualizaciones].
REPO = "karsa1412-codedesign/DetectiveConanCardGameSim"

# Nombre del instalador dentro de cada versión publicada
PATRON_INSTALADOR = "SimuladorConan-Setup-{version}.exe"


def comparar(a: str, b: str) -> int:
    """-1, 0 o 1 según a sea menor, igual o mayor que b. Admite «v1.2.3» y «1.2»."""
    def partes(v: str):
        v = v.strip().lstrip("vV").split("-")[0].split("+")[0]
        out = []
        for x in v.split("."):
            num = "".join(ch for ch in x if ch.isdigit())
            out.append(int(num) if num else 0)
        while len(out) < 3:
            out.append(0)
        return out
    pa, pb = partes(a), partes(b)
    return (pa > pb) - (pa < pb)
