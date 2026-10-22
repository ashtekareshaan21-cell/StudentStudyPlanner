# analytics.py
# Data Exploration & Visualization layer for SmartStudyPlanner.
#
# This module is the DEVL (Data Exploration and Visualization Lab) core of
# the project: it loads a student's study sessions and quiz results from the
# database into pandas DataFrames, cleans and explores them (summary
# statistics, group-by aggregations, correlations), renders matplotlib
# charts on the server, and turns the numbers into plain-language insights.
#
# Pipeline:  SQL database -> pandas DataFrame -> cleaning -> EDA
#            -> matplotlib figures -> insights for the /analytics page.

import base64
import os
from io import BytesIO

# On Vercel the filesystem is read-only outside /tmp; matplotlib needs a
# writable config/cache directory before it is imported.
os.environ.setdefault("MPLCONFIGDIR", "/tmp/matplotlib")

import matplotlib

matplotlib.use("Agg")  # headless backend: no display on a server
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from models import QuizResult, StudySession, db

PRIMARY = "#6366F1"  # matches --primary in static/style.css
GREEN = "#10B981"
AMBER = "#F59E0B"
RED = "#EF4444"
GREY = "#94A3B8"

plt.rcParams.update(
    {
        "axes.edgecolor": "#CBD5E1",
        "axes.labelcolor": "#334155",
        "xtick.color": "#64748B",
        "ytick.color": "#64748B",
        "text.color": "#334155",
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "font.size": 9,
    }
)


# ---------------------------------------------------------------------------
# 1. DATA LOADING & CLEANING  (database -> DataFrame)
# ---------------------------------------------------------------------------
def load_frames(user_id):
    """Load one user's sessions and quiz results as cleaned DataFrames."""
    sessions_stmt = (
        StudySession.query.filter_by(user_id=user_id)
        .order_by(StudySession.session_date.asc())
        .statement
    )
    quiz_stmt = (
        QuizResult.query.filter_by(user_id=user_id)
        .order_by(QuizResult.created_at.asc())
        .statement
    )
    sessions = pd.read_sql_query(sessions_stmt, db.engine)
    quizzes = pd.read_sql_query(quiz_stmt, db.engine)

    # --- cleaning: sessions ---
    if not sessions.empty:
        sessions["session_date"] = pd.to_datetime(
            sessions["session_date"], errors="coerce", utc=True
        )
        for col in ("mood", "study_hours", "sleep_hours", "productivity_score"):
            sessions[col] = pd.to_numeric(sessions[col], errors="coerce")
        sessions = sessions.dropna(
            subset=["session_date", "study_hours", "productivity_score"]
        )

    # --- cleaning: quizzes ---
    if not quizzes.empty:
        quizzes["created_at"] = pd.to_datetime(
            quizzes["created_at"], errors="coerce", utc=True
        )
        quizzes["score"] = pd.to_numeric(quizzes["score"], errors="coerce")
        quizzes["total_questions"] = pd.to_numeric(
            quizzes["total_questions"], errors="coerce"
        )
        quizzes = quizzes.dropna(subset=["created_at", "score", "total_questions"])
        quizzes = quizzes[quizzes["total_questions"] > 0]
        # normalise raw marks to a percentage so quizzes are comparable
        quizzes["score_pct"] = quizzes["score"] / quizzes["total_questions"] * 100

    return sessions, quizzes


# ---------------------------------------------------------------------------
# 2. EXPLORATION  (summary statistics & aggregations)
# ---------------------------------------------------------------------------
def _describe_rows(df, columns):
    """Return df.describe() for `columns` as template-friendly rows."""
    if df.empty:
        return []
    desc = df[columns].describe().round(2)
    labels = {
        "count": "Count",
        "mean": "Mean",
        "std": "Std dev",
        "min": "Min",
        "25%": "25th percentile",
        "50%": "Median",
        "75%": "75th percentile",
        "max": "Max",
    }
    rows = []
    for stat, label in labels.items():
        if stat in desc.index:
            rows.append(
                {
                    "label": label,
                    "values": [desc.loc[stat, c] for c in columns],
                }
            )
    return rows


def subject_breakdown(sessions):
    """Study hours per subject (a session's hours are split equally across
    the subjects it lists) — a pandas explode + groupby aggregation."""
    if sessions.empty:
        return []
    exploded = sessions.assign(
        subject=sessions["subjects"].fillna("General").str.split(";")
    ).explode("subject")
    exploded["subject"] = exploded["subject"].str.strip()
    exploded = exploded[exploded["subject"] != ""]
    # split each session's hours equally across the subjects that session
    # lists (count of subjects per session, NOT per subject)
    subjects_per_session = exploded.groupby("id")["subject"].transform("size")
    exploded = exploded.assign(
        share_hours=exploded["study_hours"] / subjects_per_session
    )
    grouped = (
        exploded.groupby("subject")
        .agg(sessions=("study_hours", "size"), hours=("share_hours", "sum"))
        .reset_index()
        .sort_values("hours", ascending=False)
    )
    return [
        {
            "subject": r.subject,
            "sessions": int(r.sessions),
            "hours": round(float(r.hours), 1),
        }
        for r in grouped.itertuples()
    ]


