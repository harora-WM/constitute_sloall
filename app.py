"""
Streamlit UI for the Conversational SLO Manager.
Talks to the FastAPI backend running at http://localhost:8000.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config
import json
import requests
import streamlit as st
from datetime import datetime

API_URL = "http://localhost:8000"

# Maps internal data-source keys to user-facing display names
SOURCE_DISPLAY_NAMES = {
    "java_stats_api":    "Real-Time Service Metrics",
    "clickhouse":        "Historical Behavior Patterns",
    # "clickhouse_infra":  "Infrastructure Metrics",    # DISABLED
    # "alerts_count":      "Alert & Incident History",  # DISABLED
    "change_impact":     "Deployment & Change Impact",
    "postgres":          "SLO Definitions",
    "opensearch":        "Logs & Traces",
}

def source_label(key: str) -> str:
    return SOURCE_DISPLAY_NAMES.get(key, key.replace("_", " ").title())

def render_source_stat(source: str, data: dict) -> None:
    label = source_label(source)
    if "stats" in data:
        st.markdown(f"**{label} stats:**")
        st.json(data["stats"])
    elif "total_records" in data:
        st.markdown(f"**{label}:** `{data['total_records']}` records")
    elif "records" in data and isinstance(data["records"], list) and data["records"]:
        st.markdown(f"**{label}:** `{len(data['records'])}` records")

st.set_page_config(
    page_title="SLO Advisor",
    page_icon="📊",
    layout="wide",
)

st.title("📊 SLO Advisor")
st.caption("Ask anything about your service reliability in plain English.")

# ── Sidebar — connection & settings ───────────────────────────────────────────

with st.sidebar:
    st.header("Settings")
    api_base = st.text_input("API URL", value=API_URL)
    app_id = st.number_input("App ID", value=config.APP_ID, step=1)
    project_id = st.number_input("Project ID", value=config.PROJECT_ID, step=1)

    st.divider()
    st.subheader("Time Override")
    st.caption("Leave blank to auto-extract from query.")
    start_time_input = st.text_input("Start Time (Unix ms)", value="", placeholder="e.g. 1774432047000")
    end_time_input = st.text_input("End Time (Unix ms)", value="", placeholder="e.g. 1774518447000")

    st.divider()

    # Health check
    if st.button("Check backend health"):
        try:
            r = requests.get(f"{api_base}/health", timeout=5)
            if r.status_code == 200:
                h = r.json()
                st.success(f"Backend ready — {h['services_loaded']} services loaded")
            else:
                st.error(f"Backend returned {r.status_code}")
        except Exception as e:
            st.error(f"Cannot reach backend: {e}")

    st.divider()
    if st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()

# ── Chat history ──────────────────────────────────────────────────────────────

if "messages" not in st.session_state:
    st.session_state.messages = []

# Render existing messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("technical"):
            with st.expander("Technical details"):
                _t = msg["technical"]

                col1, col2 = st.columns(2)
                with col1:
                    st.markdown(f"**Primary intent:** `{_t.get('primary_intent')}`")
                    enriched = _t.get("enriched_intents", [])
                    if enriched:
                        st.markdown("**Enriched intents:** " + ", ".join(f"`{i}`" for i in enriched))

                with col2:
                    tr = _t.get("time_resolution", {})
                    if tr.get("start_time"):
                        start = datetime.fromtimestamp(tr["start_time"] / 1000).strftime("%Y-%m-%d %H:%M")
                        end   = datetime.fromtimestamp(tr["end_time"]   / 1000).strftime("%Y-%m-%d %H:%M")
                        eff   = tr.get("effective_time_range")
                        if eff:
                            st.markdown(f"**Time range:** {eff} ({start} → {end})")
                        else:
                            st.markdown(f"**Time range:** {start} → {end}")
                        st.markdown(f"**Index:** `{tr.get('index')}`")

                sources = _t.get("data_sources_used", [])
                if sources:
                    st.markdown("**Data sources used:** " + ", ".join(f"`{source_label(s)}`" for s in sources))

                # Per-source stats
                for source, data in _t.get("data", {}).items():
                    if isinstance(data, dict):
                        render_source_stat(source, data)

# ── Input ─────────────────────────────────────────────────────────────────────

query = st.chat_input("e.g. How is my application performing in the last 7 days?")

if query:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    # Call API (streaming)
    with st.chat_message("assistant"):
        try:
            payload = {"query": query, "app_id": int(app_id), "project_id": int(project_id)}
            if start_time_input.strip():
                payload["start_time"] = int(start_time_input.strip())
            if end_time_input.strip():
                payload["end_time"] = int(end_time_input.strip())

            with requests.post(
                f"{api_base}/query/stream",
                json=payload,
                stream=True,
                timeout=120,
            ) as resp:
                resp.raise_for_status()

                line_iter = resp.iter_lines(decode_unicode=True)
                technical = None

                # Phase 1: wait for metadata while data is being fetched (spinner shows)
                with st.spinner("Analysing..."):
                    for line in line_iter:
                        if not line or not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        if event["type"] == "metadata":
                            technical = event["data"]
                            break
                        elif event["type"] == "error":
                            raise Exception(event.get("detail", "Unknown error from server"))

                # Phase 2: spinner gone — stream LLM tokens directly into chat
                def token_gen():
                    for line in line_iter:
                        if not line or not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        if event["type"] == "token":
                            yield event["text"]
                        elif event["type"] in ("done", "error"):
                            break

                full_answer = st.write_stream(token_gen())

                if technical:
                    with st.expander("Technical details"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Primary intent:** `{technical['classification']['primary_intent']}`")
                            enriched = technical["classification"].get("enriched_intents", [])
                            if enriched:
                                st.markdown("**Enriched intents:** " + ", ".join(f"`{i}`" for i in enriched))
                        with col2:
                            tr = technical.get("time_resolution", {})
                            if tr.get("start_time"):
                                start = datetime.fromtimestamp(tr["start_time"] / 1000).strftime("%Y-%m-%d %H:%M")
                                end   = datetime.fromtimestamp(tr["end_time"]   / 1000).strftime("%Y-%m-%d %H:%M")
                                eff   = tr.get("effective_time_range")
                                if eff:
                                    st.markdown(f"**Time range:** {eff} ({start} → {end})")
                                else:
                                    st.markdown(f"**Time range:** {start} → {end}")
                                st.markdown(f"**Index:** `{tr.get('index')}`")

                        sources = technical.get("data_sources_used", [])
                        if sources:
                            st.markdown("**Data sources used:** " + ", ".join(f"`{source_label(s)}`" for s in sources))

                        for source, sdata in technical.get("data", {}).items():
                            if isinstance(sdata, dict):
                                render_source_stat(source, sdata)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": full_answer or "",
                    "technical": {
                        "primary_intent":    technical["classification"]["primary_intent"],
                        "enriched_intents":  technical["classification"].get("enriched_intents", []),
                        "time_resolution":   technical.get("time_resolution", {}),
                        "data_sources_used": technical.get("data_sources_used", []),
                        "data":              technical.get("data", {}),
                    } if technical else None,
                })

        except requests.exceptions.ConnectionError:
            msg = "Cannot connect to the backend. Make sure the FastAPI server is running:\n```\nuvicorn main:app --host 0.0.0.0 --port 8000 --workers 1\n```"
            st.error(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
        except requests.exceptions.Timeout:
            msg = "Request timed out (>120s). The backend may still be processing."
            st.error(msg)
            st.session_state.messages.append({"role": "assistant", "content": msg})
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            st.session_state.messages.append({"role": "assistant", "content": str(e)})
