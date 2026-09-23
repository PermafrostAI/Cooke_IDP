import streamlit as st
import pandas as pd
from utils.snowflake_client import get_review_queue, get_queue_summary
from utils.constants import DOC_TYPES, FLAG_REASONS
from utils.helpers import confidence_label


st.header("Review queue")

try:
    summary = get_queue_summary()
    df = get_review_queue().copy(deep=True)
except RuntimeError as e:
    st.error(str(e))
    st.stop()

# Normalise the display label on the Python side so it works regardless
# of whether DOC_TYPE_LABEL is backfilled in the database yet.
# Falls back to replacing underscores and title-casing DOC_TYPE.
# Normalise DOC_TYPE_LABEL from DOC_TYPE - replace underscores with spaces, all caps
df["DOC_TYPE_LABEL"] = (
    df["DOC_TYPE"]
    .fillna("UNKNOWN")
    .str.replace("_", " ", regex=False)
    .str.upper()
)
    
# === METRIC CARDS ===================================
col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Awaiting review", summary["AWAITING"].iloc[0])
with col2:
    st.metric("Oldest item", f"{summary['OLDEST_HOURS'].iloc[0]}h ago")
with col3:
    st.metric("Avg confidence", f"{summary['AVG_CONFIDENCE'].iloc[0]}%")

st.divider()

# === FILTERS =======================================
col_left, col_right = st.columns(2)

with col_left:
    filter_doc_type = st.selectbox(
        "Document type", DOC_TYPES, key="queue_filter_doc_type"
    )
with col_right:
    filter_flag_reason = st.text_input(
        "Flag reason",
        placeholder="Search flag reason...",
        key="queue_filter_flag_reason",
    )

# === APPLY FILTERS =================================
filtered_df = df.copy()

if filter_doc_type != "All":
    filtered_df = filtered_df[
        filtered_df["DOC_TYPE_LABEL"] == filter_doc_type
    ]

if filter_flag_reason:
    filtered_df = filtered_df[
        filtered_df["FLAG_REASON"].str.contains(
            filter_flag_reason, case=False, na=False
        )
    ]


# === EMPTY STATE ====================================
if filtered_df.empty:
    if df.empty:
        st.info("No documents are waiting for review.")
    else:
        st.info("No documents match the selected filters.")
    st.stop()


# === COLUMN HEADERS =================================
st.caption(f"{len(filtered_df)} document(s) awaiting review")
 
hcol_file, hcol_type, hcol_flag, hcol_conf, hcol_age, hcol_action = st.columns(
    [2, 3, 2.5, 1.5, 1, 1]
)
hcol_type.caption("Document type")
hcol_file.caption("Filename")
hcol_flag.caption("Flag reason")
hcol_conf.caption("Confidence")
hcol_age.caption("Age")
hcol_action.caption("")

st.divider()

# === SCROLLABLE ROW LOOP ============================
# The opening div applies the .review-queue-scroll class.
# Each row is rendered as standard st.columns inside.
# The closing div is written after the loop.
with st.container(height=520, border=False):
    for _, row in filtered_df.iterrows():
        col_file, col_type, col_flag, col_conf, col_age, col_action = st.columns(
            [2, 3, 2.5, 1.5, 1, 1]
        )

        # Age calculation must come before any write call that uses age_str
        if pd.isna(row["CREATED_AT"]):
            age_str = "Unknown"
        else:
            age_hours = (
                pd.Timestamp.now(tz="UTC") - pd.to_datetime(row["CREATED_AT"], utc=True)
            ).seconds // 3600
            age_str = f"{age_hours}h"

        col_file.write(row["ORIGINAL_FILENAME"] or "")
        col_type.write(row["DOC_TYPE_LABEL"])
        col_flag.write(row["FLAG_REASON"] or "")
        col_conf.write(confidence_label(row["CONFIDENCE"]))
        col_age.write(age_str)

        if col_action.button("Open", key=f"queue_open_{row['QUEUE_ID']}"):
            st.session_state["queue_selected_doc_id"] = row["DOC_ID"]
            st.session_state["queue_selected_queue_id"] = row["QUEUE_ID"]
            st.session_state["queue_selected_doc_type"] = row["DOC_TYPE"] or ""
            st.switch_page("pages/3_review_detail.py")

        st.divider()

