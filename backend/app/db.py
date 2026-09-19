import sqlite3
import os
import json
import datetime
from typing import Optional, List, Dict, Any

_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ip_sakti.db")


def get_conn():
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            query TEXT NOT NULL,
            jurisdiction TEXT,
            category TEXT,
            confidence REAL,
            abstained INTEGER,
            sources_json TEXT
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            query TEXT NOT NULL,
            answer_id TEXT,
            rating INTEGER NOT NULL,
            comment TEXT
        );

        CREATE TABLE IF NOT EXISTS escalation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            query TEXT NOT NULL,
            product_category TEXT,
            jurisdiction TEXT,
            relevant_ip_area TEXT,
            retrieved_sources TEXT,
            contact_email TEXT,
            status TEXT DEFAULT 'open'
        );
        """
    )
    conn.commit()
    conn.close()


def log_audit(query: str, jurisdiction: str, category: str, confidence: float,
              abstained: bool, sources: List[Dict[str, Any]]):
    conn = get_conn()
    conn.execute(
        "INSERT INTO audit_log (timestamp, query, jurisdiction, category, confidence, abstained, sources_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.datetime.utcnow().isoformat(),
            query, jurisdiction, category, confidence, int(abstained),
            json.dumps([s.get("id") for s in sources]),
        ),
    )
    conn.commit()
    conn.close()


def log_feedback(query: str, answer_id: Optional[str], rating: int, comment: Optional[str]):
    conn = get_conn()
    conn.execute(
        "INSERT INTO feedback (timestamp, query, answer_id, rating, comment) VALUES (?, ?, ?, ?, ?)",
        (datetime.datetime.utcnow().isoformat(), query, answer_id, rating, comment),
    )
    conn.commit()
    conn.close()


def log_escalation(query: str, product_category: Optional[str], jurisdiction: Optional[str],
                    relevant_ip_area: Optional[List[str]], retrieved_sources: Optional[List[str]],
                    contact_email: Optional[str]) -> int:
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO escalation (timestamp, query, product_category, jurisdiction, relevant_ip_area, "
        "retrieved_sources, contact_email) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            datetime.datetime.utcnow().isoformat(), query, product_category, jurisdiction,
            json.dumps(relevant_ip_area or []), json.dumps(retrieved_sources or []), contact_email,
        ),
    )
    conn.commit()
    escalation_id = cur.lastrowid
    conn.close()
    return escalation_id


def get_eval_summary() -> Dict[str, Any]:
    """Simple developer/admin evaluation panel data — real counts only, never fabricated."""
    conn = get_conn()
    total = conn.execute("SELECT COUNT(*) c FROM audit_log").fetchone()["c"]
    abstained = conn.execute("SELECT COUNT(*) c FROM audit_log WHERE abstained=1").fetchone()["c"]
    avg_conf_row = conn.execute("SELECT AVG(confidence) a FROM audit_log").fetchone()
    avg_conf = avg_conf_row["a"]
    conn.close()

    if total == 0:
        return {
            "total_queries": 0,
            "safe_abstention_rate": None,
            "average_confidence": None,
            "note": "Evaluation pending — no queries logged yet.",
        }

    return {
        "total_queries": total,
        "safe_abstention_rate": round(abstained / total, 2) if total else None,
        "average_confidence": round(avg_conf, 2) if avg_conf is not None else None,
        "note": (
            "Figures reflect real logged interactions in this session/database only. "
            "Answer accuracy, citation correctness and classification accuracy require "
            "manual review against the verified test set (see /backend/data/test_queries.json) "
            "and are not auto-computed in this prototype."
        ),
    }
