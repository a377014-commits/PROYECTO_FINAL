"""CarnetUACH Ingeniería - aplicación web (Flask + Oracle)."""
import os
import re
from datetime import datetime
from functools import wraps

import oracledb
from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()

import db  # noqa: E402

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "cambia-esta-clave")

HOME_POR_ROL = {"ADMIN": "admin_panel", "ORGANIZADOR": "org_eventos", "ALUMNO": "alumno_eventos"}
OCUPAN_CUPO = "('INSCRITO', 'ASISTIO')"

# ----------------------------------------------------------------------
# Filtros de plantilla
# ----------------------------------------------------------------------
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
ETIQUETAS = {
    "PENDIENTE": "Pendiente", "APROBADO": "Aprobado", "RECHAZADO": "Rechazado",
    "CANCELADO": "Cancelado", "INSCRITO": "Inscrito", "ASISTIO": "Asistió",
    "ADMIN": "Administrador", "ORGANIZADOR": "Organizador", "ALUMNO": "Alumno",
}


@app.template_filter("dia")
def f_dia(d):
    return d.day


@app.template_filter("mes")
def f_mes(d):
    return MESES[d.month - 1]


@app.template_filter("hora")
def f_hora(d):
    return f"{d:%H:%M}"


@app.template_filter("fechahora")
def f_fechahora(d):
    return f"{d.day} {MESES[d.month - 1]} {d.year}, {d:%H:%M}" if d else ""


@app.template_filter("inputdt")
def f_inputdt(d):
    return d.strftime("%Y-%m-%dT%H:%M") if d else ""


@app.template_filter("etiqueta")
def f_etiqueta(valor):
    return ETIQUETAS.get(valor, str(valor).capitalize())


# ----------------------------------------------------------------------
# Utilidades
# ----------------------------------------------------------------------
def login_required(*roles):
    def decorador(f):
        @wraps(f)
        def envoltura(*args, **kwargs):
            if "user_id" not in session:
                return redirect(url_for("login"))
            if roles and session["rol"] not in roles:
                abort(403)
            return f(*args, **kwargs)
        return envoltura
    return decorador


def mensaje_oracle(e):
    """Traduce errores de Oracle a mensajes claros para la persona usuaria."""
    err = e.args[0] if e.args else None
    codigo = getattr(err, "code", None)
    texto = getattr(err, "message", str(e))
    if codigo == 20001:
        m = re.search(r"ORA-20001: ([^\n]+)", texto)
        return m.group(1) if m else "El evento ya no tiene cupo disponible."
    if codigo == 1:
        return "Ya existe un registro con esos datos."
    if codigo == 2292:
        return "No se puede eliminar: hay registros que dependen de este dato."
    if codigo == 2290:
        return "Alguno de los valores no cumple las reglas de la base de datos."
    app.logger.error("Error de base de datos: %s", texto)
    return "Ocurrió un error con la base de datos. Intenta de nuevo."


def ejecutar_y_avisar(sql, params, mensaje_ok):
    try:
        db.execute(sql, params)
        flash(mensaje_ok, "success")
    except oracledb.DatabaseError as e:
        flash(mensaje_oracle(e), "danger")


def parse_dt(valor):
    return datetime.strptime(valor, "%Y-%m-%dT%H:%M")


@app.errorhandler(403)
def prohibido(_):
    return render_template("error.html", titulo="Sin acceso",
                           mensaje="Tu perfil no tiene permiso para ver esta página."), 403


@app.errorhandler(404)
def no_encontrado(_):
    return render_template("error.html", titulo="No encontramos la página",
                           mensaje="Revisa la dirección o vuelve al inicio."), 404


# ----------------------------------------------------------------------
# Sesión y registro
# ----------------------------------------------------------------------
@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for(HOME_POR_ROL[session["rol"]]))
    return redirect(url_for("login"))


