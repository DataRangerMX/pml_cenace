import json
import urllib.request
import urllib.error

from datetime import datetime, timedelta
from pathlib import Path


# ============================================================
# CONFIGURACIÓN
# ============================================================

SISTEMA = "SIN"
PROCESO = "MDA"
NODO = "01PLO-115"

# Cuántos días hacia atrás probar si no encontramos información
MAX_DIAS_BUSQUEDA = 10


# ============================================================
# FUNCIÓN PARA CONSTRUIR LA URL
# ============================================================

def construir_url(fecha):

    fecha_url = fecha.strftime("%Y/%m/%d")

    return (
        "https://ws01.cenace.gob.mx:8082/"
        "SWPML/SIM/"
        f"{SISTEMA}/"
        f"{PROCESO}/"
        f"{NODO}/"
        f"{fecha_url}/"
        f"{fecha_url}/"
        "JSON"
    )


# ============================================================
# FUNCIÓN PARA CONSULTAR CENACE
# ============================================================

def consultar_cenace(fecha):

    url = construir_url(fecha)

    print()
    print("=" * 70)
    print(f"Probando fecha: {fecha.strftime('%Y-%m-%d')}")
    print(f"URL: {url}")

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            contenido = (
                response
                .read()
                .decode("utf-8")
            )

        datos = json.loads(contenido)

        return datos


    except urllib.error.HTTPError as error:

        print(
            f"HTTP {error.code}: "
            f"{error.reason}"
        )

        return None


    except Exception as error:

        print(
            "Error:",
            type(error).__name__,
            error
        )

        return None


# ============================================================
# FUNCIÓN PARA VALIDAR SI REALMENTE HAY PML
# ============================================================

def tiene_datos(datos):

    if not datos:
        return False

    if datos.get("status") != "OK":
        return False

    resultados = datos.get("Resultados")

    if not resultados:
        return False

    primer_nodo = resultados[0]

    valores = primer_nodo.get("Valores")

    if not valores:
        return False

    return True


# ============================================================
# BUSCAR FECHA MÁS RECIENTE DISPONIBLE
# ============================================================

print("=" * 70)
print("SW-PML CENACE")
print("BÚSQUEDA DEL ÚLTIMO DATO DISPONIBLE")
print("=" * 70)

print(f"Sistema : {SISTEMA}")
print(f"Proceso : {PROCESO}")
print(f"NodoP   : {NODO}")


# Empezamos desde hoy.
# Si todavía no existe información, iremos retrocediendo.

fecha_actual = datetime.now().date()

datos_encontrados = None
fecha_encontrada = None


for dias_atras in range(MAX_DIAS_BUSQUEDA + 1):

    fecha_prueba = (
        fecha_actual
        - timedelta(days=dias_atras)
    )

    datos = consultar_cenace(
        fecha_prueba
    )

    if tiene_datos(datos):

        datos_encontrados = datos
        fecha_encontrada = fecha_prueba

        print()
        print("DATOS ENCONTRADOS")

        break

    else:

        print(
            "Sin información válida."
        )


# ============================================================
# VALIDAR RESULTADO
# ============================================================

if datos_encontrados is None:

    raise RuntimeError(
        "No se encontró información PML "
        f"en los últimos {MAX_DIAS_BUSQUEDA} días."
    )


# ============================================================
# MOSTRAR RESUMEN
# ============================================================

resultados = datos_encontrados["Resultados"]

nodo_resultado = resultados[0]

valores = nodo_resultado["Valores"]


print()
print("=" * 70)
print("ÚLTIMO DATO DISPONIBLE")
print("=" * 70)

print(
    "Fecha:",
    fecha_encontrada.strftime("%Y-%m-%d")
)

print(
    "NodoP:",
    nodo_resultado["clv_nodo"]
)

print(
    "Registros horarios:",
    len(valores)
)


# ============================================================
# GUARDAR ARCHIVO PRINCIPAL
# ============================================================

archivo_salida = Path(
    "datos_pml.json"
)

with open(
    archivo_salida,
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        datos_encontrados,
        archivo,
        ensure_ascii=False,
        indent=4
    )


print()
print(
    "Archivo actualizado:",
    archivo_salida
)


# ============================================================
# GUARDAR COPIA HISTÓRICA
# ============================================================

carpeta_historica = Path(
    "datos",
    str(fecha_encontrada.year)
)

carpeta_historica.mkdir(
    parents=True,
    exist_ok=True
)


archivo_historico = (
    carpeta_historica
    /
    f"{fecha_encontrada.strftime('%Y-%m-%d')}.json"
)


with open(
    archivo_historico,
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        datos_encontrados,
        archivo,
        ensure_ascii=False,
        indent=4
    )


print(
    "Histórico guardado:",
    archivo_historico
)


# ============================================================
# CREAR ÍNDICE DE FECHAS DISPONIBLES
# ============================================================

archivos_historicos = sorted(
    Path("datos").glob("*/*.json"),
    reverse=True
)


fechas_disponibles = [
    archivo.stem
    for archivo in archivos_historicos
]


indice = {

    "ultima_actualizacion":
        datetime.now().isoformat(
            timespec="seconds"
        ),

    "sistema":
        SISTEMA,

    "proceso":
        PROCESO,

    "nodo":
        NODO,

    "ultima_fecha_disponible":
        fecha_encontrada.strftime(
            "%Y-%m-%d"
        ),

    "fechas_disponibles":
        fechas_disponibles

}


with open(
    "indice_pml.json",
    "w",
    encoding="utf-8"
) as archivo:

    json.dump(
        indice,
        archivo,
        ensure_ascii=False,
        indent=4
    )


print(
    "Índice actualizado: indice_pml.json"
)


print()
print("=" * 70)
print("PROCESO TERMINADO CORRECTAMENTE")
print("=" * 70)
