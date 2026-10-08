# Infrastructure

The current development setup runs natively through the root launcher. Docker is not a prerequisite for the scaffold.

Future infrastructure work belongs here: container definitions, deployment configuration, HTTPS, secret injection, health checks, backup/restore, and rollback documentation. Choose a small deployment before introducing orchestration services.

The planned database is Neon. Keep its connection string on the backend. Free compute scales to zero; continuous idle polling of a database-backed job queue may keep compute active. Plan worker signaling alongside the job implementation.
