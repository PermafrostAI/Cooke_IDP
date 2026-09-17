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
        filtered_df["DOC_TYPE"].str.lower() == filter_doc_type.lower()
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


# === QUEUE TABLE ====================================

col_doc_type, col_flag, col_confidence, col_age, col_action = st.columns(
    [2, 3, 1, 1, 1]
)
col_doc_type.caption("Document type")
col_flag.caption("Flag reason")
col_confidence.caption("Confidence")
col_age.caption("Age")
col_action.caption("")

st.divider()

for _, row in filtered_df.iterrows():
    col_doc_type, col_flag, col_confidence, col_age, col_action = st.columns(
        [2, 3, 1, 1, 1]
    )

    if pd.isna(row["CREATED_AT"]):
        age_str = "Unknown"
    else:
        age_hours = (
            pd.Timestamp.now(tz="UTC") - pd.to_datetime(row["CREATED_AT"], utc=True)
        ).seconds // 3600
        age_str = f"{age_hours}h ago"

    col_doc_type.write(row["DOC_TYPE"] or "Unknown")
    col_flag.write(row["FLAG_REASON"] or "Unknown")
    col_confidence.write(confidence_label(row["CONFIDENCE"]))
    col_age.write(age_str)

    if col_action.button("Open", key=f"queue_open_{row['QUEUE_ID']}"):
        st.session_state["queue_selected_doc_id"] = row["DOC_ID"]
        st.session_state["queue_selected_queue_id"] = row["QUEUE_ID"]
        st.switch_page("pages/3_review_detail.py")

    st.divider()

# st.dataframe(
#     df,
#     use_container_width=True,
#     hide_index=True
# )