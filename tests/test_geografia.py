"""Pruebas aisladas de clasificación geográfica, sin conectar a INEGI."""
import ast
from pathlib import Path
import numpy as np
import pandas as pd
from shapely.geometry import Polygon, mapping, shape, Point
from shapely.prepared import prep

source=Path(__file__).resolve().parents[1].joinpath('app.py').read_text()
module=ast.parse(source)
fn=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='classify_coordinates')
fn.decorator_list=[]
ns={'np':np,'pd':pd,'prep':prep,'shape':shape,'Point':Point}
exec(compile(ast.Module(body=[fn],type_ignores=[]),'app.py','exec'),ns)
geometry=mapping(Polygon([(-102,20),(-101,20),(-101,21),(-102,21)]))
df=pd.DataFrame({'lat':[20.5,21.5,np.nan,200,0], 'lon':[-101.5,-101.5,-101.5,-101.5,0]})
out=ns['classify_coordinates'](df,geometry)
assert out.geo_ok.tolist()==[True,False,False,False,False]
assert out.coord_estado.tolist()==['Dentro del municipio','Fuera del municipio (revisar)','Sin coordenadas / no numéricas','Coordenadas inválidas','Coordenadas inválidas']
print('OK: dentro, fuera, faltantes, inválidas y 0,0')
