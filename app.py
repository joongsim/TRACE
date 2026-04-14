"""TRACE — Streamlit UI shell. All data logic lives in trace_app.frontend."""

import uuid

import plotly.graph_objects as go
import streamlit as st
from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from trace_app.config import Settings
from trace_app.frontend.comparison import get_admin_comparison
from trace_app.frontend.search import get_rule, search_rules
from trace_app.storage.database import build_engine, build_session_factory

ADMIN_COLORS = {
    "Obama": "#89b4fa",
    "Trump 1": "#fab387",
    "Biden": "#a6e3a1",
    "Trump 2": "#f38ba8",
}

DOC_TYPE_COLORS = {
    "RULE": "#89b4fa",
    "PROPOSED_RULE": "#a6e3a1",
    "NOTICE": "#f9e2af",
}


@st.cache_resource
def _get_session_factory():
    settings = Settings()  # ty: ignore[missing-argument]
    engine = build_engine(settings.database_url)
    return build_session_factory(engine)


@st.cache_resource
def _get_embed_model():
    settings = Settings()  # ty: ignore[missing-argument]
    return SentenceTransformer(settings.embedding_model)


def _get_session() -> Session:
    factory = _get_session_factory()
    return factory()


# --- Sidebar navigation ---

st.set_page_config(page_title="TRACE", layout="wide")

view = st.sidebar.radio(
    "Navigation",
    ["Search", "Rule Detail", "Administration Comparison", "Graph Explorer"],
    index=0,
)

# --- Search view ---

if view == "Search":
    st.title("Search FERC Rules")

    query = st.text_input("Search", placeholder="e.g. electricity transmission rates")

    with st.expander("Filters"):
        col1, col2 = st.columns(2)
        with col1:
            admin_filter = st.multiselect(
                "Administration",
                ["Obama", "Trump 1", "Biden", "Trump 2"],
            )
            doc_type_filter = st.multiselect(
                "Document Type",
                ["RULE", "PROPOSED_RULE", "NOTICE"],
            )
        with col2:
            date_from = st.date_input("From date", value=None)
            date_to = st.date_input("To date", value=None)

    filters: dict = {}
    if admin_filter:
        filters["administration"] = admin_filter
    if doc_type_filter:
        filters["document_type"] = doc_type_filter
    if date_from:
        filters["date_from"] = date_from
    if date_to:
        filters["date_to"] = date_to

    if st.button("Search") or query:
        session = _get_session()
        try:
            results = search_rules(session, query=query, filters=filters)
        finally:
            session.close()

        if not results:
            st.info("No results found.")
        else:
            st.caption(f"{len(results)} results")
            for r in results:
                admin_color = ADMIN_COLORS.get(r["administration"], "#6c7086")
                doc_color = DOC_TYPE_COLORS.get(r["document_type"], "#6c7086")
                with st.container(border=True):
                    col_title, col_badges = st.columns([4, 1])
                    with col_title:
                        if st.button(r["title"], key=str(r["rule_id"])):
                            st.session_state["selected_rule_id"] = str(r["rule_id"])
                            st.session_state["nav_to_detail"] = True
                            st.rerun()
                    with col_badges:
                        st.markdown(
                            f"<span style='background:{admin_color};color:#1e1e2e;"
                            f"padding:2px 8px;border-radius:4px;font-size:0.8em'>"
                            f"{r['administration']}</span> "
                            f"<span style='background:{doc_color};color:#1e1e2e;"
                            f"padding:2px 8px;border-radius:4px;font-size:0.8em'>"
                            f"{r['document_type']}</span>",
                            unsafe_allow_html=True,
                        )
                    if r.get("abstract"):
                        st.caption(
                            r["abstract"][:200] + ("..." if len(r["abstract"] or "") > 200 else "")
                        )
                    meta_parts = [str(r["publication_date"])]
                    if r.get("cfr_sections"):
                        meta_parts.append(" · ".join(r["cfr_sections"]))
                    st.caption(" · ".join(meta_parts))

# --- Rule Detail view ---

elif view == "Rule Detail":
    st.title("Rule Detail")

    rule_id_str = st.session_state.get("selected_rule_id")
    if not rule_id_str:
        st.info("Select a rule from the Search view to see its details.")
    else:
        session = _get_session()
        try:
            rule = get_rule(session, uuid.UUID(rule_id_str))
        finally:
            session.close()

        if rule is None:
            st.error("Rule not found.")
        else:
            st.header(rule["title"])

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Date", str(rule["publication_date"]))
            col2.metric("Administration", rule["administration"])
            col3.metric("Type", rule["document_type"])
            col4.markdown(f"[Federal Register]({rule['fr_url']})")

            if rule.get("cfr_sections"):
                st.markdown("**CFR Sections:** " + ", ".join(rule["cfr_sections"]))

            if rule.get("abstract"):
                st.subheader("Abstract")
                st.write(rule["abstract"])

            with st.expander("Full Text"):
                st.write(rule["full_text"])

            st.subheader("Citation Graph")
            st.info("Citation graph coming soon — pending citation extraction implementation.")

# --- Administration Comparison view ---

elif view == "Administration Comparison":
    st.title("Administration Comparison")

    session = _get_session()
    try:
        data = get_admin_comparison(session)
    finally:
        session.close()

    if not data["counts_by_admin"]:
        st.info("No rules in the database yet.")
    else:
        # Metric cards
        cols = st.columns(len(data["admin_spans"]))
        for i, span in enumerate(data["admin_spans"]):
            count = data["counts_by_admin"].get(span["name"], 0)
            cols[i].metric(span["name"], count)

        # Stacked bar chart
        admin_names = [s["name"] for s in data["admin_spans"]]
        doc_types = sorted({dt for _, dt in data["counts_by_admin_type"]})

        fig = go.Figure()
        for dt in doc_types:
            counts = [data["counts_by_admin_type"].get((admin, dt), 0) for admin in admin_names]
            fig.update_layout(barmode="stack")
            fig.add_trace(
                go.Bar(
                    name=dt,
                    x=admin_names,
                    y=counts,
                    marker_color=DOC_TYPE_COLORS.get(dt, "#6c7086"),
                )
            )
        fig.update_layout(
            title="Rules by Type per Administration",
            barmode="stack",
            xaxis_title="Administration",
            yaxis_title="Count",
        )
        st.plotly_chart(fig, use_container_width=True)

        # Timeline
        fig_timeline = go.Figure()
        for span in data["admin_spans"]:
            count = data["counts_by_admin"].get(span["name"], 0)
            fig_timeline.add_trace(
                go.Bar(
                    name=span["name"],
                    x=[(span["end"] - span["start"]).days],
                    y=[span["name"]],
                    orientation="h",
                    marker_color=ADMIN_COLORS.get(span["name"], "#6c7086"),
                    text=[f"{count} rules"],
                    textposition="inside",
                )
            )
        fig_timeline.update_layout(
            title="Administration Timeline",
            showlegend=False,
            barmode="stack",
            xaxis_title="Days in Office",
        )
        st.plotly_chart(fig_timeline, use_container_width=True)

        # Topic drift stub
        st.subheader("Topic Drift")
        st.info("Topic drift analysis coming soon — pending embedding centroid computation.")

# --- Graph Explorer view ---

elif view == "Graph Explorer":
    st.title("Graph Explorer")
    st.info(
        "Citation graph coming soon — this view will show the full FERC rule citation "
        "network, filterable by administration and document type."
    )

# --- Handle nav-to-detail redirect ---

if st.session_state.get("nav_to_detail"):
    st.session_state["nav_to_detail"] = False
