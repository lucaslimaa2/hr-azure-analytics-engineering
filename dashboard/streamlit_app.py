"""HR analytics dashboard.

Reads the curated employee snapshots LIVE from the Synapse serverless SQL pool
(the `dbo.curated_employees_all` serving view) as a read-only login, and renders the
monthly headcount / churn / compensation story.

The serving view consolidates every `curated/{yyyy}/{MM}` partition, so new months
appear automatically as the pipeline writes them — no re-export, no snapshot to refresh.

Local dev:
    1. Copy .streamlit/secrets.toml.example -> .streamlit/secrets.toml and fill it in.
    2. streamlit run dashboard/streamlit_app.py

Streamlit Community Cloud:
    Paste the same keys into the app's Settings -> Secrets. No code change needed.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import pymssql
import streamlit as st

st.set_page_config(page_title="HR Analytics", page_icon=":bar_chart:", layout="wide")


@st.cache_resource
def _conn():
    """One read-only connection per session, reused across queries."""
    return pymssql.connect(
        server=st.secrets["SQL_SERVER"],
        user=st.secrets["SQL_USER"],
        password=st.secrets["SQL_PASSWORD"],
        database=st.secrets.get("SQL_DATABASE", "hr_curated"),
        login_timeout=30,
        timeout=120,
    )


@st.cache_data(ttl=3600)  # one-hour cache; the pipeline writes at most monthly
def load() -> pd.DataFrame:
    cur = _conn().cursor(as_dict=True)
    cur.execute(
        """
        SELECT snapshot_year, snapshot_month, reference_date, employee_id,
               department, job_title, employment_type, gender,
               salary, tenure_months, age, location
        FROM dbo.curated_employees_all
        """
    )
    df = pd.DataFrame(cur.fetchall())
    cur.close()
    df["reference_date"] = pd.to_datetime(df["reference_date"])
    df["month"] = df["reference_date"].dt.strftime("%Y-%m")
    return df


df = load()
months = sorted(df["month"].unique())
latest = months[-1]

# ─── month-over-month movement: headcount, hires, leavers, churn ────────────
ids = {m: set(df.loc[df["month"] == m, "employee_id"]) for m in months}
movement_rows = []
for i, m in enumerate(months):
    cur_ids = ids[m]
    if i == 0:
        hires, leavers, churn = len(cur_ids), 0, None
    else:
        prev_ids = ids[months[i - 1]]
        hires = len(cur_ids - prev_ids)
        leavers = len(prev_ids - cur_ids)
        churn = leavers / len(prev_ids) if prev_ids else None
    movement_rows.append(
        {"month": m, "headcount": len(cur_ids), "hires": hires, "leavers": leavers, "churn_rate": churn}
    )
movement = pd.DataFrame(movement_rows)

# ─── header ─────────────────────────────────────────────────────────────────
st.title("HR Analytics")
st.caption(
    "Live monthly headcount snapshots from the Azure lakehouse, read from the "
    "`curated_employees_all` serving view on the Synapse serverless SQL pool. Each month "
    "is a full-roster snapshot; the same employee recurs across months, so headcount, "
    "hires, leavers, churn, and retention are all derived from how the roster changes."
)
st.divider()

# ─── KPI strip (latest month) ───────────────────────────────────────────────
last = movement.iloc[-1]
snap_latest = df[df["month"] == latest]
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Headcount", f"{int(last['headcount']):,}")
k2.metric("New hires", f"{int(last['hires']):,}", help=f"first appearing in {latest}")
k3.metric("Leavers", f"{int(last['leavers']):,}", help=f"present the prior month, gone in {latest}")
k4.metric("Avg salary", f"R$ {snap_latest['salary'].mean():,.0f}")
k5.metric("Avg tenure", f"{snap_latest['tenure_months'].mean():.0f} mo")
st.divider()

# ─── headcount + movement ───────────────────────────────────────────────────
col1, col2 = st.columns(2)
with col1:
    st.subheader("Headcount by month")
    fig = px.area(movement, x="month", y="headcount", markers=True)
    fig.update_layout(height=340, margin=dict(l=20, r=20, t=10, b=20))
    st.plotly_chart(fig, use_container_width=True)
with col2:
    st.subheader("Hires vs leavers")
    mv = movement.melt(id_vars="month", value_vars=["hires", "leavers"], var_name="kind", value_name="count")
    fig = px.bar(mv, x="month", y="count", color="kind", barmode="group")
    fig.update_layout(height=340, margin=dict(l=20, r=20, t=10, b=20), legend_title="")
    st.plotly_chart(fig, use_container_width=True)

# ─── churn + retention ──────────────────────────────────────────────────────
col3, col4 = st.columns(2)
with col3:
    st.subheader("Monthly churn rate")
    cr = movement.dropna(subset=["churn_rate"])
    fig = px.line(cr, x="month", y="churn_rate", markers=True)
    fig.update_layout(height=320, margin=dict(l=20, r=20, t=10, b=20), yaxis_tickformat=".1%")
    st.plotly_chart(fig, use_container_width=True)
with col4:
    st.subheader(f"Retention of the {months[0]} cohort")
    cohort = ids[months[0]]
    ret = pd.DataFrame([{"month": m, "retained": len(cohort & ids[m]) / len(cohort)} for m in months])
    fig = px.line(ret, x="month", y="retained", markers=True)
    fig.update_layout(height=320, margin=dict(l=20, r=20, t=10, b=20), yaxis_tickformat=".0%")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# ─── composition + compensation (as of a chosen month) ──────────────────────
sel = st.selectbox("As-of month", months, index=len(months) - 1)
snap = df[df["month"] == sel]

col5, col6 = st.columns(2)
with col5:
    st.subheader(f"Department headcount — {sel}")
    dept = snap.groupby("department", as_index=False)["employee_id"].nunique()
    dept.columns = ["department", "headcount"]
    fig = px.bar(dept.sort_values("headcount"), x="headcount", y="department", orientation="h")
    fig.update_layout(height=380, margin=dict(l=20, r=20, t=10, b=20))
    st.plotly_chart(fig, use_container_width=True)
with col6:
    st.subheader(f"Salary distribution — {sel}")
    fig = px.histogram(snap, x="salary", nbins=30)
    fig.update_layout(height=380, margin=dict(l=20, r=20, t=10, b=20), yaxis_title="employees")
    st.plotly_chart(fig, use_container_width=True)

col7, col8 = st.columns(2)
with col7:
    st.subheader(f"Avg salary by department — {sel}")
    sal = snap.groupby("department", as_index=False)["salary"].mean()
    fig = px.bar(sal.sort_values("salary"), x="salary", y="department", orientation="h")
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=10, b=20))
    st.plotly_chart(fig, use_container_width=True)
with col8:
    st.subheader(f"Employment type — {sel}")
    et = snap.groupby("employment_type", as_index=False)["employee_id"].nunique()
    et.columns = ["employment_type", "count"]
    fig = px.pie(et, names="employment_type", values="count", hole=0.5)
    fig.update_layout(height=360, margin=dict(l=20, r=20, t=10, b=20))
    st.plotly_chart(fig, use_container_width=True)

st.divider()
st.caption(
    "Source: Azure ADLS curated parquet, read live through the serverless SQL serving view "
    "(`curated_employees_all`) as a read-only login. Display rollups are computed over the "
    "already-clean snapshot rows."
)
