"""Histórico 2022+ y actualización incremental SEN L0 desde SIM CENACE.

Reutiliza scripts/procesar_generacion.py. No crea desagregaciones por sistema.
"""
import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests
from procesar_generacion import URL, descargar, procesar_csv


def meses_entre(inicio, fin):
    a, b = (int(x) for x in inicio.split('-')), (int(x) for x in fin.split('-'))
    ya, ma = a
    yb, mb = b
    if (ya, ma) > (yb, mb) or not (1 <= ma <= 12 and 1 <= mb <= 12):
        raise ValueError('Rango de meses inválido')
    return [f'{n // 12:04d}-{n % 12 + 1:02d}' for n in range(ya * 12 + ma - 1, yb * 12 + mb)]


def ultimo_cerrado(hoy):
    return f'{hoy.year - 1:04d}-12' if hoy.month == 1 else f'{hoy.year:04d}-{hoy.month - 1:02d}'


def guardar_si_cambio(ruta, contenido):
    if ruta.exists() and ruta.read_bytes() == contenido:
        return False
    ruta.write_bytes(contenido)
    return True


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--modo', choices=['historico', 'mensual'], default='mensual')
    p.add_argument('--desde', default='2022-01', help='Primer mes histórico')
    p.add_argument('--hasta', help='Último mes histórico; por defecto último mes cerrado')
    p.add_argument('--salida', default='generacion_data')
    p.add_argument('--revisar-meses', type=int, default=2, help='Meses cerrados a revisar en modo mensual')
    p.add_argument('--pausa', type=float, default=2.0, help='Segundos entre meses')
    args = p.parse_args()
    if not 1 <= args.revisar_meses <= 12 or args.pausa < 0:
        p.error('Revisar meses: 1..12; pausa no negativa')
    hoy = datetime.now(ZoneInfo('America/Mexico_City'))
    fin = args.hasta or ultimo_cerrado(hoy)
    meses = meses_entre(args.desde if args.modo == 'historico' else '2022-01', fin)
    if args.modo == 'mensual':
        meses = meses[-args.revisar_meses:]
    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    indice_path = salida / 'indice_generacion.json'
    if indice_path.exists():
        indice = json.loads(indice_path.read_text(encoding='utf-8'))
        if indice.get('sistema') != 'SEN' or indice.get('liquidacion') != 'L0':
            raise RuntimeError('Índice incompatible: se esperaba SEN L0')
        registros = {r['periodo']: r for r in indice.get('periodos', [])}
    else:
        registros = {}
    fallos, actualizados, omitidos = [], 0, 0
    print(f'Modo: {args.modo}; meses: {meses[0]} a {meses[-1]} ({len(meses)})', flush=True)
    with requests.Session() as sesion:
        sesion.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; SIM-Reportes-Publicos/1.0)'})
        for pos, periodo in enumerate(meses):
            ruta_csv = salida / f'generacion_L0_SEN_{periodo}.csv'
            ruta_json = salida / f'generacion_L0_SEN_{periodo}.json'
            anterior = registros.get(periodo, {})
            if args.modo == 'historico' and anterior and ruta_csv.exists() and ruta_json.exists():
                huella = hashlib.sha256(ruta_csv.read_bytes()).hexdigest()
                if not anterior.get('sha256_csv') or anterior['sha256_csv'] == huella:
                    # Confirmar integridad del histórico local sin solicitar otra descarga.
                    try:
                        procesar_csv(ruta_csv.read_bytes(), *map(int, periodo.split('-')))
                        omitidos += 1
                        print(f'YA EXISTE {periodo}: se conserva el archivo validado', flush=True)
                        continue
                    except (ValueError, UnicodeError):
                        print(f'AVISO {periodo}: archivo local no válido; se descargará otra vez', flush=True)
            if pos and args.pausa:
                time.sleep(args.pausa)
            try:
                anio, mes = map(int, periodo.split('-'))
                # Reintentos solo para errores de transporte, sin relajar validaciones.
                for intento in range(1, 4):
                    try:
                        contenido, fuente = descargar(sesion, anio, mes)
                        break
                    except requests.RequestException as exc:
                        if intento == 3:
                            raise
                        espera = 3 * intento
                        print(f'REINTENTO {periodo} ({intento}/3): {exc}; espera {espera}s', flush=True)
                        time.sleep(espera)
                        sesion.cookies.clear()
                resultado = procesar_csv(contenido, anio, mes)
                sha = hashlib.sha256(contenido).hexdigest()
                nuevo = {
                    'periodo': periodo, 'sistema': 'SEN', 'liquidacion': 'L0',
                    'horas': resultado['horas'], 'total_mwh': resultado['total_mwh'],
                    'archivo_fuente': fuente, 'archivo_json': ruta_json.name, 'sha256_csv': sha,
                }
                guardar_si_cambio(ruta_csv, contenido)
                guardar_si_cambio(ruta_json, json.dumps(resultado, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
                registros[periodo] = nuevo
                actualizados += 1
                print(f'OK {periodo}: {resultado["horas"]} horas; {resultado["total_mwh"]:,.2f} MWh; {fuente}', flush=True)
            except (requests.RequestException, RuntimeError, ValueError, UnicodeError) as exc:
                fallos.append(periodo)
                print(f'AVISO {periodo}: {exc}', flush=True)
    if not registros:
        print('ERROR: no hay meses validados para crear índice', file=sys.stderr)
        return 1
    doc = {
        'fuente': 'CENACE SIM (Área Pública)', 'url': URL,
        'sistema': 'SEN', 'liquidacion': 'L0',
        'periodos': [registros[k] for k in sorted(registros)],
    }
    guardar_si_cambio(indice_path, (json.dumps(doc, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))
    print(f'RESUMEN: actualizados={actualizados}; conservados={omitidos}; fallidos={len(fallos)}; en índice={len(registros)}', flush=True)
    if fallos:
        print('PENDIENTES:', ', '.join(fallos), flush=True)
        if any(m in registros for m in fallos):
            print('ERROR: falló la revisión de un mes previamente validado', file=sys.stderr)
            return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
