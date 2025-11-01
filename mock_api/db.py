import sqlite3
import os
from typing import List, Dict, Any
import csv

DB_PATH = os.path.join(os.path.dirname(__file__), 'data.db')
CSV_PATH = os.path.join(os.path.dirname(__file__), '..', 'fake_users.csv')


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('''
    CREATE TABLE IF NOT EXISTS users (
        dn TEXT PRIMARY KEY,
        cn TEXT,
        sAMAccountName TEXT,
        uidNumber INTEGER,
        gidNumber INTEGER,
        memberOf TEXT,
        mail TEXT,
        sn TEXT,
        givenName TEXT,
        telephoneNumber TEXT,
        accountExpires TEXT,
        lockoutTime TEXT,
        userAccountControl INTEGER
    )
    ''')
    conn.commit()

    # seed from CSV if table empty
    cur.execute('SELECT COUNT(*) as c FROM users')
    row = cur.fetchone()
    if row and row['c'] == 0:
        if os.path.exists(CSV_PATH):
            with open(CSV_PATH, newline='') as f:
                reader = csv.DictReader(f)
                to_insert = []
                for r in reader:
                    to_insert.append(
                        (
                            r.get('dn',''),
                            r.get('cn',''),
                            r.get('sAMAccountName',''),
                            int(r.get('uidNumber') or 0),
                            int(r.get('gidNumber') or 0),
                            r.get('memberOf',''),
                            r.get('mail',''),
                            r.get('sn',''),
                            r.get('givenName',''),
                            r.get('telephoneNumber',''),
                            r.get('accountExpires',''),
                            r.get('lockoutTime',''),
                            int(r.get('userAccountControl') or 0),
                        )
                    )
            cur.executemany('''INSERT OR IGNORE INTO users (dn,cn,sAMAccountName,uidNumber,gidNumber,memberOf,mail,sn,givenName,telephoneNumber,accountExpires,lockoutTime,userAccountControl)
                               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', to_insert)
            conn.commit()
    conn.close()


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = {k: row[k] for k in row.keys()}
    mof = d.get('memberOf') or ''
    d['memberOf'] = [g.strip() for g in mof.split(';') if g.strip()]
    return d


def get_all_users() -> List[Dict[str, Any]]:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users')
    rows = cur.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


def find_users_by_kv(key: str, val: str) -> List[Dict[str, Any]]:
    # validate key
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('PRAGMA table_info(users)')
    cols = [r['name'] for r in cur.fetchall()]
    if key not in cols:
        # try case-insensitive match
        key_map = {c.lower(): c for c in cols}
        key = key_map.get(key.lower(), key)
    if key not in cols:
        conn.close()
        return []
    q = f"SELECT * FROM users WHERE lower({key}) = lower(?)"
    cur.execute(q, (val,))
    rows = cur.fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


def get_user_by_sAMAccountName(name: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE lower(sAMAccountName)=lower(?)', (name,))
    row = cur.fetchone()
    conn.close()
    return row_to_dict(row) if row else None


def create_user(payload: Dict[str, Any]) -> Dict[str, Any]:
    conn = get_conn()
    cur = conn.cursor()
    memberOf = payload.get('memberOf')
    if isinstance(memberOf, (list, tuple)):
        mof = ';'.join(memberOf)
    else:
        mof = memberOf or ''
    cur.execute('''INSERT OR REPLACE INTO users (dn,cn,sAMAccountName,uidNumber,gidNumber,memberOf,mail,sn,givenName,telephoneNumber,accountExpires,lockoutTime,userAccountControl)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
        payload.get('dn',''),
        payload.get('cn',''),
        payload.get('sAMAccountName',''),
        int(payload.get('uidNumber') or 0),
        int(payload.get('gidNumber') or 0),
        mof,
        payload.get('mail',''),
        payload.get('sn',''),
        payload.get('givenName',''),
        payload.get('telephoneNumber',''),
        payload.get('accountExpires',''),
        payload.get('lockoutTime',''),
        int(payload.get('userAccountControl') or 0),
    ))
    conn.commit()
    conn.close()
    return payload
