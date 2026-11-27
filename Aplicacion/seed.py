"""Crea el usuario administrador (y datos de demostración con --demo).

    python seed.py          -> solo el administrador
    python seed.py --demo   -> administrador, organizador, alumno y eventos de ejemplo
"""
import sys
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

from werkzeug.security import generate_password_hash  # noqa: E402

import db  # noqa: E402

ADMIN = ("admin@uach.mx", "Admin123!")
ORGANIZADOR = ("organizador@uach.mx", "Organiza123!")
ALUMNO = ("alumno@uach.mx", "Alumno123!")


def crear_usuario(cur, correo, password, rol):
    cur.execute("SELECT id_usuario FROM usuario WHERE correo = :c", {"c": correo})
    fila = cur.fetchone()
    if fila:
        return fila[0], False
    cur.execute("SELECT id_rol FROM rol WHERE nombre = :n", {"n": rol})
    id_rol = cur.fetchone()[0]
    id_usuario = db.insert_returning(
        cur,
        "INSERT INTO usuario (correo, password_hash, id_rol) VALUES (:c, :p, :r)",
        {"c": correo, "p": generate_password_hash(password), "r": id_rol},
        "id_usuario",
    )
    return id_usuario, True


def main(demo):
    with db.transaction() as cur:
        _, nuevo = crear_usuario(cur, *ADMIN, "ADMIN")
        print(f"Administrador {ADMIN[0]} / {ADMIN[1]}", "(creado)" if nuevo else "(ya existía)")

        if not demo:
            return

        id_usu_org, nuevo = crear_usuario(cur, *ORGANIZADOR, "ORGANIZADOR")
        if nuevo:
            cur.execute(
                "INSERT INTO organizador (id_usuario, nombre, departamento) VALUES (:u, :n, :d)",
                {"u": id_usu_org, "n": "Coordinación de Actividades", "d": "Servicios estudiantiles"},
            )
        cur.execute("SELECT id_organizador FROM organizador WHERE id_usuario = :u", {"u": id_usu_org})
        id_org = cur.fetchone()[0]
        print(f"Organizador {ORGANIZADOR[0]} / {ORGANIZADOR[1]}")

        id_usu_alu, nuevo = crear_usuario(cur, *ALUMNO, "ALUMNO")
        if nuevo:
            cur.execute("SELECT MIN(id_carrera) FROM carrera")
            id_carrera = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO alumno (id_usuario, matricula, nombre, apellidos, id_carrera, semestre) "
                "VALUES (:u, :m, :n, :a, :c, :s)",
                {"u": id_usu_alu, "m": "123456", "n": "Ana", "a": "Prueba Ramírez", "c": id_carrera, "s": 4},
            )
        cur.execute("SELECT id_alumno FROM alumno WHERE id_usuario = :u", {"u": id_usu_alu})
        id_alumno = cur.fetchone()[0]
        print(f"Alumno {ALUMNO[0]} / {ALUMNO[1]}")

        cur.execute("SELECT COUNT(*) FROM evento")
        if cur.fetchone()[0] > 0:
            print("Ya hay eventos, no se agregan los de ejemplo.")
            return

        cur.execute("SELECT MIN(id_lugar) FROM lugar")
        id_lugar = cur.fetchone()[0]
        cur.execute("SELECT id_categoria, nombre FROM categoria ORDER BY id_categoria")
        categorias = cur.fetchall()

        ahora = datetime.now()
        ejemplos = [
            "Taller de currículum y entrevistas",
            "Jornada de salud y nutrición",
            "Colecta para el banco de alimentos",
            "Noche de música y poesía",
            "Conferencia de divulgación científica",
            "Torneo relámpago de fútbol",
        ]
        for i, (id_cat, nombre_cat) in enumerate(categorias):
            inicio = ahora + timedelta(days=3 + i, hours=2)
            db.insert_returning(
                cur,
                "INSERT INTO evento (titulo, descripcion, id_categoria, id_organizador, id_lugar, "
                "fecha_inicio, fecha_fin, cupo, estatus) VALUES (:t, :d, :c, :o, :l, :fi, :ff, :cu, 'APROBADO')",
                {"t": ejemplos[i], "d": f"Evento de ejemplo de la categoría {nombre_cat}.", "c": id_cat,
                 "o": id_org, "l": id_lugar, "fi": inicio, "ff": inicio + timedelta(hours=2), "cu": 30},
                "id_evento",
            )

        # Evento en curso para probar el registro de asistencia.
        id_en_curso = db.insert_returning(
            cur,
            "INSERT INTO evento (titulo, descripcion, id_categoria, id_organizador, id_lugar, "
            "fecha_inicio, fecha_fin, cupo, estatus) VALUES (:t, :d, :c, :o, :l, :fi, :ff, :cu, 'APROBADO')",
            {"t": "Evento en curso (prueba de asistencia)", "d": "Ya comenzó: úsalo para marcar asistencia.",
             "c": categorias[0][0], "o": id_org, "l": id_lugar, "fi": ahora - timedelta(hours=1),
             "ff": ahora + timedelta(hours=2), "cu": 30},
            "id_evento",
        )
        cur.execute(
            "INSERT INTO inscripcion (id_alumno, id_evento) VALUES (:a, :e)",
            {"a": id_alumno, "e": id_en_curso},
        )

        # Evento pendiente para probar la aprobación del administrador.
        inicio = ahora + timedelta(days=10)
        db.insert_returning(
            cur,
            "INSERT INTO evento (titulo, descripcion, id_categoria, id_organizador, id_lugar, "
            "fecha_inicio, fecha_fin, cupo, estatus) VALUES (:t, :d, :c, :o, :l, :fi, :ff, :cu, 'PENDIENTE')",
            {"t": "Evento pendiente de aprobación", "d": "Espera la revisión del administrador.",
             "c": categorias[1][0], "o": id_org, "l": id_lugar, "fi": inicio,
             "ff": inicio + timedelta(hours=2), "cu": 20},
            "id_evento",
        )
        print("Eventos de ejemplo creados.")


if __name__ == "__main__":
    main("--demo" in sys.argv)
