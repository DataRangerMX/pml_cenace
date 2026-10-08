"""Descarga y procesa reportes públicos SIM CENACE: Generación Liquidada L0 SEN.

Dependencias: requests, beautifulsoup4. No modifica el proceso de PML.
Uso: python scripts/procesar_generacion.py --meses 2026-07 2026-08
"""
import argparse
import calendar
import csv
import io
import json
import math
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import unquote

import requests
from bs4 import BeautifulSoup

URL = 'https://www.cenace.gob.mx/Paginas/SIM/Reportes/EnergiaGeneradaTipoTec.aspx'
MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
TECNOS = ['Eolica', 'Fotovoltaica', 'Biomasa', 'Carboelectrica', 'Ciclo Combinado', 'Combustion Interna', 'Geotermoelectrica', 'Hidroelectrica', 'Nucleoelectrica', 'Termica Convencional', 'Turbo Gas']


def campos(html):
    soup = BeautifulSoup(html, 'html.parser')
    form = soup.find('form')
    if form is None:
        raise RuntimeError('El SIM no devolvió el formulario esperado')
    values = {}
    for el in form.select('input[name]'):
        if el.get('type', '').lower() not in ('submit', 'button', 'image', 'file'):
            values[el['name']] = el.get('value', '')
    for el in form.select('select[name]'):
        option = el.find('option', selected=True) or el.find('option')
        values[el['name']] = option.get('value', '') if option else ''
    return form, values


def actualizar_fecha(values, control, year, month):
    # Se reproduce la selección de mes del control Telerik. El día 17 se usa
    # solo como fecha representativa del mes, no como fecha de operación.
    d = f'{year:04d}-{month:02d}-17'
    prefix = f'ctl00_ContentPlaceHolder1_{control}'
    name = f'ctl00$ContentPlaceHolder1${control}'
    label = f'{MESES[month - 1]} de {year}'
    values[name] = d
    values[name + '$dateInput'] = label
    state_name = prefix + '_dateInput_ClientState'
    state = json.loads(values.get(state_name, '{}') or '{}')
    state.update(validationText=d + '-00-00-00', valueAsString=d + '-00-00-00', lastSetTextBoxValue=label)
    values[state_name] = json.dumps(state, ensure_ascii=False, separators=(',', ':'))
    ad_name = prefix + '_AD'
    if ad_name in values:
        ad = json.loads(values[ad_name])
        if isinstance(ad, list) and len(ad) >= 3:
            ad[1] = [year, month, 17]
            ad[2] = [year, month, 17]
            values[ad_name] = json.dumps(ad, separators=(',', ':'))


def botones_csv(form):
    # Los controles de imagen generan coordenadas .x y .y en el POST.
    return list(dict.fromkeys(el['name'].removesuffix('.x').removesuffix('.y')
        for el in form.select('input[name]')
        if re.search(r'GridRadResultado.*gbccolumn', el['name'], re.I)))


def descargar(session, year, month):
    r = session.get(URL, timeout=60)
    r.raise_for_status()
    form, values = campos(r.text)
    for control in ('FechaConsulta', 'FechaInicial', 'FechaFinal'):
        actualizar_fecha(values, control, year, month)
    values['__EVENTTARGET'] = 'ctl00$ContentPlaceHolder1$FechaConsulta'
    values['__EVENTARGUMENT'] = ''
    r = session.post(URL, data=values, headers={'Referer': URL}, timeout=90)
    r.raise_for_status()
    if 'attachment' in r.headers.get('Content-Disposition', '').lower():
        raise RuntimeError('La selección del mes produjo una descarga inesperada')
    form, values = campos(r.text)
    candidates = botones_csv(form)
    if not candidates:
        raise RuntimeError('No hay controles CSV visibles para el mes solicitado')
    # El formulario filtrado suele presentar una fila. Si hay varias,
    # NO descargar indiscriminadamente: identificar la fila que corresponda.
    target = None
    for row in form.select('tr'):
        text = row.get_text(' ', strip=True).lower()
        if re.search(rf'\b{MESES[month-1]}\s+{year}\b', text) and re.search(r'(?<![a-z0-9])(?:l0|0)(?![a-z0-9])', text):
            el = row.find('input', attrs={'name': re.compile(r'GridRadResultado.*gbccolumn', re.I)})
            if el:
                target = el['name']
                break
    if not target:
        if len(candidates) != 1:
            raise RuntimeError('No se puede identificar inequívocamente la fila L0 del mes')
        target = candidates[0]
    values[target + '.x'] = '12'
    values[target + '.y'] = '15'
    values['__EVENTTARGET'] = ''
    values['__EVENTARGUMENT'] = ''
    r = session.post(URL, data=values, headers={'Referer': URL}, timeout=90)
    r.raise_for_status()
    disp = unquote(r.headers.get('Content-Disposition', ''))
    name = re.search(r'filename\s*=\s*"?([^";]+)', disp, re.I)
    filename = name.group(1).strip() if name else ''
    if 'attachment' not in disp.lower() or not re.search(rf'{MESES[month-1]}[ _-]+{year}', filename, re.I) or not re.search(r'(?<![a-z0-9])l0(?![a-z0-9])', filename, re.I) or not re.search(r'\bSEN\b', filename, re.I):
        raise RuntimeError(f'Archivo incorrecto para {year}-{month:02d} L0 SEN: {filename or "sin nombre"}')
    if not r.content or b'<html' in r.content[:500].lower():
        raise RuntimeError('Respuesta vacía o HTML en lugar de CSV')
    return r.content, filename