def cargar_perfil(usuario):
    if usuario["rol"] == "ALUMNO":
        return db.query_one("SELECT id_alumno AS id_perfil, nombre FROM alumno WHERE id_usuario = :u",
                            {"u": usuario["id_usuario"]})
    if usuario["rol"] == "ORGANIZADOR":
        return db.query_one("SELECT id_organizador AS id_perfil, nombre FROM organizador WHERE id_usuario = :u",
                            {"u": usuario["id_usuario"]})
    return {"id_perfil": None, "nombre": "Administrador"}


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        correo = request.form.get("correo", "").strip().lower()
        password = request.form.get("password", "")
        usuario = db.query_one(
            "SELECT u.id_usuario, u.password_hash, u.activo, r.nombre AS rol "
            "FROM usuario u JOIN rol r ON r.id_rol = u.id_rol WHERE LOWER(u.correo) = :c",
            {"c": correo},
        )
        if not usuario or not check_password_hash(usuario["password_hash"], password):
            flash("Correo o contraseña incorrectos.", "danger")
        elif not usuario["activo"]:
            flash("Tu cuenta está desactivada. Contacta al administrador.", "warning")
        else:
            perfil = cargar_perfil(usuario)
            if not perfil:
                flash("Tu cuenta no tiene un perfil asociado. Contacta al administrador.", "warning")
            else:
                session.clear()
                session.update(user_id=usuario["id_usuario"], rol=usuario["rol"],
                               perfil_id=perfil["id_perfil"], nombre=perfil["nombre"])
                return redirect(url_for("index"))
    return render_template("login.html")


@app.route("/registro", methods=["GET", "POST"])
def registro():
    carreras = db.query("SELECT id_carrera, nombre FROM carrera ORDER BY nombre")
    if request.method == "POST":
        f = request.form
        correo = f.get("correo", "").strip().lower()
        matricula = f.get("matricula", "").strip()
        nombre = f.get("nombre", "").strip()
        apellidos = f.get("apellidos", "").strip()
        errores = []
        if "@" not in correo:
            errores.append("Escribe un correo válido.")
        if len(f.get("password", "")) < 8:
            errores.append("La contraseña debe tener al menos 8 caracteres.")
        if not re.fullmatch(r"[A-Za-z0-9]{5,10}", matricula):
            errores.append("La matrícula debe tener entre 5 y 10 letras o números.")
        if not nombre or not apellidos:
            errores.append("Escribe tu nombre y tus apellidos.")
        try:
            semestre = int(f.get("semestre", ""))
            id_carrera = int(f.get("id_carrera", ""))
            if not 1 <= semestre <= 12:
                raise ValueError
        except ValueError:
            errores.append("Elige tu carrera e indica un semestre entre 1 y 12.")
        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template("registro.html", carreras=carreras, form=f)
        try:
            with db.transaction() as cur:
                cur.execute("SELECT id_rol FROM rol WHERE nombre = 'ALUMNO'")
                id_rol = cur.fetchone()[0]
                id_usuario = db.insert_returning(
                    cur,
                    "INSERT INTO usuario (correo, password_hash, id_rol) VALUES (:c, :p, :r)",
                    {"c": correo, "p": generate_password_hash(f["password"]), "r": id_rol},
                    "id_usuario",
                )
                cur.execute(
                    "INSERT INTO alumno (id_usuario, matricula, nombre, apellidos, id_carrera, semestre) "
                    "VALUES (:u, :m, :n, :a, :c, :s)",
                    {"u": id_usuario, "m": matricula, "n": nombre, "a": apellidos,
                     "c": id_carrera, "s": semestre},
                )
            flash("Cuenta creada. Ya puedes iniciar sesión.", "success")
            return redirect(url_for("login"))
        except oracledb.IntegrityError:
            flash("Ese correo o esa matrícula ya están registrados.", "danger")
        except oracledb.DatabaseError as e:
            flash(mensaje_oracle(e), "danger")
        return render_template("registro.html", carreras=carreras, form=f)
    return render_template("registro.html", carreras=carreras, form={})


