-- =====================================================================
-- Ejecutar conectado como el usuario "carnet" con "Run Script" (F5)
-- en SQL Developer.
-- =====================================================================

-- ---------- (Opcional) Reiniciar todo: descomenta estas líneas ----------
-- DROP VIEW v_avance_carnet;
-- DROP TABLE asistencia   CASCADE CONSTRAINTS;
-- DROP TABLE inscripcion  CASCADE CONSTRAINTS;
-- DROP TABLE evento       CASCADE CONSTRAINTS;
-- DROP TABLE lugar        CASCADE CONSTRAINTS;
-- DROP TABLE categoria    CASCADE CONSTRAINTS;
-- DROP TABLE organizador  CASCADE CONSTRAINTS;
-- DROP TABLE alumno       CASCADE CONSTRAINTS;
-- DROP TABLE carrera      CASCADE CONSTRAINTS;
-- DROP TABLE usuario      CASCADE CONSTRAINTS;
-- DROP TABLE rol          CASCADE CONSTRAINTS;

-- ---------------------------- TABLAS ----------------------------------

CREATE TABLE rol (
    id_rol    NUMBER GENERATED ALWAYS AS IDENTITY,
    nombre    VARCHAR2(30 CHAR) NOT NULL,
    CONSTRAINT pk_rol        PRIMARY KEY (id_rol),
    CONSTRAINT uq_rol_nombre UNIQUE (nombre)
);

CREATE TABLE usuario (
    id_usuario     NUMBER GENERATED ALWAYS AS IDENTITY,
    correo         VARCHAR2(120 CHAR) NOT NULL,
    password_hash  VARCHAR2(255 CHAR) NOT NULL,
    id_rol         NUMBER NOT NULL,
    activo         NUMBER(1) DEFAULT 1 NOT NULL,
    CONSTRAINT pk_usuario        PRIMARY KEY (id_usuario),
    CONSTRAINT uq_usuario_correo UNIQUE (correo),
    CONSTRAINT fk_usuario_rol    FOREIGN KEY (id_rol) REFERENCES rol (id_rol),
    CONSTRAINT ck_usuario_activo CHECK (activo IN (0, 1))
);

CREATE TABLE carrera (
    id_carrera  NUMBER GENERATED ALWAYS AS IDENTITY,
    nombre      VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT pk_carrera        PRIMARY KEY (id_carrera),
    CONSTRAINT uq_carrera_nombre UNIQUE (nombre)
);

CREATE TABLE alumno (
    id_alumno   NUMBER GENERATED ALWAYS AS IDENTITY,
    id_usuario  NUMBER NOT NULL,
    matricula   VARCHAR2(10 CHAR) NOT NULL,
    nombre      VARCHAR2(60 CHAR) NOT NULL,
    apellidos   VARCHAR2(80 CHAR) NOT NULL,
    id_carrera  NUMBER NOT NULL,
    semestre    NUMBER(2) NOT NULL,
    CONSTRAINT pk_alumno           PRIMARY KEY (id_alumno),
    CONSTRAINT uq_alumno_usuario   UNIQUE (id_usuario),
    CONSTRAINT uq_alumno_matricula UNIQUE (matricula),
    CONSTRAINT fk_alumno_usuario   FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario),
    CONSTRAINT fk_alumno_carrera   FOREIGN KEY (id_carrera) REFERENCES carrera (id_carrera),
    CONSTRAINT ck_alumno_semestre  CHECK (semestre BETWEEN 1 AND 12)
);

CREATE TABLE organizador (
    id_organizador  NUMBER GENERATED ALWAYS AS IDENTITY,
    id_usuario      NUMBER NOT NULL,
    nombre          VARCHAR2(100 CHAR) NOT NULL,
    departamento    VARCHAR2(100 CHAR) NOT NULL,
    CONSTRAINT pk_organizador         PRIMARY KEY (id_organizador),
    CONSTRAINT uq_organizador_usuario UNIQUE (id_usuario),
    CONSTRAINT fk_organizador_usuario FOREIGN KEY (id_usuario) REFERENCES usuario (id_usuario)
);

CREATE TABLE categoria (
    id_categoria        NUMBER GENERATED ALWAYS AS IDENTITY,
    nombre              VARCHAR2(60 CHAR) NOT NULL,
    eventos_requeridos  NUMBER(2) NOT NULL,
    CONSTRAINT pk_categoria        PRIMARY KEY (id_categoria),
    CONSTRAINT uq_categoria_nombre UNIQUE (nombre),
    CONSTRAINT ck_categoria_req    CHECK (eventos_requeridos > 0)
);