def topic_breakdown(quizzes):
    """Quiz attempts and average score per topic — groupby aggregation."""
    if quizzes.empty:
        return []
    grouped = (
        quizzes.groupby("topics")
        .agg(
            attempts=("score_pct", "size"),
            avg_pct=("score_pct", "mean"),
            best_pct=("score_pct", "max"),
        )
        .reset_index()
        .sort_values("attempts", ascending=False)
    )
    return [
        {
            "topic": r.topics,
            "attempts": int(r.attempts),
            "avg_pct": round(float(r.avg_pct), 1),
            "best_pct": round(float(r.best_pct), 1),
        }
        for r in grouped.itertuples()
    ]


# ---------------------------------------------------------------------------
# 3. VISUALIZATION  (matplotlib figures -> base64 PNG for the template)
# ---------------------------------------------------------------------------
def _fig_to_base64(fig):
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def chart_score_trend(quizzes):
    """Quiz score % over time with a rolling-average trend line."""
    if len(quizzes) < 2:
        return None
    q = quizzes.sort_values("created_at")
    rolling = q["score_pct"].rolling(window=3, min_periods=1).mean()
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    ax.plot(
        q["created_at"],
        q["score_pct"],
        marker="o",
        color=PRIMARY,
        linewidth=1.6,
        label="Quiz score %",
    )
    ax.plot(
        q["created_at"],
        rolling,
        color=AMBER,
        linewidth=2.2,
        label="Rolling average (3 quizzes)",
    )
    ax.set_ylim(0, 105)
    ax.set_ylabel("Score (%)")
    ax.set_title("Quiz performance over time")
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False, loc="lower right")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    fig.autofmt_xdate(rotation=30)
    return _fig_to_base64(fig)


def chart_score_histogram(quizzes):
    """Distribution of quiz scores — a classic EDA histogram."""
    if len(quizzes) < 3:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    ax.hist(
        quizzes["score_pct"],
        bins=np.arange(0, 101, 10),
        color=PRIMARY,
        edgecolor="white",
        alpha=0.9,
    )
    ax.axvline(
        quizzes["score_pct"].mean(),
        color=RED,
        linestyle="--",
        linewidth=1.6,
        label=f"Mean = {quizzes['score_pct'].mean():.1f}%",
    )
    ax.set_xlim(0, 100)
    ax.set_xlabel("Score (%)")
    ax.set_ylabel("Number of quizzes")
    ax.set_title("Distribution of quiz scores")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(frameon=False)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return _fig_to_base64(fig)


def chart_activity_heatmap(sessions):
    """Pivot-table heatmap: total study hours by weekday x hour of day."""
    if len(sessions) < 3:
        return None
    s = sessions.copy()
    s["weekday"] = s["session_date"].dt.day_name().str[:3]
    s["hour"] = s["session_date"].dt.hour
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    pivot = (
        s.pivot_table(
            index="weekday", columns="hour", values="study_hours",
            aggfunc="sum", fill_value=0,
        )
        .reindex(days)
        .fillna(0)
    )
    if pivot.to_numpy().sum() == 0:
        return None
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    im = ax.imshow(pivot.to_numpy(), cmap="Purples", aspect="auto")
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index)
    ax.set_xlabel("Hour of day (UTC, when the session was logged)")
    ax.set_title("When do you study? Total hours by weekday and hour")
    fig.colorbar(im, ax=ax, shrink=0.9, label="Study hours")
    return _fig_to_base64(fig)


def chart_mood_productivity(sessions):
    """Scatter: mood vs productivity, numpy trend line, Pearson r."""
    if len(sessions) < 3 or sessions["mood"].nunique() < 2:
        return None
    rng = np.random.default_rng(7)  # fixed seed: stable jitter between loads
    x = sessions["mood"].to_numpy(dtype=float) + rng.normal(0, 0.09, len(sessions))
    y = sessions["productivity_score"].to_numpy(dtype=float)
    r = float(sessions["mood"].corr(sessions["productivity_score"]))
    fig, ax = plt.subplots(figsize=(7.2, 3.1))
    ax.scatter(x, y, color=PRIMARY, alpha=0.75, edgecolor="white", s=55)
    slope, intercept = np.polyfit(
        sessions["mood"].to_numpy(dtype=float), y, 1
    )
    xs = np.array([sessions["mood"].min(), sessions["mood"].max()], dtype=float)
    ax.plot(xs, slope * xs + intercept, color=RED, linewidth=1.8,
            label=f"Trend (Pearson r = {r:.2f})")
    ax.set_xlabel("Mood (1 = low, 5 = great)")
    ax.set_ylabel("Productivity score")
    ax.set_title("Does mood predict productivity?")
    ax.grid(True, alpha=0.3)
    ax.legend(frameon=False, loc="lower right")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    return _fig_to_base64(fig)