@app.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----------------------------------------------------------------------
# Alumno
# ----------------------------------------------------------------------
@app.route("/eventos")
@login_required("ALUMNO")
def alumno_eventos():
    filtro = request.args.get("categoria", type=int)
    sql = f"""
        SELECT e.id_evento, e.titulo, e.descripcion, e.fecha_inicio, e.fecha_fin, e.cupo,
               c.nombre AS categoria, l.nombre AS lugar, o.nombre AS organizador,
               (SELECT COUNT(*) FROM inscripcion i
                 WHERE i.id_evento = e.id_evento AND i.estatus IN {OCUPAN_CUPO}) AS inscritos,
               (SELECT i.estatus FROM inscripcion i
                 WHERE i.id_evento = e.id_evento AND i.id_alumno = :alumno) AS mi_estatus
        FROM evento e
        JOIN categoria c   ON c.id_categoria = e.id_categoria
        JOIN lugar l       ON l.id_lugar = e.id_lugar
        JOIN organizador o ON o.id_organizador = e.id_organizador
        WHERE e.estatus = 'APROBADO' AND e.fecha_fin >= SYSDATE
    """
    params = {"alumno": session["perfil_id"]}
    if filtro:
        sql += " AND e.id_categoria = :cat"
        params["cat"] = filtro
    sql += " ORDER BY e.fecha_inicio"
    eventos = db.query(sql, params)
    categorias = db.query("SELECT id_categoria, nombre FROM categoria ORDER BY id_categoria")
    return render_template("alumno_eventos.html", eventos=eventos, categorias=categorias, filtro=filtro)


@app.post("/eventos/<int:id_evento>/inscribir")
@login_required("ALUMNO")
def inscribir(id_evento):
    try:
        with db.transaction() as cur:
            # Bloquea el evento para que dos alumnos no ocupen el último lugar a la vez.
            cur.execute("SELECT cupo, estatus, fecha_fin FROM evento WHERE id_evento = :e FOR UPDATE",
                        {"e": id_evento})
            ev = cur.fetchone()
            if not ev or ev[1] != "APROBADO" or ev[2] < datetime.now():
                raise ValueError("Este evento ya no está disponible para inscripción.")
            cur.execute(f"SELECT COUNT(*) FROM inscripcion WHERE id_evento = :e AND estatus IN {OCUPAN_CUPO}",
                        {"e": id_evento})
            if cur.fetchone()[0] >= ev[0]:
                raise ValueError("El evento ya no tiene cupo disponible.")
            cur.execute("SELECT id_inscripcion, estatus FROM inscripcion WHERE id_alumno = :a AND id_evento = :e",
                        {"a": session["perfil_id"], "e": id_evento})
            previa = cur.fetchone()
            if previa and previa[1] != "CANCELADO":
                raise ValueError("Ya estás inscrito en este evento.")
            if previa:
                cur.execute("UPDATE inscripcion SET estatus = 'INSCRITO', fecha_registro = SYSDATE "
                            "WHERE id_inscripcion = :i", {"i": previa[0]})
            else:
                cur.execute("INSERT INTO inscripcion (id_alumno, id_evento) VALUES (:a, :e)",
                            {"a": session["perfil_id"], "e": id_evento})
        flash("Listo, quedaste inscrito en el evento.", "success")
    except ValueError as e:
        flash(str(e), "warning")
    except oracledb.DatabaseError as e:
        flash(mensaje_oracle(e), "danger")
    return redirect(request.referrer or url_for("alumno_eventos"))


@app.post("/inscripciones/<int:id_inscripcion>/cancelar")
@login_required("ALUMNO")
def cancelar_inscripcion(id_inscripcion):
    try:
        filas = db.execute(
            "UPDATE inscripcion SET estatus = 'CANCELADO' "
            "WHERE id_inscripcion = :i AND id_alumno = :a AND estatus = 'INSCRITO' "
            "AND id_evento IN (SELECT id_evento FROM evento WHERE fecha_inicio > SYSDATE)",
            {"i": id_inscripcion, "a": session["perfil_id"]},
        )
        if filas:
            flash("Cancelaste tu inscripción.", "success")
        else:
            flash("Solo puedes cancelar inscripciones de eventos que no han comenzado.", "warning")
    except oracledb.DatabaseError as e:
        flash(mensaje_oracle(e), "danger")
    return redirect(request.referrer or url_for("alumno_inscripciones"))


