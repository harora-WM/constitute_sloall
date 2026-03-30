"""
Streamlit UI for the Conversational SLO Manager.
Talks to the FastAPI backend running at http://localhost:8000.
"""

import requests
import streamlit as st
from datetime import datetime

API_URL = "http://localhost:8000"

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
    app_id = st.number_input("App ID", value=31854, step=1)
    project_id = st.number_input("Project ID", value=215853, step=1)

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
                        st.markdown(f"**Time range:** {start} → {end}")
                        st.markdown(f"**Index:** `{tr.get('index')}`")

                sources = _t.get("data_sources_used", [])
                if sources:
                    st.markdown("**Data sources used:** " + ", ".join(f"`{s}`" for s in sources))

                # Per-source stats
                for source, data in _t.get("data", {}).items():
                    if isinstance(data, dict) and "stats" in data:
                        st.markdown(f"**{source} stats:**")
                        st.json(data["stats"])

# ── Input ─────────────────────────────────────────────────────────────────────

query = st.chat_input("e.g. How is my application performing in the last 7 days?")

if query:
    # Show user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    # Call API
    with st.chat_message("assistant"):
        with st.spinner("Analysing..."):
            try:
                payload = {"query": query, "app_id": int(app_id), "project_id": int(project_id)}
                if start_time_input.strip():
                    payload["start_time"] = int(start_time_input.strip())
                if end_time_input.strip():
                    payload["end_time"] = int(end_time_input.strip())

                response = requests.post(
                    f"{api_base}/query",
                    json=payload,
                    timeout=60,
                )

                if response.status_code == 200:
                    data = response.json()
                    answer = data.get("conversational_response", "No response generated.")
                    st.markdown(answer)

                    technical = {
                        "primary_intent":   data["classification"]["primary_intent"],
                        "enriched_intents": data["classification"]["enriched_intents"],
                        "time_resolution":  data["time_resolution"],
                        "data_sources_used": data["data_sources_used"],
                        "data":             data["data"],
                    }

                    with st.expander("Technical details"):
                        col1, col2 = st.columns(2)
                        with col1:
                            st.markdown(f"**Primary intent:** `{technical['primary_intent']}`")
                            if technical["enriched_intents"]:
                                st.markdown("**Enriched intents:** " + ", ".join(f"`{i}`" for i in technical["enriched_intents"]))
                        with col2:
                            tr = technical["time_resolution"]
                            if tr.get("start_time"):
                                start = datetime.fromtimestamp(tr["start_time"] / 1000).strftime("%Y-%m-%d %H:%M")
                                end   = datetime.fromtimestamp(tr["end_time"]   / 1000).strftime("%Y-%m-%d %H:%M")
                                st.markdown(f"**Time range:** {start} → {end}")
                                st.markdown(f"**Index:** `{tr.get('index')}`")

                        sources = technical["data_sources_used"]
                        if sources:
                            st.markdown("**Data sources used:** " + ", ".join(f"`{s}`" for s in sources))

                        for source, sdata in technical["data"].items():
                            if isinstance(sdata, dict) and "stats" in sdata:
                                st.markdown(f"**{source} stats:**")
                                st.json(sdata["stats"])

                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": answer,
                        "technical": technical,
                    })

                else:
                    err = response.json().get("detail", response.text)
                    st.error(f"API error {response.status_code}: {err}")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"Error {response.status_code}: {err}",
                    })

            except requests.exceptions.ConnectionError:
                msg = "Cannot connect to the backend. Make sure the FastAPI server is running:\n```\nuvicorn main:app --host 0.0.0.0 --port 8000 --workers 1\n```"
                st.error(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
            except requests.exceptions.Timeout:
                msg = "Request timed out (>60s). The backend may still be processing."
                st.error(msg)
                st.session_state.messages.append({"role": "assistant", "content": msg})
            except Exception as e:
                st.error(f"Unexpected error: {e}")
                st.session_state.messages.append({"role": "assistant", "content": str(e)})
