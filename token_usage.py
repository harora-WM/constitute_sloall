"""
Token Usage Dashboard — tracks LLM token consumption from metrics.llm_token_usage.
Standalone Streamlit app; does NOT require the FastAPI backend to be running.

Run:
    streamlit run token_usage.py
"""

import sys
import os
from datetime import date, datetime, timedelta

import altair as alt
import pandas as pd
import requests
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

# ── Page config ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Token Usage Dashboard",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
    /* Backgrounds */
    .stApp,
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    section.main { background-color: #ffffff; }

    [data-testid="stSidebar"] { background-color: #f4f6f8; }

    /* Base text */
    html, body, [class*="css"],
    .stMarkdown, .stText, p, span, label,
    [data-testid="stMarkdownContainer"] p { color: #1a1a2e; }

    /* Headings */
    h1, h2, h3, h4, h5, h6 { color: #0f0f23; }

    /* Metric cards */
    [data-testid="stMetric"] {
        background-color: #f4f6f8;
        border: 1px solid #e0e4ea;
        border-radius: 10px;
        padding: 16px;
    }
    [data-testid="stMetricLabel"] > div { color: #2d3748 !important; font-size: 0.85rem; }
    [data-testid="stMetricValue"]       { color: #0f0f23 !important; }
    [data-testid="stMetricDelta"] svg   { display: none; }
    [data-testid="stMetricDelta"] > div { color: #2d3748 !important; font-size: 0.8rem; }

    /* Containers with border */
    [data-testid="stVerticalBlockBorderWrapper"] > div {
        background-color: #f4f6f8;
        border: 1px solid #e0e4ea !important;
        border-radius: 10px;
    }

    /* Form inputs */
    .stRadio label, .stDateInput label { color: #1a1a2e !important; }
    .stRadio > div > label > div > p   { color: #1a1a2e !important; }

    /* Buttons */
    .stFormSubmitButton button[kind="secondaryFormSubmit"] {
        background-color: #e0e4ea;
        color: #1a1a2e;
        border: 1px solid #c8cdd6;
        border-radius: 6px;
    }
    .stFormSubmitButton button[kind="primaryFormSubmit"] {
        background-color: #4f6ef7;
        color: #ffffff;
        border: none;
        border-radius: 6px;
    }

    /* Divider */
    hr { border-color: #e0e4ea; }

    /* Caption */
    .stCaption, [data-testid="stCaptionContainer"] { color: #3d4a5c !important; }

    /* Dataframe */
    [data-testid="stDataFrame"] { border: 1px solid #e0e4ea; border-radius: 8px; }

    /* Spinner */
    .stSpinner > div { color: #4f6ef7; }

    /* Info / error / warning boxes */
    .stAlert { border-radius: 8px; }

    /* Utilization table */
    .util-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.875rem;
        color: #1a1a2e;
    }
    .util-table thead tr {
        background-color: #f4f6f8;
        border-bottom: 2px solid #e0e4ea;
    }
    .util-table th {
        padding: 10px 14px;
        text-align: left;
        font-weight: 600;
        color: #2d3748;
        white-space: nowrap;
    }
    .util-table td {
        padding: 10px 14px;
        border-bottom: 1px solid #f0f2f5;
        vertical-align: top;
    }
    .util-table tbody tr:hover { background-color: #f8f9fc; }
    .task-name  { font-weight: 600; color: #1a1a2e; }
    .task-id    { font-size: 0.72rem; color: #6b7280; font-family: monospace; margin-top: 2px; }
    .badge      { display: inline-block; padding: 2px 10px; border-radius: 12px;
                  font-size: 0.75rem; font-weight: 600; }
    .badge-completed { background: #d1fae5; color: #065f46; }
    .badge-failed    { background: #fee2e2; color: #991b1b; }
    .num-cell   { text-align: right; font-variant-numeric: tabular-nums; }

    /* ── Request Log table ── */
    .log-table { width: 100%; font-size: 0.875rem; color: #1a1a2e; }
    .log-header {
        display: grid;
        grid-template-columns: 2fr 1.1fr 2fr 3fr 2.5fr 1.6fr 1.5fr 0.4fr;
        padding: 10px 14px;
        background: #f4f6f8;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.8rem;
        color: #2d3748;
        margin-bottom: 2px;
    }
    details.log-row { border-bottom: 1px solid #f0f2f5; }
    details.log-row > summary {
        display: grid;
        grid-template-columns: 2fr 1.1fr 2fr 3fr 2.5fr 1.6fr 1.5fr 0.4fr;
        padding: 10px 14px;
        list-style: none;
        cursor: pointer;
        color: #1a1a2e;
        align-items: center;
    }
    details.log-row > summary::-webkit-details-marker { display: none; }
    details.log-row > summary:hover { background: #f8f9fc; border-radius: 4px; }
    .task-col   { display: flex; flex-direction: column; gap: 1px; }
    .task-main  { font-weight: 500; }
    .task-sub   { font-size: 0.72rem; color: #6b7280; font-family: monospace; }
    .mono-sm    { font-family: monospace; font-size: 0.8rem; color: #374151; }
    .log-badge  { display: inline-block; padding: 2px 10px; border-radius: 12px;
                  font-size: 0.75rem; font-weight: 600; }
    .log-badge-completed { background: #d1fae5; color: #065f46; }
    .log-badge-failed    { background: #fee2e2; color: #991b1b; }
    .chevron-icon {
        font-size: 1.1rem; color: #9ca3af; text-align: center;
        display: inline-block; transition: transform 0.18s ease;
    }
    details.log-row[open] .chevron-icon { transform: rotate(90deg); }
    .detail-panel {
        padding: 16px 24px;
        background: #fafbfc;
        border-top: 1px solid #f0f2f5;
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 14px 32px;
        margin-bottom: 2px;
    }
    .dl  { display: flex; flex-direction: column; gap: 3px; }
    .dk  { font-size: 0.7rem; color: #6b7280; font-weight: 600;
           text-transform: uppercase; letter-spacing: 0.05em; }
    .dv  { font-size: 0.875rem; color: #1a1a2e; font-family: monospace; word-break: break-all; }
</style>
""", unsafe_allow_html=True)

st.title("Token Usage Dashboard")
st.caption("LLM token consumption across all pipeline runs.")

# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt(n: float) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return f"{int(n):,}"


def _ch(sql: str) -> list[dict]:
    resp = requests.post(
        config.CLICKHOUSE_URL,
        params={"query": sql + " FORMAT JSON"},
        auth=(config.CLICKHOUSE_USERNAME, config.CLICKHOUSE_PASSWORD),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])


def _where(start: str, end: str) -> str:
    return (
        f"event_date >= toDate('{start}') AND event_date <= toDate('{end}') "
        f"AND started_at >= '{start}' AND started_at < '{end}'"
    )


# ── Data fetchers ──────────────────────────────────────────────────────────────

def fetch_overview(start: str, end: str) -> dict:
    rows = _ch(f"""
        SELECT count() AS total_requests, sum(total_tokens) AS total_tokens,
               sum(input_tokens) AS total_input, sum(output_tokens) AS total_output,
               avg(input_tokens) AS avg_input,   avg(output_tokens) AS avg_output
        FROM metrics.llm_token_usage WHERE {_where(start, end)}
    """)
    return {k: float(v) if v is not None else 0.0 for k, v in rows[0].items()} if rows else {}


def fetch_tokens_over_time(start: str, end: str) -> pd.DataFrame:
    rows = _ch(f"""
        SELECT toDate(started_at) AS day,
               sum(total_tokens) AS total_tokens, sum(input_tokens) AS input_tokens,
               sum(output_tokens) AS output_tokens
        FROM metrics.llm_token_usage WHERE {_where(start, end)}
        GROUP BY day ORDER BY day
    """)
    if not rows:
        return pd.DataFrame(columns=["day", "total_tokens", "input_tokens", "output_tokens"])
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["day"])
    for c in ["total_tokens", "input_tokens", "output_tokens"]:
        df[c] = pd.to_numeric(df[c])
    return df


def fetch_requests_over_time(start: str, end: str) -> pd.DataFrame:
    rows = _ch(f"""
        SELECT toDate(started_at) AS day, count() AS total,
               countIf(had_error = 0) AS successful, countIf(had_error = 1) AS failed
        FROM metrics.llm_token_usage WHERE {_where(start, end)}
        GROUP BY day ORDER BY day
    """)
    if not rows:
        return pd.DataFrame(columns=["day", "total", "successful", "failed"])
    df = pd.DataFrame(rows)
    df["day"] = pd.to_datetime(df["day"])
    for c in ["total", "successful", "failed"]:
        df[c] = pd.to_numeric(df[c])
    return df


def fetch_distribution(start: str, end: str) -> pd.DataFrame:
    rows = _ch(f"""
        SELECT project_name, sum(input_tokens) AS input_tokens,
               sum(output_tokens) AS output_tokens, sum(total_tokens) AS total_tokens,
               count() AS total_requests
        FROM metrics.llm_token_usage WHERE {_where(start, end)}
        GROUP BY project_name ORDER BY total_tokens DESC
    """)
    if not rows:
        return pd.DataFrame(columns=["project_name", "input_tokens", "output_tokens", "total_tokens", "total_requests"])
    df = pd.DataFrame(rows)
    for c in ["input_tokens", "output_tokens", "total_tokens", "total_requests"]:
        df[c] = pd.to_numeric(df[c])
    return df


def fetch_utilization(start: str, end: str) -> pd.DataFrame:
    rows = _ch(f"""
        SELECT task_name, task_id, project_name, username,
               started_at, completed_at, input_tokens, output_tokens,
               task_status, count() OVER () AS total_requests
        FROM metrics.llm_token_usage WHERE {_where(start, end)}
        ORDER BY started_at DESC
        LIMIT 500
    """)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for c in ["input_tokens", "output_tokens", "total_requests"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c])
    return df


def fetch_request_log(start: str, end: str) -> pd.DataFrame:
    rows = _ch(f"""
        SELECT task_id, batch_id, run_id, task_name, model_name,
               input_tokens, output_tokens, total_tokens,
               duration_ms, task_status, error_type,
               started_at, completed_at, project_name, app_id, project_id, username
        FROM metrics.llm_token_usage
        WHERE {_where(start, end)}
        ORDER BY started_at DESC
        LIMIT 200
    """)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    for c in ["input_tokens", "output_tokens", "total_tokens", "duration_ms"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


# ── Session state init ─────────────────────────────────────────────────────────

ss = st.session_state
if "applied_label" not in ss:
    ss.applied_label = "Last 7 days"
    ss.applied_start = date.today() - timedelta(days=7)
    ss.applied_end   = date.today()

# ── Time range filter (shared across all tabs) ─────────────────────────────────

with st.container(border=True):
    with st.form("time_filter", border=False):
        c1, c2, c3, _, c4, c5 = st.columns([3.5, 1.8, 1.8, 0.8, 0.9, 0.9])
        with c1:
            label = st.radio(
                "Time range",
                ["Last 7 days", "Last 30 days", "Custom"],
                index=["Last 7 days", "Last 30 days", "Custom"].index(ss.applied_label),
                horizontal=True,
            )
        with c2:
            custom_start = st.date_input("Start date", value=ss.applied_start, max_value=date.today())
        with c3:
            custom_end   = st.date_input("End date",   value=ss.applied_end,   max_value=date.today())
        st.caption("Start / End date are used only when **Custom** is selected.")
        with c4:
            st.form_submit_button("Cancel", use_container_width=True)
        with c5:
            applied = st.form_submit_button("Apply", type="primary", use_container_width=True)

    if applied:
        if label == "Last 7 days":
            ss.applied_start = date.today() - timedelta(days=7)
            ss.applied_end   = date.today()
        elif label == "Last 30 days":
            ss.applied_start = date.today() - timedelta(days=30)
            ss.applied_end   = date.today()
        else:
            if custom_start > custom_end:
                st.warning("Start date must be before end date — range not applied.")
                label = ss.applied_label
            else:
                ss.applied_start = custom_start
                ss.applied_end   = custom_end
        ss.applied_label = label
        st.rerun()

# ── Active date range ──────────────────────────────────────────────────────────

start_str = ss.applied_start.strftime("%Y-%m-%d")
end_str   = (ss.applied_end + timedelta(days=1)).strftime("%Y-%m-%d")

st.markdown(
    f"**Showing:** {ss.applied_label}  ·  "
    f"`{ss.applied_start.strftime('%d %b %Y')}` → `{ss.applied_end.strftime('%d %b %Y')}`"
)
st.divider()

# ── Tabs ───────────────────────────────────────────────────────────────────────

tab1, tab2, tab3 = st.tabs(["Overview", "Utilization Report", "Request Log"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Overview
# ══════════════════════════════════════════════════════════════════════════════

with tab1:
    with st.spinner("Loading..."):
        try:
            overview  = fetch_overview(start_str, end_str)
            df_tokens = fetch_tokens_over_time(start_str, end_str)
            df_reqs   = fetch_requests_over_time(start_str, end_str)
            df_dist   = fetch_distribution(start_str, end_str)
        except Exception as e:
            st.error(f"Failed to fetch data from ClickHouse: {e}")
            st.stop()

    has_data = bool(overview) and overview.get("total_requests", 0) > 0

    # Metrics
    st.subheader("Overview")
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric("Total Requests", _fmt(overview.get("total_requests", 0)) if has_data else "0")
    with m2:
        st.metric("Total Tokens", _fmt(overview.get("total_tokens", 0)) if has_data else "0")
    with m3:
        avg_in = overview.get("avg_input", 0) if has_data else 0
        st.metric("Input Tokens",  _fmt(overview.get("total_input",  0)) if has_data else "0",
                  delta=f"Avg {_fmt(avg_in)} / req", delta_color="off")
    with m4:
        avg_out = overview.get("avg_output", 0) if has_data else 0
        st.metric("Output Tokens", _fmt(overview.get("total_output", 0)) if has_data else "0",
                  delta=f"Avg {_fmt(avg_out)} / req", delta_color="off")

    st.divider()

    color_scale = alt.Scale(domain=["Total Tokens","Input (Prompt)","Output (Completion)"],
                            range=["#636efa","#ff7f0e","#2ca02c"])
    req_scale   = alt.Scale(domain=["Total","Successful","Failed"],
                            range=["#636efa","#00cc96","#ef553b"])
    dist_scale  = alt.Scale(domain=["Input (Prompt)","Output (Completion)"],
                            range=["#ff7f0e","#2ca02c"])

    left, right = st.columns(2)

    with left:
        st.subheader("Total Tokens Over Time")
        if not has_data or df_tokens.empty:
            empty = pd.DataFrame({"day": pd.Series(dtype="datetime64[ns]"),
                                   "tokens": pd.Series(dtype="float"),
                                   "Metric": pd.Series(dtype="str")})
            st.altair_chart(
                alt.Chart(empty).mark_line().encode(
                    x=alt.X("day:T", title="Date"),
                    y=alt.Y("tokens:Q", title="Tokens"),
                    color=alt.Color("Metric:N", scale=color_scale, legend=alt.Legend(orient="bottom")),
                ).properties(height=360), use_container_width=True)
        else:
            df_m = df_tokens.melt(id_vars=["day"],
                                   value_vars=["total_tokens","input_tokens","output_tokens"],
                                   var_name="metric", value_name="tokens")
            df_m["Metric"] = df_m["metric"].map({
                "total_tokens":"Total Tokens","input_tokens":"Input (Prompt)","output_tokens":"Output (Completion)"})
            base   = alt.Chart(df_m).encode(
                x=alt.X("day:T", title="Date", axis=alt.Axis(format="%b %d", labelAngle=-30)),
                color=alt.Color("Metric:N", scale=color_scale, legend=alt.Legend(orient="bottom")))
            chart  = (base.mark_line(strokeWidth=2) + base.mark_point(size=70, filled=True)).encode(
                y=alt.Y("tokens:Q", title="Tokens"),
                tooltip=[alt.Tooltip("day:T",title="Date",format="%Y-%m-%d"),
                         alt.Tooltip("Metric:N",title="Metric"),
                         alt.Tooltip("tokens:Q",title="Tokens",format=",")],
            ).properties(height=360).interactive()
            st.altair_chart(chart, use_container_width=True)

    with right:
        st.subheader("Total Requests Over Time")
        if not has_data or df_reqs.empty:
            empty = pd.DataFrame({"day": pd.Series(dtype="datetime64[ns]"),
                                   "count": pd.Series(dtype="float"),
                                   "Status": pd.Series(dtype="str")})
            st.altair_chart(
                alt.Chart(empty).mark_bar().encode(
                    x=alt.X("day:T", title="Date"),
                    y=alt.Y("count:Q", title="Requests"),
                    color=alt.Color("Status:N", scale=req_scale, legend=alt.Legend(orient="bottom")),
                ).properties(height=360), use_container_width=True)
        else:
            df_m = df_reqs.melt(id_vars=["day"], value_vars=["total","successful","failed"],
                                 var_name="status", value_name="count")
            df_m["Status"] = df_m["status"].map({"total":"Total","successful":"Successful","failed":"Failed"})
            chart = alt.Chart(df_m).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("day:T", title="Date", axis=alt.Axis(format="%b %d", labelAngle=-30)),
                y=alt.Y("count:Q", title="Requests"),
                color=alt.Color("Status:N", scale=req_scale, legend=alt.Legend(orient="bottom")),
                xOffset="Status:N",
                tooltip=[alt.Tooltip("day:T",title="Date",format="%Y-%m-%d"),
                         alt.Tooltip("Status:N",title="Status"),
                         alt.Tooltip("count:Q",title="Requests")],
            ).properties(height=360).interactive()
            st.altair_chart(chart, use_container_width=True)

    st.divider()
    st.subheader("Token Distribution by Project")

    if not has_data or df_dist.empty:
        chart_col, table_col = st.columns([2, 1])
        with chart_col:
            empty = pd.DataFrame({"project_name": pd.Series(dtype="str"),
                                   "tokens": pd.Series(dtype="float"),
                                   "Token Type": pd.Series(dtype="str")})
            st.altair_chart(
                alt.Chart(empty).mark_bar().encode(
                    x=alt.X("project_name:N", title="Project"),
                    y=alt.Y("tokens:Q", title="Total Tokens"),
                    color=alt.Color("Token Type:N", scale=dist_scale, legend=alt.Legend(orient="bottom")),
                ).properties(height=300), use_container_width=True)
        with table_col:
            st.markdown("**Summary**")
            st.dataframe(pd.DataFrame(columns=["Project","Requests","Total Tokens","Input Tokens","Output Tokens"]),
                         hide_index=True, use_container_width=True)
    else:
        chart_col, table_col = st.columns([2, 1])
        with chart_col:
            df_m = df_dist.melt(id_vars=["project_name"], value_vars=["input_tokens","output_tokens"],
                                 var_name="token_type", value_name="tokens")
            df_m["Token Type"] = df_m["token_type"].map(
                {"input_tokens":"Input (Prompt)","output_tokens":"Output (Completion)"})
            chart = alt.Chart(df_m).mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
                x=alt.X("project_name:N", title="Project", axis=alt.Axis(labelAngle=0)),
                y=alt.Y("tokens:Q", title="Total Tokens"),
                color=alt.Color("Token Type:N", scale=dist_scale, legend=alt.Legend(orient="bottom")),
                xOffset="Token Type:N",
                tooltip=[alt.Tooltip("project_name:N",title="Project"),
                         alt.Tooltip("Token Type:N",title="Type"),
                         alt.Tooltip("tokens:Q",title="Tokens",format=",")],
            ).properties(height=300).interactive()
            st.altair_chart(chart, use_container_width=True)
        with table_col:
            st.markdown("**Summary**")
            disp = df_dist.rename(columns={
                "project_name":"Project","total_requests":"Requests",
                "total_tokens":"Total Tokens","input_tokens":"Input Tokens","output_tokens":"Output Tokens",
            })[["Project","Requests","Total Tokens","Input Tokens","Output Tokens"]]
            for col in ["Total Tokens","Input Tokens","Output Tokens"]:
                disp[col] = disp[col].apply(_fmt)
            st.dataframe(disp, hide_index=True, use_container_width=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Utilization Report
# ══════════════════════════════════════════════════════════════════════════════

with tab2:
    with st.spinner("Loading..."):
        try:
            df_util = fetch_utilization(start_str, end_str)
        except Exception as e:
            st.error(f"Failed to fetch utilization data: {e}")
            df_util = pd.DataFrame()

    # ── Inline filters ─────────────────────────────────────────────────────────
    fa, fb, fc = st.columns([3, 2, 2])
    with fa:
        search = st.text_input("Search task", placeholder="Filter by task name…", label_visibility="collapsed")
    with fb:
        status_filter = st.selectbox("Status", ["All", "completed", "failed"], label_visibility="collapsed")
    with fc:
        st.caption(f"Showing up to 500 rows · period: "
                   f"{ss.applied_start.strftime('%d %b %Y')} → {ss.applied_end.strftime('%d %b %Y')}")

    # ── Apply filters ──────────────────────────────────────────────────────────
    if not df_util.empty:
        if search:
            df_util = df_util[df_util["task_name"].str.contains(search, case=False, na=False)]
        if status_filter != "All":
            df_util = df_util[df_util["task_status"] == status_filter]

    st.divider()

    # ── Render table ───────────────────────────────────────────────────────────
    if df_util.empty:
        st.info("No records found for the selected period / filters.")
    else:
        def _dt(val) -> str:
            if not val or str(val) in ("None", "nan", "NaT"):
                return "—"
            try:
                return str(val)[:19].replace("T", " ")
            except Exception:
                return str(val)

        rows_html = ""
        for _, row in df_util.iterrows():
            badge_cls = "badge-completed" if row["task_status"] == "completed" else "badge-failed"
            tid = str(row["task_id"])
            tid_short = tid[:8] + "…" + tid[-4:] if len(tid) > 12 else tid

            rows_html += f"""
            <tr>
                <td>
                    <div class="task-name">{row['task_name']}</div>
                    <div class="task-id">{tid_short}</div>
                </td>
                <td>{row.get('project_name') or '—'}</td>
                <td>{row.get('username') or '—'}</td>
                <td>{_dt(row.get('started_at'))}</td>
                <td>{_dt(row.get('completed_at'))}</td>
                <td class="num-cell">{int(row['input_tokens']):,}</td>
                <td class="num-cell">{int(row['output_tokens']):,}</td>
                <td><span class="badge {badge_cls}">{row['task_status']}</span></td>
                <td class="num-cell">1</td>
            </tr>"""

        table_html = f"""
        <table class="util-table">
            <thead>
                <tr>
                    <th>Task</th>
                    <th>Project</th>
                    <th>User</th>
                    <th>Started At</th>
                    <th>Completed At</th>
                    <th style="text-align:right">Input Tokens</th>
                    <th style="text-align:right">Output Tokens</th>
                    <th>Status</th>
                    <th style="text-align:right">Requests</th>
                </tr>
            </thead>
            <tbody>{rows_html}</tbody>
        </table>
        """
        st.markdown(table_html, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Request Log
# ══════════════════════════════════════════════════════════════════════════════

with tab3:
    with st.spinner("Loading..."):
        try:
            df_log = fetch_request_log(start_str, end_str)
        except Exception as e:
            st.error(f"Failed to fetch request log: {e}")
            df_log = pd.DataFrame()

    # ── Inline filters ─────────────────────────────────────────────────────────
    fa, fb, fc = st.columns([3, 2, 2])
    with fa:
        log_search = st.text_input(
            "Search task", placeholder="Filter by task name…",
            label_visibility="collapsed", key="log_search",
        )
    with fb:
        log_status = st.selectbox(
            "Status", ["All", "completed", "failed"],
            label_visibility="collapsed", key="log_status",
        )
    with fc:
        st.caption(
            f"Showing up to 200 rows · "
            f"{ss.applied_start.strftime('%d %b %Y')} → {ss.applied_end.strftime('%d %b %Y')}"
        )

    # ── Apply filters ──────────────────────────────────────────────────────────
    if not df_log.empty:
        if log_search:
            df_log = df_log[df_log["task_name"].str.contains(log_search, case=False, na=False)]
        if log_status != "All":
            df_log = df_log[df_log["task_status"] == log_status]

    st.divider()

    if df_log.empty:
        st.info("No records found for the selected period / filters.")
    else:
        def _esc(s: object) -> str:
            return (
                str(s)
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
            )

        def _fmt_dt(s: object) -> str:
            val = str(s)[:19]
            try:
                return datetime.strptime(val, "%Y-%m-%d %H:%M:%S").strftime("%d %b %Y, %H:%M:%S")
            except Exception:
                return val or "—"

        def _trunc(s: str, n: int = 18) -> str:
            return s[:n] + "…" if len(s) > n else s

        rows_html = ""
        for _, row in df_log.iterrows():
            started   = _fmt_dt(row.get("started_at", ""))
            completed = _fmt_dt(row.get("completed_at", ""))
            status    = str(row.get("task_status", "")).lower()
            status_cls   = "completed" if status == "completed" else "failed"
            status_label = status.title()

            batch_id = str(row.get("batch_id", ""))
            task_id  = str(row.get("task_id",  ""))
            task_name = _esc(str(row.get("task_name", "")))

            model       = str(row.get("model_name", "") or "—")
            model_short = model.split(".")[-1] if "." in model else model

            inp = int(row.get("input_tokens",  0))
            out = int(row.get("output_tokens", 0))
            tot = int(row.get("total_tokens",  0))

            dur_str  = f"{float(row.get('duration_ms', 0)) / 1000:.3f} s"
            entity   = f"{int(row.get('app_id', 0))} ({_esc(str(row.get('project_name', '—')))})"
            err_type = _esc(str(row.get("error_type", "") or "—"))

            rows_html += f"""
<details class="log-row">
  <summary>
    <span>{started}</span>
    <span><span class="log-badge log-badge-{status_cls}">{status_label}</span></span>
    <span class="mono-sm">{_trunc(batch_id)}</span>
    <span class="task-col">
      <span class="task-main">{task_name}</span>
      <span class="task-sub">{_trunc(task_id)}</span>
    </span>
    <span class="mono-sm">{_esc(_trunc(model_short, 24))}</span>
    <span>{tot} ({inp}+{out})</span>
    <span>{dur_str}</span>
    <span class="chevron-icon">&#8250;</span>
  </summary>
  <div class="detail-panel">
    <div class="dl"><span class="dk">Request ID</span><span class="dv">{_esc(batch_id)}</span></div>
    <div class="dl"><span class="dk">Task ID</span><span class="dv">{_esc(task_id)}</span></div>
    <div class="dl"><span class="dk">Task Name</span><span class="dv">{task_name}</span></div>
    <div class="dl"><span class="dk">Entity</span><span class="dv">{entity}</span></div>
    <div class="dl"><span class="dk">Model</span><span class="dv">{_esc(model)}</span></div>
    <div class="dl"><span class="dk">Error Type</span><span class="dv">{err_type}</span></div>
    <div class="dl"><span class="dk">Tokens</span><span class="dv">{tot} ({inp} prompt + {out} completion)</span></div>
    <div class="dl"><span class="dk">Status</span><span class="dv">{status_label}</span></div>
    <div class="dl"><span class="dk">Start Time</span><span class="dv">{started}</span></div>
    <div class="dl"><span class="dk">End Time</span><span class="dv">{completed}</span></div>
    <div class="dl"><span class="dk">Duration</span><span class="dv">{dur_str}</span></div>
  </div>
</details>"""

        st.markdown(f"""
<div class="log-table">
  <div class="log-header">
    <span>Time</span>
    <span>Status</span>
    <span>Run ID</span>
    <span>Task</span>
    <span>Model</span>
    <span>Tokens</span>
    <span>Duration</span>
    <span></span>
  </div>
  {rows_html}
</div>
""", unsafe_allow_html=True)
