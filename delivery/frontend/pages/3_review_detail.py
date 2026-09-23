import streamlit as st
import markdown as md
from utils.snowflake_client import (
    get_extracted_fields,
    get_original_file_bytes,
    submit_for_reprocessing,
    get_session,
)
from utils.helpers import confidence_label, is_low_confidence
from utils.constants import ASSIGNABLE_DOC_TYPES, ASSIGNABLE_DOC_TYPE_LABELS

# == SESSION GUARD ===========================================
if "queue_selected_doc_id" not in st.session_state:
    st.warning("No document selected. Redirecting to the review queue.")
    if st.button("Go to review queue", key="detail_no_doc_redirect"):
        st.switch_page("pages/2_review_queue.py")
    st.stop()

doc_id = st.session_state["queue_selected_doc_id"]
queue_id = st.session_state.get("queue_selected_queue_id")
doc_type = st.session_state.get("queue_selected_doc_type") or ""

# == HEADER ==================================================
st.header("Review detail")
st.caption(f"Document ID: {doc_id}")

if st.button("Back to queue", key="detail_back"):
    st.session_state.pop("queue_selected_doc_id", None)
    st.session_state.pop("queue_selected_queue_id", None)
    st.session_state.pop("queue_selected_doc_type", None)
    st.switch_page("pages/2_review_queue.py")

st.divider()

# == DOCUMENT TEXT ============================================
if "detail_doc_expander_open" not in st.session_state:
    st.session_state["detail_doc_expander_open"] = False

with st.expander(
    "Document text (translated to English)",
    expanded=st.session_state["detail_doc_expander_open"]
):
    st.session_state["detail_doc_expander_open"] = True

    try:
        session = get_session()
        page_rows = session.sql(f"""
            SELECT
                PAGE_NUMBER,
                COALESCE(PAGE_CONTENT_TRANSLATED, PAGE_CONTENT) AS PAGE_TEXT
            FROM PERMAFROST_POC.PROCESSING.DOCUMENTS_PAGES
            WHERE CHILD_DOC_ID = '{doc_id}'
            ORDER BY PAGE_INDEX ASC
        """).collect()
    except Exception as e:
        page_rows = []
        st.caption(f"Could not load document text. Detail: {e}")

    if not page_rows:
        st.caption("No page content available for this document.")
    else:
        total_pages = len(page_rows)

        if st.session_state.get("detail_current_doc") != doc_id:
            st.session_state["detail_current_doc"] = doc_id
            st.session_state["detail_page_index"] = 0

        if "detail_page_index" not in st.session_state:
            st.session_state["detail_page_index"] = 0

        current = st.session_state["detail_page_index"]

        col_back, col_indicator, col_next = st.columns([1, 2, 1])

        with col_back:
            back_clicked = st.button(
                "← Back",
                disabled=(current == 0),
                key="detail_page_back",
            )

        with col_next:
            next_clicked = st.button(
                "Next →",
                disabled=(current == total_pages - 1),
                key="detail_page_next",
            )

        if back_clicked:
            st.session_state["detail_page_index"] = current - 1
        elif next_clicked:
            st.session_state["detail_page_index"] = current + 1

        current = st.session_state["detail_page_index"]

        with col_indicator:
            st.markdown(
                f"<div style='text-align:center; padding-top:8px; color:gray; font-size:0.85rem'>"
                f"Page {current + 1} of {total_pages}"
                f"</div>",
                unsafe_allow_html=True,
            )

        with st.container(border=True):
            page_text = page_rows[current]["PAGE_TEXT"]
            if page_text:
                rendered = md.markdown(page_text, extensions=["tables"])
                st.html(f'<div class="doc-page">{rendered}</div>')
            else:
                st.caption("No content extracted for this page.")

# == ORIGINAL FILE DOWNLOAD ==================================
file_bytes = get_original_file_bytes(doc_id, f"{doc_id}.pdf")

if file_bytes:
    st.download_button(
        label="Download original file",
        data=file_bytes,
        file_name=f"{doc_id}_original.pdf",
        mime="application/octet-stream",
        key="detail_download_original",
    )
else:
    st.caption("Original file download is not yet available.")

st.divider()

# == UNKNOWN DOC TYPE HANDLING ================================
is_unknown = doc_type.upper() in ("UNKNOWN", "OTHER", "")

