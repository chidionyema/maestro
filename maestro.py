#!/usr/bin/env python3
"""
MAESTRO DEPUTY v1.0
Autonomous Estate Overseer with Recursive Failure Inoculation

Core hypothesis (testable law):
LAW_OF_ENTROPIC_INVERSION: In a sufficiently instrumented system with causal
attribution, every failure mode extracted as a shape, encoded as an invariant,
and verified against simulation, reduces the probability of that shape's recurrence
in any context by an observable margin that compounds with each iteration.

Falsification conditions:
- If shape extraction produces false positives >20%
- If prevention success rate does not improve over 10 incidents
- If system introduces novel failure modes at rate >baseline human operation
"""

import os
import re
import sys
import json
import time
import sqlite3
import hashlib
import logging
import subprocess
import threading
from enum import Enum, auto
from dataclasses import dataclass, field, asdict
from typing import Optional, Dict, List, Any, Callable, Tuple
from datetime import datetime, timedelta
from contextlib import contextmanager
from pathlib import Path

# ───────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ───────────────────────────────────────────────────────────────────────────────

def _borrow_from_architect(key: str) -> str:
    """Read one value out of The Architect's .env so maestro can reach the founder.

    maestro's launchd plist carries no Telegram credentials, so until 2026-08-23
    TelegramBridge fell through to its `[TELEGRAM would send]` branch: every
    escalation it ever raised would have gone to a log file instead of his phone,
    and a healthy maestro and a mute one produced identical silence.

    Minting a second bot for maestro would cost the founder a trip to BotFather,
    and a second credential to rotate. The Architect already holds a working bot,
    and maestro only ever calls sendMessage — never getUpdates — so borrowing the
    token adds no second poller and cannot make the gateway go deaf.

    The value is read at import from a 600-mode file and never logged or written
    anywhere else. Returns '' when the file is unreadable, which leaves the
    existing rehearsal behaviour exactly as it was.
    """
    env_path = Path(
        os.getenv("ARCHITECT_HOME", "~/dev/code/hermes-v2")
    ).expanduser() / ".env"
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == key:
                return value.strip().strip("'\"")
    except OSError:
        return ""
    return ""


class Config:
    """Centralized, environment-overridable configuration."""
    DB_PATH = os.getenv("MAESTRO_DB", "~/.maestro/experience_graph.db")
    TICK_INTERVAL = int(os.getenv("MAESTRO_TICK", "60"))
    META_REVIEW_INTERVAL_HOURS = int(os.getenv("MAESTRO_META", "24"))
    CRISIS_TIMEOUT_MINUTES = int(os.getenv("MAESTRO_CRISIS", "120"))
    MAX_DAILY_SPEND_USD = float(os.getenv("MAESTRO_BUDGET", "50.0"))
    ALERT_THRESHOLD_USD = float(os.getenv("MAESTRO_ALERT", "10.0"))

    LANES = {
        "estate": {"auto_fix": True, "escalate_after_attempts": 2, "budget_usd": 5.0},
        "research": {"auto_fix": False, "escalate_after_attempts": 0, "budget_usd": 20.0},
        "meta": {"auto_fix": False, "escalate_after_attempts": 0, "budget_usd": 5.0},
    }

    TELEGRAM_TOKEN = os.getenv("MAESTRO_TELEGRAM_TOKEN", "") or _borrow_from_architect(
        "TELEGRAM_BOT_TOKEN"
    )
    TELEGRAM_CHAT_ID = os.getenv(
        "MAESTRO_TELEGRAM_CHAT_ID", ""
    ) or _borrow_from_architect("TELEGRAM_HOME_CHANNEL")
    GITHUB_TOKEN = os.getenv("MAESTRO_GITHUB_TOKEN", "")
    GITHUB_REPO = os.getenv("MAESTRO_GITHUB_REPO", "")
    DEFAULT_LOCAL_MODEL = os.getenv("MAESTRO_LOCAL_MODEL", "qwen2.5:7b")
    DEFAULT_API_MODEL = os.getenv("MAESTRO_API_MODEL", "deepseek-chat")
    ESTATE_AUDIT_PATH = os.getenv("MAESTRO_AUDIT", "~/.claude/state/estate-audit.json")
    # Free space, not percent used. See check_disk for why percent lies on APFS.
    DISK_FREE_GB_CRITICAL = float(os.getenv("MAESTRO_DISK_CRITICAL_GB", "5"))
    DISK_FREE_GB_WARNING = float(os.getenv("MAESTRO_DISK_WARNING_GB", "15"))
    INTENT_LOG_DIR = os.getenv("MAESTRO_INTENTS", "~/.maestro/intents")
    SKILLS_DIR = os.getenv("MAESTRO_SKILLS", "~/.maestro/skills")


# ───────────────────────────────────────────────────────────────────────────────
# LOGGING
# ───────────────────────────────────────────────────────────────────────────────

os.makedirs(os.path.expanduser("~/.maestro"), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(os.path.expanduser("~/.maestro/maestro.log"))
    ]
)
logger = logging.getLogger("maestro")


# ───────────────────────────────────────────────────────────────────────────────
# STATE MACHINE
# ───────────────────────────────────────────────────────────────────────────────

class State(Enum):
    IDLE = auto()
    SENSE = auto()
    ORIENT = auto()
    DECIDE = auto()
    ACT = auto()
    VERIFY = auto()
    REPORT = auto()
    CRISIS = auto()
    META_REVIEW = auto()

class Priority(Enum):
    P0 = 0
    P1 = 1
    P2 = 2
    P3 = 3


# ───────────────────────────────────────────────────────────────────────────────
# DATA CLASSES
# ───────────────────────────────────────────────────────────────────────────────

@dataclass
class Episode:
    id: str
    timestamp: str
    lane: str
    trigger: str
    action: str
    outcome: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0
    cost_usd: float = 0.0
    shape_id: Optional[str] = None

@dataclass
class Shape:
    id: str
    pattern_name: str
    morphology: Dict[str, Any] = field(default_factory=dict)
    contexts_observed: List[str] = field(default_factory=list)
    invariant_violated: str = ""
    prevention_skill: str = ""
    first_seen: str = ""
    last_seen: str = ""
    occurrence_count: int = 0
    prevention_success_rate: float = 0.0
    confidence: float = 0.0

@dataclass
class Skill:
    id: str
    name: str
    lane: str
    trigger_pattern: str
    procedure: str
    success_rate: float = 0.0
    total_uses: int = 0
    created_from_shape: Optional[str] = None
    last_used: str = ""
    avg_duration_ms: int = 0

@dataclass
class Intent:
    id: str
    timestamp: str
    trigger: str
    state_transitions: List[str] = field(default_factory=list)
    orient_analysis: Dict[str, Any] = field(default_factory=dict)
    decision: Dict[str, Any] = field(default_factory=dict)
    execution: Dict[str, Any] = field(default_factory=dict)
    verification: Dict[str, Any] = field(default_factory=dict)
    laws_applied: List[str] = field(default_factory=list)
    laws_violated: List[str] = field(default_factory=list)


# ───────────────────────────────────────────────────────────────────────────────
# EXPERIENCE GRAPH (SQLite)
# ───────────────────────────────────────────────────────────────────────────────

def problem_fingerprint(description: str, lane: str = "") -> str:
    """One id for one class of problem, stable across its varying numbers.

    "Disk at 96%" today and "Disk at 97%" tomorrow are the same problem twice,
    and treating them as two is exactly how the graph escalated one Stripe
    finding 46 times without ever learning. Lowercase, collapse every digit run
    to '#', collapse whitespace, hash. The lane is part of the class: the same
    words in two lanes are two different problems with two different fixes.
    """
    text = re.sub(r"\d+", "#", description.lower())
    text = re.sub(r"\s+", " ", text).strip()
    return hashlib.sha256(f"{lane}|{text}".encode()).hexdigest()[:16]