CREATE TABLE lugar (
    id_lugar   NUMBER GENERATED ALWAYS AS IDENTITY,
    nombre     VARCHAR2(80 CHAR) NOT NULL,
    ubicacion  VARCHAR2(150 CHAR),
    capacidad  NUMBER(5) NOT NULL,
    CONSTRAINT pk_lugar      PRIMARY KEY (id_lugar),
    CONSTRAINT ck_lugar_cap  CHECK (capacidad > 0)
);

CREATE TABLE evento (
    id_evento       NUMBER GENERATED ALWAYS AS IDENTITY,
    titulo          VARCHAR2(120 CHAR) NOT NULL,
    descripcion     VARCHAR2(1000 CHAR),
    id_categoria    NUMBER NOT NULL,
    id_organizador  NUMBER NOT NULL,
    id_lugar        NUMBER NOT NULL,
    fecha_inicio    DATE NOT NULL,
    fecha_fin       DATE NOT NULL,
    cupo            NUMBER(5) NOT NULL,
    estatus         VARCHAR2(12) DEFAULT 'PENDIENTE' NOT NULL,
    CONSTRAINT pk_evento             PRIMARY KEY (id_evento),
    CONSTRAINT fk_evento_categoria   FOREIGN KEY (id_categoria)   REFERENCES categoria (id_categoria),
    CONSTRAINT fk_evento_organizador FOREIGN KEY (id_organizador) REFERENCES organizador (id_organizador),
    CONSTRAINT fk_evento_lugar       FOREIGN KEY (id_lugar)       REFERENCES lugar (id_lugar),
    CONSTRAINT ck_evento_fechas      CHECK (fecha_fin > fecha_inicio),
    CONSTRAINT ck_evento_cupo        CHECK (cupo > 0),
    CONSTRAINT ck_evento_estatus     CHECK (estatus IN ('PENDIENTE', 'APROBADO', 'RECHAZADO', 'CANCELADO'))
);

CREATE TABLE inscripcion (
    id_inscripcion  NUMBER GENERATED ALWAYS AS IDENTITY,
    id_alumno       NUMBER NOT NULL,
    id_evento       NUMBER NOT NULL,
    fecha_registro  DATE DEFAULT SYSDATE NOT NULL,
    estatus         VARCHAR2(10) DEFAULT 'INSCRITO' NOT NULL,
    CONSTRAINT pk_inscripcion        PRIMARY KEY (id_inscripcion),
    CONSTRAINT uq_inscripcion_unica  UNIQUE (id_alumno, id_evento),
    CONSTRAINT fk_inscripcion_alumno FOREIGN KEY (id_alumno) REFERENCES alumno (id_alumno),
    CONSTRAINT fk_inscripcion_evento FOREIGN KEY (id_evento) REFERENCES evento (id_evento),
    CONSTRAINT ck_inscripcion_estatus CHECK (estatus IN ('INSCRITO', 'CANCELADO', 'ASISTIO'))
);

CREATE TABLE asistencia (
    id_asistencia   NUMBER GENERATED ALWAYS AS IDENTITY,
    id_inscripcion  NUMBER NOT NULL,
    id_organizador  NUMBER NOT NULL,
    fecha_hora      DATE DEFAULT SYSDATE NOT NULL,
    CONSTRAINT pk_asistencia             PRIMARY KEY (id_asistencia),
    CONSTRAINT uq_asistencia_inscripcion UNIQUE (id_inscripcion),
    CONSTRAINT fk_asistencia_inscripcion FOREIGN KEY (id_inscripcion) REFERENCES inscripcion (id_inscripcion),
    CONSTRAINT fk_asistencia_organizador FOREIGN KEY (id_organizador) REFERENCES organizador (id_organizador)
);

-- Índices sobre llaves foráneas (consultas más rápidas)
CREATE INDEX ix_usuario_rol         ON usuario (id_rol);
CREATE INDEX ix_alumno_carrera      ON alumno (id_carrera);
CREATE INDEX ix_evento_categoria    ON evento (id_categoria);
CREATE INDEX ix_evento_organizador  ON evento (id_organizador);
CREATE INDEX ix_evento_lugar        ON evento (id_lugar);
CREATE INDEX ix_inscripcion_evento  ON inscripcion (id_evento);
CREATE INDEX ix_asistencia_organiz  ON asistencia (id_organizador);