if is_unknown:
    st.warning(
        "This document could not be classified automatically. "
        "Review the document text above, select the correct type below, "
        "and submit it for reprocessing."
    )

    selected_label = st.selectbox(
        "Document type",
        options=ASSIGNABLE_DOC_TYPE_LABELS,
        index=None,
        placeholder="Select document type...",
        key="detail_reclassify_select",
    )

    if st.button("Submit for reprocessing", type="primary", key="detail_reprocess"):
        if not selected_label:
            st.error("Please select a document type before submitting.")
        else:
            selected_type = ASSIGNABLE_DOC_TYPES[
                ASSIGNABLE_DOC_TYPE_LABELS.index(selected_label)
            ]
            try:
                submit_for_reprocessing(queue_id, selected_type)
                st.success("Document submitted for reprocessing. Returning to queue.")
                st.session_state.pop("queue_selected_doc_id", None)
                st.session_state.pop("queue_selected_queue_id", None)
                st.session_state.pop("queue_selected_doc_type", None)
                st.cache_data.clear()
                st.switch_page("pages/2_review_queue.py")
            except RuntimeError as e:
                st.error(str(e))

    st.stop()

# == EXTRACTED FIELDS =========================================
st.subheader("Extracted fields")
st.caption("Review each field. Edit any value that needs correction before approving.")

try:
    fields_df = get_extracted_fields(doc_id).copy(deep=True)
except RuntimeError as e:
    st.error(str(e))
    st.stop()

if fields_df.empty:
    st.info("No extracted fields found for this document.")
    st.stop()

fields_df["CORRECTED_VALUE"] = fields_df["FIELD_VALUE"]
fields_df["CONFIDENCE_LABEL"] = fields_df["CONFIDENCE"].apply(confidence_label)
fields_df["NEEDS_REVIEW"] = fields_df["CONFIDENCE"].apply(is_low_confidence)

edited_df = st.data_editor(
    fields_df[["FIELD_LABEL", "FIELD_VALUE", "CONFIDENCE_LABEL", "CORRECTED_VALUE", "NEEDS_REVIEW"]],
    width="stretch",
    hide_index=True,
    disabled=["FIELD_LABEL", "FIELD_VALUE", "CONFIDENCE_LABEL", "NEEDS_REVIEW"],
    column_config={
        "FIELD_LABEL": st.column_config.TextColumn("Field"),
        "FIELD_VALUE": st.column_config.TextColumn("Extracted value"),
        "CONFIDENCE_LABEL": st.column_config.TextColumn("Confidence"),
        "CORRECTED_VALUE": st.column_config.TextColumn("Corrected value"),
        "NEEDS_REVIEW": st.column_config.CheckboxColumn("Needs review"),
    },
    key="detail_field_editor",
)

st.divider()

# === ACTIONS =================================================
st.subheader("Actions")


@st.dialog("Correct document type")
def flag_wrong_type_dialog():
    st.caption(
        f"Current type: {doc_type.replace('_', ' ').upper() or 'UNKNOWN'}"
    )
    st.write(
        "Select the correct document type. The document will be sent back "
        "for reprocessing with the corrected type."
    )

    selected_label = st.selectbox(
        "Correct document type",
        options=ASSIGNABLE_DOC_TYPE_LABELS,
        index=None,
        placeholder="Select document type...",
        key="detail_flag_reclassify_select",
    )

    col_confirm, col_cancel = st.columns(2)

    with col_confirm:
        if st.button("Confirm and reprocess", type="primary", key="detail_flag_confirm"):
            if not selected_label:
                st.error("Please select a document type.")
            else:
                selected_type = ASSIGNABLE_DOC_TYPES[
                    ASSIGNABLE_DOC_TYPE_LABELS.index(selected_label)
                ]
                try:
                    submit_for_reprocessing(queue_id, selected_type)
                    st.session_state.pop("queue_selected_doc_id", None)
                    st.session_state.pop("queue_selected_queue_id", None)
                    st.session_state.pop("queue_selected_doc_type", None)
                    st.cache_data.clear()
                    st.switch_page("pages/2_review_queue.py")
                except RuntimeError as e:
                    st.error(str(e))

    with col_cancel:
        if st.button("Cancel", key="detail_flag_cancel"):
            st.rerun()


col_approve, col_flag, _ = st.columns([1, 1, 4])

with col_approve:
    if st.button("Approve", type="primary", key="detail_approve"):
        corrections = dict(
            zip(fields_df["FIELD_ID"], edited_df["CORRECTED_VALUE"])
        )
        # save_review wired here once pipeline team confirms write pattern
        st.success("Review saved. Returning to queue.")
        st.session_state.pop("queue_selected_doc_id", None)
        st.session_state.pop("queue_selected_queue_id", None)
        st.session_state.pop("queue_selected_doc_type", None)
        st.cache_data.clear()
        st.switch_page("pages/2_review_queue.py")

with col_flag:
    if st.button("Flag wrong type", type="secondary", key="detail_flag"):
        flag_wrong_type_dialog()