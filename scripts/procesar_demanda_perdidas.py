#!/usr/bin/env python3
"""Procesa CSV oficiales CENACE de demanda real y perdidas RNT/RGD.
Uso: python procesar_demanda_perdidas.py --entrada 01_INSUMOS --salida demanda_perdidas_data
No descarga archivos ni modifica otros procesos. Requiere solo Python 3.9+.
"""
import argparse,csv,json,re,hashlib,shutil
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime

FUENTES={
 'demanda_balance': ('Demanda Real Balance','Estimacion de Demanda por Balance (MWh)'),
 'demanda_retiros': ('Demanda Real Retiro','Estimacion de Demanda por Retiros (MWh)'),
 'perdidas_rnt': ('Perdidas RNT','Perdidas (MWh)'),
 'perdidas_rgd': ('Perdidas RGD','Perdidas Tecnicas (MWh)'),
}
MESES={'ene':1,'feb':2,'mar':3,'abr':4,'may':5,'jun':6,'jul':7,'ago':8,'sep':9,'oct':10,'nov':11,'dic':12}

def fuente_archivo(nombre):
    for k,(pref,_) in FUENTES.items():
        if nombre.casefold().startswith(pref.casefold()):return k
    return None

def numero(x):
    s=str(x).strip().replace(',','')
    if not s or s in ('---','-','N/A'):return None
    try:return float(s)
    except ValueError:return None

def leer(p):
    with p.open('r',encoding='utf-8-sig',newline='',errors='replace') as f:filas=list(csv.reader(f))
    cab=next((i for i,r in enumerate(filas) if len(r)>2 and r[0].strip().casefold()=='sistema' and any(c.strip().casefold()=='hora' for c in r)),None)
    if cab is None:raise ValueError('No se encontró encabezado Sistema/Hora')
    meta=' '.join(r[0].strip() for r in filas[:cab] if r)
    m=re.search(r'Dia de Operacion:\s*(\d{2})/(\d{2})/(\d{4})',meta,re.I)
    if not m:raise ValueError('No se identificó fecha de operación')
    dia=f'{m.group(3)}-{m.group(2)}-{m.group(1)}'
    l=re.search(r'LIQUIDACION\s*(\d+)',meta,re.I)
    pub=re.search(r'Fecha de Publicacion:\s*(\d{1,2})/([a-z]{3})/(\d{4})',meta,re.I)
    publicacion=(f'{pub.group(3)}-{MESES[pub.group(2).lower()]:02d}-{int(pub.group(1)):02d}' if pub and pub.group(2).lower() in MESES else None)
    nombres=[s.strip() for s in filas[cab]]
    datos=[];errores=[]
    for nro,r in enumerate(filas[cab+1:],cab+2):
        if not r or not any(s.strip() for s in r):continue
        if len(r)!=len(nombres):errores.append({'fila':nro,'problema':'columnas_incorrectas'});continue
        d={k:v.strip() for k,v in zip(nombres,r)}
        try:d['Hora']=int(d['Hora'])
        except (ValueError,KeyError):errores.append({'fila':nro,'problema':'hora_invalida'});continue
        if not 1<=d['Hora']<=25:errores.append({'fila':nro,'problema':'hora_fuera_rango'});continue
        if not d.get('Sistema'):errores.append({'fila':nro,'problema':'sistema_vacio'});continue
        for k in nombres:
            if '(MWh)' in k or k.startswith('%'):
                v=numero(d[k]);d[k]=v
                if v is None and d.get(k) is not None and str(r[nombres.index(k)]).strip() not in ('', '---', '-', 'N/A'):errores.append({'fila':nro,'problema':'valor_no_numerico','columna':k})
        datos.append(d)
    return {'fecha_operacion':dia,'liquidacion':int(l.group(1)) if l else None,'fecha_publicacion':publicacion,'columnas':nombres,'registros':datos,'errores':errores}

def escribir(p,obj):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('w',encoding='utf-8') as f:json.dump(obj,f,ensure_ascii=False,indent=2,allow_nan=False)

