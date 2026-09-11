import streamlit as st
from utils.snowflake_client import get_extracted_fields, get_markdown_text, get_original_file_bytes
from utils.helpers import confidence_label, is_low_confidence


# == SESSION GUARD ===========================================

# Page reachable via st.switch_page from the review queue.
if "queue_selected_doc_id" not in st.session_state:
    st.warning("No document selected. Redirecting to the review queue.")
    if st.button("Go to review queue", key="detail_no_doc_redirect"):
        st.switch_page("pages/2_review_queue.py")
    st.stop()

doc_id = st.session_state["queue_selected_doc_id"]

# == HEADER ==================================================

st.header("Review detail")
st.caption(f"Document ID: {doc_id}")

if st.button("Back to queue", key="detail_back"):
    st.session_state.pop("queue_selected_doc_id", None)
    st.switch_page("pages/2_review_queue.py")

st.divider()

# == LOAD DATA ================================================
try:
    fields_df = get_extracted_fields(doc_id).copy(deep=True)
except RuntimeError as e:
    st.error(str(e))
    st.stop()

if fields_df.empty:
    st.info("No extracted fields found for this document.")
    st.stop()

# == DOCUMENT TEXT ============================================

markdown_text = get_markdown_text(doc_id)

with st.expander("Document text (translated to English)", expanded=False):
    if markdown_text:
        st.markdown(markdown_text)
    else:
        st.caption("Document text is not yet available.")

st.divider()


# === ORIGINAL FILE DOWNLOAD ==================================
# Note: filename lookup requires the documents table to be available.
# For the PoC this section renders only when the file bytes can be retrieved.
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
    st.caption("Original file download is not yet available")





# == EXTRACTED FIELD ==========================================
st.subheader("Extracted Field")
st.caption("Review each field. Edit any value that needs correction before approving.")

# Add a CORRECTED_VALUE column the reviewer can edit
# fields_df = fields_df.copy()
fields_df["CORRECTED_VALUE"] = fields_df["FIELD_VALUE"]
fields_df["CONFIDENCE_LABEL"] = fields_df["CONFIDENCE"].apply(confidence_label)
fields_df['NEEDS_REVIEW'] = fields_df["CONFIDENCE"].apply(is_low_confidence)

edited_df = st.data_editor(
    fields_df[["FIELD_NAME", "FIELD_VALUE", "CONFIDENCE_LABEL", "CORRECTED_VALUE", "NEEDS_REVIEW"]],
    width="stretch",
    hide_index=True,
    disabled=["FIELD_NAME", "FIELD_VALUE", "CONFIDENCE_LABEL", "NEEDS_REVIEW"],
    column_config={
        "FIELD_NAME": st.column_config.TextColumn("Field"),
        "FIELD_VALUE": st.column_config.TextColumn("Extracted value"),
        "CONFIDENCE_LABEL": st.column_config.TextColumn("Confidence"),
        "CORRECTED_VALUE": st.column_config.TextColumn("Corrected value"),
        "NEEDS_REVIEW": st.column_config.CheckboxColumn("Needs review"),
    },
    key="detail_field_editor"
)

st.divider()

# === ACTIONS =================================================

st.subheader("Actions")

col_approve, col_flag, _ = st.columns([1,1,4])

with col_approve:
    if st.button("Approve", type="primary", key="detail_approve"):
        corrections = dict(
            zip(edited_df["FIELD_NAME"], edited_df["CORRECTED_VALUE"])
        )
        # save_review will be wired here once the pipeline team
        # confirms the write pattern
        st.success("Review saved. Returning to queue.")
        st.session_state.pop("queue_selected_doc_id", None)  # delete the state
        st.cache_data.clear()
        st.switch_page("pages/2_review_queue.py")

with col_flag:
    if st.button("Flag wrong type", type="secondary", key="detail_flag"):
        st.warning("Document flagged as wrong type. Returning to queue.")
        st.session_state.pop("queue_selected_doc_id", None)  # delete the state
        st.cache_data.clear()
        st.switch_page("pages/2_review_queue.py")
        