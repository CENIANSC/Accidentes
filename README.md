# Observatorio de Accidentes V4 — Streamlit / GitHub

## Instalación
1. Sube el contenido de esta carpeta a un repositorio privado de GitHub, preservando `data/accidentes.xlsx`.
2. En Streamlit Community Cloud configura `app.py` como entrada.
3. Local: `pip install -r requirements.txt` y `streamlit run app.py`.

## Novedades V4
- Comparación entre dos años de intersecciones con cambios absolutos y porcentuales.
- Ranking de aumentos, disminuciones y mayores conteos.
- Evolución anual de un cruce seleccionado y aviso de secuencias de tres años consecutivos con aumentos/disminuciones.
- Comparación de dos periodos que respeta los filtros laterales y la selección espacial, excepto el rango principal de fechas.
- Umbral mínimo de accidentes para evitar saturar el ranking con cruces poco frecuentes.

## Interpretación y calidad
- `N/E`, vacíos y marcadores similares se consideran **Sin dato**, sin eliminar accidentes de los totales.
- Los cruces requieren ambas calles informadas y pueden presentar variantes ortográficas. Son agrupaciones textuales, no geocodificación oficial.
- Las tendencias son descriptivas: no demuestran causalidad ni tasas de riesgo por volumen de tránsito.
- Comparar años incompletos o de distinta cobertura puede inducir conclusiones erróneas.
- Un repositorio privado no garantiza que la app desplegada sea privada: revisa la configuración de acceso y los permisos de uso de la base.
