import streamlit as st
from utils.snowflake_client import get_staged_filenames, stage_file, call_pipeline
from utils.helpers import format_file_size
from utils.constants import (
    ACCEPTED_FILE_TYPES,
    STATUS_AUTO_APPROVED,
    STATUS_IN_REVIEW,
    STATUS_DUPLICATE,
    STATUS_PIPELINE_UNAVAILABLE,
    PIPELINE_UNAVAILABLE_MSG,
)

st.header("Upload")
st.caption("Upload supplier documents for processing. Supported formats: PDF, Excel, Word, and images.")

# Incrementing this counter forces st.file_uploader to re-render as empty
# after a successful submission.
if "upload_reset_counter" not in st.session_state:
    st.session_state["upload_reset_counter"] = 0

# === FILE UPLOADER =========================================

uploaded_files = st.file_uploader(
    "Select documents",
    type=ACCEPTED_FILE_TYPES,
    accept_multiple_files=True,
    key=f"upload_file_uploader_{st.session_state['upload_reset_counter']}",
)

if not uploaded_files:
    st.info("No files selected. Drag and drop files above or click Browse files.")
    st.stop()


# === DUPLICATION WARNING ===================================

staged_filenames = get_staged_filenames()

st.subheader(f"{len(uploaded_files)} file(s) selected")

duplicate_names = []
new_files = []

for f in uploaded_files:
    if f.name in staged_filenames:
        duplicate_names.append(f.name)
    else:
        new_files.append(f)

if duplicate_names:
    st.warning(
        f"The following file(s) already exist in the stage and will be skipped: "
        f"{','.join(duplicate_names)}. "
        f"The pipeline will handle content-level deduplication for any files that are processed"
    )

if not new_files:
    st.info("All selected files already exist in the stage.")
    st.stop()

# === FILE SUMMARY TABLE =====================================

col_name, col_type, col_size = st.columns([4,2,1])
col_name.caption("Filename")
col_type.caption("Type")
col_size.caption("Size")

st.divider()

for f in new_files:
    col_name, col_type, col_size = st.columns([4, 2, 1])
    col_name.write(f.name)
    col_type.write(f.type or "Unknown")
    col_size.write(format_file_size(f.size))

st.divider()


# === SUBMIT =================================================

if st.button("Submit for processing", type="primary", key="upload_submit"):

    results = []

    progress = st.progress(0, text="Staging files...")

    for i, f in enumerate(new_files):
        file_bytes = f.read()
        status = None
        staged_path = None

        # Stage the file
        try:
            staged_path = stage_file(file_bytes, f.name)
        except RuntimeError as e:
            results.append({
                "filename": f.name,
                "status": "STAGING_FAILED",
                "detail": str(e),
            })
            progress.progress(
                (i + 1) / len(new_files),
                text=f"Staged {i + 1} of {len(new_files)} files...",
            )
            continue

        # Call the pipeline
        status = call_pipeline(staged_path)

        results.append({
            "filename": f.name,
            "status": status,
            "staged_path": staged_path,
        })

        progress.progress(
            (i + 1) / len(new_files),
            text=f"Processed {i + 1} of {len(new_files)} files...",
        )

    progress.empty()


    # == RESULTS ==========================================================

    st.subheader("Processing results")

    for result in results:
        filename = result["filename"]
        status = result["status"]

        if status == STATUS_AUTO_APPROVED:
            st.success(f"{filename} - all fields extracted and auto-approved.")

        elif status == STATUS_IN_REVIEW:
            st.info(f"{filename} - one or more fields need review. Check the review queue.")

        elif status == STATUS_DUPLICATE:
            st.warning(f"{filename} - duplicate detected by the pipeline. No reprocessing needed.")

        elif status == STATUS_PIPELINE_UNAVAILABLE:
            st.warning(f"{filename} - staged successfully but pipeline is unavailable. {PIPELINE_UNAVAILABLE_MSG}")

        elif status == "STAGING_FAILED":
            st.error(f"{filename} - could not be staged. {result.get('detail', '')}")

        else:
            # Handles FAILED: <reason> and any unexpected status
            st.error(f"{filename} - pipeline returned an unexpected status: {status}")

    # Reset the uploader so it renders empty on the next iteraction
    st.session_state["upload_reset_counter"] += 1

    