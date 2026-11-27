# CarnetUACH Ingeniería

Sistema web para el Carnet de actividades de la Facultad de Ingeniería de la UACH.
Backend: Python + Flask. Base de datos: Oracle (python-oracledb). Frontend: HTML, Bootstrap 5 y Jinja2.

## Perfiles
- **Administrador:** aprueba o rechaza eventos, gestiona organizadores y catálogos (lugares, carreras, requisitos) y ve reportes.
- **Organizador:** crea eventos, ve inscritos y registra la asistencia (manual, sin QR).
- **Alumno:** se registra, se inscribe a eventos, cancela y consulta el avance de su carnet.

## Puesta en marcha

1. **Crear el usuario de Oracle** (como SYSTEM, conectado a la PDB `freepdb1`):
   ejecuta `00_crear_usuario.sql`.
2. **Crear las tablas** (conectado como `carnet`): abre `01_schema.sql` en SQL Developer y usa *Run Script* (F5).
3. **Instalar dependencias de Python:**
   ```
   python -m venv venv
   venv\Scripts\activate        (Windows)   |   source venv/bin/activate   (Linux/Mac)
   pip install -r requirements.txt
   ```
4. **Configurar la conexión:** copia `.env.example` a `.env` y ajusta usuario, contraseña y DSN
   (`localhost:1521/XEPDB1` en Oracle XE 18c/21c; en XE 11g usa `localhost:1521/XE`).
5. **Crear el administrador (y datos de prueba):**
   ```
   python seed.py --demo
   ```
6. **Ejecutar:**
   ```
   python app.py
   ```
   Abre http://127.0.0.1:5000

## Cuentas de prueba (solo con `--demo`)
| Perfil | Correo | Contraseña |
|---|---|---|
| Administrador | admin@uach.mx | Admin123! |
| Organizador | organizador@uach.mx | Organiza123! |
| Alumno | alumno@uach.mx | Alumno123! |

Cambia estas contraseñas antes de usar el sistema fuera de pruebas.

## Estructura
```
01_schema.sql   tablas, vista V_AVANCE_CARNET, trigger de cupo y datos iniciales
app.py          rutas y reglas del sistema
db.py           conexión a Oracle
seed.py         administrador y datos de demostración
templates/      pantallas (Jinja2 + Bootstrap)
static/         estilos
```
