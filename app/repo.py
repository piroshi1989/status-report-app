"""データアクセス層(SQLite)。すべて sqlite3.Connection を引数に取る."""

from __future__ import annotations

import sqlite3
from typing import Any, Optional

from .services.evaluation import CriterionRow


# --- patients --------------------------------------------------------------

def create_patient(conn: sqlite3.Connection, **f) -> int:
    cur = conn.execute(
        """INSERT INTO patients (code, name, sex, birth_date, pacemaker, note, med_info, is_active)
           VALUES (:code, :name, :sex, :birth_date, :pacemaker, :note, :med_info, 1)""",
        {
            "code": f["code"],
            "name": f.get("name", ""),
            "sex": f.get("sex"),
            "birth_date": f.get("birth_date"),
            "pacemaker": int(f.get("pacemaker") or 0),
            "note": f.get("note"),
            "med_info": f.get("med_info"),
        },
    )
    return cur.lastrowid


def update_patient(conn: sqlite3.Connection, pid: int, **f) -> None:
    conn.execute(
        """UPDATE patients SET name=:name, sex=:sex, birth_date=:birth_date,
                  pacemaker=:pacemaker, note=:note, med_info=:med_info,
                  updated_at=datetime('now','localtime')
           WHERE id=:id""",
        {
            "id": pid,
            "name": f.get("name", ""),
            "sex": f.get("sex"),
            "birth_date": f.get("birth_date"),
            "pacemaker": int(f.get("pacemaker") or 0),
            "note": f.get("note"),
            "med_info": f.get("med_info"),
        },
    )


def set_patient_active(conn: sqlite3.Connection, pid: int, active: bool) -> None:
    conn.execute("UPDATE patients SET is_active=? WHERE id=?", (1 if active else 0, pid))


