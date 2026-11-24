# SimuladorConan

Simulador de **Detective Conan Card Game** para jugar en el ordenador. Proyecto de fans,
no oficial y sin relación con Takara Tomy ni con los titulares de Detective Conan.
Es independiente de CardScraper: no comparte código con él.

Estado: **fase 1 en marcha**. El motor aplica el reglamento oficial Ver. 2.6. Hay perfiles de
usuario, registro de accesos y dos modos de juego: **Tutorial** (partida guiada pregrabada) y
**Partida local** (dos jugadores en el mismo equipo). Los efectos impresos de las cartas se aplican a mano.

## Perfiles y modos de juego

- Al abrir la app se elige o se crea un **perfil**. La primera vez que entra un perfil nuevo,
  la app recomienda hacer el tutorial; se puede saltar.
- **Tutorial**: partida guiada por Marta, siempre igual (pregrabada). Explica el campo, las
  reglas y las habilidades, resalta en naranja dónde mirar y solo deja hacer la jugada que toca:
  la hace el jugador, no la app. Las jugadas del rival se aplican al pulsar «Continuar».
  Se puede salir en cualquier momento y repetir desde el menú tantas veces como se quiera.
- **Partida local**: partida libre a dos jugadores con cualquier mazo de `datos/mazos`.
- **Registro de accesos**: botón en el menú. Guarda inicios y cierres de sesión, tutoriales
  (iniciado, completado, saltado, abandonado) y partidas (iniciada, terminada, abandonada).

El guion del tutorial está en `datos/tutorial/tutorial.json`. Las pruebas automáticas lo
recorren entero en cada compilación, así que si un cambio en el motor rompe el tutorial,
`generar_instalador.bat` y GitHub no generan el instalador.

## Cartas reales, traducción y mazos

- **Cartas y descargas** (menú): descarga los datos de las colecciones oficiales desde la lista
  oficial de cartas, y las imágenes a una carpeta de tu equipo (por defecto `imagenes/` en tu carpeta de datos).
  El botón «Descargar los mazos de ejemplo» baja CT-D10 y CT-D11, cuyos mazos ya vienen montados
  en `datos/mazos` con el recuento oficial de copias: con eso ya se juega con cartas reales.
- **Traducción**: una clave de DeepL general y, si quieres, una distinta por idioma. Cada texto se
  traduce una sola vez y queda en `datos/traducciones/<idioma>.json`. Los iconos del juego no se
  mandan a DeepL (salen de `datos/glosario/terminos.json`) y los nombres propios se fijan en
  `datos/glosario/nombres_<idioma>.csv`, que puedes editar. Toda la base de cartas son unos
  165.000 caracteres japoneses por idioma.
- **Traducciones** (menú): revisa y corrige a mano el nombre, los rasgos y el texto de cada
  carta, con la carta traducida al lado. Las correcciones se guardan en
  `datos/traducciones/<idioma>.json` (apartado «manual»), mandan sobre DeepL y el glosario, no se
  pierden al volver a traducir y se aplican a todas las cartas que comparten ese texto.
  «Volver a la traducción automática» las deshace.
- **Creador de mazos**: busca por nombre, ID, rasgo o texto; filtra por color, tipo, nivel y
  colección; controla 40 cartas y el máximo de copias por ID de reglas (las versiones paralelas
  cuentan juntas); avisa de las cartas que no comparten color con el Caso. Guarda en `mazos/`
  e importa o exporta listas de texto («3 D10011», «Compañero: D10001», «Caso: D10026»).

## Mesa de juego

El tablero es una mesa gráfica: las cartas se deslizan al moverse y giran al dormirse (90°) o
aturdirse (180°). Las jugadas se pueden hacer arrastrando (las zonas válidas se iluminan en
dorado mientras arrastras):

| Arrastra… | …a | Jugada |
| --- | --- | --- |
| Carta de la mano | Tu Escena (o sobre un Personaje propio si está llena) | Jugar carta / Cambio |
| Tu Personaje | Un Personaje rival dormido o aturdido | Acción |
| Tu Personaje | El Caso rival | Acción al Caso |
| Tu Personaje o tu Compañero | Tus Pruebas | Deducir |
| Tu Compañero | Tu FILE | Asistir |
| Tu Compañero | Tu Caso | Resolver el caso |
| Tu FILE | Tu mano | Siguiente pista |
| Irrupción o Disfraz (en Contacto) | La Escena | Usarla |
| Tu Personaje (cuando te atacan) | El lado rival | Guardar |

Un clic sigue abriendo el menú de la carta; doble clic la amplía. En partida local, el botón
«Rendirse» (o menú Partida) termina la partida en cualquier momento y da la victoria al rival. Los botones de la derecha
siguen disponibles para todo.

## Fundas

Cada jugador elige el dorso de sus cartas. Vienen cinco fundas de diseño propio y se pueden
añadir las tuyas poniendo imágenes (PNG, JPG o WEBP) en la carpeta `fundas/` junto al .exe:
se recortan solas al formato de carta. La funda por defecto se guarda en el perfil (menú →
Fundas) y al empezar una partida local se puede elegir una para cada jugador.

## Cartas traducidas sobre la imagen

Cuando una carta tiene traducción, la app dibuja el texto traducido encima de su imagen al
mostrarla: caja de texto, nombre y rasgos, con los iconos del juego como etiquetas de color.
La imagen descargada no se modifica ni se guarda retocada; todo ocurre en memoria. Se ve en la
vista previa al pasar el ratón, con doble clic («Ver en grande») y en el creador de mazos. Se
activa o desactiva en el menú Partida → «Mostrar las cartas traducidas». Las zonas de cada tipo
de carta están en `gui/superposicion.py` (PLANTILLAS) por si alguna colección necesita ajuste.

