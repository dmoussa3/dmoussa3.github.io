from __future__ import annotations

import os
import re
import json
import sqlite3
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, jsonify, render_template, request
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ──────────────────────────────────────────────────────────────────────────────
# Config DB and OpenAI
# ──────────────────────────────────────────────────────────────────────────────

MODEL_ID = "gpt-4o-mini-2024-07-18"
DB_PATH = os.getenv("DANIEL_KB_DB", "daniel_kb.db")
PORT = int(os.getenv("PORT", "5001"))

# IMPORTANT: do not hardcode keys
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("Missing OPENAI_API_KEY env var. Refusing to start.")

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_ROUTER = (
    "You are a routing component for a Q&A assistant about Daniel Moussa.\n"
    "Given a user question and a list of DB categories, select the best category "
    "and propose 2-5 short search queries suitable for SQLite FTS.\n"
    "Return ONLY valid JSON with keys: category, search_queries.\n"
    "category must be one of the provided categories OR 'Unknown'.\n"
)

SYSTEM_ANSWER = (
    "You are a public-facing Q&A assistant for Daniel Moussa.\n"
    "CRITICAL RULES:\n"
    "1) Use ONLY the provided local knowledge-base entries as your source of truth.\n"
    "2) If the KB does not contain the requested info, say so plainly.\n"
    "3) Do not invent facts. Do not guess.\n"
    "4) Be clear and helpful.\n"
)

# ──────────────────────────────────────────────────────────────────────────────
# DB schema (SQLite + FTS5)
# ──────────────────────────────────────────────────────────────────────────────

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL UNIQUE,
  description TEXT
);

CREATE TABLE IF NOT EXISTS qa (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  category_id INTEGER NOT NULL,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  tags TEXT DEFAULT '',
  is_public INTEGER NOT NULL DEFAULT 1,
  updated_at TEXT DEFAULT (datetime('now')),
  FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE CASCADE
);

