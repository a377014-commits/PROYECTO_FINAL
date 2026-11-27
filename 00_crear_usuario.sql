-- Ejecutar como SYSTEM (o SYS) conectado a la PDB: freepdb1 en Oracle.
-- Crea el usuario (esquema) donde vivirá la base de datos del Carnet.
CREATE USER carnet IDENTIFIED BY carnet123 QUOTA UNLIMITED ON USERS;
GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE TRIGGER, CREATE SEQUENCE TO carnet;