@app.route("/mis-eventos")
@login_required("ALUMNO")
def alumno_inscripciones():
    inscripciones = db.query(
        """
        SELECT i.id_inscripcion, i.estatus, e.titulo, e.fecha_inicio, e.fecha_fin,
               c.nombre AS categoria, l.nombre AS lugar,
               CASE WHEN e.fecha_inicio > SYSDATE THEN 1 ELSE 0 END AS cancelable
        FROM inscripcion i
        JOIN evento e    ON e.id_evento = i.id_evento
        JOIN categoria c ON c.id_categoria = e.id_categoria
        JOIN lugar l     ON l.id_lugar = e.id_lugar
        WHERE i.id_alumno = :a
        ORDER BY e.fecha_inicio DESC
        """,
        {"a": session["perfil_id"]},
    )
    return render_template("alumno_inscripciones.html", inscripciones=inscripciones)


@app.route("/mi-carnet")
@login_required("ALUMNO")
def alumno_carnet():
    a = session["perfil_id"]
    alumno = db.query_one(
        "SELECT al.matricula, al.nombre, al.apellidos, al.semestre, c.nombre AS carrera "
        "FROM alumno al JOIN carrera c ON c.id_carrera = al.id_carrera WHERE al.id_alumno = :a",
        {"a": a},
    )
    filas = db.query(
        "SELECT id_categoria, categoria, eventos_requeridos, cursados FROM v_avance_carnet "
        "WHERE id_alumno = :a ORDER BY id_categoria",
        {"a": a},
    )
    categorias, total_req, total_ok = [], 0, 0
    for f in filas:
        req = int(f["eventos_requeridos"])
        ok = min(int(f["cursados"]), req)
        categorias.append({"nombre": f["categoria"], "requeridos": req, "cursados": ok,
                           "sellos": [i < ok for i in range(req)], "completa": ok >= req})
        total_req += req
        total_ok += ok
    historial = db.query(
        """
        SELECT e.titulo, c.nombre AS categoria, s.fecha_hora
        FROM asistencia s
        JOIN inscripcion i ON i.id_inscripcion = s.id_inscripcion
        JOIN evento e      ON e.id_evento = i.id_evento
        JOIN categoria c   ON c.id_categoria = e.id_categoria
        WHERE i.id_alumno = :a
        ORDER BY s.fecha_hora DESC
        """,
        {"a": a},
    )
    return render_template("alumno_carnet.html", alumno=alumno, categorias=categorias,
                           total_req=total_req, total_ok=total_ok, historial=historial)


# ----------------------------------------------------------------------
# Organizador
# ----------------------------------------------------------------------
@app.route("/organizador")
@login_required("ORGANIZADOR")
def org_eventos():
    eventos = db.query(
        f"""
        SELECT e.id_evento, e.titulo, e.fecha_inicio, e.fecha_fin, e.cupo, e.estatus,
               c.nombre AS categoria, l.nombre AS lugar,
               (SELECT COUNT(*) FROM inscripcion i
                 WHERE i.id_evento = e.id_evento AND i.estatus IN {OCUPAN_CUPO}) AS inscritos,
               (SELECT COUNT(*) FROM asistencia s JOIN inscripcion i ON i.id_inscripcion = s.id_inscripcion
                 WHERE i.id_evento = e.id_evento) AS asistentes,
               CASE WHEN e.fecha_inicio <= SYSDATE THEN 1 ELSE 0 END AS ya_inicio
        FROM evento e
        JOIN categoria c ON c.id_categoria = e.id_categoria
        JOIN lugar l     ON l.id_lugar = e.id_lugar
        WHERE e.id_organizador = :o
        ORDER BY e.fecha_inicio DESC
        """,
        {"o": session["perfil_id"]},
    )
    return render_template("org_eventos.html", eventos=eventos)


