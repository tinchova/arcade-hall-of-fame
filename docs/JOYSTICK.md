# Joysticks USB genéricos: hoja de referencia

Para dos joysticks USB genéricos "Lion King" (Microntek "USB Joystick", DragonRise, VID `0x0079`, PID `0x0006`) en macOS, con ES-DE y RetroArch (core FinalBurn Neo). La versión para imprimir (una página HTML con el dibujo) tiene el mismo contenido. La instalación y los problemas que hubo están en [INTEGRACION_ESDE.md](INTEGRACION_ESDE.md), sección Joysticks.

## El joystick

```
        L2 ┌──┐                               ┌──┐ R2
        L1 └──┘                               └──┘ R1
     ┌──────────────────────────────────────────────────┐
     │                                                  │
     │       ▲                                (1)       │
     │     ◄ ✚ ►      [SELECT]  [START]    (4)   (2)    │
     │       ▼          "9"      "10"         (3)       │
     │                                                  │
     └──────────────────────────────────────────────────┘
        cruz                                 botones
```

Los botones de la derecha están en rombo: 1 arriba, 2 a la derecha, 3 abajo y 4 a la izquierda. La cruz es digital (no tiene palancas analógicas).

| Botón físico | Número HID | RetroArch (driver hid) | RetroPad | Equivale en un mando de PlayStation |
|---|---|---|---|---|
| 1 (arriba) | 1 | botón 0 | X (arriba) | triángulo |
| 2 (derecha) | 2 | botón 1 | A (derecha) | círculo |
| 3 (abajo) | 3 | botón 2 | B (abajo) | cruz |
| 4 (izquierda) | 4 | botón 3 | Y (izquierda) | cuadrado |
| L1 | 5 | botón 4 | L | L1 |
| R1 | 6 | botón 5 | R | R1 |
| L2 | 7 | botón 6 | L2 | L2 |
| R2 | 8 | botón 7 | R2 | R2 |
| SELECT ("9") | 9 | botón 8 | Select | Select |
| START ("10") | 10 | botón 9 | Start | Start |
| Cruz | ejes X e Y (0 / 127 / 255) | ejes 0 y 1 | cruz (d-pad) | cruz |

Comprobado botón por botón con `contrib/macos/probar_joystick.sh`. La cruz mueve los ejes X e Y (arriba = Y en 0, abajo = Y en 255, izquierda = X en 0, derecha = X en 255). El dispositivo declara también un hat, pero la cruz no lo usa; el perfil de RetroArch lo mapea igual por si acaso.

## En ES-DE (menú de juegos)

Cualquiera de los dos joysticks maneja el menú.

| Botón | Qué hace |
|---|---|
| Cruz arriba / abajo | moverse por la lista |
| 3 (abajo) | elegir, abrir el juego |
| 2 (derecha) | volver |
| 4 (izquierda) | ver las imágenes y el video del juego |
| 1 (arriba) | marcar o desmarcar como favorito |
| L1 / R1 | sistema anterior / siguiente |
| L2 / R2 | ir al primero / al último de la lista |
| SELECT | opciones de la lista (buscar, ordenar, filtrar) |
| START | menú principal |

Cualquier botón saca el protector de pantalla. El mapeo está en `~/ES-DE/controllers/es_controller_mappings.cfg` (entrada "Lion King USB Joystick") y la configuración de botones en `~/ES-DE/settings/es_input.xml`.

## En los juegos (RetroArch con FinalBurn Neo)

El perfil de RetroArch (`contrib/retroarch/autoconfig/hid/USB_Joystick_0079_0006.cfg`) deja el joystick como un RetroPad estilo PlayStation. FinalBurn Neo reparte los botones del arcade según la posición en el RetroPad (código del core: `src/burner/libretro/retro_input.cpp`, mapeo "Classic", el que se usa por defecto):

| Botón físico | RetroPad | La mayoría de los juegos | Capcom de 6 botones (Street Fighter II y similares) | Neo Geo |
|---|---|---|---|---|
| 3 (abajo) | B | botón 1 | patada débil (LK) | A |
| 2 (derecha) | A | botón 2 | patada media (MK) | B |
| 4 (izquierda) | Y | botón 3 | piña débil (LP) | C |
| 1 (arriba) | X | botón 4 | piña media (MP) | D |
| R1 | R | botón 5 | patada fuerte (HK) | — |
| L1 | L | botón 6 | piña fuerte (HP) | — |
| SELECT | Select | moneda (crédito) | moneda | moneda |
| START | Start | empezar | empezar | empezar |
| Cruz | cruz | mover | mover | mover |

- En la mayoría de los juegos: 3 = botón 1 (disparar, saltar, etc.), 2 = botón 2, 4 = botón 3, 1 = botón 4. Los de 5 y 6 botones siguen con R1 (5) y L1 (6).
- Capcom de 6 botones (CPS1 con 3 piñas y 3 patadas, todos los de CPS2 con 5 o más botones): las piñas quedan arriba (4, 1, L1, de débil a fuerte) y las patadas abajo (3, 2, R1).
- Neo Geo: A, B, C, D en 3, 2, 4, 1.
- El juego del jugador 1 lo maneja el joystick del puerto 1 de RetroArch; el teclado también maneja al jugador 1.

## Atajos de RetroArch con el joystick

Se mantiene apretado SELECT y se aprieta el otro botón. Solo funcionan en el joystick del **jugador 1**.