-- ----------------------------- VISTA ----------------------------------
-- Avance del carnet: una fila por alumno y categoría, con las asistencias
-- confirmadas contra los eventos requeridos.
CREATE OR REPLACE VIEW v_avance_carnet AS
SELECT a.id_alumno,
       a.matricula,
       a.nombre || ' ' || a.apellidos AS alumno,
       c.id_categoria,
       c.nombre AS categoria,
       c.eventos_requeridos,
       COUNT(s.id_asistencia) AS cursados
FROM alumno a
CROSS JOIN categoria c
LEFT JOIN inscripcion i ON i.id_alumno = a.id_alumno
LEFT JOIN evento e      ON e.id_evento = i.id_evento
                       AND e.id_categoria = c.id_categoria
LEFT JOIN asistencia s  ON s.id_inscripcion = i.id_inscripcion
                       AND e.id_evento IS NOT NULL
GROUP BY a.id_alumno, a.matricula, a.nombre || ' ' || a.apellidos,
         c.id_categoria, c.nombre, c.eventos_requeridos;

-- ---------------------------- TRIGGER ---------------------------------
-- Valida el cupo: no permite más inscritos que el cupo del evento.
CREATE OR REPLACE TRIGGER trg_inscripcion_cupo
FOR INSERT OR UPDATE OF estatus ON inscripcion
COMPOUND TRIGGER
    TYPE t_lista IS TABLE OF NUMBER INDEX BY PLS_INTEGER;
    g_eventos t_lista;

    AFTER EACH ROW IS
    BEGIN
        IF :NEW.estatus IN ('INSCRITO', 'ASISTIO') THEN
            g_eventos(g_eventos.COUNT + 1) := :NEW.id_evento;
        END IF;
    END AFTER EACH ROW;

    AFTER STATEMENT IS
        v_cupo     NUMBER;
        v_ocupados NUMBER;
    BEGIN
        FOR i IN 1 .. g_eventos.COUNT LOOP
            SELECT cupo INTO v_cupo FROM evento WHERE id_evento = g_eventos(i);
            SELECT COUNT(*) INTO v_ocupados
              FROM inscripcion
             WHERE id_evento = g_eventos(i)
               AND estatus IN ('INSCRITO', 'ASISTIO');
            IF v_ocupados > v_cupo THEN
                RAISE_APPLICATION_ERROR(-20001, 'El evento ya no tiene cupo disponible.');
            END IF;
        END LOOP;
    END AFTER STATEMENT;
END trg_inscripcion_cupo;
/

-- ------------------------ DATOS INICIALES -----------------------------
INSERT INTO rol (nombre) VALUES ('ADMIN');
INSERT INTO rol (nombre) VALUES ('ORGANIZADOR');
INSERT INTO rol (nombre) VALUES ('ALUMNO');

INSERT INTO categoria (nombre, eventos_requeridos) VALUES ('Herramientas para mi vida futura', 8);
INSERT INTO categoria (nombre, eventos_requeridos) VALUES ('Salud', 6);
INSERT INTO categoria (nombre, eventos_requeridos) VALUES ('Apoyo a tu comunidad', 6);
INSERT INTO categoria (nombre, eventos_requeridos) VALUES ('Actividad artística', 6);
INSERT INTO categoria (nombre, eventos_requeridos) VALUES ('Actividad científico-filosófica', 6);
INSERT INTO categoria (nombre, eventos_requeridos) VALUES ('Actividad deportiva', 6);

-- Carreras de ejemplo: (tambien desde el panel admin).
INSERT INTO carrera (nombre) VALUES ('Ingeniería Civil');
INSERT INTO carrera (nombre) VALUES ('Ingeniería en Ciencias de la Computación');
INSERT INTO carrera (nombre) VALUES ('Ingeniería Física');
INSERT INTO carrera (nombre) VALUES ('Ingeniería Eléctrica');

INSERT INTO lugar (nombre, ubicacion, capacidad) VALUES ('Auditorio de la Facultad', 'Edificio principal', 300);
INSERT INTO lugar (nombre, ubicacion, capacidad) VALUES ('Sala de usos múltiples', 'Planta baja', 80);
INSERT INTO lugar (nombre, ubicacion, capacidad) VALUES ('Cancha deportiva', 'Área deportiva', 150);
INSERT INTO lugar (nombre, ubicacion, capacidad) VALUES ('Aula magna', 'Edificio de posgrado', 120);

COMMIT;