def validar_evento(form, exigir_futuro):
    errores, d = [], {}
    d["titulo"] = form.get("titulo", "").strip()
    d["descripcion"] = form.get("descripcion", "").strip()
    if not d["titulo"]:
        errores.append("Escribe el título del evento.")
    try:
        d["id_categoria"] = int(form.get("id_categoria", ""))
        d["id_lugar"] = int(form.get("id_lugar", ""))
        d["cupo"] = int(form.get("cupo", ""))
    except ValueError:
        errores.append("Elige categoría y lugar, e indica el cupo con un número.")
        return d, errores
    try:
        d["fecha_inicio"] = parse_dt(form.get("fecha_inicio", ""))
        d["fecha_fin"] = parse_dt(form.get("fecha_fin", ""))
    except ValueError:
        errores.append("Indica la fecha y hora de inicio y de fin.")
        return d, errores
    if d["fecha_fin"] <= d["fecha_inicio"]:
        errores.append("La hora de fin debe ser posterior a la de inicio.")
    if exigir_futuro and d["fecha_inicio"] <= datetime.now():
        errores.append("La fecha de inicio debe ser futura.")
    if d["cupo"] < 1:
        errores.append("El cupo debe ser de al menos 1.")
    lugar = db.query_one("SELECT capacidad FROM lugar WHERE id_lugar = :l", {"l": d["id_lugar"]})
    if not lugar:
        errores.append("El lugar elegido no existe.")
    elif d["cupo"] > lugar["capacidad"]:
        errores.append(f"El cupo no puede superar la capacidad del lugar ({lugar['capacidad']}).")
    return d, errores


def catalogos_evento():
    return (db.query("SELECT id_categoria, nombre FROM categoria ORDER BY id_categoria"),
            db.query("SELECT id_lugar, nombre, capacidad FROM lugar ORDER BY nombre"))


@app.route("/organizador/eventos/nuevo", methods=["GET", "POST"])
@login_required("ORGANIZADOR")
def org_evento_nuevo():
    categorias, lugares = catalogos_evento()
    if request.method == "POST":
        datos, errores = validar_evento(request.form, exigir_futuro=True)
        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template("org_evento_form.html", modo="nuevo", evento=datos,
                                   categorias=categorias, lugares=lugares)
        try:
            db.execute(
                "INSERT INTO evento (titulo, descripcion, id_categoria, id_organizador, id_lugar, "
                "fecha_inicio, fecha_fin, cupo, estatus) "
                "VALUES (:t, :d, :c, :o, :l, :fi, :ff, :cu, 'PENDIENTE')",
                {"t": datos["titulo"], "d": datos["descripcion"], "c": datos["id_categoria"],
                 "o": session["perfil_id"], "l": datos["id_lugar"], "fi": datos["fecha_inicio"],
                 "ff": datos["fecha_fin"], "cu": datos["cupo"]},
            )
            flash("Evento creado. Quedó pendiente de aprobación del administrador.", "success")
            return redirect(url_for("org_eventos"))
        except oracledb.DatabaseError as e:
            flash(mensaje_oracle(e), "danger")
        return render_template("org_evento_form.html", modo="nuevo", evento=datos,
                               categorias=categorias, lugares=lugares)
    return render_template("org_evento_form.html", modo="nuevo", evento={},
                           categorias=categorias, lugares=lugares)


@app.route("/organizador/eventos/<int:id_evento>/editar", methods=["GET", "POST"])
@login_required("ORGANIZADOR")
def org_evento_editar(id_evento):
    evento = db.query_one("SELECT * FROM evento WHERE id_evento = :e AND id_organizador = :o",
                          {"e": id_evento, "o": session["perfil_id"]})
    if not evento:
        abort(404)
    if evento["estatus"] not in ("PENDIENTE", "RECHAZADO"):
        flash("Solo puedes editar eventos pendientes o rechazados.", "warning")
        return redirect(url_for("org_eventos"))
    categorias, lugares = catalogos_evento()
    if request.method == "POST":
        datos, errores = validar_evento(request.form, exigir_futuro=True)
        if errores:
            for e in errores:
                flash(e, "danger")
            return render_template("org_evento_form.html", modo="editar", evento={**datos, "id_evento": id_evento},
                                   categorias=categorias, lugares=lugares)
        ejecutar_y_avisar(
            "UPDATE evento SET titulo = :t, descripcion = :d, id_categoria = :c, id_lugar = :l, "
            "fecha_inicio = :fi, fecha_fin = :ff, cupo = :cu, estatus = 'PENDIENTE' "
            "WHERE id_evento = :e AND id_organizador = :o",
            {"t": datos["titulo"], "d": datos["descripcion"], "c": datos["id_categoria"],
             "l": datos["id_lugar"], "fi": datos["fecha_inicio"], "ff": datos["fecha_fin"],
             "cu": datos["cupo"], "e": id_evento, "o": session["perfil_id"]},
            "Cambios guardados. El evento volvió a revisión del administrador.",
        )
        return redirect(url_for("org_eventos"))
    return render_template("org_evento_form.html", modo="editar", evento=evento,
                           categorias=categorias, lugares=lugares)