CREATE VIRTUAL TABLE IF NOT EXISTS qa_fts USING fts5(
  question,
  answer,
  tags,
  content='qa',
  content_rowid='id',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER IF NOT EXISTS qa_ai AFTER INSERT ON qa BEGIN
  INSERT INTO qa_fts(rowid, question, answer, tags)
  VALUES (new.id, new.question, new.answer, new.tags);
END;

CREATE TRIGGER IF NOT EXISTS qa_ad AFTER DELETE ON qa BEGIN
  INSERT INTO qa_fts(qa_fts, rowid, question, answer, tags)
  VALUES ('delete', old.id, old.question, old.answer, old.tags);
END;

CREATE TRIGGER IF NOT EXISTS qa_au AFTER UPDATE ON qa BEGIN
  INSERT INTO qa_fts(qa_fts, rowid, question, answer, tags)
  VALUES ('delete', old.id, old.question, old.answer, old.tags);
  INSERT INTO qa_fts(rowid, question, answer, tags)
  VALUES (new.id, new.question, new.answer, new.tags);
END;
"""

SEED: Dict[str, List[Tuple[str, str, str]]] = {
    "Bio & Overview": [
        (
            "Who is Daniel Moussa?",
            "Daniel Moussa is a software engineer and data scientist working to make new technology impactful, and also accessible to users of all backgrounds and demographics. His background spans web development, data analytics, to even psychology.",
            "bio,overview,engineer,data science,psychology,Daniel Moussa bio,Daniel Moussa overview",
        ),
        (
            "What is Daniel's educational background?",
            "Daniel holds a Bachelor of Science in Computer Science from Rutgers University, along with a minor in Psychology.",
            "education,computer science,Rutgers University,psychology minor,Daniel Moussa education, Daniel Moussa background, Daniel Moussa academic history",
        ),
        (
            "What was Daniel's role at Brunswick Medical Associates?",
            "Daniel served as an IT Consultant at Brunswick Medical Associates, where he led the transition of the clinic into a secure digital database to keep client records and coordinated with staff and clients to ensure smooth adoption of new technology.",
            "Daniel Moussa IT Consultant,Daniel Moussa Brunswick Medical Associates,clinic,digital database,technology adoption,Daniel Moussa role,Daniel Moussa position",
        ),
    ],
    "Projects & Platforms": [
        (
            "How has Daniel contributed to his platforms?",
            "Daniel has used experience in designing web applications, from Django to React to Streamlit, to make impactful and user-friendly platforms that make technology and data more accessible and easier to comprehend for almost any user.",
            "contributed,contributions,Daniel Moussa platforms,Daniel Moussa contributions",
        ),
        (
            "What projects has Daniel worked on?",
            "Daniel has worked on a variety of projects including a Reddit sentiment analysis tool, a todo app, and a data analysis explorer.",
            "Daniel Moussa projects,data analysis explorer,Daniel Moussa worked on",
        ),
        (
            "What does the Reddit Sentiment Analysis project do?",
            "The Reddit Sentiment Analysis project is a web application that analyzes the sentiment of posts in specific subreddits. It provides visual representations of sentiment trends and keeps track of previous searches for user convenience in a MongoDB database.",
            "reddit,sentiment analysis,web application,visualization,database",
        ),
        (
            "What does the To-do App project do?",
            "The To-do App is a real-time collaborative task management tool that allows users to create, share, and manage tasks with reminders and notifications to enhance productivity.",
            "to-do app,todo app,task management,collaboration,productivity,reminders,notifications",
        ),        
    ],
    "Focus Areas": [
        (
            "What areas does Daniel focus on?",
            "Core focus areas include Machine Learning & Data Science, Web Development, Data Engineering & Analytics, and User-friendly interactive programming.",
            "Daniel Moussa skills,Daniel Moussa focus areas,web development,data engineering,user-friendly programming",
        ),
        (
            "What technologies does Daniel use?",
            "Daniel utilizes a range of technologies including Python, Pandas, NumPy, Streamlit, Django, HTML/CSS, Java, JavaScript, React, Flask, and SQL in his projects.",
            "Daniel Moussa technologies,python,pandas,numpy,streamlit,django,html,css,java,javascript,react,flask,sql,Daniel Moussa uses, Daniel Moussa tech stack",
        ),
        (
            "What is Daniel's core mission?",
            "Daniel focuses on building platforms that help people get the most out of today's technology, such as through looking at modern day data in new ways, and better build up to the future of technology. With a background in IT consulting, web development, and data science, Daniel aims to bridge the gap between complex technology and user-friendly applications.",
            "Daniel Moussa mission,data,engineering,Daniel Moussa core, Daniel Moussa core mission",
        ),
    ],
    "Contact & Links": [
        (
            "How can I contact Daniel?",
            "Email: danielmoussa1203@gmail.com. LinkedIn: www.linkedin.com/in/daniel-moussa3. GitHub/Portfolio: github.com/dmoussa3.",
            "Daniel Moussa contact information,Daniel Moussa email,Daniel Moussa portfolio,Daniel Moussa github, reach out to Daniel Moussa, connect Daniel Moussa, contact Daniel Moussa",
        ),
        (
            "Where is Daniel based?",
            "Daniel is based in New Jersey, and is open to working globally.",
            "Daniel Moussa location,Daniel Moussa new jersey,Daniel Moussa global",
        ),
    ],
}

def _db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db() -> None:
    with _db_connect() as conn:
        conn.executescript(SCHEMA_SQL)
        conn.commit()

    # seed if empty
    with _db_connect() as conn:
        n = conn.execute("SELECT COUNT(1) AS n FROM qa").fetchone()["n"]
        if n == 0:
            for cat, rows in SEED.items():
                conn.execute(
                    "INSERT OR IGNORE INTO categories(name, description) VALUES (?, ?)",
                    (cat, f"Q&A about {cat}"),
                )
            conn.commit()

            for cat, rows in SEED.items():
                cat_id = conn.execute("SELECT id FROM categories WHERE name = ?", (cat,)).fetchone()["id"]
                for q, a, tags in rows:
                    conn.execute(
                        "INSERT INTO qa(category_id, question, answer, tags, is_public) VALUES (?, ?, ?, ?, 1)",
                        (cat_id, q, a, tags),
                    )
            conn.commit()

def list_categories() -> List[str]:
    with _db_connect() as conn:
        rows = conn.execute("SELECT name FROM categories ORDER BY name").fetchall()
    return [r["name"] for r in rows]

def normalize(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"\s+", " ", s)
    return s

@dataclass
class Hit:
    qa_id: int
    category: str
    question: str
    answer: str
    tags: str
    score: float

def fts_search(query: str, limit: int = 6, category: Optional[str] = None) -> List[Hit]:
    q = normalize(query)
    if not q:
        return []

    with _db_connect() as conn:
        params: List[Any] = [q]
        where_cat = ""
        if category:
            where_cat = "AND c.name = ?"
            params.append(category)

        sql = f"""
            SELECT
              qa.id AS qa_id,
              c.name AS category,
              qa.question,
              qa.answer,
              qa.tags,
              bm25(qa_fts, 2.0, 1.0, 0.5) AS score
            FROM qa_fts
            JOIN qa ON qa_fts.rowid = qa.id
            JOIN categories c ON c.id = qa.category_id
            WHERE qa_fts MATCH ?
              AND qa.is_public = 1
              {where_cat}
            ORDER BY score ASC
            LIMIT {int(limit)}
        """
        rows = conn.execute(sql, params).fetchall()

    return [
        Hit(
            qa_id=int(r["qa_id"]),
            category=str(r["category"]),
            question=str(r["question"]),
            answer=str(r["answer"]),
            tags=str(r["tags"] or ""),
            score=float(r["score"]),
        )
        for r in rows
    ]

# ──────────────────────────────────────────────────────────────────────────────
# OpenAI calls (ONLY gpt-4o-mini-2024-07-18)
# ──────────────────────────────────────────────────────────────────────────────

def _extract_json_obj(text: str) -> Dict[str, Any]:
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if m:
        text = m.group(0)
    return json.loads(text)

def _llm(system: str, user: str, temperature: float = 0.2, max_tokens: int = 900) -> str:
    resp = client.chat.completions.create(
        model=MODEL_ID,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        top_p=0.9,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()

def route_question(question: str, categories: List[str]) -> Dict[str, Any]:
    payload = {"categories": categories, "question": question}
    out = _llm(SYSTEM_ROUTER, json.dumps(payload, ensure_ascii=False), temperature=0.0, max_tokens=350)
    data = _extract_json_obj(out)

    cat = data.get("category")
    if cat not in categories:
        cat = "Unknown"

    sq = data.get("search_queries") or []
    sq = [normalize(x)[:120] for x in sq if normalize(x)]
    if not sq:
        sq = [normalize(question)[:120]]

    return {"category": cat, "search_queries": sq}

def answer_from_hits(question: str, hits: List[Hit]) -> str:
    if not hits:
        return (
            "I don’t have that in the local database yet. "
            "Add a Q&A entry for it and I’ll answer it consistently from the KB."
        )

    kb_entries = [
        {
            "category": h.category,
            "stored_question": h.question,
            "stored_answer": h.answer,
            "tags": h.tags,
        }
        for h in hits[:6]
    ]

    payload = {"question": question, "kb_entries": kb_entries}
    return _llm(SYSTEM_ANSWER, json.dumps(payload, ensure_ascii=False), temperature=0.2, max_tokens=850)

def query_kb(question: str) -> Tuple[str, Dict[str, Any]]:
    categories = list_categories()
    route = route_question(question, categories)

    collected: List[Hit] = []

    cat = route["category"]
    for sq in route["search_queries"]:
        collected.extend(fts_search(sq, limit=6, category=None if cat == "Unknown" else cat))

    if not collected:
        for sq in route["search_queries"]:
            collected.extend(fts_search(sq, limit=6, category=None))

    best: Dict[int, Hit] = {}
    for h in collected:
        if h.qa_id not in best or h.score < best[h.qa_id].score:
            best[h.qa_id] = h
    hits = sorted(best.values(), key=lambda x: x.score)[:6]

    answer = answer_from_hits(question, hits)
    debug = {
        "route": route,
        "hits": [{"id": h.qa_id, "category": h.category, "score": h.score, "q": h.question, "tags": h.tags} for h in hits],
    }
    return answer, debug

# ──────────────────────────────────────────────────────────────────────────────
# Minimal KB write API (optional, protect in production)
# ──────────────────────────────────────────────────────────────────────────────

def _upsert_category(conn: sqlite3.Connection, name: str, description: str = "") -> int:
    conn.execute("INSERT OR IGNORE INTO categories(name, description) VALUES (?, ?)", (name, description))
    row = conn.execute("SELECT id FROM categories WHERE name = ?", (name,)).fetchone()
    return int(row["id"])

def add_qa(category: str, question: str, answer: str, tags: str = "", is_public: int = 1) -> int:
    with _db_connect() as conn:
        cat_id = _upsert_category(conn, category, f"Q&A about {category}")
        cur = conn.execute(
            "INSERT INTO qa(category_id, question, answer, tags, is_public) VALUES (?, ?, ?, ?, ?)",
            (cat_id, question, answer, tags, int(is_public)),
        )
        conn.commit()

        if cur.lastrowid is None:
            raise RuntimeError("Failed to insert QA entry")
        return int(cur.lastrowid)

# ──────────────────────────────────────────────────────────────────────────────
# Flask app
# ──────────────────────────────────────────────────────────────────────────────

app = Flask(__name__, static_folder='.', static_url_path='')

@app.route("/")
def home():
    return app.send_static_file('index.html')

@app.route("/profile")
def profile():
    profile_data = {
        'name': 'Daniel Moussa',
        'title': 'Software Engineer',
        'bio': 'Passionate developer with years of experience building web applications and working in data science.',
        'email': 'danielmoussa1203@gmail.com',
        'github': 'https://github.com/dmoussa3',
        'linkedin': 'https://linkedin.com/in/daniel-moussa3',
        'image': 'prof.jpeg',
        
        'skills': [
            'Python',
            'Pandas',
            'NumPy',
            'Streamlit',
            'Django',
            'HTML/CSS',
            'Java',
            'JavaScript',
            'React',
            'Flask',
            'SQL'
        ],
        
        'projects': [
            {
                'title': 'Reddit Sentiment Analysis',
                'description': 'Subreddit sentiment analysis web app with visual representations and keeps track of previous searches',
                'tech': ['Python Streamlit', 'Pandas', 'Matplotlib'],
                'image': 'reddit_logo.png',
                'link': 'https://github.com/dmoussa3/reddit'
            },
            {
                'title': 'To-do App',
                'description': 'Real-time collaborative task management tool with reminders and notifications',
                'tech': ['React', 'Node.js', 'MongoDB'],
                'image': 'To-do.png',
                'link': 'https://github.com/dmoussa3/todo-app'
            },
            {
                'title': 'Database Analysis Explorer 📊',
                'description': 'Interactive app used to look over large datasets, uploaded by the user, with data visualization',
                'tech': ['Python Streamlit', 'Matplotlib', 'Seaborn'],
                'link': 'https://github.com/dmoussa3/explorer'
            }
        ],
        
        'experience': [
            {
                'title': 'IT Consultant',
                'company': 'Brunswick Medical Associates',
                'period': 'May 2021 - September 2021',
                'description': 'Led the transition of the clinic into a secure digital database to keep client records and coordinated with staff and clients to ensure smooth adoption of new technology.'
            }
        ]
    }
    
    return render_template('../templates/profile.html', profile=profile_data)

@app.route("/api/ask", methods=["POST"])
def api_ask():
    data = request.get_json(silent=True) or {}
    question = normalize(data.get("question") or "")
    debug_flag = bool(data.get("debug", False))
    if not question:
        return jsonify({"ok": False, "error": "question is required"}), 400

    try:
        answer, debug = query_kb(question)
        resp = {"ok": True, "answer": answer}
        if debug_flag:
            resp["debug"] = debug
        return jsonify(resp)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/kb/add", methods=["POST"])
def api_kb_add():
    """
    Add knowledge base entries.
    Optional protection: set KB_ADMIN_TOKEN and send header X-Admin-Token.
    """
    token_required = os.getenv("KB_ADMIN_TOKEN", "")
    if token_required:
        got = request.headers.get("X-Admin-Token", "")
        if got != token_required:
            return jsonify({"ok": False, "error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    category = normalize(data.get("category") or "")
    question = normalize(data.get("question") or "")
    answer = normalize(data.get("answer") or "")
    tags = normalize(data.get("tags") or "")
    is_public = int(bool(data.get("is_public", True)))

    if not (category and question and answer):
        return jsonify({"ok": False, "error": "category, question, answer are required"}), 400

    try:
        qa_id = add_qa(category, question, answer, tags=tags, is_public=is_public)
        return jsonify({"ok": True, "id": qa_id})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/kb/categories", methods=["GET"])
def api_kb_categories():
    try:
        return jsonify({"ok": True, "categories": list_categories()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    init_db()
    app.run(debug=True, host="0.0.0.0", port=PORT)
