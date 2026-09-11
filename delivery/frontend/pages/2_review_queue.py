import streamlit as st
from utils.helpers import confidence_label
from utils.constants import DOC_TYPES, FLAG_REASONS
from utils.snowflake_client import (
    get_review_queue, 
    get_queue_summary
)

st.header("Review Queue")


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
col_left, col_mid, col_right = st.columns(3)

with col_left:
    filter_doc_type = st.selectbox("Document type", DOC_TYPES, key="queue_filter_doc_type")
with col_mid:
    filter_flag_reason = st.selectbox("Flag reason", FLAG_REASONS, key="queue_filter_flag_reason")
with col_right:
    filter_supplier = st.text_input("Supplier", placeholder="Search by supplier name...", key="queue_filter_supplier")
    

# === APPLY FILTERS =================================
filtered_df = df.copy()

if filter_doc_type != "All":
    filtered_df = filtered_df[filtered_df["DOC_TYPE"] == filter_doc_type]

if filter_flag_reason != "All":
    filtered_df = filtered_df[filtered_df["FLAG_REASON"] == filter_flag_reason]

if filter_supplier:
    filtered_df = filtered_df[
        filtered_df["SUPPLIER"].str.contains(filter_supplier, case=False, na=False)
    ]


# === EMPTY STATE ====================================
if filtered_df.empty:
    if df.empty:
        st.info("No documents are waiting for review.")
    else:
        st.info("No documents match the selected filters.")
    st.stop()


# === QUEUE TABLE ====================================

# Column headers
col_doc_type, col_supplier, col_flag, col_confidence, col_age, col_action = st.columns([2,2,2,1,1,1])
col_doc_type.caption("Document type")
col_supplier.caption("Supplier")
col_flag.caption("Flag reason")
col_confidence.caption("Confidence")
col_age.caption("Age")
col_action.caption("")

st.divider()

# One row per document
for _, row in filtered_df.iterrows():
    col_doc_type, col_supplier, col_flag, col_confidence, col_age, col_action = st.columns([2,2,2,1,1,1])

    age_hours = (
        (st.session_state.get("_now", __import__("datetime").datetime.now()) - row["CREATED_AT"]).seconds // 3600
        )
    col_doc_type.write(row["DOC_TYPE"])
    col_supplier.write(row["SUPPLIER"])
    col_flag.write(row["FLAG_REASON"])
    col_confidence.write(confidence_label(row["CONFIDENCE"]))
    col_age.write(f"{age_hours}h ago")

    if col_action.button("Open", key=f"queue_open_{row['DOC_ID']}"):
        st.session_state["queue_selected_doc_id"] = row["DOC_ID"]
        st.switch_page("pages/3_review_detail.py")

    st.divider()

# st.dataframe(
#     df,
#     use_container_width=True,
#     hide_index=True
# )