| Combinación | Qué hace |
|---|---|
| SELECT + START | salir del juego y volver a ES-DE (RetroArch pide confirmar: apretar otra vez) |
| SELECT + 1 | menú de RetroArch (con el juego en pausa) |
| SELECT + R1 | guardar el estado (partida guardada al instante) |
| SELECT + L1 | cargar el estado guardado |

- Un toque corto de SELECT sigue poniendo una moneda. Mientras SELECT está apretado (después de unos 5 cuadros), los demás botones no le llegan al juego, así que las combinaciones no se cuelan en la partida.
- Si se pone una moneda y enseguida START sin soltar SELECT, aparece el aviso para salir; no sale si no se aprieta de nuevo.
- En el menú de RetroArch: cruz para moverse, 3 (abajo) para aceptar y 2 (derecha) para volver. SELECT + 1 de nuevo cierra el menú y sigue el juego.
- El teclado sigue igual: Esc sale (con confirmación), F1 abre el menú, F2 guarda y F4 carga.

## Juegos de carreras

Out Run, Super Hang-On y Chase H.Q. tienen remaps propios (`config/remaps/FinalBurn Neo/<juego>.rmp`): acelerar y frenar son botones, no la cruz.

| Juego | Acelerar | Frenar | Marcha (alta/baja) | Otro |
|---|---|---|---|---|
| Out Run (`outrun`) | 3 | 2 | R1, 4 o 1 | — |
| Super Hang-On (`shangon`) | 3 | 2 | — | 4: turbo (Super Charger) |
| Chase H.Q. (`chasehq`) | 3 | 2 | R1 o 1 | 4: turbo (nitro) |

La cruz izquierda/derecha dobla. Con el teclado no cambia nada: x acelera, z frena, s cambia de marcha y a es el turbo. Para eso cada juego tiene además un override (`config/FinalBurn Neo/<juego>.cfg`) que intercambia las teclas x y z solo en ese juego.

## Jugador 1 y jugador 2

Los dos joysticks son iguales (mismo nombre, VID y PID). Lo único que los distingue es el puerto USB (`locationID` en `ioreg`).

- **ES-DE:** da igual cuál se use.
- **RetroArch 1.22:** el driver "hid" numera los joysticks en el orden en que IOHIDManager los entrega al abrirse, y ese orden **cambia de una vez a otra**: en 10 aperturas seguidas, sin desenchufar nada, cada joystick quedó primero 8 y 2 veces. Las versiones viejas (1.9) los ordenaban por `locationID`; la 1.22 ya no. La reserva de dispositivo por jugador (`input_player1_reserved_device`) solo distingue por nombre o por VID:PID, así que no sirve para dos joysticks iguales. Por eso un sticker por puerto no sirve en RetroArch.
- **Si el juego no responde al joystick que tenés en la mano** (sos el jugador 2): SELECT + START no sirve (los atajos son del jugador 1). Usar el otro joystick, o con el teclado: F1 → Ajustes → Entrada → Controles del puerto 1 → Índice del dispositivo → elegir el otro "Lion King USB Joystick"; después Controles del puerto 2 → el que queda. Volver con Backspace y F1 para seguir. RetroArch guarda ese cambio al salir, pero la próxima vez el orden puede volver a cambiar.
- Para ver qué joystick es cuál: `contrib/macos/probar_joystick.sh` muestra, al apretar un botón, el número del joystick (#1, #2) y su `locationID`. El número es el orden de IOHIDManager en esa apertura (el mismo criterio que RetroArch), así que también cambia entre aperturas.

## Apagado de la pantalla

`apagar_pantalla.sh` apaga la pantalla tras un rato sin uso (`HIDIdleTime`). Comprobado con `probar_joystick.sh`: usar el joystick **sí** reinicia `HIDIdleTime` en macOS 10.15, igual que el teclado y el mouse (los botones y la cruz de los dos joysticks). Jugando solo con el joystick, la pantalla no se apaga. Si se apaga, la enciende el teclado o el mouse.

## Archivos (RetroArch, en `~/Library/Application Support/RetroArch/`)

- `autoconfig/hid/USB_Joystick_0079_0006.cfg`: el perfil. Gana sobre `Retrolink_N64_USB_Controller.cfg` y `DragonRise_ZeroDelay.cfg` (otros mandos con el mismo VID/PID) porque también coincide el nombre, "USB Joystick" con 10 espacios al final, tal como lo informa el dispositivo. RetroArch lo confirma en el registro: `[Autoconf] Lion King USB Joystick configured in port 1` y `port 2`.
- `config/retroarch.cfg`: no se cambió para el joystick. Ya tenía `input_joypad_driver = "hid"`, `input_max_users = "8"`, `input_player1_joypad_index = "0"`, `input_player2_joypad_index = "1"` y `confirm_quit = "true"`.
- `config/remaps/FinalBurn Neo/{outrun,shangon,chasehq}.rmp`: en los tres, B → R2 (acelerar) y A → L2 (frenar). Out Run agrega Y → R (marcha); Super Hang-On mantiene Y → B (Super Charger); Chase H.Q. mantiene X → R (marcha) e Y (turbo).
- `config/FinalBurn Neo/{outrun,shangon,chasehq}.cfg`: overrides con `input_player1_a = "z"` e `input_player1_b = "x"`.
