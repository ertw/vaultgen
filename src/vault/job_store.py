"""Transactional SQLite state for the CAD task queue; no workers on import/open."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import uuid

from .generator import parse_configuration


SCHEMA_VERSION = 1
ACTIVE = ('queued', 'running')
TERMINAL = ('completed', 'failed', 'cancelled')
JOB_ID = re.compile(r'[a-f0-9]{32}')
LOG_LIMIT = 40000


def now():
    return datetime.now(timezone.utc).isoformat()


def seconds(start, end=None):
    if start is None:
        return None
    return max(0., (datetime.fromisoformat(end or now()) - datetime.fromisoformat(start)).total_seconds())


def configuration_key(configuration):
    return hashlib.sha256(json.dumps(configuration, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class JobStore:
    """Every mutation uses BEGIN IMMEDIATE, including submit/dedup and claim.

    Opening a store never recovers running work. Only the scheduler holding the
    output directory's exclusive ownership lock may call recover_interrupted.
    JSON payloads retain optional historical fields without guessing timings.
    """

    def __init__(self, state):
        self.state = Path(state)
        self.state.mkdir(parents=True, exist_ok=True)
        self.path = self.state / 'jobs.sqlite3'
        with self._connection() as db:
            db.execute('PRAGMA journal_mode=WAL')
        with self.transaction() as db:
            version = db.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise RuntimeError(f'Unsupported queue database version {version}')
            db.execute('CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('''CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, config_key TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, data TEXT NOT NULL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                ordinal INTEGER NOT NULL, kind TEXT NOT NULL, status TEXT NOT NULL,
                data TEXT NOT NULL, UNIQUE(job_id, ordinal))''')
            db.execute('CREATE INDEX IF NOT EXISTS jobs_configuration ON jobs(config_key, status)')
            db.execute('CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status, created_at)')
            db.execute('CREATE INDEX IF NOT EXISTS tasks_status ON tasks(status, job_id, ordinal)')
            db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
            if db.execute("SELECT value FROM metadata WHERE key='legacy_imported'").fetchone() is None:
                self._import_legacy(db)
                db.execute("INSERT INTO metadata VALUES ('legacy_imported', ?)", (now(),))

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            yield db
        finally:
            db.close()

    @contextmanager
    def transaction(self):
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            try:
                yield db
                db.commit()
            except BaseException:
                db.rollback()
                raise

    @staticmethod
    def _write_job(db, job):
        db.execute('UPDATE jobs SET status=?, data=? WHERE id=?',
                   (job['status'], json.dumps(job), job['id']))

    @staticmethod
    def _write_task(db, task):
        db.execute('UPDATE tasks SET status=?, data=? WHERE id=?',
                   (task['status'], json.dumps(task), task['id']))

    @staticmethod
    def _job(db, job_id):
        row = db.execute('SELECT data FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            raise FileNotFoundError('Unknown job')
        return json.loads(row['data'])

    @staticmethod
    def _tasks(db, job_id):
        return [json.loads(row['data']) for row in db.execute(
            'SELECT data FROM tasks WHERE job_id=? ORDER BY ordinal', (job_id,))]

    @staticmethod
    def _task(db, task_id):
        row = db.execute('SELECT data FROM tasks WHERE id=?', (task_id,)).fetchone()
        if row is None:
            raise FileNotFoundError('Unknown task')
        return json.loads(row['data'])

    @staticmethod
    def _new_task(job_id, ordinal, kind, status='queued', *, legacy=False):
        return {'id': uuid.uuid4().hex, 'job_id': job_id, 'ordinal': ordinal, 'kind': kind,
                'status': status, 'created_at': None, 'started_at': None, 'finished_at': None,
                'elapsed_seconds': None, 'render_seconds': None, 'stage': None,
                'stage_timings': [], 'error': None, 'logs': '', 'build_ids': [],
                'reused': None, 'pid': None, 'process_start': None, 'legacy': legacy}

    def _insert(self, db, job, config, *, legacy=False):
        db.execute('INSERT INTO jobs VALUES (?, ?, ?, ?, ?)',
                   (job['id'], configuration_key(job['configuration']), job['status'],
                    job['created_at'], json.dumps(job)))
        kinds = [*config.parts, *(['assembly'] if config.part == 'set' else [])]
        for ordinal, kind in enumerate(kinds):
            task = self._new_task(job['id'], ordinal, kind,
                                  'blocked' if kind == 'assembly' else 'queued', legacy=legacy)
            task['created_at'] = job['created_at']
            if legacy:
                if kind != 'assembly' and ordinal < len(job['build_ids']):
                    task.update(status='completed', build_ids=[job['build_ids'][ordinal]])
                elif job['status'] in TERMINAL:
                    task['status'] = job['status']
                elif job['status'] == 'running' and (kind == 'assembly' or ordinal == len(job['build_ids'])):
                    task['status'] = 'running'
            db.execute('INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?)',
                       (task['id'], job['id'], ordinal, kind, task['status'], json.dumps(task)))

    def _import_legacy(self, db):
        # Original files and receipts remain untouched and readable by old tooling.
        for path in sorted(self.state.glob('*.json')):
            if not JOB_ID.fullmatch(path.stem):
                continue
            try:
                old = json.loads(path.read_text())
                if old.get('id') != path.stem or old.get('status') not in (*ACTIVE, *TERMINAL):
                    continue
                config = parse_configuration(old['configuration'])
                datetime.fromisoformat(old['created_at'])
                builds = old.get('build_ids', [])
                if not builds:
                    receipt = self.state / (path.stem + '.receipt')
                    if receipt.is_file():
                        builds = json.loads(receipt.read_text())
                if not isinstance(builds, list) or any(not isinstance(item, str) for item in builds):
                    builds = []
                job = {**old, 'build_ids': builds, 'logs': old.get('logs', '')[-LOG_LIMIT:],
                       'started_at': None, 'finished_at': None, 'elapsed_seconds': None,
                       'wait_seconds': None, 'source_digest': None, 'error': old.get('error'),
                       'legacy': True, 'retry_of': None}
            except (ValueError, TypeError, KeyError, OSError):
                continue
            self._insert(db, job, config, legacy=True)

    def submit(self, config, *, capacity=4, retry_of=None):
        configuration = config.as_dict()
        with self.transaction() as db:
            existing = db.execute("SELECT id FROM jobs WHERE config_key=? AND status IN ('queued','running') ORDER BY created_at LIMIT 1",
                                  (configuration_key(configuration),)).fetchone()
            if existing:
                return self._job(db, existing['id'])
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running')").fetchone()[0] >= capacity:
                raise OverflowError('The build queue is full. Wait for a build to finish.')
            job = {'id': uuid.uuid4().hex, 'configuration': configuration, 'status': 'queued',
                   'created_at': now(), 'started_at': None, 'finished_at': None,
                   'elapsed_seconds': None, 'wait_seconds': None, 'source_digest': None,
                   'error': None, 'logs': '', 'build_ids': [], 'legacy': False, 'retry_of': retry_of}
            self._insert(db, job, config)
            return job

    def get(self, job_id):
        with self._connection() as db:
            job = self._job(db, job_id)
            job['tasks'] = self._tasks(db, job_id)
            return self._describe(db, job)

    def _describe(self, db, job):
        job = dict(job)
        if job['status'] == 'running':
            job['elapsed_seconds'] = seconds(job['started_at'])
        if job['status'] == 'queued' and not job.get('legacy'):
            job['wait_seconds'] = seconds(job['created_at'])
        job['queue_position'] = None
        if job['status'] == 'queued':
            job['queue_position'] = db.execute("SELECT count(*) FROM jobs WHERE status='queued' AND (created_at<? OR (created_at=? AND id<=?))",
                                               (job['created_at'], job['created_at'], job['id'])).fetchone()[0]
        tasks = job.get('tasks') or self._tasks(db, job['id'])
        job['task_counts'] = {status: sum(task['status'] == status for task in tasks)
                              for status in ('blocked', 'queued', 'running', *TERMINAL)}
        for task in tasks:
            task.pop('pid', None)
            task.pop('process_start', None)
            if task['status'] == 'running':
                task['elapsed_seconds'] = seconds(task['started_at'])
        return job

    def list(self, *, status=None, limit=30, offset=0, active_first=True):
        if not isinstance(limit, int) or not 1 <= limit <= 100 or not isinstance(offset, int) or offset < 0:
            raise ValueError('limit must be 1–100 and offset must be nonnegative')
        statuses = (*ACTIVE, *TERMINAL) if status in (None, 'all') else ACTIVE if status == 'active' else TERMINAL if status == 'terminal' else (status,)
        if any(item not in (*ACTIVE, *TERMINAL) for item in statuses):
            raise ValueError('Unknown job status')
        where = ','.join('?' for _ in statuses)
        order = ("CASE WHEN status IN ('queued','running') THEN 0 ELSE 1 END, "
                 "CASE WHEN status IN ('queued','running') THEN created_at END ASC, created_at DESC, id" if active_first else 'created_at DESC, id')
        with self._connection() as db:
            total = db.execute(f'SELECT count(*) FROM jobs WHERE status IN ({where})', statuses).fetchone()[0]
            rows = db.execute(f'SELECT data FROM jobs WHERE status IN ({where}) ORDER BY {order} LIMIT ? OFFSET ?',
                              (*statuses, limit, offset)).fetchall()
            items = [self._describe(db, json.loads(row['data'])) for row in rows]
            counts = {item: 0 for item in (*ACTIVE, *TERMINAL)}
            counts.update({row['status']: row['count'] for row in db.execute('SELECT status,count(*) AS count FROM jobs GROUP BY status')})
            return {'jobs': items, 'total': total, 'limit': limit, 'offset': offset, 'counts': counts}

    def has_ready(self):
        with self._connection() as db:
            return db.execute("SELECT 1 FROM tasks JOIN jobs ON jobs.id=tasks.job_id WHERE tasks.status='queued' AND jobs.status IN ('queued','running') LIMIT 1").fetchone() is not None

    def running_jobs(self):
        with self._connection() as db:
            return [json.loads(row['data']) for row in db.execute("SELECT data FROM jobs WHERE status='running'")]

    def clear_process(self, task_id):
        with self.transaction() as db:
            task = self._task(db, task_id)
            task.update(pid=None, process_start=None)
            self._write_task(db, task)

    def claim(self, source_digest):
        """Claim one ready task, pinning its job's revision on the first claim."""
        with self.transaction() as db:
            row = db.execute("""SELECT tasks.id FROM tasks JOIN jobs ON jobs.id=tasks.job_id
                WHERE tasks.status='queued' AND jobs.status IN ('queued','running')
                ORDER BY jobs.created_at, jobs.id, tasks.ordinal LIMIT 1""").fetchone()
            if row is None:
                return None
            task = self._task(db, row['id'])
            job = self._job(db, task['job_id'])
            stamp = now()
            if job['started_at'] is None:
                job.update(started_at=stamp, wait_seconds=seconds(job['created_at'], stamp),
                           source_digest=source_digest, status='running', legacy=False)
            if job['source_digest'] != source_digest:
                self._terminate_job(db, job, 'failed', 'Generator source changed while this job was waiting. Generate again to use one revision.')
                return None
            task.update(status='running', started_at=stamp, render_seconds=0.)
            self._write_task(db, task)
            self._write_job(db, job)
            # Assembly receives only successfully completed part task IDs.
            completed = self._tasks(db, job['id'])
            return {**task, 'configuration': job['configuration'], 'source_digest': job['source_digest'],
                    'job_started_at': job['started_at'],
                    'component_builds': {item['kind']: item['build_ids'][0] for item in completed
                                         if item['kind'] != 'assembly' and item['status'] == 'completed' and len(item['build_ids']) == 1}}

    def process_started(self, task_id, pid, process_start):
        with self.transaction() as db:
            task = self._task(db, task_id)
            task.update(pid=pid, process_start=process_start)
            self._write_task(db, task)
            return task['status'] == 'running' and self._job(db, task['job_id'])['status'] == 'running'

    def log(self, task_id, line):
        with self.transaction() as db:
            task = self._task(db, task_id)
            job = self._job(db, task['job_id'])
            task['logs'] = (task['logs'] + line)[-LOG_LIMIT:]
            job['logs'] = (job['logs'] + f"[{task['kind']}] {line}")[-LOG_LIMIT:]
            self._write_task(db, task)
            self._write_job(db, job)

    def event(self, task_id, event):
        with self.transaction() as db:
            task = self._task(db, task_id)
            if task['status'] == 'completed':
                return
            name = event.get('event')
            stage = event.get('stage')
            if name == 'stage_started' and isinstance(stage, str) and task['status'] == 'running':
                task['stage'] = stage
            elif name == 'stage_finished' and isinstance(stage, str):
                duration = event.get('elapsed_seconds')
                if not isinstance(duration, (int, float)) or not math.isfinite(duration) or duration < 0:
                    return
                task['stage_timings'].append({key: event[key] for key in ('stage', 'elapsed_seconds', 'failed', 'error') if key in event})
                if 'render' in stage.lower():
                    task['render_seconds'] = (task['render_seconds'] or 0) + duration
                if task['stage'] == stage:
                    task['stage'] = None
            elif name == 'task_failed' and task['status'] == 'running':
                task['error'] = str(event.get('error', 'CAD task failed'))
            elif name == 'part_completed' and isinstance(event.get('build_id'), str):
                if event['build_id'] not in task['build_ids']:
                    task['build_ids'].append(event['build_id'])
                task['reused'] = bool(event.get('reused'))
                job = self._job(db, task['job_id'])
                self._write_task(db, task)
                self._collect_builds(db, job)
                self._write_job(db, job)
                return
            self._write_task(db, task)

    def _collect_builds(self, db, job):
        builds = []
        for task in self._tasks(db, job['id']):
            if task['kind'] != 'assembly':
                for build_id in task['build_ids']:
                    if build_id not in builds:
                        builds.append(build_id)
        job['build_ids'] = builds

    def finish(self, task_id, *, error=None, build_ids=()):
        with self.transaction() as db:
            task = self._task(db, task_id)
            job = self._job(db, task['job_id'])
            if task['status'] == 'completed':
                return job
            if build_ids:
                task['build_ids'] = list(build_ids)
            if task['status'] == 'running':
                stamp = now()
                task.update(status='failed' if error else 'completed', error=error,
                            finished_at=stamp, elapsed_seconds=seconds(task['started_at'], stamp), stage=None,
                            pid=None, process_start=None)
            task.update(pid=None, process_start=None)
            self._write_task(db, task)
            self._collect_builds(db, job)
            if job['status'] in ACTIVE:
                if error:
                    self._terminate_job(db, job, 'failed', error,
                                        task_error=f"Stopped because another task failed: {task['kind']}: {error}")
                else:
                    tasks = self._tasks(db, job['id'])
                    if all(item['status'] == 'completed' for item in tasks):
                        stamp = now()
                        job.update(status='completed', finished_at=stamp,
                                   elapsed_seconds=seconds(job['started_at'], stamp), error=None)
                    elif all(item['status'] == 'completed' for item in tasks if item['kind'] != 'assembly'):
                        for item in tasks:
                            if item['kind'] == 'assembly' and item['status'] == 'blocked':
                                item['status'] = 'queued'
                                self._write_task(db, item)
            self._write_job(db, job)
            return job

    def _terminate_job(self, db, job, status, error, *, task_error=None):
        stamp = now()
        task_error = task_error or (f'Stopped because the job failed: {error}' if status == 'failed' else error)
        job.update(status=status, error=error, finished_at=stamp,
                   elapsed_seconds=seconds(job['started_at'], stamp))
        if job['started_at'] is None and not job.get('legacy'):
            job['wait_seconds'] = seconds(job['created_at'], stamp)
        for task in self._tasks(db, job['id']):
            if task['status'] in ('queued', 'blocked', 'running'):
                task.update(status='cancelled', error=task_error, finished_at=stamp,
                            elapsed_seconds=seconds(task['started_at'], stamp), stage=None)
                self._write_task(db, task)
        self._write_job(db, job)

    def cancel(self, job_id):
        with self.transaction() as db:
            job = self._job(db, job_id)
            if job['status'] in ACTIVE:
                self._terminate_job(db, job, 'cancelled', 'Cancelled by the user; completed parts remain available.')
            return job

    def fail(self, job_id, error):
        with self.transaction() as db:
            job = self._job(db, job_id)
            if job['status'] in ACTIVE:
                self._terminate_job(db, job, 'failed', error)
            return job

    def running_processes(self):
        with self._connection() as db:
            return [json.loads(row['data']) for row in db.execute("SELECT data FROM tasks WHERE status='running' OR json_extract(data, '$.pid') IS NOT NULL")]

    def recover_interrupted(self):
        """Explicit scheduler-owner operation; queued jobs are left untouched."""
        with self.transaction() as db:
            jobs = [json.loads(row['data']) for row in db.execute("SELECT data FROM jobs WHERE status='running'")]
            for job in jobs:
                for task in self._tasks(db, job['id']):
                    if task['status'] == 'running':
                        task.update(status='failed', error='The service stopped during this task.', finished_at=now(),
                                    elapsed_seconds=None, stage=None, pid=None, process_start=None)
                        self._write_task(db, task)
                self._collect_builds(db, job)
                self._terminate_job(db, job, 'failed', 'The service restarted during this job. Retry to reuse eligible completed parts.')
                # We cannot establish when an interrupted process actually stopped.
                job['elapsed_seconds'] = None
                self._write_job(db, job)
            return len(jobs)
