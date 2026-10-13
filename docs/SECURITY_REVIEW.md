# Security review

Implemented controls include PBKDF2-HMAC-SHA256 password hashing, signed expiring JWTs, server-side ownership checks, parameterized metadata queries, a separate lab connection, statement/lock/run limits, and step SQL validation.

Production requirements:

- Set an unpredictable `JWT_SECRET`; production startup rejects the built-in default.
- Set exact HTTPS `CORS_ORIGINS`; credentialed wildcard CORS is not used.
- Give `LAB_DATABASE_URL` a separate least-privilege role and database. Do not reuse metadata credentials.
- Keep `.env` out of Git (it is ignored), rotate any secret that was ever committed or shared, and use Render secret variables.

Residual risks: SQL text filtering is not a complete sandbox, lab resets are destructive by design, and in-memory run control does not support multi-instance coordination.