@app.route("/organizador/eventos/<int:id_evento>/asistencia", methods=["GET", "POST"])
@login_required("ORGANIZADOR")
def org_asistencia(id_evento):
    evento = db.query_one(
        "SELECT id_evento, titulo, fecha_inicio, fecha_fin, estatus FROM evento "
        "WHERE id_evento = :e AND id_organizador = :o",
        {"e": id_evento, "o": session["perfil_id"]},
    )
    if not evento:
        abort(404)
    ya_comenzo = evento["fecha_inicio"] <= datetime.now()
    puede_registrar = evento["estatus"] == "APROBADO" and ya_comenzo

    if request.method == "POST":
        if not puede_registrar:
            flash("La asistencia se registra cuando el evento está aprobado y ya comenzó.", "warning")
            return redirect(url_for("org_asistencia", id_evento=id_evento))
        marcadas = [int(x) for x in request.form.getlist("inscripcion") if x.isdigit()]
        registradas = 0
        try:
            with db.transaction() as cur:
                for id_insc in marcadas:
                    cur.execute(
                        "UPDATE inscripcion SET estatus = 'ASISTIO' "
                        "WHERE id_inscripcion = :i AND id_evento = :e AND estatus = 'INSCRITO'",
                        {"i": id_insc, "e": id_evento},
                    )
                    if cur.rowcount == 1:
                        cur.execute(
                            "INSERT INTO asistencia (id_inscripcion, id_organizador) VALUES (:i, :o)",
                            {"i": id_insc, "o": session["perfil_id"]},
                        )
                        registradas += 1
            flash(f"Asistencia registrada para {registradas} alumno(s).", "success")
        except oracledb.DatabaseError as e:
            flash(mensaje_oracle(e), "danger")
        return redirect(url_for("org_asistencia", id_evento=id_evento))

    inscritos = db.query(
        """
        SELECT i.id_inscripcion, i.estatus, a.matricula, a.nombre || ' ' || a.apellidos AS alumno,
               ca.nombre AS carrera, s.fecha_hora
        FROM inscripcion i
        JOIN alumno a   ON a.id_alumno = i.id_alumno
        JOIN carrera ca ON ca.id_carrera = a.id_carrera
        LEFT JOIN asistencia s ON s.id_inscripcion = i.id_inscripcion
        WHERE i.id_evento = :e AND i.estatus IN ('INSCRITO', 'ASISTIO')
        ORDER BY a.apellidos, a.nombre
        """,
        {"e": id_evento},
    )
    return render_template("org_asistencia.html", evento=evento, inscritos=inscritos,
                           puede_registrar=puede_registrar, ya_comenzo=ya_comenzo)


# ----------------------------------------------------------------------
# Administrador
# ----------------------------------------------------------------------
@app.route("/admin")
@login_required("ADMIN")
def admin_panel():
    resumen = db.query_one(
        """
        SELECT (SELECT COUNT(*) FROM alumno) AS alumnos,
               (SELECT COUNT(*) FROM organizador) AS organizadores,
               (SELECT COUNT(*) FROM evento WHERE estatus = 'PENDIENTE') AS pendientes,
               (SELECT COUNT(*) FROM evento WHERE estatus = 'APROBADO') AS aprobados,
               (SELECT COUNT(*) FROM inscripcion WHERE estatus <> 'CANCELADO') AS inscripciones,
               (SELECT COUNT(*) FROM asistencia) AS asistencias,
               (SELECT COUNT(*) FROM (
                    SELECT id_alumno FROM v_avance_carnet GROUP BY id_alumno
                    HAVING SUM(CASE WHEN cursados >= eventos_requeridos THEN 1 ELSE 0 END) = COUNT(*)
               )) AS carnets_completos
        FROM dual
        """
    )
    por_categoria = db.query(
        """
        SELECT categoria, eventos_requeridos,
               SUM(CASE WHEN cursados >= eventos_requeridos THEN 1 ELSE 0 END) AS completaron,
               COUNT(*) AS total
        FROM v_avance_carnet
        GROUP BY id_categoria, categoria, eventos_requeridos
        ORDER BY id_categoria
        """
    )
    por_alumno = db.query(
        """
        SELECT matricula, alumno, SUM(LEAST(cursados, eventos_requeridos)) AS avance,
               SUM(eventos_requeridos) AS total
        FROM v_avance_carnet
        GROUP BY id_alumno, matricula, alumno
        ORDER BY avance DESC, matricula
        FETCH FIRST 50 ROWS ONLY
        """
    )
    return render_template("admin_panel.html", resumen=resumen, por_categoria=por_categoria,
                           por_alumno=por_alumno)