def ejecutar(entrada,salida):
    entrada=Path(entrada);salida=Path(salida)
    encontrados=sorted(p for p in entrada.rglob('*.csv') if fuente_archivo(p.name))
    manifest=[];seleccion={};incidencias=[]
    for p in encontrados:
        fuente=fuente_archivo(p.name)
        try:obj=leer(p)
        except Exception as e:
            incidencias.append({'archivo':p.name,'error':str(e)});continue
        if obj['fecha_operacion']<'2022-01-01':continue
        raw=p.read_bytes();sha=hashlib.sha256(raw).hexdigest()
        destino=salida/'originales'/fuente/obj['fecha_operacion']/p.name
        destino.parent.mkdir(parents=True,exist_ok=True)
        if p.resolve()!=destino.resolve():shutil.copy2(p,destino)
        item={'fuente':fuente,'archivo':p.name,'fecha_operacion':obj['fecha_operacion'],
              'fecha_publicacion':obj['fecha_publicacion'],'liquidacion':obj['liquidacion'],
              'registros':len(obj['registros']),'errores':len(obj['errores']),'sha256':sha}
        manifest.append(item)
        if obj['errores']:incidencias.append({'archivo':p.name,'detalles':obj['errores'][:50]})
        # Version vigente por fuente, día y liquidación: publicación más reciente, desempate por nombre.
        clave=(fuente,obj['fecha_operacion'],obj['liquidacion'])
        prev=seleccion.get(clave)
        if prev is None or ((obj['fecha_publicacion'] or ''),p.name)>((prev[0]['fecha_publicacion'] or ''),prev[1].name):
            seleccion[clave]=(obj,p)
    agregados=defaultdict(lambda:defaultdict(float));conteos=Counter();claves=set()
    for (fuente,fecha,liq),(obj,p) in seleccion.items():
        # Conservar granularidad completa, no cruzar gerencias o zonas indiscriminadamente.
        escribir(salida/'normalizados'/fuente/f'{fecha}_L{liq}.json',
                 {'fuente':fuente,'fecha_operacion':fecha,'liquidacion':liq,
                  'fecha_publicacion':obj['fecha_publicacion'],'columnas':obj['columnas'],
                  'registros':obj['registros']})
        for d in obj['registros']:
            sistema=d['Sistema'];hora=d['Hora']
            dims=[d.get(k,'') for k in ('Area','Zona de Carga','Gerencia de Control Regional')]
            clave_fila=(fuente,fecha,liq,sistema,hora,*dims)
            if clave_fila in claves:incidencias.append({'archivo':p.name,'problema':'clave_duplicada','clave':clave_fila})
            claves.add(clave_fila)
            conteos[(fuente,fecha,liq,sistema)]+=1
            # Sumatoria de variables energéticas; no sumar porcentajes.
            for campo,valor in d.items():
                if campo.endswith('(MWh)') and isinstance(valor,(float,int)):
                    agregados[(fuente,fecha,liq,sistema,hora)][campo]+=valor
    salida_horaria=[]
    for (fuente,fecha,liq,sistema,hora),campos in sorted(agregados.items()):
        salida_horaria.append({'fuente':fuente,'fecha_operacion':fecha,'liquidacion':liq,
                               'sistema':sistema,'hora':hora,**{k:round(v,6) for k,v in campos.items()}})
    escribir(salida/'agregados_por_sistema_hora.json',salida_horaria)
    escribir(salida/'inventario.json',{'inicio_objetivo':'2022-01-01','archivos':manifest,
       'cobertura': [{'fuente':f,'fecha':dt,'liquidacion':liq,'sistema':s,'registros':n}
                    for (f,dt,liq,s),n in sorted(conteos.items())],
       'incidencias':incidencias})
    print(f'CSV identificados: {len(encontrados)} | versiones procesadas: {len(seleccion)} | registros horarios agregados: {len(salida_horaria)} | incidencias: {len(incidencias)}')
    for k in FUENTES:
        fechas=sorted({f for (t,f,l) in seleccion if t==k})
        print(f'{k}: {len(fechas)} fechas, {fechas[0] if fechas else "sin datos"} a {fechas[-1] if fechas else "sin datos"}')

if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--entrada',default='01_INSUMOS')
    a.add_argument('--salida',default='demanda_perdidas_data')
    args=a.parse_args();ejecutar(args.entrada,args.salida)
