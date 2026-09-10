import streamlit as st
from pathlib import Path
from utils.snowflake_client import get_session

st.set_page_config(
    layout="wide", 
    page_title="Slade Gorton Document Hub",
    initial_sidebar_state="expanded",
)

# Global styles for rendered document content.
# Scoped to .doc-page class so they do not affect other Streamlit elements.
st.html(Path("assets/doc_page.css"))


# Warm the session cache on app startup so no page shows
get_session()

pages = [
    st.Page(
        "pages/1_upload.py",
        title="Upload",
        icon=":material/upload:"
    ),
    st.Page(
        "pages/2_review_queue.py",
        title="Review queue",
        icon=":material/inbox:"
    ),
    st.Page(
        "pages/3_review_detail.py",
        title="Review detail",
        icon=":material/edit_document:",
        visibility="hidden",
    ),
    st.Page(
        "pages/4_audit_search.py",
        title="Audit search",
        icon=":material/search:"
    ),
    st.Page(
        "pages/5_export.py",
        title="Export",
        icon=":material/download:"
    ),
    st.Page(
        "pages/z_test.py",
        title="Test/Debug",
    )
]

pg = st.navigation(pages)
pg.run()
# st.write("Coming Soon")