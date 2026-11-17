# Observatorio de Accidentes de Tránsito · Guanajuato V8

Plataforma de análisis para los **46 municipios de Guanajuato**.

Desarrollada por **Daniel A. Aguirre Ibarra** (Doctorado en Logística y Dirección de la Cadena de Suministro | UPAEP), con el apoyo del **Observatorio Ciudadano de Irapuato**.

## Publicación
1. Subir el contenido de esta carpeta a un repositorio privado de GitHub.
2. Desplegar `app.py` desde Streamlit Community Cloud.
3. El repositorio incluye `data/accidentes.xlsx` (Irapuato) y `data/plantilla_municipal.xlsx`.
4. Para otro municipio, seleccionarlo y cargar su Excel desde la interfaz. Opcionalmente, guardar una base persistente como `data/municipios/11XXX.xlsx`.

## Estructura de datos
Una fila por accidente, encabezados en la primera fila. Usa la plantilla `data/plantilla_municipal.xlsx`.

**Obligatorias:** FECHA, HORA, COLONIA, CALLE1, CALLE2, LATITUD, LONGITUD, VEHÍCULOS PARTICIPANTES, TIPO DE ACCIDENTE, CAUSA.

**Opcionales:** DIA, MES, AÑO (se derivan de FECHA).

- FECHA: fecha Excel o AAAA-MM-DD.
- HORA: hora Excel, HH:MM o HH:MM:SS (24 h); N/E o vacío si se desconoce.
- LATITUD/LONGITUD: números decimales con signo, no grados/minutos/segundos.
- N/E: se trata como información faltante, no como categoría de accidente.
- No cargar datos personales.

## Periodos del día
- Madrugada: 00:00–05:59
- Mañana: 06:00–11:59
- Tarde: 12:00–17:59
- Noche: 18:00–23:59

## Validación geográfica
Se consulta el límite municipal INEGI. Los registros sin coordenadas válidas o fuera del polígono se excluyen de todos los mapas y estadísticas y se registran en auditoría. Si INEGI no responde, el análisis se detiene para no mostrar resultados con límites aproximados.

## Notas
La base de Irapuato incluida proviene del Excel actualizado entregado para esta versión. La selección de municipio no cambia la procedencia de los datos. Las cargas temporales no se guardan automáticamente en GitHub. El archivo de datos original se conserva.