@app.route("/admin/eventos")
@login_required("ADMIN")
def admin_eventos():
    estatus = request.args.get("estatus", "PENDIENTE")
    sql = """
        SELECT e.id_evento, e.titulo, e.descripcion, e.fecha_inicio, e.fecha_fin, e.cupo, e.estatus,
               c.nombre AS categoria, l.nombre AS lugar, o.nombre AS organizador
        FROM evento e
        JOIN categoria c   ON c.id_categoria = e.id_categoria
        JOIN lugar l       ON l.id_lugar = e.id_lugar
        JOIN organizador o ON o.id_organizador = e.id_organizador
    """
    params = {}
    if estatus != "TODOS":
        sql += " WHERE e.estatus = :est"
        params["est"] = estatus
    sql += " ORDER BY e.fecha_inicio"
    return render_template("admin_eventos.html", eventos=db.query(sql, params), estatus=estatus)


@app.post("/admin/eventos/<int:id_evento>/<accion>")
@login_required("ADMIN")
def admin_evento_decidir(id_evento, accion):
    nuevo = {"aprobar": "APROBADO", "rechazar": "RECHAZADO"}.get(accion)
    if not nuevo:
        abort(404)
    ejecutar_y_avisar(
        "UPDATE evento SET estatus = :n WHERE id_evento = :e AND estatus = 'PENDIENTE'",
        {"n": nuevo, "e": id_evento},
        "Evento aprobado." if nuevo == "APROBADO" else "Evento rechazado.",
    )
    return redirect(url_for("admin_eventos"))


@app.route("/admin/usuarios", methods=["GET", "POST"])
@login_required("ADMIN")
def admin_usuarios():
    if request.method == "POST":
        f = request.form
        correo = f.get("correo", "").strip().lower()
        nombre = f.get("nombre", "").strip()
        departamento = f.get("departamento", "").strip()
        if "@" not in correo or len(f.get("password", "")) < 8 or not nombre or not departamento:
            flash("Completa todos los campos. La contraseña debe tener al menos 8 caracteres.", "danger")
        else:
            try:
                with db.transaction() as cur:
                    cur.execute("SELECT id_rol FROM rol WHERE nombre = 'ORGANIZADOR'")
                    id_rol = cur.fetchone()[0]
                    id_usuario = db.insert_returning(
                        cur,
                        "INSERT INTO usuario (correo, password_hash, id_rol) VALUES (:c, :p, :r)",
                        {"c": correo, "p": generate_password_hash(f["password"]), "r": id_rol},
                        "id_usuario",
                    )
                    cur.execute(
                        "INSERT INTO organizador (id_usuario, nombre, departamento) VALUES (:u, :n, :d)",
                        {"u": id_usuario, "n": nombre, "d": departamento},
                    )
                flash("Organizador creado.", "success")
            except oracledb.IntegrityError:
                flash("Ya existe un usuario con ese correo.", "danger")
            except oracledb.DatabaseError as e:
                flash(mensaje_oracle(e), "danger")
        return redirect(url_for("admin_usuarios"))
    usuarios = db.query(
        """
        SELECT u.id_usuario, u.correo, u.activo, r.nombre AS rol,
               CASE r.nombre
                    WHEN 'ALUMNO' THEN a.nombre || ' ' || a.apellidos
                    WHEN 'ORGANIZADOR' THEN o.nombre
                    ELSE 'Administrador' END AS nombre
        FROM usuario u
        JOIN rol r ON r.id_rol = u.id_rol
        LEFT JOIN alumno a      ON a.id_usuario = u.id_usuario
        LEFT JOIN organizador o ON o.id_usuario = u.id_usuario
        ORDER BY r.nombre, u.correo
        """
    )
    return render_template("admin_usuarios.html", usuarios=usuarios)


