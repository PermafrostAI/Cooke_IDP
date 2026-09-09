import streamlit as st

st.set_page_config(layout="wide", page_title="Slade Gorton Document Hub")

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
        default=False
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
]

pg = st.navigation(pages)
pg.run()
# st.write("Coming Soon")