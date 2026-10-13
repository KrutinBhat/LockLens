-- Creates the lab database and a least-privilege role for experiment execution.
-- The lab role can only touch schema `lab` in database `locklens_lab`.
\getenv lab_password LAB_PASSWORD
CREATE DATABASE locklens_lab;
CREATE USER locklens_lab WITH PASSWORD :'lab_password';
\c locklens_lab
CREATE SCHEMA IF NOT EXISTS lab AUTHORIZATION locklens_lab;
GRANT CONNECT ON DATABASE locklens_lab TO locklens_lab;
GRANT USAGE, CREATE ON SCHEMA lab TO locklens_lab;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA lab TO locklens_lab;
ALTER DEFAULT PRIVILEGES IN SCHEMA lab GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO locklens_lab;
REVOKE ALL ON SCHEMA public FROM locklens_lab;