@app.post("/admin/usuarios/<int:id_usuario>/estado")
@login_required("ADMIN")
def admin_usuario_estado(id_usuario):
    if id_usuario == session["user_id"]:
        flash("No puedes desactivar tu propia cuenta.", "warning")
    else:
        ejecutar_y_avisar("UPDATE usuario SET activo = 1 - activo WHERE id_usuario = :u",
                          {"u": id_usuario}, "Estado de la cuenta actualizado.")
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/catalogos")
@login_required("ADMIN")
def admin_catalogos():
    return render_template(
        "admin_catalogos.html",
        lugares=db.query("SELECT id_lugar, nombre, ubicacion, capacidad FROM lugar ORDER BY nombre"),
        carreras=db.query("SELECT id_carrera, nombre FROM carrera ORDER BY nombre"),
        categorias=db.query("SELECT id_categoria, nombre, eventos_requeridos FROM categoria ORDER BY id_categoria"),
    )


@app.post("/admin/catalogos/lugar")
@login_required("ADMIN")
def admin_lugar_agregar():
    nombre = request.form.get("nombre", "").strip()
    ubicacion = request.form.get("ubicacion", "").strip()
    try:
        capacidad = int(request.form.get("capacidad", ""))
        if capacidad < 1 or not nombre:
            raise ValueError
    except ValueError:
        flash("Escribe el nombre del lugar y una capacidad válida.", "danger")
        return redirect(url_for("admin_catalogos"))
    ejecutar_y_avisar("INSERT INTO lugar (nombre, ubicacion, capacidad) VALUES (:n, :u, :c)",
                      {"n": nombre, "u": ubicacion, "c": capacidad}, "Lugar agregado.")
    return redirect(url_for("admin_catalogos"))


@app.post("/admin/catalogos/lugar/<int:id_lugar>/eliminar")
@login_required("ADMIN")
def admin_lugar_eliminar(id_lugar):
    ejecutar_y_avisar("DELETE FROM lugar WHERE id_lugar = :i", {"i": id_lugar}, "Lugar eliminado.")
    return redirect(url_for("admin_catalogos"))


@app.post("/admin/catalogos/carrera")
@login_required("ADMIN")
def admin_carrera_agregar():
    nombre = request.form.get("nombre", "").strip()
    if not nombre:
        flash("Escribe el nombre de la carrera.", "danger")
    else:
        ejecutar_y_avisar("INSERT INTO carrera (nombre) VALUES (:n)", {"n": nombre}, "Carrera agregada.")
    return redirect(url_for("admin_catalogos"))


@app.post("/admin/catalogos/carrera/<int:id_carrera>/eliminar")
@login_required("ADMIN")
def admin_carrera_eliminar(id_carrera):
    ejecutar_y_avisar("DELETE FROM carrera WHERE id_carrera = :i", {"i": id_carrera}, "Carrera eliminada.")
    return redirect(url_for("admin_catalogos"))


@app.post("/admin/catalogos/categoria/<int:id_categoria>")
@login_required("ADMIN")
def admin_categoria_actualizar(id_categoria):
    try:
        requeridos = int(request.form.get("eventos_requeridos", ""))
        if requeridos < 1:
            raise ValueError
    except ValueError:
        flash("Indica un número de eventos requeridos mayor a cero.", "danger")
        return redirect(url_for("admin_catalogos"))
    ejecutar_y_avisar("UPDATE categoria SET eventos_requeridos = :r WHERE id_categoria = :i",
                      {"r": requeridos, "i": id_categoria}, "Requisito actualizado.")
    return redirect(url_for("admin_catalogos"))


if __name__ == "__main__":
    app.run(debug=True)
