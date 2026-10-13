#!/usr/bin/env python3
"""Selecciona la liquidacion mas alta por fuente y fecha a partir de normalizados/."""
import argparse, json, re
from pathlib import Path

def main(base):
    root=Path(base); archivos=list((root/'normalizados').glob('*/*.json'))
    elegidos={}
    for path in archivos:
        try:
            data=json.loads(path.read_text(encoding='utf-8'))
            fuente=data['fuente']; fecha=data['fecha_operacion']; liq=data['liquidacion']
            if not isinstance(liq,int) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',fecha):continue
            key=(fuente,fecha)
            priority=(liq,data.get('fecha_publicacion') or '',path.name)
            if key not in elegidos or priority>elegidos[key][0]:elegidos[key]=(priority,data)
        except (ValueError,KeyError,TypeError) as exc:
            print(f'AVISO: se omite {path}: {exc}')
    catalogo=[]; horas=[]
    for (fuente,fecha),(_,data) in sorted(elegidos.items()):
        catalogo.append({'fuente':fuente,'fecha_operacion':fecha,'liquidacion':data['liquidacion'],
                         'fecha_publicacion':data.get('fecha_publicacion'),'registros':len(data['registros'])})
        grouped={}
        for row in data['registros']:
            sistema=row.get('Sistema'); hora=row.get('Hora')
            if not sistema or not isinstance(hora,int):continue
            key=(sistema,hora); dest=grouped.setdefault(key,{})
            for campo,valor in row.items():
                if campo.endswith('(MWh)') and isinstance(valor,(int,float)):
                    dest[campo]=dest.get(campo,0)+valor
        for (sistema,hora),valores in sorted(grouped.items()):
            horas.append({'fuente':fuente,'fecha_operacion':fecha,'liquidacion':data['liquidacion'],
                          'sistema':sistema,'hora':hora,**{k:round(v,6) for k,v in valores.items()}})
    root.mkdir(parents=True,exist_ok=True)
    for nombre,obj in [('liquidaciones_vigentes.json',catalogo),('vigente_por_sistema_hora.json',horas)]:
        (root/nombre).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Fechas-fuente seleccionadas: {len(catalogo)} | filas sistema-hora: {len(horas)}')
    for c in catalogo[:8]:print(c['fuente'],c['fecha_operacion'],f"L{c['liquidacion']}")

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--datos',default='demanda_perdidas_data');a=p.parse_args();main(a.datos)
