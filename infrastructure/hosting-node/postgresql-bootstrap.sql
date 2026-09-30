\set ON_ERROR_STOP on

-- Run once as the PostgreSQL cluster administrator on a DEDICATED Ithute
-- hosting database service. Supply the password without putting it in shell
-- history, for example by loading a protected psql variables file.
-- Required psql variable: hosting_admin_password
\if :{?hosting_admin_password}
\else
  \echo 'Missing required psql variable: hosting_admin_password'
  \quit 3
\endif

SELECT format(
  'CREATE ROLE ithute_hosting_admin LOGIN NOSUPERUSER CREATEDB CREATEROLE INHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'hosting_admin_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ithute_hosting_admin')
\gexec

SELECT format(
  'ALTER ROLE ithute_hosting_admin LOGIN NOSUPERUSER CREATEDB CREATEROLE INHERIT NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'hosting_admin_password'
)
\gexec

-- The v4 hosting agent creates customer login roles itself. Current PostgreSQL
-- grants a CREATEROLE user administration rights over roles it creates, which
-- allows the agent to ALTER/DROP those roles and SET ROLE for pg_dump/restore.
-- The agent, not this bootstrap, owns each hosted database and revokes PUBLIC
-- CONNECT/TEMPORARY plus PUBLIC CREATE on the public schema per database.

\du ithute_hosting_admin