class ExperienceGraph:
    def __init__(self, db_path: str):
        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """The one place a connection to the experience graph is opened.

        WAL, because the tick loop reads while a write is in flight and the default
        rollback journal makes those two block each other. WAL is a property of the
        database file and survives, so this sets it once and it stays set; the pragma
        is repeated here anyway because a restored copy arrives in DELETE mode.

        busy_timeout is NOT persistent and is the half that actually bites: it is
        per-connection, defaults to 0, and a zero timeout turns any overlap into an
        immediate `database is locked` instead of a short wait.
        """
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def kv_get(self, key: str, default=None):
        with self._connect() as conn:
            row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
        return row[0] if row else default

    def kv_set(self, key: str, value: str):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO kv (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, str(value)),
            )

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS episodes (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    lane TEXT,
                    trigger TEXT,
                    action TEXT,
                    outcome TEXT,
                    evidence TEXT,
                    duration_ms INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    shape_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_episodes_time ON episodes(timestamp);
                CREATE INDEX IF NOT EXISTS idx_episodes_lane ON episodes(lane);
                CREATE INDEX IF NOT EXISTS idx_episodes_shape ON episodes(shape_id);

                CREATE TABLE IF NOT EXISTS shapes (
                    id TEXT PRIMARY KEY,
                    pattern_name TEXT NOT NULL,
                    morphology TEXT,
                    contexts_observed TEXT,
                    invariant_violated TEXT,
                    prevention_skill TEXT,
                    first_seen TEXT,
                    last_seen TEXT,
                    occurrence_count INTEGER DEFAULT 0,
                    prevention_success_rate REAL DEFAULT 0.0,
                    confidence REAL DEFAULT 0.0
                );
                CREATE INDEX IF NOT EXISTS idx_shapes_name ON shapes(pattern_name);

                CREATE TABLE IF NOT EXISTS skills (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    lane TEXT,
                    trigger_pattern TEXT,
                    procedure TEXT,
                    success_rate REAL DEFAULT 0.0,
                    total_uses INTEGER DEFAULT 0,
                    created_from_shape TEXT,
                    last_used TEXT,
                    avg_duration_ms INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_skills_lane ON skills(lane);

                CREATE TABLE IF NOT EXISTS invariants (
                    id TEXT PRIMARY KEY,
                    law_name TEXT NOT NULL,
                    violations_prevented INTEGER DEFAULT 0,
                    violations_allowed INTEGER DEFAULT 0,
                    last_enforced TEXT
                );

                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    role TEXT,
                    content TEXT,
                    context_summary TEXT,
                    session_id TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_conv_session ON conversations(session_id);

                CREATE TABLE IF NOT EXISTS daily_spend (
                    date TEXT PRIMARY KEY,
                    amount_usd REAL DEFAULT 0.0
                );

                CREATE TABLE IF NOT EXISTS open_alarms (
                    finding_id TEXT PRIMARY KEY,
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    last_alerted TEXT NOT NULL,
                    times_seen INTEGER DEFAULT 1,
                    description TEXT,
                    lane TEXT
                );

                CREATE TABLE IF NOT EXISTS replay_incidents (
                    fingerprint TEXT PRIMARY KEY,
                    lane TEXT,
                    trigger TEXT,
                    times_paged INTEGER DEFAULT 1,
                    first_seen TEXT,
                    frozen_at TEXT
                );
            """)

    def log_episode(self, episode: Episode) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO episodes
                (id, timestamp, lane, trigger, action, outcome, evidence,
                 duration_ms, cost_usd, shape_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                episode.id, episode.timestamp, episode.lane, episode.trigger,
                episode.action, episode.outcome, json.dumps(episode.evidence),
                episode.duration_ms, episode.cost_usd, episode.shape_id
            ))

    # How many recent success episodes one memory consult scans. Bounded so a
    # years-old ledger cannot turn every decide pass into a table scan.
    MEMORY_SCAN_LIMIT = 500

    def remembered_fix(self, description: str, lane: str) -> Optional[str]:
        """The skill that last fixed this class of problem, or None.

        Consult-before-escalate: a problem this graph has already watched a
        skill fix is retried from that memory before a person is paged. Only a
        success episode that recorded WHICH skill ran can teach — an older
        success with no skill_id in its evidence is history, not memory.
        """
        target = problem_fingerprint(description, lane)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT trigger, evidence FROM episodes "
                "WHERE lane = ? AND action = 'auto_fix' AND outcome = 'success' "
                "ORDER BY timestamp DESC LIMIT ?",
                (lane, self.MEMORY_SCAN_LIMIT),
            ).fetchall()
        for trigger, evidence in rows:
            if problem_fingerprint(trigger or "", lane) != target:
                continue
            try:
                skill_id = json.loads(evidence or "{}").get("skill_id")
            except json.JSONDecodeError:
                continue
            if skill_id:
                return str(skill_id)
        return None

    # The frozen exam is bounded: the worst historic problem classes, by how
    # often each paged a person. Small enough that one replay is a handful of
    # indexed reads, large enough that a rising score is not noise.
    REPLAY_SET_SIZE = 20

    def freeze_replay_set(self) -> int:
        """Seed the frozen replay set from every escalation ever recorded, once.

        The set is frozen at first seeding and never reseeded, so a rising
        replay score means the graph learned, not that the questions changed.
        Returns the size of the set.
        """
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT COUNT(*) FROM replay_incidents"
            ).fetchone()[0]
            if existing:
                return existing
            rows = conn.execute(
                "SELECT lane, trigger, timestamp FROM episodes "
                "WHERE action IN ('escalated', 'crisis_escalation') "
                "ORDER BY timestamp"
            ).fetchall()
        classes: Dict[str, Dict] = {}
        for lane, trigger, ts in rows:
            fp = problem_fingerprint(trigger or "", lane or "")
            entry = classes.setdefault(fp, {
                "lane": lane or "estate", "trigger": trigger or "",
                "first_seen": ts, "times_paged": 0,
            })
            entry["times_paged"] += 1
        top = sorted(
            classes.items(), key=lambda kv: kv[1]["times_paged"], reverse=True
        )[: self.REPLAY_SET_SIZE]
        frozen_at = datetime.utcnow().isoformat()
        with self._connect() as conn:
            for fp, c in top:
                conn.execute(
                    "INSERT OR IGNORE INTO replay_incidents "
                    "(fingerprint, lane, trigger, times_paged, first_seen, frozen_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (fp, c["lane"], c["trigger"], c["times_paged"],
                     c["first_seen"], frozen_at),
                )
        return len(top)

    def replay_set(self) -> List[tuple]:
        with self._connect() as conn:
            return conn.execute(
                "SELECT fingerprint, lane, trigger FROM replay_incidents "
                "ORDER BY times_paged DESC"
            ).fetchall()

    # A standing problem alerts again after this long, so suppression cannot
    # become silence. 24h, because the founder reads a daily rhythm, not a tick.
    ALARM_REALERT_SECONDS = 24 * 3600

    def alarm_disposition(self, finding_id: str, description: str = "",
                          lane: str = "estate") -> str:
        """One open alarm per live problem, so a problem pages once, not once per tick.

        Returns "new" on first sighting, "realert" when the interval has lapsed
        with the problem still standing, "suppressed" otherwise. Every call
        updates last_seen and the sighting count, so the eventual cleared episode
        can say how long it stood and how many times it was seen.
        """
        now = datetime.utcnow().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_alerted FROM open_alarms WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO open_alarms "
                    "(finding_id, first_seen, last_seen, last_alerted, times_seen, description, lane) "
                    "VALUES (?, ?, ?, ?, 1, ?, ?)",
                    (finding_id, now, now, now, description, lane),
                )
                return "new"
            lapsed = (datetime.utcnow() - datetime.fromisoformat(row[0])).total_seconds()
            if lapsed >= self.ALARM_REALERT_SECONDS:
                conn.execute(
                    "UPDATE open_alarms SET last_seen = ?, last_alerted = ?, "
                    "times_seen = times_seen + 1 WHERE finding_id = ?",
                    (now, now, finding_id),
                )
                return "realert"
            conn.execute(
                "UPDATE open_alarms SET last_seen = ?, times_seen = times_seen + 1 "
                "WHERE finding_id = ?",
                (now, finding_id),
            )
            return "suppressed"

    def close_cleared_alarms(self, active_ids) -> List[Dict[str, Any]]:
        """Close every open alarm whose problem this sense pass did not find.

        Returns the closed rows so the caller can say the problem ended. An
        alarm that opens loudly and closes silently teaches that silence means
        nothing, which is how channels get muted.
        """
        active = set(active_ids)
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT finding_id, first_seen, last_seen, times_seen, description, lane "
                "FROM open_alarms"
            ).fetchall()
            closed = [
                {"finding_id": r[0], "first_seen": r[1], "last_seen": r[2],
                 "times_seen": r[3], "description": r[4], "lane": r[5]}
                for r in rows if r[0] not in active
            ]
            for alarm in closed:
                conn.execute(
                    "DELETE FROM open_alarms WHERE finding_id = ?",
                    (alarm["finding_id"],),
                )
        return closed

    def get_shapes(self, pattern_name: Optional[str] = None) -> List[Shape]:
        with self._connect() as conn:
            if pattern_name:
                rows = conn.execute(
                    "SELECT * FROM shapes WHERE pattern_name = ?", (pattern_name,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM shapes").fetchall()
            return [self._row_to_shape(r) for r in rows]

    def get_shape_by_context(self, context: str) -> List[Shape]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM shapes WHERE contexts_observed LIKE ?", (f"%{context}%",)
            ).fetchall()
            return [self._row_to_shape(r) for r in rows]

    def upsert_shape(self, shape: Shape) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO shapes
                (id, pattern_name, morphology, contexts_observed, invariant_violated,
                 prevention_skill, first_seen, last_seen, occurrence_count,
                 prevention_success_rate, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    occurrence_count = excluded.occurrence_count,
                    last_seen = excluded.last_seen,
                    prevention_success_rate = excluded.prevention_success_rate,
                    confidence = excluded.confidence,
                    contexts_observed = excluded.contexts_observed
            """, (
                shape.id, shape.pattern_name, json.dumps(shape.morphology),
                json.dumps(shape.contexts_observed), shape.invariant_violated,
                shape.prevention_skill, shape.first_seen, shape.last_seen,
                shape.occurrence_count, shape.prevention_success_rate, shape.confidence
            ))

    def get_skill(self, skill_id: str) -> Optional[Skill]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM skills WHERE id = ?", (skill_id,)).fetchone()
            if not row:
                return None
            return self._row_to_skill(row)

    def get_skills_for_lane(self, lane: str) -> List[Skill]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM skills WHERE lane = ?", (lane,)).fetchall()
            return [self._row_to_skill(r) for r in rows]

    def upsert_skill(self, skill: Skill) -> None:
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO skills
                (id, name, lane, trigger_pattern, procedure, success_rate,
                 total_uses, created_from_shape, last_used, avg_duration_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    success_rate = excluded.success_rate,
                    total_uses = excluded.total_uses,
                    last_used = excluded.last_used,
                    avg_duration_ms = excluded.avg_duration_ms
            """, (
                skill.id, skill.name, skill.lane, skill.trigger_pattern,
                skill.procedure, skill.success_rate, skill.total_uses,
                skill.created_from_shape, skill.last_used, skill.avg_duration_ms
            ))

    def get_daily_spend(self, date: str) -> float:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT amount_usd FROM daily_spend WHERE date = ?", (date,)
            ).fetchone()
            return row[0] if row else 0.0

    def add_spend(self, amount_usd: float) -> None:
        today = datetime.utcnow().strftime("%Y-%m-%d")
        with self._connect() as conn:
            conn.execute("""
                INSERT INTO daily_spend (date, amount_usd)
                VALUES (?, ?)
                ON CONFLICT(date) DO UPDATE SET
                    amount_usd = amount_usd + excluded.amount_usd
            """, (today, amount_usd))

    def get_stats(self) -> Dict[str, Any]:
        with self._connect() as conn:
            total_episodes = conn.execute("SELECT COUNT(*) FROM episodes").fetchone()[0]
            total_shapes = conn.execute("SELECT COUNT(*) FROM shapes").fetchone()[0]
            total_skills = conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
            success_rate = conn.execute(
                "SELECT AVG(CASE WHEN outcome='success' THEN 1.0 ELSE 0.0 END) FROM episodes"
            ).fetchone()[0] or 0.0
            today_spend = self.get_daily_spend(datetime.utcnow().strftime("%Y-%m-%d"))
            return {
                "total_episodes": total_episodes,
                "total_shapes": total_shapes,
                "total_skills": total_skills,
                "success_rate": round(success_rate, 3),
                "today_spend_usd": round(today_spend, 2),
            }

    @staticmethod
    def _row_to_shape(row) -> Shape:
        return Shape(
            id=row[0], pattern_name=row[1],
            morphology=json.loads(row[2]) if row[2] else {},
            contexts_observed=json.loads(row[3]) if row[3] else [],
            invariant_violated=row[4], prevention_skill=row[5],
            first_seen=row[6], last_seen=row[7],
            occurrence_count=row[8], prevention_success_rate=row[9],
            confidence=row[10]
        )

    @staticmethod
    def _row_to_skill(row) -> Skill:
        return Skill(
            id=row[0], name=row[1], lane=row[2],
            trigger_pattern=row[3], procedure=row[4],
            success_rate=row[5], total_uses=row[6],
            created_from_shape=row[7], last_used=row[8],
            avg_duration_ms=row[9]
        )


# ───────────────────────────────────────────────────────────────────────────────
# THE 7 LAWS — CONSTITUTIONAL INVARIANTS
# ───────────────────────────────────────────────────────────────────────────────

class LawViolation(Exception):
    def __init__(self, law_name: str, reason: str, evidence: Dict = None):
        self.law_name = law_name
        self.reason = reason
        self.evidence = evidence or {}
        super().__init__(f"LAW_VIOLATION: {law_name} — {reason}")

class LawMiddleware:
    @classmethod
    def validate(cls, plan: Dict, context: Dict, graph: ExperienceGraph) -> List[str]:
        applied = []

        applied.append("LAW_CONTEXT")
        if not cls._law_context(plan, context):
            raise LawViolation("LAW_CONTEXT",
                f"Plan domain '{plan.get('domain', 'unknown')}' not in allowed contexts")

        applied.append("LAW_DEGREE")
        if not cls._law_degree(plan):
            raise LawViolation("LAW_DEGREE",
                "Plan contains binary assessment without scalar metric")

        applied.append("LAW_BASELINE")
        if not cls._law_baseline(plan):
            raise LawViolation("LAW_BASELINE",
                "Plan claims improvement without baseline comparison")

        applied.append("LAW_TRADEOFF")
        if not cls._law_tradeoff(plan):
            raise LawViolation("LAW_TRADEOFF",
                "Plan does not surface invisible costs")

        applied.append("LAW_RIPPLE")
        if not cls._law_ripple(plan, depth=2):
            raise LawViolation("LAW_RIPPLE",
                f"Plan traces insufficient ripple effects")

        applied.append("LAW_MECHANISM")
        if not cls._law_mechanism(plan):
            raise LawViolation("LAW_MECHANISM",
                "Plan mechanism is hand-waving")

        applied.append("LAW_SOURCE")
        if not cls._law_source(plan):
            raise LawViolation("LAW_SOURCE",
                "Plan uses unattributed data")

        return applied

    @staticmethod
    def _law_context(plan: Dict, context: Dict) -> bool:
        allowed = context.get("allowed_domains", ["estate", "research", "meta"])
        domain = plan.get("domain", "unknown")
        return domain in allowed or domain == "meta"

    @staticmethod
    def _law_degree(plan: Dict) -> bool:
        assessments = plan.get("assessments", {})
        if not assessments:
            return True
        for key, val in assessments.items():
            if isinstance(val, bool):
                return False
            if isinstance(val, dict):
                if "value" not in val or "threshold" not in val:
                    return False
        return True

    @staticmethod
    def _law_baseline(plan: Dict) -> bool:
        baseline = plan.get("baseline")
        if baseline is None and plan.get("outcome_claim") in ["improved", "better", "faster"]:
            return False
        return True

    @staticmethod
    def _law_tradeoff(plan: Dict) -> bool:
        tradeoffs = plan.get("tradeoffs", [])
        if not plan.get("actions"):
            return True
        return len(tradeoffs) > 0

    @staticmethod
    def _law_ripple(plan: Dict, depth: int = 2) -> bool:
        effects = plan.get("ripple_effects", [])
        max_depth = 0
        for effect in effects:
            d = 1
            current = effect
            while isinstance(current, dict) and "then" in current:
                d += 1
                current = current["then"]
            max_depth = max(max_depth, d)
        return max_depth >= depth or len(effects) == 0

    @staticmethod
    def _law_mechanism(plan: Dict) -> bool:
        mechanism = plan.get("mechanism", "")
        if not mechanism:
            return True
        steps = [s for s in mechanism.split("\n") if s.strip()]
        return len(steps) >= 2 and all(len(s.strip()) > 10 for s in steps)

    @staticmethod
    def _law_source(plan: Dict) -> bool:
        evidence_nodes = plan.get("evidence", {})
        if not evidence_nodes:
            return True
        for key, val in evidence_nodes.items():
            if isinstance(val, dict) and "source" not in val:
                return False
        return True


# ───────────────────────────────────────────────────────────────────────────────
# SHAPE EXTRACTOR
# ───────────────────────────────────────────────────────────────────────────────

class ShapeExtractor:
    KNOWN_PATTERNS = {
        "resource-exhaustion-monotonic": {
            "triggers": ["disk full", "memory full", "connection pool exhausted", "GPU OOM"],
            "signals": [
                r"\b(disk|volume|memory|ram|swap|inode)\b.*\b(full|free|used|exhaust)",
                r"\bno space left\b",
                r"\b\d+(\.\d+)?%\s*used\b",
            ],
            "mechanism": "monotonic growth of ephemeral artifact without cleanup",
            "contexts": ["disk", "memory", "network", "gpu"],
            "invariant": "LAW_RIPPLE",
        },
        "retry-storm-no-backoff": {
            "triggers": ["infinite loop", "retry exceeded", "timeout cascade", "connection refused loop"],
            "mechanism": "failure triggers immediate retry with no state change, identical failure recurs",
            "contexts": ["api", "db", "git", "file-lock"],
            "invariant": "LAW_DEGREE",
        },
        "manual-intervention-left-in-production": {
            "triggers": ["debug flag set", "temp file old", "cron commented", "firewall rule open"],
            "mechanism": "temporary change made for debugging, never reverted, silently decays",
            "contexts": ["config", "cron", "firewall", "env", "feature-flag"],
            "invariant": "LAW_RIPPLE",
        },
        "scope-creep-sidequest": {
            "triggers": ["task expanded", "unrelated files touched", "goal drift", "original issue abandoned"],
            "mechanism": "agent expands task scope beyond original goal, loses focus, original deliverable delayed",
            "contexts": ["coding", "research", "writing", "analysis"],
            "invariant": "LAW_CONTEXT",
        },
        "credential-leak-surface": {
            "triggers": ["key in log", "token in history", "password in diff", "secret in env"],
            "signals": [
                r"\b(api[ _-]?key|live key|secret[ _-]?key|access[ _-]?key|token|password|passphrase|credential)\b"
                # No leading \b on the surface words: the commonest surface on this
                # machine is ".zsh_history", and "_" is a word character, so \bhistory
                # never matches it. Measured: that one boundary hid 85 of 86 leaks.
                r".{0,80}?(history|\.log\b|logfile|log file|diff|commit|env|environment|config|transcript|jsonl)",
            ],
            "mechanism": "sensitive material written to durable surface without redaction",
            "contexts": ["shell-history", "git-log", "log-file", "env-var", "config-file"],
            "invariant": "LAW_TRADEOFF",
        },
        "service-unreachable-endpoint": {
            "triggers": ["not responding", "connection refused", "unreachable"],
            "signals": [
                r"\bnot responding\b",
                r"\bconnection refused\b",
                r"\b(unreachable|no route to host)\b",
                r"\b(dead|down|offline)\b.{0,30}\bport\b",
            ],
            "mechanism": "a process the estate depends on stopped listening and nothing restarted it",
            "contexts": ["ollama", "gateway", "api", "daemon"],
            "invariant": "LAW_MECHANISM",
        },
    }

    def __init__(self, graph: ExperienceGraph):
        self.graph = graph

    def extract(self, episode: Episode) -> Optional[Shape]:
        pattern_id = self.pattern_for(f"{episode.trigger} {episode.action}")
        if pattern_id:
            return self._create_or_update_shape(
                pattern_id, self.KNOWN_PATTERNS[pattern_id], episode
            )
        logger.info(f"Novel incident logged: {episode.id}")
        return None

    def pattern_for(self, text: str) -> Optional[str]:
        """Which shape does this text belong to, if any.

        One matcher, used by both callers. `extract` classifies an incident on the
        way in and `find_prevention` classifies it again on the way out, and until
        today they matched differently: find_prevention compared against
        `morphology["trigger_keywords"]`, which holds the hand written English
        phrases, so it answered None for text that `extract` had just classified.
        """
        probe = Episode(id="", timestamp="", lane="", trigger=text,
                        action="", outcome="")
        for pattern_id, pattern in self.KNOWN_PATTERNS.items():
            if self._matches_pattern(probe, pattern):
                return pattern_id
        return None

    def _matches_pattern(self, episode: Episode, pattern: Dict) -> bool:
        """Does this episode belong to this shape?

        The trigger list is hand written English: "disk full", "token in history".
        Real episodes are machine written: "Disk has 1.9 GiB free (99.6% used)",
        "Stripe live key found in /Users/chidionyema/.zsh_history". Measured on the
        121 episodes recorded up to 2026-08-23, substring matching against those
        phrases found 0, while 105 of them are plainly two known shapes. So the
        triggers stay as documentation of the pattern and `signals` does the work:
        a regex per shape, written against the text the estate actually emits.
        """
        text = f"{episode.trigger} {episode.action}".lower()
        if any(t in text for t in pattern["triggers"]):
            return True
        return any(re.search(s, text) for s in pattern.get("signals", ()))

    def _create_or_update_shape(self, pattern_id: str, pattern: Dict, episode: Episode) -> Shape:
        existing = self.graph.get_shapes(pattern_name=pattern_id)

        if existing:
            shape = existing[0]
            shape.occurrence_count += 1
            shape.last_seen = episode.timestamp
            if episode.lane not in shape.contexts_observed:
                shape.contexts_observed.append(episode.lane)
            if episode.outcome == "prevented":
                successes = shape.prevention_success_rate * (shape.occurrence_count - 1)
                shape.prevention_success_rate = (successes + 1) / shape.occurrence_count
        else:
            shape = Shape(
                id=pattern_id,
                pattern_name=pattern_id,
                morphology={
                    "trigger_keywords": pattern["triggers"],
                    "mechanism": pattern["mechanism"],
                },
                contexts_observed=[episode.lane],
                invariant_violated=pattern["invariant"],
                prevention_skill=pattern_id,
                first_seen=episode.timestamp,
                last_seen=episode.timestamp,
                occurrence_count=1,
                prevention_success_rate=0.0,
                confidence=0.7
            )

        self.graph.upsert_shape(shape)
        return shape

    def find_prevention(self, trigger: str, lane: str) -> Optional[Skill]:
        """The skill that handles this incident, or None to send it to a person.

        The old gate asked for `shape.prevention_success_rate > 0.5`. A shape is
        born at 0.0 and that number only moves when its skill runs, so no shape
        could ever hand over its skill and no skill could ever earn a rate. The
        loop the whole design rests on could not turn once. The gate belongs on
        the skill instead: a skill that has never run is allowed exactly the run
        that gives it a record, and one that has run and mostly failed is not.
        """
        pattern_id = self.pattern_for(trigger)
        if not pattern_id:
            return None
        shapes = self.graph.get_shapes(pattern_name=pattern_id)
        for shape in shapes:
            if shape.confidence <= 0.5:
                continue
            skill = self.graph.get_skill(self._skill_id(shape))
            if not skill:
                continue
            if skill.total_uses == 0 or skill.success_rate > 0.5:
                return skill
        return None

    @staticmethod
    def _skill_id(shape: Shape) -> str:
        """Shapes recorded before 2026-08-23 hold a path, "skills/<name>.py", while
        the skills table is keyed by bare name, so every lookup missed. New shapes
        store the bare name; this reads both."""
        ref = shape.prevention_skill or shape.pattern_name
        return os.path.basename(ref).removesuffix(".py")


# ───────────────────────────────────────────────────────────────────────────────
# TELEGRAM BRIDGE
# ───────────────────────────────────────────────────────────────────────────────

class TelegramBridge:
    # Three tries per message: a blip costs a second and is invisible.
    SEND_TRIES = 3
    # One message that exhausted all three tries opens the circuit. It has already spent
    # three attempts proving the far side is not answering; spending another six to reach
    # a threshold of three MESSAGES would burn most of a tick learning the same fact.
    BREAKER_THRESHOLD = 1
    # How long the circuit stays open before one request is allowed through to test the
    # far side. Telegram being down is not a reason to spend the tick budget on retries,
    # and it is not a reason to stop trying forever either.
    BREAKER_COOLDOWN_SECONDS = 300
    # How long the same alert stays said. The state machine advances one state
    # per 60s tick, so IDLE -> SENSE -> CRISIS is about three minutes: an estate
    # holding eight standing criticals would send the founder the same crisis
    # message twenty times an hour, forever, and the twentieth teaches him to
    # stop reading the first. An alert is worth exactly one message until either
    # the situation changes or this much time passes.
    REPEAT_COOLDOWN_SECONDS = float(os.getenv("MAESTRO_REPEAT_COOLDOWN_S", str(6 * 3600)))
    # On disk, because launchd restarts maestro on any exit (KeepAlive) and an
    # in-memory fence would re-send everything on every restart.
    FENCE_PATH = os.path.expanduser(os.getenv("MAESTRO_FENCE", "~/.maestro/alert_fence.json"))

    def __init__(self, token: str, chat_id: str, graph: ExperienceGraph):
        self.token = token
        self.chat_id = chat_id
        self.graph = graph
        self.enabled = bool(token and chat_id)
        self._consecutive_failures = 0
        self._circuit_opened_at = 0.0

    def _load_fence(self) -> Dict[str, float]:
        try:
            with open(self.FENCE_PATH) as fh:
                data = json.load(fh)
            return {k: float(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except Exception:
            # A missing or corrupt fence must never stop an alert. Failing open
            # costs a duplicate message; failing closed loses the alert itself.
            return {}

    def _already_said(self, key: str) -> bool:
        """True when this exact alert went out inside the cooldown.

        The fence is written only on a successful send, so a message that was
        dropped by the circuit breaker is not recorded as delivered and will be
        tried again on the next tick.
        """
        fence = self._load_fence()
        now = time.time()
        last = fence.get(key)
        if last is not None and now - last < self.REPEAT_COOLDOWN_SECONDS:
            return True
        return False

    def _record_said(self, key: str) -> None:
        fence = self._load_fence()
        now = time.time()
        fence[key] = now
        # Drop entries older than two cooldowns so the file cannot grow forever.
        cutoff = now - 2 * self.REPEAT_COOLDOWN_SECONDS
        fence = {k: v for k, v in fence.items() if v >= cutoff}
        try:
            os.makedirs(os.path.dirname(self.FENCE_PATH), exist_ok=True)
            tmp = self.FENCE_PATH + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(fence, fh)
            os.replace(tmp, self.FENCE_PATH)
        except Exception as e:
            logger.error("Could not write the alert fence: %s", e)

    def _circuit_is_open(self) -> bool:
        """Open means: stop calling, the far side is not answering.

        It closes on a clock, not on hope. After the cooldown one request is let
        through; if it works the counter resets, if it does not the circuit opens
        again from the current time.
        """
        if self._consecutive_failures < self.BREAKER_THRESHOLD:
            return False
        if time.time() - self._circuit_opened_at >= self.BREAKER_COOLDOWN_SECONDS:
            return False
        return True

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures == self.BREAKER_THRESHOLD:
            self._circuit_opened_at = time.time()
            logger.error(
                "Telegram circuit open after %d message(s) that exhausted %d tries; "
                "no further sends for %ds",
                self.BREAKER_THRESHOLD, self.SEND_TRIES, self.BREAKER_COOLDOWN_SECONDS,
            )

    def _record_success(self) -> None:
        if self._consecutive_failures:
            logger.info("Telegram recovered after %d failure(s)", self._consecutive_failures)
        self._consecutive_failures = 0
        self._circuit_opened_at = 0.0

    def send(self, message: str, priority: Priority = Priority.P2,
             dedup_key: Optional[str] = None) -> bool:
        """Send one message to the founder.

        `dedup_key` names WHAT the message is about, so a digest whose episode
        counters have ticked is still recognised as the same alert. Without one,
        the message text is the key.
        """
        if not self.enabled:
            logger.info(f"[TELEGRAM would send]: {message}")
            return True
        if priority == Priority.P3:
            return True

        key = dedup_key or "text:" + hashlib.sha256(message.encode()).hexdigest()[:16]
        if self._already_said(key):
            logger.info("Already told him about %s inside the cooldown; not repeating", key)
            return True

        if self._circuit_is_open():
            logger.warning("Telegram circuit open, dropping a %s message", priority.name)
            return False

        import urllib.request
        import urllib.parse
        import urllib.error
        url = f"https://api.telegram.org/bot{self.token}/sendMessage"

        # Every message this class sends interpolates a finding's description
        # into a Markdown template ("*Estate Digest*", "• {description}"). A
        # description holding an underscore or a lone asterisk -- a file path, a
        # config key, a shell glob -- makes Telegram reject the whole body with
        # 400 "can't parse entities", and the retry loop then sent the same
        # unparseable bytes twice more before opening the circuit breaker.
        # Measured 2026-08-23: three failures, one dropped P2, and the finding
        # it was carrying (a HuggingFace token in ~/.claude/history.jsonl) was
        # lost. Formatting is worth trying and never worth losing a message
        # over, so a parse rejection drops parse_mode and sends it as text.
        plain = False

        def body() -> bytes:
            fields = {"chat_id": self.chat_id, "text": message}
            if not plain:
                fields["parse_mode"] = "Markdown"
            return urllib.parse.urlencode(fields).encode()

        last_error = None
        for attempt in range(self.SEND_TRIES):
            try:
                req = urllib.request.Request(url, data=body(), method="POST")
                with urllib.request.urlopen(req, timeout=10) as resp:
                    if resp.status == 200:
                        self._record_success()
                        self._record_said(key)
                        return True
                    last_error = f"HTTP {resp.status}"
            except urllib.error.HTTPError as e:
                # Telegram puts the real reason in the body. "HTTP Error 400:
                # Bad Request" on its own names nothing and cost an afternoon.
                try:
                    detail = json.loads(e.read()).get("description", "")
                except Exception:
                    detail = ""
                last_error = f"HTTP {e.code}: {detail or e.reason}"
                if e.code == 400 and not plain:
                    plain = True
                    logger.warning("Telegram rejected the Markdown (%s); "
                                   "resending as plain text", detail or "no detail")
                    continue          # retry now, do not spend a backoff on it
            except Exception as e:
                last_error = str(e)
            if attempt < self.SEND_TRIES - 1:
                time.sleep(2 ** attempt)

        logger.error("Telegram send failed after %d tries: %s",
                     self.SEND_TRIES, last_error)
        self._record_failure()
        return False

    def send_digest(self, stats: Dict, incidents: List[Dict], needs_human: List[Dict]) -> bool:
        lines = [
            "🏠 *Estate Digest*",
            f"\n📊 Stats: {stats['total_episodes']} episodes, "
            f"{stats['total_shapes']} shapes, {stats['total_skills']} skills",
            f"💰 Today: ${stats['today_spend_usd']:.2f} / ${Config.MAX_DAILY_SPEND_USD:.0f}",
        ]

        if needs_human:
            lines.append(f"\n⚠️ *Need you: {len(needs_human)}*")
            for item in needs_human:
                lines.append(f"  • {item['description']}")

        if incidents:
            lines.append(f"\n✅ *Auto-resolved: {len(incidents)}*")
            for inc in incidents:
                lines.append(f"  • {inc['description']}")

        if not needs_human and not incidents:
            lines.append("\n✅ All clear. Nothing needs you.")

        # Key on WHICH things need him, not on the rendered text: the stats line
        # carries episode and spend counters that move every tick, so the text
        # of an unchanged estate is never twice the same.
        subject = ",".join(sorted(str(i.get("id", "?")) for i in needs_human))
        key = "digest:" + hashlib.sha256(subject.encode()).hexdigest()[:16]
        return self.send("\n".join(lines), Priority.P2, dedup_key=key)

    def poll_commands(self) -> List[Dict]:
        if not self.enabled:
            return []
        try:
            import urllib.request
            url = f"https://api.telegram.org/bot{self.token}/getUpdates?offset=-10"
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.loads(resp.read())
                commands = []
                for update in data.get("result", []):
                    msg = update.get("message", {})
                    text = msg.get("text", "")
                    if text.startswith("/"):
                        commands.append({
                            "command": text.split()[0],
                            "args": text.split()[1:],
                            "from": msg.get("from", {}).get("id"),
                            "timestamp": msg.get("date")
                        })
                return commands
        except Exception as e:
            logger.error(f"Telegram poll failed: {e}")
            return []


# ───────────────────────────────────────────────────────────────────────────────
# ESTATE SENSORS
# ───────────────────────────────────────────────────────────────────────────────

class EstateSensors:
    # What the estate audit actually writes, and what this class used to expect.
    #
    # `estate_audit.py:474` emits {"generated_at": <epoch>, "counts": {...},
    # "rows": [{domain, title, value, severity, proof, detail}]} with severities
    # from `estate_audit.py:43` -- critical / warn / ok / unknown. This class
    # asked for `data["findings"]` and P0..P3 and got neither, so every read
    # returned an empty list. Measured 2026-08-23 20:07: a 24,311-byte file
    # holding 57 rows and 8 criticals, read once a minute, producing 0 findings
    # and the log line "All clear -- no digest sent (P3)". The estate had a
    # billing incident and unrestorable backups that whole time.
    #
    # A key that does not exist is the worst kind of sensor fault: nothing
    # raises, nothing logs, and silence is indistinguishable from health.
    AUDIT_SEVERITY_TO_PRIORITY = {"critical": "P0", "warn": "P1", "unknown": "P2"}
    # `ok` rows are the audit saying a check passed. They are not findings and
    # are dropped rather than mapped, so a clean estate still reports clean.
    AUDIT_SEVERITY_IGNORED = frozenset({"ok"})
    # The audit runs on its own schedule. Past this, what it says is history,
    # and reading history as current state is how a dead checker looks green.
    AUDIT_STALE_AFTER_HOURS = float(os.getenv("MAESTRO_AUDIT_STALE_H", "6"))

    def __init__(self):
        self.audit_path = os.path.expanduser(Config.ESTATE_AUDIT_PATH)

    def _sensor_fault(self, fault_id: str, description: str) -> Dict:
        """A sensor that cannot see must say so, not report nothing.

        These are P1: the estate may be perfectly healthy, but nobody can
        currently tell, and that is a fact the founder needs rather than a
        silence he will read as good news.
        """
        return {
            "id": fault_id,
            "severity": "P1",
            "lane": "estate",
            "description": description,
            "auto_fix": False,
            "skill": "estate_audit_repair",
            "context": {"audit_path": self.audit_path},
        }

    def read_audit(self) -> List[Dict]:
        if not os.path.exists(self.audit_path):
            logger.warning(f"Audit file not found: {self.audit_path}")
            return [self._sensor_fault(
                "estate-audit-missing",
                f"The estate audit maestro senses through is not there: {self.audit_path}",
            )]
        try:
            with open(self.audit_path) as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to read audit: {e}")
            return [self._sensor_fault(
                "estate-audit-unreadable",
                f"The estate audit cannot be read: {e}",
            )]

        findings: List[Dict] = []

        age_h = (time.time() - os.path.getmtime(self.audit_path)) / 3600
        generated_at = data.get("generated_at")
        if isinstance(generated_at, (int, float)):
            age_h = (time.time() - generated_at) / 3600
        if age_h > self.AUDIT_STALE_AFTER_HOURS:
            findings.append(self._sensor_fault(
                "estate-audit-stale",
                f"The estate audit last ran {age_h:.1f}h ago; "
                f"everything below it is that old",
            ))

        # `rows` is what the audit writes today. `findings` is accepted too, so a
        # writer that already speaks this class's own shape keeps working.
        rows = data.get("rows")
        if rows is None:
            rows = data.get("findings")
        if rows is None:
            logger.error(
                "The audit at %s has neither 'rows' nor 'findings' (keys: %s)",
                self.audit_path, sorted(data)[:10],
            )
            return findings + [self._sensor_fault(
                "estate-audit-schema-unknown",
                f"The estate audit has no rows this reader understands "
                f"(keys: {', '.join(sorted(data)[:10])})",
            )]

        unmapped = set()
        for row in rows:
            severity = str(row.get("severity", "")).lower()
            if severity in self.AUDIT_SEVERITY_IGNORED:
                continue
            # Already in this class's vocabulary: pass it through untouched.
            if severity.upper() in ("P0", "P1", "P2", "P3"):
                findings.append(row)
                continue
            priority = self.AUDIT_SEVERITY_TO_PRIORITY.get(severity)
            if priority is None:
                # Never drop a row because its severity is a word nobody taught
                # this map. An unknown severity is treated as a real finding at
                # P1 and the word is reported, because a silent skip here is the
                # exact defect this whole function is a fix for.
                unmapped.add(severity or "(blank)")
                priority = "P1"

            domain = row.get("domain", "estate")
            title = row.get("title", "untitled check")
            value = row.get("value", "")
            findings.append({
                "id": "estate-audit-" + hashlib.sha256(
                    f"{domain}|{title}".encode()
                ).hexdigest()[:12],
                "severity": priority,
                "lane": "estate",
                "description": f"[{domain}] {title}: {value}",
                # An audit row describes a state, not a repair. Nothing here has
                # a verified skill behind it, and _do_act invents an `echo` skill
                # for anything marked auto-fixable and then records it as
                # resolved -- a fix that never happened, reported as one.
                "auto_fix": False,
                "skill": "estate_audit_followup",
                "context": {
                    "domain": domain,
                    "title": title,
                    "value": value,
                    "proof": row.get("proof", ""),
                    "detail": row.get("detail", ""),
                },
            })

        if unmapped:
            logger.warning(
                "Audit severities this reader does not know, raised as P1: %s",
                ", ".join(sorted(unmapped)),
            )
        logger.info(
            "Estate audit: %d row(s) read, %d finding(s) after dropping %s",
            len(rows), len(findings), "/".join(sorted(self.AUDIT_SEVERITY_IGNORED)),
        )
        return findings

    def check_bridges(self) -> List[Dict]:
        findings = []
        bridges = [("kimi-bridge", 8765), ("deepseek-bridge", 8767), ("ollama", 11434)]
        for name, port in bridges:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(2)
                result = sock.connect_ex(("127.0.0.1", port))
                sock.close()
                if result != 0:
                    findings.append({
                        "id": f"bridge-down-{name}",
                        "severity": "P1",
                        "lane": "estate",
                        "description": f"{name} not responding on port {port}",
                        "auto_fix": True,
                        "skill": "restart_bridge",
                        "context": {"bridge_name": name, "port": port}
                    })
            except Exception as e:
                logger.error(f"Bridge check failed for {name}: {e}")
        return findings

    def check_disk(self) -> List[Dict]:
        findings = []
        try:
            # Percent-used is not a usable signal on APFS. statvfs f_bfree and
            # f_bavail both exclude purgeable space, so this machine reads 95.9%
            # while `df -h /` reads 40% -- a P0 crisis every 60 seconds on a disk
            # with 19 GiB free. Free bytes is the same number under both
            # accountings, so alert on that and report percent for context only.
            stat = os.statvfs("/")
            free_gb = stat.f_bavail * stat.f_frsize / (1024 ** 3)
            percent = (stat.f_blocks - stat.f_bfree) / stat.f_blocks * 100
            if free_gb < Config.DISK_FREE_GB_CRITICAL:
                findings.append({
                    "id": "disk-critical",
                    "severity": "P0",
                    "lane": "estate",
                    "description": f"Disk has {free_gb:.1f} GiB free ({percent:.1f}% used)",
                    "auto_fix": True,
                    "skill": "disk_cleanup",
                    "context": {"free_gb": free_gb, "percent": percent,
                                "threshold_gb": Config.DISK_FREE_GB_CRITICAL}
                })
            elif free_gb < Config.DISK_FREE_GB_WARNING:
                findings.append({
                    "id": "disk-warning",
                    "severity": "P1",
                    "lane": "estate",
                    "description": f"Disk has {free_gb:.1f} GiB free ({percent:.1f}% used)",
                    "auto_fix": True,
                    "skill": "disk_cleanup",
                    "context": {"free_gb": free_gb, "percent": percent,
                                "threshold_gb": Config.DISK_FREE_GB_WARNING}
                })
        except Exception as e:
            logger.error(f"Disk check failed: {e}")
        return findings

    def check_credentials(self) -> List[Dict]:
        findings = []
        history_paths = [
            os.path.expanduser("~/.bash_history"),
            os.path.expanduser("~/.zsh_history"),
            os.path.expanduser("~/.claude/history.jsonl"),
        ]
        patterns = [
            (r"sk-ant-api[0-9a-zA-Z-_]{100,}", "Anthropic API key"),
            (r"sk_live_[a-zA-Z0-9]{40,}", "Stripe live key"),
            (r"hf_[a-zA-Z0-9]{30,}", "HuggingFace token"),
            (r"ghp_[a-zA-Z0-9]{36,}", "GitHub token"),
        ]

        for hist_path in history_paths:
            if not os.path.exists(hist_path):
                continue
            try:
                with open(hist_path, "rb") as f:
                    content = f.read().decode("utf-8", errors="ignore")
                    for pattern, name in patterns:
                        import re
                        if re.search(pattern, content):
                            findings.append({
                                "id": f"credential-leak-{name.lower().replace(' ', '-')}",
                                "severity": "P0",
                                "lane": "estate",
                                "description": f"{name} found in {hist_path}",
                                # Removing a leaked key from a history file is a
                                # repair, not a rotation, and secret-scrub.py already
                                # runs on every Stop hook estate wide, so letting
                                # maestro run it adds no reach it did not have. It
                                # redacts in place, never changes a line count, and
                                # refuses the files whose job is to hold secrets.
                                # Rotating the key at the provider is still a person's
                                # decision and is not what this does.
                                "auto_fix": True,
                                "skill": "credential-leak-surface",
                                "context": {"file": hist_path, "key_type": name}
                            })
            except Exception as e:
                logger.error(f"Credential scan failed for {hist_path}: {e}")
        return findings

    def sense(self) -> List[Dict]:
        findings = []
        findings.extend(self.read_audit())
        findings.extend(self.check_bridges())
        findings.extend(self.check_disk())
        findings.extend(self.check_credentials())
        return findings


# ───────────────────────────────────────────────────────────────────────────────
# SKILL EXECUTOR
# ───────────────────────────────────────────────────────────────────────────────

class SkillExecutor:
    ALLOWED_PATHS = [
        os.path.expanduser("~/.estate"),
        os.path.expanduser("~/.maestro"),
        os.path.expanduser("~/prospector"),
        "/tmp",
    ]

    DANGEROUS_PATTERNS = [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf\s+~",
        r":\s*\{\s*:\s*\}\s*;\s*while",
        r"mkfs\.",
        r"dd\s+if=.*of=/dev/",
    ]

    def __init__(self, graph: ExperienceGraph):
        self.graph = graph

    def execute(self, skill: Skill, context: Dict) -> Tuple[bool, Dict]:
        start = time.time()
        evidence = {"skill_id": skill.id, "context": context}

        if not self._path_safe(skill.procedure):
            return False, {**evidence, "error": "Path violation", "blocked": True}

        if self._dangerous_detected(skill.procedure):
            return False, {**evidence, "error": "Dangerous pattern detected", "blocked": True}

        try:
            if skill.procedure.startswith("shell:"):
                cmd = skill.procedure.replace("shell:", "").strip()
                result = subprocess.run(
                    cmd, shell=True, capture_output=True, text=True,
                    timeout=300, cwd=context.get("cwd", "/tmp")
                )
                success = result.returncode == 0
                evidence["stdout"] = result.stdout[:2000]
                evidence["stderr"] = result.stderr[:2000]
                evidence["returncode"] = result.returncode
            elif skill.procedure.startswith("python:"):
                code = skill.procedure.replace("python:", "").strip()
                namespace = {"__builtins__": {}}
                exec(code, namespace)
                success = namespace.get("__result__", False)
                evidence["result"] = success
            else:
                success = False
                evidence["error"] = f"Unknown procedure type: {skill.procedure[:50]}"

            duration_ms = int((time.time() - start) * 1000)
            evidence["duration_ms"] = duration_ms

            skill.total_uses += 1
            skill.last_used = datetime.utcnow().isoformat()
            skill.avg_duration_ms = int(
                (skill.avg_duration_ms * (skill.total_uses - 1) + duration_ms) / skill.total_uses
            )
            if success:
                skill.success_rate = (skill.success_rate * (skill.total_uses - 1) + 1.0) / skill.total_uses
            else:
                skill.success_rate = (skill.success_rate * (skill.total_uses - 1)) / skill.total_uses

            self.graph.upsert_skill(skill)
            return success, evidence

        except Exception as e:
            evidence["error"] = str(e)
            evidence["duration_ms"] = int((time.time() - start) * 1000)
            return False, evidence

    def _path_safe(self, procedure: str) -> bool:
        suspicious = ["/etc/", "/usr/", "/bin/", "/sbin/", "/var/", "/home/"]
        for s in suspicious:
            if s in procedure and not any(a in procedure for a in self.ALLOWED_PATHS):
                return False
        return True

    def _dangerous_detected(self, procedure: str) -> bool:
        import re
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, procedure):
                return True
        return False


# ───────────────────────────────────────────────────────────────────────────────
# THE MAESTRO
# ───────────────────────────────────────────────────────────────────────────────

class Maestro:
    def __init__(self):
        self.db = ExperienceGraph(Config.DB_PATH)
        self.extractor = ShapeExtractor(self.db)
        self.bridge = TelegramBridge(Config.TELEGRAM_TOKEN, Config.TELEGRAM_CHAT_ID, self.db)
        self.sensors = EstateSensors()
        self.executor = SkillExecutor(self.db)
        self.state = State.IDLE
        self.current_intent: Optional[Intent] = None
        self.crisis_mode = False
        # Was: utcnow() - 25h. That made every fresh process go IDLE -> META_REVIEW
        # and stop there, so `--once` could never reach SENSE and the dry test only
        # ever exercised one branch. The timestamp is durable now: a restart resumes
        # the real schedule, and a first-ever run senses before it reviews itself.
        _last = self.db.kv_get("last_meta_review")
        self.last_meta_review = (
            datetime.fromisoformat(_last) if _last else datetime.utcnow()
        )
        self.daily_findings: List[Dict] = []
        self.daily_resolved: List[Dict] = []
        self.daily_needs_human: List[Dict] = []
        self._seed_invariants()

    def _seed_invariants(self):
        laws = ["LAW_CONTEXT", "LAW_DEGREE", "LAW_BASELINE",
                "LAW_TRADEOFF", "LAW_RIPPLE", "LAW_MECHANISM", "LAW_SOURCE"]
        with self.db._connect() as conn:
            for law in laws:
                conn.execute("""
                    INSERT OR IGNORE INTO invariants (id, law_name, last_enforced)
                    VALUES (?, ?, ?)
                """, (law, law, datetime.utcnow().isoformat()))

    def _new_intent(self, trigger: str) -> Intent:
        self.current_intent = Intent(
            id=f"INTENT-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}-{hashlib.sha256(trigger.encode()).hexdigest()[:8]}",
            timestamp=datetime.utcnow().isoformat(),
            trigger=trigger,
            state_transitions=["IDLE"]
        )
        return self.current_intent

    def _transition(self, new_state: State):
        self.state = new_state
        if self.current_intent:
            self.current_intent.state_transitions.append(new_state.name)
        logger.info(f"State: {new_state.name}")

    def _save_intent(self):
        if not self.current_intent:
            return
        intent_dir = os.path.expanduser(Config.INTENT_LOG_DIR)
        os.makedirs(intent_dir, exist_ok=True)
        path = os.path.join(intent_dir, f"{self.current_intent.id}.json")
        with open(path, "w") as f:
            json.dump(asdict(self.current_intent), f, indent=2, default=str)

    def tick(self):
        try:
            if self.state == State.IDLE:
                self._do_idle()
            elif self.state == State.SENSE:
                self._do_sense()
            elif self.state == State.ORIENT:
                self._do_orient()
            elif self.state == State.DECIDE:
                self._do_decide()
            elif self.state == State.ACT:
                self._do_act()
            elif self.state == State.VERIFY:
                self._do_verify()
            elif self.state == State.REPORT:
                self._do_report()
            elif self.state == State.CRISIS:
                self._do_crisis()
            elif self.state == State.META_REVIEW:
                self._do_meta_review()
        except Exception as e:
            logger.exception("Tick failed")
            self._transition(State.IDLE)
            self._save_intent()

    def _do_idle(self):
        self._new_intent("periodic_tick")
        if self.crisis_mode:
            self._transition(State.CRISIS)
            return
        if datetime.utcnow() - self.last_meta_review > timedelta(hours=Config.META_REVIEW_INTERVAL_HOURS):
            self._transition(State.META_REVIEW)
            return
        self._transition(State.SENSE)

    def _do_sense(self):
        findings = self.sensors.sense()
        self._close_alarms_for_what_cleared(findings)
        self.daily_findings.extend(findings)
        p0s = [f for f in findings if f.get("severity") == "P0"]
        if p0s:
            self.crisis_mode = True
            self._transition(State.CRISIS)
            return
        if findings:
            self._transition(State.ORIENT)
        else:
            self._transition(State.REPORT)

    def _close_alarms_for_what_cleared(self, findings: List[Dict]):
        """A problem that stopped being sensed closes its alarm, once, out loud."""
        cleared = self.db.close_cleared_alarms({str(f.get("id", "?")) for f in findings})
        for alarm in cleared:
            self.db.log_episode(Episode(
                id=f"EP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-cleared-"
                   f"{hashlib.sha256(alarm['finding_id'].encode()).hexdigest()[:6]}",
                timestamp=datetime.utcnow().isoformat(),
                lane=alarm.get("lane") or "estate",
                trigger=alarm.get("description") or alarm["finding_id"],
                action="alarm_cleared",
                outcome="self_cleared",
                evidence={"finding_id": alarm["finding_id"],
                          "open_since": alarm["first_seen"],
                          "times_seen": alarm["times_seen"]},
            ))
        if cleared:
            names = "\n".join(
                f"• {a.get('description') or a['finding_id']}" for a in cleared
            )
            subject = ",".join(sorted(a["finding_id"] for a in cleared))
            self.bridge.send(
                f"✅ Cleared: {len(cleared)} alarm(s) no longer present\n{names}",
                Priority.P1,
                dedup_key="cleared:" + hashlib.sha256(subject.encode()).hexdigest()[:16],
            )

    def _do_orient(self):
        intent = self.current_intent
        intent.orient_analysis["findings"] = len(self.daily_findings)
        intent.orient_analysis["shapes_matched"] = 0
        intent.orient_analysis["novel"] = 0

        for finding in self.daily_findings:
            prevention = self.extractor.find_prevention(
                finding["description"], finding.get("lane", "estate")
            )
            if prevention:
                finding["prevention_skill"] = prevention.id
                finding["prevention_available"] = True
                intent.orient_analysis["shapes_matched"] += 1
            else:
                episode = Episode(
                    id=f"EP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{hashlib.sha256(finding['id'].encode()).hexdigest()[:6]}",
                    timestamp=datetime.utcnow().isoformat(),
                    lane=finding.get("lane", "estate"),
                    trigger=finding["description"],
                    action="detected",
                    outcome="unknown"
                )
                shape = self.extractor.extract(episode)
                if shape:
                    finding["shape_extracted"] = shape.id
                    intent.orient_analysis["shapes_matched"] += 1
                else:
                    intent.orient_analysis["novel"] += 1

        self._transition(State.DECIDE)

    def _do_decide(self):
        intent = self.current_intent
        intent.decision["auto_fix"] = []
        intent.decision["queue"] = []
        intent.decision["escalate"] = []

        for finding in self.daily_findings:
            lane = finding.get("lane", "estate")
            lane_config = Config.LANES.get(lane, Config.LANES["estate"])

            plan = {
                "domain": lane,
                "assessments": {
                    "severity": {"value": finding.get("severity", "P2"), "threshold": "P1", "rate": "static"}
                },
                "baseline": "previous_state_normal",
                "tradeoffs": [{"cost": "time", "probability": 0.3, "impact": "delay"}],
                "ripple_effects": [{"effect": "service_restart", "then": {"effect": "brief_downtime"}}],
                # Two real steps, because that is what _do_act and _do_verify do.
                # The old one-liner ("<skill> execution with verification") failed
                # _law_mechanism's two-step floor on EVERY plan, so every finding
                # since the gate existed was escalated as a LAW_MECHANISM
                # violation and the auto_fix and queue branches below were dead
                # code. Measured 2026-08-24 across all 183 live intents: the only
                # 2 findings that ever reached this method were both rejected here.
                "mechanism": (
                    f"run skill {finding.get('skill', 'unknown')} against the finding's context\n"
                    "re-sense the lane and confirm the finding is gone before reporting"
                ),
                "sources": [{"source": "estate_audit", "retrieval_date": datetime.utcnow().isoformat(), "confidence": 0.9}]
            }

            try:
                laws = LawMiddleware.validate(plan, {"allowed_domains": list(Config.LANES.keys())}, self.db)
                intent.laws_applied.extend(laws)
            except LawViolation as e:
                intent.laws_violated.append({"law": e.law_name, "reason": e.reason})
                finding["route"] = "escalate"
                finding["reason"] = f"Law violation: {e.law_name}"
                intent.decision["escalate"].append(finding)
                continue

            if finding.get("severity") == "P0":
                finding["route"] = "escalate"
                intent.decision["escalate"].append(finding)
            elif finding.get("auto_fix") and lane_config["auto_fix"]:
                finding["route"] = "auto_fix"
                intent.decision["auto_fix"].append(finding)
            else:
                # Before this finding costs a person attention, ask the graph
                # whether it has watched a skill fix this exact class before.
                # A remembered fix is retried; only a problem the graph has
                # never solved goes to the queue. P0 stays above this branch on
                # purpose — a crisis pages first and learns second.
                remembered = (
                    self.db.remembered_fix(finding.get("description", ""), lane)
                    if lane_config["auto_fix"] else None
                )
                if remembered:
                    finding["skill"] = remembered
                    finding["route"] = "auto_fix"
                    finding.setdefault("context", {})["source"] = "memory"
                    intent.decision["auto_fix"].append(finding)
                else:
                    finding["route"] = "queue"
                    intent.decision["queue"].append(finding)

        self._transition(State.ACT)

    def _do_act(self):
        intent = self.current_intent
        intent.execution["results"] = []

        for finding in intent.decision.get("auto_fix", []):
            skill_id = finding.get("skill", "generic_fallback")
            skill = self.db.get_skill(skill_id)

            if not skill:
                # The sensor names its fix with a string written next to the check
                # ("disk_cleanup"), while fixes are registered against the shape
                # they repair. The two drifted, so check_disk asked for a skill id
                # that has never existed. The graph is the source of truth about
                # what handles an incident, so ask it before giving up.
                skill = self.extractor.find_prevention(
                    finding["description"], finding.get("lane", "estate")
                )

            if not skill:
                # There is no skill for this. Until today the code wrote one whose
                # whole procedure was `echo 'Fix for X'`, saved it to the skills
                # table as though it were real, and then read echo's exit 0 as a
                # successful repair: the incident was reported resolved and the
                # graph gained a fake skill that would be trusted next time. An
                # incident nobody can fix goes to a person, and says why.
                logger.warning(
                    f"No skill for {finding['id']} ({skill_id}); escalating instead of inventing one"
                )
                finding["route"] = "escalate"
                finding["no_skill"] = skill_id
                self.daily_needs_human.append(finding)
                intent.execution["results"].append({
                    "finding_id": finding["id"],
                    "skill_id": skill_id,
                    "success": False,
                    "evidence": {"reason": "no skill exists for this shape"}
                })
                continue

            success, evidence = self.executor.execute(skill, finding.get("context", {}))
            intent.execution["results"].append({
                "finding_id": finding["id"],
                "skill_id": skill.id,
                "success": success,
                "evidence": evidence
            })

            if success:
                # The success episode's evidence must name the skill that ran,
                # or remembered_fix can never learn from this repair and the
                # next occurrence pages a person for a problem already solved.
                finding.setdefault("context", {})["skill_id"] = skill.id
                self.daily_resolved.append(finding)
            else:
                finding["route"] = "escalate"
                finding["auto_fix_failed"] = True
                self.daily_needs_human.append(finding)

        for finding in intent.decision.get("queue", []):
            self.daily_needs_human.append(finding)

        for finding in intent.decision.get("escalate", []):
            self.daily_needs_human.append(finding)

        self._transition(State.VERIFY)

    def _do_verify(self):
        intent = self.current_intent
        intent.verification["checks"] = []
        recheck = self.sensors.sense()
        remaining_ids = {f["id"] for f in recheck}

        for result in intent.execution.get("results", []):
            if result["success"]:
                if result["finding_id"] not in remaining_ids:
                    intent.verification["checks"].append({
                        "finding_id": result["finding_id"],
                        "status": "verified_fixed"
                    })
                else:
                    intent.verification["checks"].append({
                        "finding_id": result["finding_id"],
                        "status": "fix_failed_still_present"
                    })
                    self.daily_needs_human.append(next(
                        f for f in self.daily_resolved if f["id"] == result["finding_id"]
                    ))

        self._transition(State.REPORT)

    def _do_report(self):
        stats = self.db.get_stats()

        # Same ledger as _do_crisis: a needs_human finding already alarmed and
        # still standing is counted, not re-escalated and not re-episoded.
        needs_human_news = []
        suppressed = 0
        for finding in self.daily_needs_human:
            disposition = self.db.alarm_disposition(
                str(finding.get("id", "?")),
                finding.get("description", ""),
                finding.get("lane", "estate"),
            )
            if disposition == "suppressed":
                suppressed += 1
            else:
                needs_human_news.append(finding)

        if needs_human_news:
            self.bridge.send_digest(stats, self.daily_resolved, needs_human_news)
        elif self.daily_resolved:
            self.bridge.send(f"✅ Auto-resolved {len(self.daily_resolved)} issues. All clear.", Priority.P3)
        else:
            logger.info("All clear — no digest sent (P3)")

        for finding in self.daily_resolved:
            self.db.log_episode(Episode(
                id=f"EP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{finding['id']}",
                timestamp=datetime.utcnow().isoformat(),
                lane=finding.get("lane", "estate"),
                trigger=finding["description"],
                action="auto_fix",
                outcome="success",
                evidence=finding.get("context", {}),
                shape_id=finding.get("shape_extracted")
            ))

        for finding in needs_human_news:
            self.db.log_episode(Episode(
                id=f"EP-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{finding['id']}",
                timestamp=datetime.utcnow().isoformat(),
                lane=finding.get("lane", "estate"),
                trigger=finding["description"],
                action="escalated",
                outcome="needs_human",
                evidence=finding.get("context", {}),
                shape_id=finding.get("shape_extracted")
            ))
        if suppressed:
            logger.info(
                "%d standing needs_human alarm(s) already open; ledger updated",
                suppressed,
            )

        self._maybe_send_learning_receipt()

        self.daily_findings = []
        self.daily_resolved = []
        self.daily_needs_human = []
        self._save_intent()
        self._transition(State.IDLE)

    # The receipt is weekly. It lives in the kv table, not in a scheduler,
    # so it needs no plist and survives restarts.
    LEARNING_RECEIPT_KEY = "last_learning_receipt"
    LEARNING_RECEIPT_DAYS = 7

    def _learning_receipt_text(self) -> str:
        """One paragraph proving whether last week's pages got cheaper.

        For every problem class that paged the founder in the week before last
        week, say what happened to it since: fixed without him, paged him
        again, or not seen. A class that did both in one week is counted as
        paging him again, because "learned" is the stronger claim and it loses
        ties. An all-zero week is reported as itself, not skipped — silence is
        also what a dead checker sounds like.
        """
        now = datetime.utcnow()
        week = timedelta(days=self.LEARNING_RECEIPT_DAYS)
        with self.db._connect() as conn:
            prior = conn.execute(
                "SELECT trigger, lane FROM episodes "
                "WHERE action IN ('escalated', 'crisis_escalation') "
                "AND timestamp >= ? AND timestamp < ?",
                ((now - 2 * week).isoformat(), (now - week).isoformat()),
            ).fetchall()
            current = conn.execute(
                "SELECT trigger, lane, action, outcome, evidence FROM episodes "
                "WHERE timestamp >= ?",
                ((now - week).isoformat(),),
            ).fetchall()
        prior_fps = {problem_fingerprint(t or "", l or "") for t, l in prior}
        fixed, paged_again, memory_fixes = set(), set(), 0
        for trigger, lane, action, outcome, evidence in current:
            fp = problem_fingerprint(trigger or "", lane or "")
            if action == "auto_fix" and outcome == "success":
                if fp in prior_fps:
                    fixed.add(fp)
                try:
                    if json.loads(evidence or "{}").get("source") == "memory":
                        memory_fixes += 1
                except json.JSONDecodeError:
                    pass
            elif action in ("escalated", "crisis_escalation") and fp in prior_fps:
                paged_again.add(fp)
        fixed -= paged_again
        gone = len(prior_fps) - len(fixed) - len(paged_again)
        replay = self._replay_frozen_incidents()
        prev = self._last_replay_score()
        trend = "first sitting" if prev is None else f"last receipt: {prev}"
        return (
            "📚 Learning receipt\n"
            f"Problem classes that paged you last week: {len(prior_fps)}.\n"
            f"Since then: {len(fixed)} fixed without you, "
            f"{len(paged_again)} paged you again, {gone} not seen.\n"
            f"Fixes replayed from memory this week: {memory_fixes}.\n"
            f"Frozen replay: {replay['solved']} of {replay['total']} past "
            f"incidents would now be fixed without you ({trend})."
        )

    def _replay_frozen_incidents(self) -> Dict:
        """Re-sit the frozen exam: which past pages would the graph fix today?

        The set is the historic escalation classes, frozen at first run (the
        founder's wealth of data, made a repeatable benchmark). This is a dry
        run of the same consult _do_decide makes — remembered_fix against the
        same lane rules — so it executes nothing and pages nobody. It answers
        one question: of the problems that used to cost a person attention,
        how many would now be fixed from memory?
        """
        self.db.freeze_replay_set()
        solved = []
        incidents = self.db.replay_set()
        for fingerprint, lane, trigger in incidents:
            lane_config = Config.LANES.get(lane, Config.LANES["estate"])
            if not lane_config["auto_fix"]:
                continue
            if self.db.remembered_fix(trigger or "", lane or "estate"):
                solved.append(fingerprint)
        return {"solved": len(solved), "total": len(incidents),
                "fingerprints": solved}

    def _last_replay_score(self) -> Optional[int]:
        with self.db._connect() as conn:
            row = conn.execute(
                "SELECT evidence FROM episodes WHERE action = 'replay' "
                "ORDER BY timestamp DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0] or "{}").get("solved")
        except json.JSONDecodeError:
            return None

    def _maybe_send_learning_receipt(self) -> None:
        last = self.db.kv_get(self.LEARNING_RECEIPT_KEY)
        if last and datetime.utcnow() - datetime.fromisoformat(last) < timedelta(
            days=self.LEARNING_RECEIPT_DAYS
        ):
            return
        # kv advances only on a delivered send: a dropped receipt is retried
        # next pass, not marked done. The loop closes at the reader.
        if self.bridge.send(
            self._learning_receipt_text(), Priority.P2, dedup_key="learning-receipt"
        ):
            self.db.kv_set(self.LEARNING_RECEIPT_KEY, datetime.utcnow().isoformat())
            # The replay score is recorded only when its receipt was delivered,
            # so the trend has exactly one point per week and a Telegram outage
            # cannot write a run of identical rows (LAW 28: the loop closes at
            # the reader, and LAW 30: a result worth knowing lands on disk).
            replay = self._replay_frozen_incidents()
            self.db.log_episode(Episode(
                id=f"REPLAY-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-"
                   f"{os.urandom(3).hex()}",
                timestamp=datetime.utcnow().isoformat(),
                lane="meta",
                trigger="frozen replay set",
                action="replay",
                outcome="measured",
                evidence=replay,
            ))

    def _do_crisis(self):
        p0_findings = [f for f in self.daily_findings if f.get("severity") == "P0"]

        # The alarm ledger, not the message fence, decides who gets escalated.
        # The fence only spaces repeats of one message; without the ledger a
        # standing P0 wrote a fresh needs_human episode every three-minute pass
        # — 46 copies of one Stripe finding in 29 hours, and nothing ever said
        # it had cleared.
        to_alert = []
        suppressed = 0
        for finding in p0_findings:
            disposition = self.db.alarm_disposition(
                str(finding.get("id", "?")),
                finding.get("description", ""),
                finding.get("lane", "estate"),
            )
            if disposition == "suppressed":
                suppressed += 1
            else:
                to_alert.append(finding)

        if to_alert:
            subject = ",".join(sorted(str(f.get("id", "?")) for f in to_alert))
            self.bridge.send(
                f"🚨 *CRISIS MODE*\n\n"
                f"{len(to_alert)} P0 finding(s):\n" +
                "\n".join(f"• {f['description']}" for f in to_alert) +
                "\n\nAll non-essential lanes frozen. Manual intervention required.",
                Priority.P0,
                dedup_key="crisis:" + hashlib.sha256(subject.encode()).hexdigest()[:16],
            )
            for finding in to_alert:
                self.db.log_episode(Episode(
                    # The timestamp is second-resolution, so the same finding
                    # escalating twice inside a second needs the random tail to
                    # avoid a UNIQUE collision that would crash the loop.
                    id=f"CRISIS-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-"
                       f"{os.urandom(3).hex()}-{finding['id']}",
                    timestamp=datetime.utcnow().isoformat(),
                    lane=finding.get("lane", "estate"),
                    trigger=finding["description"],
                    action="crisis_escalation",
                    outcome="needs_human",
                    evidence=finding.get("context", {})
                ))
        if suppressed:
            logger.info(
                "%d standing P0 alarm(s) already open; ledger updated, founder not re-paged",
                suppressed,
            )

        # A standing P0 makes every cycle SENSE -> CRISIS -> IDLE, so REPORT is
        # never reached and anything that only fires there starves. Measured
        # 2026-08-24 on the live loop: 5 standing estate-audit P0s had it
        # orbiting crisis indefinitely. The weekly receipt must survive that —
        # a week with a standing fire is exactly the week he needs the numbers.
        self._maybe_send_learning_receipt()

        self.crisis_mode = False
        self.daily_findings = []
        self._save_intent()
        self._transition(State.IDLE)

    def _do_meta_review(self):
        stats = self.db.get_stats()
        with self.db._connect() as conn:
            yesterday = (datetime.utcnow() - timedelta(hours=24)).isoformat()
            rows = conn.execute(
                "SELECT * FROM episodes WHERE timestamp > ?", (yesterday,)
            ).fetchall()

        failure_shapes = {}
        for row in rows:
            if row[5] == "failure":
                shape_id = row[9]
                if shape_id:
                    failure_shapes[shape_id] = failure_shapes.get(shape_id, 0) + 1

        proposals = []
        for shape_id, count in failure_shapes.items():
            if count >= 2:
                proposals.append(f"Shape {shape_id} failed {count} times — review prevention skill")

        if proposals:
            self.bridge.send(
                f"📊 *Meta-Review*\n\n"
                f"24h episodes: {len(rows)}\n"
                f"Failure patterns: {len(failure_shapes)}\n\n"
                f"Proposals:\n" + "\n".join(f"• {p}" for p in proposals) +
                "\n\n[Review on GitHub]",
                Priority.P2
            )

        self.last_meta_review = datetime.utcnow()
        self.db.kv_set("last_meta_review", self.last_meta_review.isoformat())
        self._transition(State.IDLE)

    def run(self):
        logger.info("Maestro Deputy v1.0 starting...")
        logger.info(f"Database: {self.db.db_path}")
        logger.info(f"Tick interval: {Config.TICK_INTERVAL}s")

        try:
            while True:
                self.tick()
                time.sleep(Config.TICK_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Shutting down gracefully...")
            self._save_intent()


# ───────────────────────────────────────────────────────────────────────────────
# CLI ENTRY POINT
# ───────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Maestro Deputy")
    parser.add_argument("--once", action="store_true", help="Run one tick and exit")
    parser.add_argument("--status", action="store_true", help="Print status and exit")
    parser.add_argument("--init", action="store_true", help="Initialize database and exit")
    parser.add_argument("--learning-receipt", action="store_true",
                        help="Print and send the weekly learning receipt now, then exit")
    args = parser.parse_args()

    if args.learning_receipt:
        m = Maestro()
        text = m._learning_receipt_text()
        print(text)
        ok = m.bridge.send(text, Priority.P2, dedup_key="learning-receipt")
        print(f"delivered: {ok}")
        sys.exit(0 if ok else 1)

    if args.init:
        db = ExperienceGraph(Config.DB_PATH)
        print(f"Initialized: {db.db_path}")
        sys.exit(0)

    if args.status:
        db = ExperienceGraph(Config.DB_PATH)
        stats = db.get_stats()
        print(json.dumps(stats, indent=2))
        sys.exit(0)

    maestro = Maestro()

    if args.once:
        # One tick is one state transition, so a single call stopped at SENSE and
        # proved nothing. A dry run drives the machine until it comes back to IDLE.
        for _ in range(20):
            maestro.tick()
            if maestro.state == State.IDLE:
                break
        else:
            logger.warning("Dry run did not return to IDLE within 20 transitions")
            sys.exit(1)
    else:
        maestro.run()