def procesar_csv(data, year, month):
    text = data.decode('utf-8-sig')
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 9:
        raise ValueError('CSV sin encabezado y datos suficientes')
    preamble = ' '.join(' '.join(row) for row in rows[:7]).lower()
    if f'{MESES[month-1]} {year}' not in preamble or 'original (l0)' not in preamble or 'sistema electrico nacional' not in preamble:
        raise ValueError('El encabezado interno no corresponde al periodo, SEN y L0 solicitados')
    header = [x.strip() for x in rows[7]]
    expected = ['Sistema', 'Dia', 'Hora'] + TECNOS
    if header != expected:
        raise ValueError(f'Columnas inesperadas: {header}')
    seen = set()
    hourly = []
    by_day = defaultdict(lambda: defaultdict(float))
    by_hour = defaultdict(lambda: defaultdict(float))
    totals = defaultdict(float)
    for idx, row in enumerate(rows[8:], 9):
        if not any(x.strip() for x in row):
            continue
        if len(row) != len(header):
            raise ValueError(f'Fila {idx} con {len(row)} columnas en lugar de {len(header)}')
        sistema, fecha_txt, hora_txt = [v.strip() for v in row[:3]]
        fecha = datetime.strptime(fecha_txt, '%d/%m/%Y').date()
        hora = int(hora_txt)
        if sistema != 'SEN' or fecha.year != year or fecha.month != month or not 1 <= hora <= 24:
            raise ValueError(f'Fila {idx}: sistema, fecha u hora fuera del periodo')
        key = (fecha.isoformat(), hora)
        if key in seen:
            raise ValueError(f'Duplicado: {key}')
        seen.add(key)
        vals = {}
        for tech, raw in zip(TECNOS, row[3:]):
            number = float(raw.strip())
            if not math.isfinite(number) or number < 0:
                raise ValueError(f'Valor no válido en fila {idx}, tecnología {tech}')
            vals[tech] = round(number, 4)
            totals[tech] += number
            by_day[fecha.isoformat()][tech] += number
            by_hour[hora][tech] += number
        hourly.append({'fecha': fecha.isoformat(), 'hora': hora, 'sistema': 'SEN', 'tecnologias_mwh': vals, 'total_mwh': round(sum(vals.values()), 4)})
    days = calendar.monthrange(year, month)[1]
    if len(seen) != days * 24 or any((date(year, month, day).isoformat(), hour) not in seen for day in range(1, days+1) for hour in range(1, 25)):
        raise ValueError(f'Cobertura horaria incompleta: {len(seen)} de {days*24}')
    def r4(v): return round(v, 4)
    return {
        'periodo': f'{year}-{month:02d}', 'sistema': 'SEN', 'liquidacion': 'L0', 'unidad': 'MWh',
        'agregacion': 'SEN (sin desglose SIN/BCA/BCS)', 'horas': len(hourly),
        'total_mwh': r4(sum(totals.values())),
        'totales_tecnologia_mwh': {t: r4(totals[t]) for t in TECNOS},
        'diario': [{'fecha': d, 'total_mwh': r4(sum(by_day[d].values())), 'tecnologias_mwh': {t: r4(by_day[d][t]) for t in TECNOS}} for d in sorted(by_day)],
        'perfil_horario': [{'hora': h, 'total_mwh': r4(sum(by_hour[h].values())), 'tecnologias_mwh': {t: r4(by_hour[h][t]) for t in TECNOS}} for h in range(1, 25)],
        'horario': hourly,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--meses', nargs='+', required=True, help='Periodos YYYY-MM (ejemplo: 2026-07 2026-08)')
    parser.add_argument('--salida', default='generacion_data')
    parser.add_argument('--solo-local', action='store_true', help='Validar archivos CSV locales, sin red')
    parser.add_argument('--entrada', default='.', help='Carpeta de CSV en modo --solo-local')
    args = parser.parse_args()
    out = Path(args.salida)
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with requests.Session() as session:
        session.headers.update({'User-Agent': 'Mozilla/5.0 (compatible; SIM-Reportes-Publicos/1.0)'})
        for period in args.meses:
            if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', period):
                raise ValueError(f'Periodo inválido: {period}')
            year, month = map(int, period.split('-'))
            if args.solo_local:
                matches = list(Path(args.entrada).glob(f'*{MESES[month-1]}*{year}*.csv')) + list(Path(args.entrada).glob(f'*{period}*.csv'))
                if not matches:
                    raise FileNotFoundError(f'No hay CSV local para {period}')
                data, filename = matches[0].read_bytes(), matches[0].name
            else:
                data, filename = descargar(session, year, month)
            parsed = procesar_csv(data, year, month)
            # Escribir resultados únicamente después de validar el CSV completo.
            (out / f'generacion_L0_SEN_{period}.csv').write_bytes(data)
            (out / f'generacion_L0_SEN_{period}.json').write_text(json.dumps(parsed, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
            results.append({'periodo': period, 'sistema': 'SEN', 'liquidacion': 'L0', 'horas': parsed['horas'], 'total_mwh': parsed['total_mwh'], 'archivo_fuente': filename, 'archivo_json': f'generacion_L0_SEN_{period}.json'})
            print(f'OK {period} SEN L0: {parsed["horas"]} horas, {parsed["total_mwh"]:,.2f} MWh; {filename}')
    (out / 'indice_generacion.json').write_text(json.dumps({'fuente': 'CENACE SIM (Área Pública)', 'url': URL, 'sistema': 'SEN', 'liquidacion': 'L0', 'periodos': results, 'actualizado_utc': datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Índice generado:', out / 'indice_generacion.json')

if __name__ == '__main__':
    main()