## Instalación y actualizaciones

**Para jugar** basta con `SimuladorConan-Setup-<versión>.exe`: instala la app para tu usuario (sin
permisos de administrador), crea los accesos directos y se desinstala desde Configuración de Windows.
Al arrancar, la app busca versiones nuevas; si hay una, la descarga, comprueba su firma SHA-256,
se cierra, se actualiza y vuelve a abrirse. También: menú Ayuda → «Buscar actualizaciones».

**Tus datos no se tocan nunca.** El programa está en `%LOCALAPPDATA%\Programs\SimuladorConan` y
tus datos en `%APPDATA%\SimuladorConan` (Ayuda → Acerca de → «Abrir la carpeta de datos").
Si venías de la versión en carpeta, Ayuda → «Importar datos de una versión anterior» copia
perfiles, mazos, claves, traducciones, imágenes y fundas (la app también lo ofrece la primera vez).
Modo portátil: un archivo `portable.txt` junto al .exe hace que todo se guarde junto al .exe.

### Publicar una versión nueva (lo hace GitHub)

1. Sube el número en `core/version.py` (por ejemplo `0.7.1`) y, si quieres, escribe las novedades
   en `notas/0.7.1.md`.
2. Sube los cambios a GitHub y crea la etiqueta: `git tag v0.7.1` y `git push --tags`.
3. GitHub Actions (`.github/workflows/publicar.yml`) pasa las pruebas, compila el .exe y el
   instalador en Windows y publica la versión. Si las pruebas fallan, no publica nada.
4. Las apps instaladas la detectan al arrancar.

El repositorio se indica en `REPO` de `core/version.py` («usuario/repositorio»). Para que las apps
puedan descargar sin contraseña, el repositorio tiene que ser **público** (no contiene imágenes ni
datos oficiales: las cartas las descarga cada usuario).

### Compilar en tu equipo (opcional)

`generar_instalador.bat` hace lo mismo que GitHub: pruebas, .exe en `dist\SimuladorConan` e
instalador en `salida\` (necesita Inno Setup 6). Para probar el código sin compilar:
`python -m pip install -r requirements.txt` y `python app.py`.

## Cómo se juega en el tablero

- **Acciones posibles** (derecha): solo aparecen las que el reglamento permite en ese
  momento, incluidas las respuestas del rival (Guardia, Pista falsa, Contacto).
- **Pulsar una carta**: muestra sus acciones y las **herramientas manuales** (mover a la
  mano, al descarte, a FILE, dormir, aturdir, AP ±1000…) para aplicar efectos de carta.
- **Ocultar la mano del rival** (menú Partida): al cambiar de jugador aparece una pantalla
  de «Pasa el equipo» para no ver la mano del otro.
- **Carpeta de imágenes** (menú Partida): busca cada imagen por el ID de la carta. Puede ser
  la carpeta donde CardScraper guarda las imágenes. Sin imágenes se dibuja un marco con los datos.
- **Idioma** (menú): castellano y catalán. Para añadir otro, copia `idiomas/es.json` con
  otro nombre (`en.json`…) y traduce los textos.

## Qué está automatizado

| Regla | Estado |
| --- | --- |
| Preparación, mano de 5 y mulligan | Sí |
| Fase automática: activar, robar 1, FILE +2 (+1 el primer turno) | Sí |
| Jugar de la mano: nivel ≤ FILE, color del Caso, 1 por turno | Sí |
| Siguiente pista | Sí |
| Cambio con la escena llena (5) | Sí |
| Asistir, paso a Resolución con 7 en FILE, Resolver el caso | Sí |
| Deducir y Pista falsa | Sí |
| Acción, Guardia, Contacto, Irrupción, Disfraz | Sí |
| Robo de Prueba al Caso (aviso de Inspiración) | Sí (el efecto de Inspiración, manual) |
| Reciclar el mazo y derrota sin descarte | Sí |
| Rapidez, Asalto, Bala | Sí |
| Reglas de MR | Básicas |
| Efectos impresos de cada carta | Manual (fase 3) |

## Estructura

```
app.py          arranque (y `python app.py --prueba 10` para partidas automáticas)
core/           motor de reglas, sin interfaz
  cartas.py     datos de carta, catálogo y validación de mazos
  estado.py     zonas, cartas en juego y decisiones pendientes
  acciones.py   acciones que envía cada jugador
  reglas.py     el reglamento
  efectos/      futuro lenguaje de efectos
  perfiles.py   perfiles de usuario y registro de accesos
  tutorial.py   motor del tutorial pregrabado
datos/          cartas (de momento, inventadas para pruebas), mazos y guion del tutorial
gui/            ventana, tablero, pantallas de perfil y menú (PySide6)
idiomas/        textos de la interfaz (es, ca)
tests/          pruebas automáticas del motor: python -m pytest -q
```

## Archivos de usuario (%APPDATA%\SimuladorConan)

| Archivo | Qué es |
| --- | --- |
| `config.ini` | Idioma, carpeta de imágenes y preferencias. |
| `config.ini` · sección `[deepl]` | Claves de DeepL. No compartas este archivo. |
| `datos/cartas.json` | Cartas descargadas y sus traducciones (no se distribuye). |
| `imagenes/` | Imágenes descargadas (no se distribuyen). |
| `mazos/` | Tus mazos. |
| `fundas/` | Tus imágenes de fundas (opcional). |
| `perfiles/perfiles.json` | Perfiles y sus estadísticas. |
| `perfiles/accesos.csv` | Registro de accesos (se abre con Excel). |
| `datos/glosario/nombres_*.csv` | Tus nombres fijos para DeepL (se copian de serie la primera vez). |
| `idiomas/` | Textos de la interfaz. |
