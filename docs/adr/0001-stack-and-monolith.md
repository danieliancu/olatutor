# ADR 0001: Stack and modular monolith

**Status:** accepted, Milestone 0.

**Decision:** Python 3.13, Django 5.2 LTS, PostgreSQL 17, server-rendered templates, vanilla JavaScript, all run through Docker. Dependencies are locked with uv. Redis, Celery, DRF, SymPy, Lark and Alpine are not installed yet.

**Why:**

- Django 5.2 receives security fixes until April 2028 according to the Django project, later than 6.1's December 2027. Move to 6.2 LTS after its planned release in April 2027.
- The host has Python 3.11, and running in containers makes that irrelevant.
- Each deferred dependency arrives with the workload that needs it, as the brief requires. M0 has no asynchronous inference, device API or grading.

**Consequences:** Postgres is not published to the host, because ports 5432–5434 are taken by other projects on this machine. Production settings do not exist yet; the prototype cannot run with them.
