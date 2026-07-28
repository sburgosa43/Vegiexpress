# Pruebas

```bash
python tests/run_all.py
```

Devuelve exit code 0 solo si pasan todas. También se puede correr una sola:

```bash
python tests/test_propagacion_costo.py
```

## Cómo están hechas

**No requieren dependencias.** Corren con Python pelado: sin `streamlit`, sin
`gspread` y sin credenciales de Google. Eso es a propósito — protegen lógica de
negocio, no la integración con Sheets, y tienen que poder correrse en cualquier
lado antes de tocar código financiero.

Para lograrlo, `_stubs.py` registra módulos falsos en `sys.modules` **antes** de
importar el código real. Por eso cada prueba se lanza en su **propio proceso**:
si compartieran intérprete, los dobles de una pisarían los de la otra.

En vez de llamar a la API, los dobles acumulan los `updates` que el código
habría escrito, y las pruebas verifican **qué celdas se habrían tocado y con qué
valores**.

## Qué cubre cada una

| Archivo | Qué protege |
|---|---|
| `test_gsheets_cache.py` | El caché del handle de worksheet y su invalidación acoplada: los handles referencian al cliente, así que limpiar uno sin el otro deja punteros muertos. |
| `test_propagacion_costo.py` | La regla de propagación: costo a toda la semana en curso (lunes a domingo), **sin tocar el precio de venta** — cada línea puede tener un precio negociado por cliente/grupo/zona. |
| `test_rutas_costo.py` | Que todas las rutas escriban la fila coherente (F,G,H,I,J,K juntas) vía `order_helper.celdas_linea`, y que Corrección Masiva conserve lo suyo: su semana elegida y su escritura de precio. |

## Al tocar precios o costos

Estas pruebas existen porque ese código ya tuvo bugs caros y silenciosos: un
precio negociado pisado por el precio del catálogo, totales que no cerraban con
su propia fila, y pedidos del lunes que nunca veían un cambio de costo del
miércoles.

Si cambiás algo en `order_helper.py`, `excel_helper.actualizar_precio_semana` o
`modulo_productos._propagar_precios_pedidos`, corré las pruebas antes de
commitear. Y si agregás una regla nueva, agregá el caso: una prueba que no puede
fallar no protege nada.