# ---------------------------------------------------------------------------
# 4. INSIGHTS  (plain-language findings computed from the data)
# ---------------------------------------------------------------------------
def build_insights(sessions, quizzes):
    insights = []

    if len(sessions) >= 4:
        rested = sessions[sessions["sleep_hours"] >= 7]["productivity_score"]
        tired = sessions[sessions["sleep_hours"] < 7]["productivity_score"]
        if len(rested) >= 2 and len(tired) >= 2:
            diff = rested.mean() - tired.mean()
            insights.append(
                {
                    "icon": "😴",
                    "text": (
                        f"After 7+ hours of sleep your average productivity is "
                        f"{rested.mean():.0f}% vs {tired.mean():.0f}% on less "
                        f"sleep — a {abs(diff):.0f}-point "
                        f"{'boost' if diff >= 0 else 'drop'}."
                    ),
                }
            )

    if len(sessions) >= 3 and sessions["mood"].nunique() >= 2:
        r = sessions["mood"].corr(sessions["productivity_score"])
        if pd.notna(r):
            strength = (
                "strong" if abs(r) >= 0.6 else "moderate" if abs(r) >= 0.35
                else "weak"
            )
            direction = "higher" if r > 0 else "lower"
            insights.append(
                {
                    "icon": "🙂",
                    "text": (
                        f"Mood and productivity show a {strength} correlation "
                        f"(r = {r:.2f}) — on better-mood days you tend to be "
                        f"{direction} in productivity."
                    ),
                }
            )

    if len(sessions) >= 4:
        s = sessions.copy()
        s["weekday"] = s["session_date"].dt.day_name()
        by_day = s.groupby("weekday")["productivity_score"].mean()
        if len(by_day) >= 2:
            insights.append(
                {
                    "icon": "📅",
                    "text": (
                        f"{by_day.idxmax()} is your most productive day of "
                        f"the week (average {by_day.max():.0f}% productivity)."
                    ),
                }
            )

    if len(quizzes) >= 4:
        q = quizzes.sort_values("created_at")
        half = len(q) // 2
        early = q["score_pct"].iloc[:half].mean()
        recent = q["score_pct"].iloc[half:].mean()
        change = recent - early
        insights.append(
            {
                "icon": "📈" if change >= 0 else "📉",
                "text": (
                    f"Your recent quizzes average {recent:.0f}% vs "
                    f"{early:.0f}% in your earlier ones — "
                    f"{'an improvement' if change >= 0 else 'a dip'} of "
                    f"{abs(change):.0f} points."
                ),
            }
        )

    subjects = subject_breakdown(sessions)
    if subjects:
        top = subjects[0]
        insights.append(
            {
                "icon": "📚",
                "text": (
                    f"{top['subject']} is your most-studied subject so far "
                    f"with {top['hours']} hours across {top['sessions']} "
                    f"sessions."
                ),
            }
        )

    return insights[:4]


# ---------------------------------------------------------------------------
# Orchestrator used by the /analytics route
# ---------------------------------------------------------------------------
def build_analytics(user_id):
    sessions, quizzes = load_frames(user_id)

    overview = {
        "total_sessions": int(len(sessions)),
        "total_study_hours": round(float(sessions["study_hours"].sum()), 1)
        if not sessions.empty
        else 0.0,
        "avg_productivity": round(
            float(sessions["productivity_score"].mean()), 1
        )
        if not sessions.empty
        else 0.0,
        "quizzes_taken": int(len(quizzes)),
        "avg_quiz_pct": round(float(quizzes["score_pct"].mean()), 1)
        if not quizzes.empty
        else 0.0,
    }

    return {
        "overview": overview,
        "has_sessions": not sessions.empty,
        "has_quizzes": not quizzes.empty,
        "session_describe_columns": [
            "study_hours",
            "sleep_hours",
            "mood",
            "productivity_score",
        ],
        "session_describe": _describe_rows(
            sessions,
            ["study_hours", "sleep_hours", "mood", "productivity_score"],
        ),
        "quiz_describe_columns": ["score_pct"],
        "quiz_describe": _describe_rows(quizzes, ["score_pct"]),
        "subjects": subject_breakdown(sessions),
        "topics": topic_breakdown(quizzes),
        "insights": build_insights(sessions, quizzes),
        "chart_trend": chart_score_trend(quizzes),
        "chart_histogram": chart_score_histogram(quizzes),
        "chart_heatmap": chart_activity_heatmap(sessions),
        "chart_scatter": chart_mood_productivity(sessions),
    }
