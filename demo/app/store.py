import csv
import io
import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

PERMISSIONS = ["reports.read", "exports.create", "exports.download"]
JOB_FIELDS = (
    "id, customer_id, member_id, report_id, request_id, state, "
    "error_code, created_at, started_at, finished_at"
)
SCENARIOS = ["healthy", "permission_removed", "feature_disabled", "job_failed", "ambiguous"]


def timestamp():
    return datetime.now(UTC).isoformat()


class MissingRecord(Exception):
    pass


class ExportRejected(Exception):
    def __init__(self, status: int, detail: str, request_id: str):
        self.status, self.detail, self.request_id = status, detail, request_id


class DemoStore:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys = ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def initialize(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.execute("PRAGMA journal_mode = WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY);
                INSERT OR IGNORE INTO schema_version VALUES (1);
                CREATE TABLE IF NOT EXISTS customers (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, external_id TEXT UNIQUE NOT NULL,
                    exports_enabled INTEGER NOT NULL, config_version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL, fault_mode TEXT, log_coverage TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS members (
                    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                    name TEXT NOT NULL, role TEXT NOT NULL, permissions TEXT NOT NULL,
                    UNIQUE(id, customer_id)
                );
                CREATE TABLE IF NOT EXISTS reports (
                    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                    title TEXT NOT NULL, rows_json TEXT NOT NULL, UNIQUE(id, customer_id)
                );
                CREATE TABLE IF NOT EXISTS export_jobs (
                    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL, member_id TEXT NOT NULL,
                    report_id TEXT NOT NULL, request_id TEXT NOT NULL, state TEXT NOT NULL
                        CHECK(state IN ('queued','running','completed','failed')),
                    error_code TEXT, created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT,
                    UNIQUE(id, customer_id),
                    FOREIGN KEY(member_id,customer_id) REFERENCES members(id,customer_id),
                    FOREIGN KEY(report_id,customer_id) REFERENCES reports(id,customer_id)
                );
                CREATE TABLE IF NOT EXISTS request_logs (
                    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                    member_id TEXT NOT NULL, request_id TEXT NOT NULL,
                    event TEXT NOT NULL, status_code INTEGER NOT NULL,
                    message_redacted TEXT NOT NULL, observed_at TEXT NOT NULL,
                    FOREIGN KEY(member_id,customer_id) REFERENCES members(id,customer_id)
                );
                CREATE TABLE IF NOT EXISTS lab_runs (
                    id TEXT PRIMARY KEY, customer_id TEXT NOT NULL REFERENCES customers(id),
                    member_id TEXT NOT NULL, report_id TEXT NOT NULL, generation INTEGER NOT NULL
                );
                CREATE INDEX IF NOT EXISTS jobs_customer_created
                    ON export_jobs(customer_id,created_at,id);
                CREATE INDEX IF NOT EXISTS logs_customer_created
                    ON request_logs(customer_id,observed_at,id);
            """)
            if db.execute("SELECT max(version) FROM schema_version").fetchall()[0][0] != 1:
                raise RuntimeError("Unsupported demo database schema version.")

    @staticmethod
    def required(db, statement, values):
        row = db.execute(statement, values).fetchone()
        if row is None:
            raise MissingRecord()
        return row

    def customers(self, limit=50, offset=0):
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,name,external_id FROM customers ORDER BY name,id LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            ]

    def customer(self, customer_id):
        with self.connection() as db:
            row = self.required(
                db,
                (
                    "SELECT "
                    "id,name,external_id,exports_enabled,config_version,updated_at "
                    "FROM customers WHERE id=?"
                ),
                (customer_id,),
            )
            return {**dict(row), "exports_enabled": bool(row["exports_enabled"])}

    def members(self, customer_id):
        self.customer(customer_id)
        with self.connection() as db:
            return [
                {**dict(row), "permissions": json.loads(row["permissions"])}
                for row in db.execute(
                    (
                        "SELECT id,customer_id,name,role,permissions FROM members WHERE "
                        "customer_id=? ORDER BY name,id"
                    ),
                    (customer_id,),
                )
            ]

    def reports(self, customer_id):
        self.customer(customer_id)
        with self.connection() as db:
            return [
                {
                    "id": row["id"],
                    "customer_id": row["customer_id"],
                    "title": row["title"],
                    "rows": json.loads(row["rows_json"]),
                }
                for row in db.execute(
                    (
                        "SELECT id,customer_id,title,rows_json FROM reports WHERE "
                        "customer_id=? ORDER BY id"
                    ),
                    (customer_id,),
                )
            ]

    def jobs(self, customer_id, limit=50, offset=0):
        self.customer(customer_id)
        with self.connection() as db:
            return [
                dict(row)
                for row in db.execute(
                    f"SELECT {JOB_FIELDS} FROM export_jobs WHERE customer_id=? "
                    "ORDER BY created_at DESC,id LIMIT ? OFFSET ?",
                    (customer_id, limit, offset),
                )
            ]

    def job(self, customer_id, job_id):
        with self.connection() as db:
            return dict(
                self.required(
                    db,
                    f"SELECT {JOB_FIELDS} FROM export_jobs WHERE id=? AND customer_id=?",
                    (job_id, customer_id),
                )
            )

    def logs(self, customer_id, limit=50, offset=0, request_id=None):
        self.customer(customer_id)
        with self.connection() as db:
            coverage = self.required(
                db, "SELECT log_coverage FROM customers WHERE id=?", (customer_id,)
            )[0]
            rows = db.execute(
                (
                    "SELECT id,customer_id,member_id,request_id,event,status_code,"
                    "message_redacted,observed_at FROM request_logs WHERE "
                    "customer_id=? AND (? IS NULL OR request_id=?) ORDER BY "
                    "observed_at DESC,id LIMIT ? OFFSET ?"
                ),
                (customer_id, request_id, request_id, limit, offset),
            )
            return {
                "items": [dict(row) for row in rows],
                "coverage": coverage,
                "limit": limit,
                "offset": offset,
            }

    @staticmethod
    def log(db, customer_id, member_id, request_id, event, status, message):
        db.execute(
            "INSERT INTO request_logs VALUES (?,?,?,?,?,?,?,?)",
            (str(uuid4()), customer_id, member_id, request_id, event, status, message, timestamp()),
        )

    def create_export(self, customer_id, member_id, report_id):
        request_id = str(uuid4())
        rejected = None
        with self.connection() as db:
            customer = self.required(db, "SELECT * FROM customers WHERE id=?", (customer_id,))
            member = self.required(
                db,
                "SELECT permissions FROM members WHERE id=? AND customer_id=?",
                (member_id, customer_id),
            )
            self.required(
                db, "SELECT id FROM reports WHERE id=? AND customer_id=?", (report_id, customer_id)
            )
            if "exports.create" not in json.loads(member["permissions"]):
                rejected = ExportRejected(403, "Export permission is missing.", request_id)
                self.log(
                    db,
                    customer_id,
                    member_id,
                    request_id,
                    "permission_denied",
                    403,
                    "exports.create permission is absent for the requesting member.",
                )
            elif not customer["exports_enabled"]:
                rejected = ExportRejected(
                    409, "Exports are disabled for this customer.", request_id
                )
                self.log(
                    db,
                    customer_id,
                    member_id,
                    request_id,
                    "feature_disabled",
                    409,
                    "The customer export setting is disabled.",
                )
            else:
                job_id = str(uuid4())
                db.execute(
                    (
                        "INSERT INTO export_jobs "
                        "(id,customer_id,member_id,report_id,request_id,state,created_at) "
                        "VALUES (?,?,?,?,?,'queued',?)"
                    ),
                    (job_id, customer_id, member_id, report_id, request_id, timestamp()),
                )
                self.log(
                    db,
                    customer_id,
                    member_id,
                    request_id,
                    "export_queued",
                    202,
                    "Export request accepted for processing.",
                )
        # Raise after the log transaction commits, so denied requests remain observable.
        if rejected:
            raise rejected
        return self.job(customer_id, job_id)

    def finish_export(self, job_id):
        with self.connection() as db:
            job = self.required(db, "SELECT * FROM export_jobs WHERE id=?", (job_id,))
            if job["state"] != "queued":
                return
            customer = self.required(
                db, "SELECT fault_mode FROM customers WHERE id=?", (job["customer_id"],)
            )
            db.execute(
                "UPDATE export_jobs SET state='running',started_at=? WHERE id=?",
                (timestamp(), job_id),
            )
            mode = customer["fault_mode"]
            error = (
                "STORAGE_WRITE_FAILED"
                if mode == "write_failure"
                else "EXPORT_TIMEOUT"
                if mode == "unknown_timeout"
                else None
            )
            state = "failed" if error else "completed"
            db.execute(
                "UPDATE export_jobs SET state=?,error_code=?,finished_at=? WHERE id=?",
                (state, error, timestamp(), job_id),
            )
            message = (
                "Export artifact written successfully."
                if not error
                else "Export artifact storage rejected the write."
                if mode == "write_failure"
                else "Export timed out; downstream diagnostics are unavailable."
            )
            self.log(
                db,
                job["customer_id"],
                job["member_id"],
                job["request_id"],
                "export_" + state,
                200 if not error else 502,
                message,
            )

    def download(self, customer_id, job_id, member_id):
        job = self.job(customer_id, job_id)
        with self.connection() as db:
            member = self.required(
                db,
                "SELECT permissions FROM members WHERE id=? AND customer_id=?",
                (member_id, customer_id),
            )
            if "exports.download" not in json.loads(member[0]):
                raise ExportRejected(403, "Download permission is missing.", job["request_id"])
            if job["state"] != "completed":
                raise ExportRejected(409, "Export artifact is not ready.", job["request_id"])
            report = self.required(
                db,
                "SELECT rows_json FROM reports WHERE id=? AND customer_id=?",
                (job["report_id"], customer_id),
            )
            stream = io.StringIO(newline="")
            writer = csv.DictWriter(stream, fieldnames=["month", "revenue_usd"])
            writer.writeheader()
            writer.writerows(json.loads(report[0]))
            return stream.getvalue()

    def create_run(self, scenario):
        if scenario not in SCENARIOS:
            raise ValueError("Unknown scenario.")
        run_id, customer_id, member_id, report_id = [str(uuid4()) for _ in range(4)]
        permissions = [
            p for p in PERMISSIONS if scenario != "permission_removed" or p != "exports.create"
        ]
        fault = (
            "write_failure"
            if scenario == "job_failed"
            else "unknown_timeout"
            if scenario == "ambiguous"
            else None
        )
        with self.connection() as db:
            db.execute(
                "INSERT INTO customers VALUES (?,?,?,?,?,?,?,?)",
                (
                    customer_id,
                    "Example account " + customer_id[:8],
                    "demo-" + customer_id,
                    True,
                    1,
                    timestamp(),
                    fault,
                    "partial" if scenario == "ambiguous" else "full",
                ),
            )
            db.execute(
                "INSERT INTO members VALUES (?,?,?,?,?)",
                (member_id, customer_id, "Jamie", "analyst", json.dumps(PERMISSIONS)),
            )
            db.execute(
                "INSERT INTO members VALUES (?,?,?,?,?)",
                (str(uuid4()), customer_id, "Lee", "viewer", json.dumps(["reports.read"])),
            )
            db.execute(
                "INSERT INTO reports VALUES (?,?,?,?)",
                (
                    report_id,
                    customer_id,
                    "Monthly revenue",
                    json.dumps(
                        [
                            {"month": "2026-07", "revenue_usd": 12000},
                            {"month": "2026-08", "revenue_usd": 15000},
                            {"month": "2026-09", "revenue_usd": 18000},
                        ]
                    ),
                ),
            )
            if scenario == "permission_removed":
                db.execute(
                    "UPDATE members SET permissions=? WHERE id=?",
                    (json.dumps(permissions), member_id),
                )
                self.log(
                    db,
                    customer_id,
                    member_id,
                    str(uuid4()),
                    "permissions_updated",
                    200,
                    "exports.create was removed from the analyst's permissions.",
                )
            elif scenario == "feature_disabled":
                db.execute(
                    "UPDATE customers SET exports_enabled=0,config_version=2,"
                    "updated_at=? WHERE id=?",
                    (timestamp(), customer_id),
                )
                self.log(
                    db,
                    customer_id,
                    member_id,
                    str(uuid4()),
                    "configuration_updated",
                    200,
                    "Customer exports were changed from enabled to disabled.",
                )
            db.execute(
                "INSERT INTO lab_runs VALUES (?,?,?,?,1)",
                (run_id, customer_id, member_id, report_id),
            )
        return self.probe(run_id)

    def probe(self, run_id):
        with self.connection() as db:
            run = dict(self.required(db, "SELECT * FROM lab_runs WHERE id=?", (run_id,)))
        try:
            job = self.create_export(run["customer_id"], run["member_id"], run["report_id"])
            self.finish_export(job["id"])
            probe = {"status_code": 202, "job_id": job["id"], "request_id": job["request_id"]}
        except ExportRejected as error:
            probe = {"status_code": error.status, "job_id": None, "request_id": error.request_id}
        return {
            "run_id": run["id"],
            **{k: run[k] for k in ("customer_id", "member_id", "report_id", "generation")},
            "probe": probe,
        }

    def reset(self, run_id):
        with self.connection() as db:
            run = self.required(db, "SELECT * FROM lab_runs WHERE id=?", (run_id,))
            customer_id = run["customer_id"]
            db.execute("DELETE FROM request_logs WHERE customer_id=?", (customer_id,))
            db.execute("DELETE FROM export_jobs WHERE customer_id=?", (customer_id,))
            db.execute(
                "UPDATE members SET permissions=? WHERE id=? AND customer_id=?",
                (json.dumps(PERMISSIONS), run["member_id"], customer_id),
            )
            db.execute(
                (
                    "UPDATE customers SET exports_enabled=1,"
                    "config_version=config_version+1,updated_at=?,fault_mode=NULL,"
                    "log_coverage='full' WHERE id=?"
                ),
                (timestamp(), customer_id),
            )
            db.execute("UPDATE lab_runs SET generation=generation+1 WHERE id=?", (run_id,))
        return self.probe(run_id)
