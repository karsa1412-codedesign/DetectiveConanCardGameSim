"""Datos de cartas del simulador.

- cartas_demo.json: cartas inventadas para probar el motor (no son cartas reales).
- mazos/*.json: mazos de 40 cartas: {"nombre", "companero", "caso", "cartas": {id: copias}}.

Fase 0 del plan: aquí irá el módulo propio que descarga las cartas reales (nivel,
color, AP, LP, rasgos y texto de efecto) y las traduce con DeepL y glosario, sin
depender de CardScraper. Generará un cartas.json con el mismo formato que el de demo.
"""