def get_patient(conn: sqlite3.Connection, pid: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM patients WHERE id=?", (pid,)).fetchone()


def get_patient_by_code(conn: sqlite3.Connection, code: str) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM patients WHERE code=?", (str(code),)).fetchone()


def list_patients(conn: sqlite3.Connection, q: str = "", include_inactive: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM patients WHERE 1=1"
    params: list[Any] = []
    if not include_inactive:
        sql += " AND is_active=1"
    if q:
        sql += " AND (code LIKE ? OR name LIKE ?)"
        params += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY code"
    return conn.execute(sql, params).fetchall()


# --- measurement_sessions --------------------------------------------------

def create_session(conn: sqlite3.Connection, session_no, measured_on, source_file, note=None) -> int:
    cur = conn.execute(
        """INSERT INTO measurement_sessions (session_no, measured_on, source_file, note)
           VALUES (?,?,?,?)""",
        (session_no, measured_on, source_file, note),
    )
    return cur.lastrowid


def get_session(conn: sqlite3.Connection, sid: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM measurement_sessions WHERE id=?", (sid,)).fetchone()


def list_sessions(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM measurement_sessions ORDER BY COALESCE(measured_on,'') DESC, id DESC"
    ).fetchall()


def list_sessions_for_patient(conn: sqlite3.Connection, pid: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT s.* FROM measurement_sessions s
           JOIN measurements m ON m.session_id = s.id
           WHERE m.patient_id = ?
           GROUP BY s.id
           ORDER BY COALESCE(s.measured_on,'') DESC, s.id DESC""",
        (pid,),
    ).fetchall()


def patients_in_session(conn: sqlite3.Connection, sid: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT p.* FROM patients p
           JOIN measurements m ON m.patient_id = p.id
           WHERE m.session_id = ?
           GROUP BY p.id ORDER BY p.code""",
        (sid,),
    ).fetchall()


# --- measurements ----------------------------------------------------------

def upsert_measurement(conn, session_id, patient_id, item_id, value, raw_text) -> None:
    conn.execute(
        """INSERT INTO measurements (session_id, patient_id, item_id, value, raw_text)
           VALUES (?,?,?,?,?)
           ON CONFLICT(session_id, patient_id, item_id)
           DO UPDATE SET value=excluded.value, raw_text=excluded.raw_text""",
        (session_id, patient_id, item_id, value, raw_text),
    )


def get_measurements(conn, session_id, patient_id) -> dict[int, sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM measurements WHERE session_id=? AND patient_id=?",
        (session_id, patient_id),
    ).fetchall()
    return {r["item_id"]: r for r in rows}


# --- eval_items ------------------------------------------------------------

def list_items(conn, include_inactive: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM eval_items"
    if not include_inactive:
        sql += " WHERE is_active=1"
    sql += " ORDER BY sort_order, id"
    return conn.execute(sql).fetchall()


def get_item(conn, item_id) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM eval_items WHERE id=?", (item_id,)).fetchone()


def get_item_by_name(conn, name) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM eval_items WHERE name=?", (name,)).fetchone()


def create_item(conn, **f) -> int:
    cur = conn.execute(
        """INSERT INTO eval_items
           (name, unit, category, sort_order, direction, in_radar, source_column,
            derived_formula, is_qualitative, is_active)
           VALUES (:name,:unit,:category,:sort_order,:direction,:in_radar,:source_column,
                   :derived_formula,:is_qualitative,1)""",
        {
            "name": f["name"],
            "unit": f.get("unit"),
            "category": f.get("category"),
            "sort_order": int(f.get("sort_order") or 0),
            "direction": f.get("direction", "higher_better"),
            "in_radar": int(f.get("in_radar", 1)),
            "source_column": f.get("source_column"),
            "derived_formula": f.get("derived_formula"),
            "is_qualitative": int(f.get("is_qualitative", 0)),
        },
    )
    return cur.lastrowid


def update_item(conn, item_id, **f) -> None:
    conn.execute(
        """UPDATE eval_items SET name=:name, unit=:unit, category=:category,
                  sort_order=:sort_order, direction=:direction, in_radar=:in_radar,
                  source_column=:source_column, derived_formula=:derived_formula,
                  is_qualitative=:is_qualitative, is_active=:is_active
           WHERE id=:id""",
        {
            "id": item_id,
            "name": f["name"],
            "unit": f.get("unit"),
            "category": f.get("category"),
            "sort_order": int(f.get("sort_order") or 0),
            "direction": f.get("direction", "higher_better"),
            "in_radar": int(f.get("in_radar", 1)),
            "source_column": f.get("source_column"),
            "derived_formula": f.get("derived_formula"),
            "is_qualitative": int(f.get("is_qualitative", 0)),
            "is_active": int(f.get("is_active", 1)),
        },
    )


# --- eval_criteria ---------------------------------------------------------

def list_criteria_for_item(conn, item_id) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM eval_criteria WHERE item_id=? ORDER BY sex, age_band, pacemaker, threshold",
        (item_id,),
    ).fetchall()


def criterion_rows_for_item(conn, item_id) -> list[CriterionRow]:
    rows = conn.execute(
        "SELECT sex, age_band, pacemaker, threshold, score, comment FROM eval_criteria WHERE item_id=?",
        (item_id,),
    ).fetchall()
    return [
        CriterionRow(
            sex=r["sex"], age_band=r["age_band"],
            pacemaker=r["pacemaker"], threshold=r["threshold"],
            score=r["score"], comment=r["comment"],
        )
        for r in rows
    ]


def add_criterion(conn, item_id, sex, age_band, pacemaker, threshold, score, comment=None, description=None) -> int:
    cur = conn.execute(
        """INSERT INTO eval_criteria (item_id, sex, age_band, pacemaker, threshold, score, comment, description)
           VALUES (?,?,?,?,?,?,?,?)""",
        (item_id, sex, age_band, pacemaker, threshold, score, comment, description),
    )
    return cur.lastrowid


def delete_criteria_for_item(conn, item_id) -> None:
    conn.execute("DELETE FROM eval_criteria WHERE item_id=?", (item_id,))


def delete_criterion(conn, crit_id) -> None:
    conn.execute("DELETE FROM eval_criteria WHERE id=?", (crit_id,))


# --- column_aliases --------------------------------------------------------

def alias_map(conn) -> dict[str, int]:
    rows = conn.execute("SELECT alias, item_id FROM column_aliases").fetchall()
    return {r["alias"]: r["item_id"] for r in rows}


def add_alias(conn, alias, item_id) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO column_aliases (alias, item_id) VALUES (?,?)",
        (alias, item_id),
    )


# --- report_settings -------------------------------------------------------

def get_setting(conn, key, default=None) -> Optional[str]:
    row = conn.execute("SELECT value FROM report_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(conn, key, value) -> None:
    conn.execute(
        """INSERT INTO report_settings (key, value) VALUES (?,?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
        (key, value),
    )
