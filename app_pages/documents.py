"""
app_pages/documents.py - knowledge base: upload docs, rebuild index, test search.
"""
import streamlit as st

from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ui_theme import inject_theme
inject_theme(1000)
st.title(":material/description: Documents")

import rag  # noqa: E402
from jarvis.app_data import bust, index_stats  # noqa: E402

stats = index_stats()

with st.container(horizontal=True):
    st.metric("Files indexed", stats["files"], border=True)
    st.metric("Chunks", stats["chunks"], border=True)
    st.metric("Files in docs/", len(list(rag.DOCS_DIR.glob("*"))) if rag.DOCS_DIR.exists() else 0,
              border=True)

# --- upload + rebuild ---------------------------------------------------------
with st.expander("Add documents", expanded=False):
    uploads = st.file_uploader(
        f"Supported: {', '.join(sorted(rag.SUPPORTED))}",
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="doc_upload",
    )
    c1, c2 = st.columns([1, 1])
    if c1.button("Index uploaded files", type="primary", icon=":material/upload:",
                 disabled=not uploads):
        rag.DOCS_DIR.mkdir(exist_ok=True)
        for f in uploads:
            (rag.DOCS_DIR / f.name).write_bytes(f.getvalue())
        try:
            with st.spinner("Rebuilding index..."):
                res = rag.build_index()
            bust()
            st.success(f"Indexed {res['files']} file(s) - {res['chunks']} chunks "
                       f"ready for questions.")
        except ValueError as e:
            st.error(str(e))
    if c2.button("Rebuild full index", icon=":material/refresh:",
                 help="Re-embed everything in docs/ (offline model, no API key)"):
        try:
            with st.spinner("Rebuilding index..."):
                res = rag.build_index()
            bust()
            note = f" Skipped {len(res['skipped'])} unreadable." if res["skipped"] else ""
            st.success(f"Index rebuilt: {res['chunks']} chunks.{note}")
        except ValueError as e:
            st.error(str(e))

# --- search preview -----------------------------------------------------------
st.subheader("Test a query")
q = st.text_input("Ask the knowledge base", label_visibility="collapsed",
                   placeholder="Ask something about your documents...",
                   key="rag_query")
if q.strip():
    try:
        with st.status(f"Searching {stats['files']} files...", expanded=False) as status:
            hits = rag.search(q, k=5)
            status.update(label=f"{len(hits)} matching chunks", state="complete")
    except FileNotFoundError:
        hits = []
        st.warning("No index yet - add documents above first.")
    if not hits:
        st.info("No relevant chunks found.")
    else:
        for h in hits:
            score = h.get("score", 0.0)
            with st.container(border=True):
                st.caption(f"{h['source']}  ·  score {score:.2f}")
                st.markdown(h["text"][:600])

# --- current index ------------------------------------------------------------
st.subheader("In the index")
if not stats["sources"]:
    st.info("Index is empty - upload documents above, or ask the agent to "
            "learn from docs/.")
else:
    import pandas as pd

    st.dataframe(pd.DataFrame(stats["sources"]), hide_index=True,
                 alt="Indexed source files with chunk counts")
    st.caption("Ask the agent a question with @files or 'based on my docs' to "
               "use these.")
