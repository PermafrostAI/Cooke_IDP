import streamlit as st
import pandas as pd
from datetime import date, datetime
from utils.constants import settings, DOC_TYPES
from utils.snowflake_client import get_extraction_output
from utils.helpers import to_excel_bytes


def render_export():
    st.title("Export to Excel")
    st.caption(
        "Download extracted data as a spreadsheet for reporting. "
        "No Snowflake access is needed to use the file."
    )

    # == Filters ================================
    with st.container():
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            doc_type = st.selectbox(
                "Document type",
                options=DOC_TYPES,
                index=0,
            )

        with col2:
            date_from = st.date_input(
                "Date from",
                value=date(date.today().year, date.today().month, 1),
            )

        with col3:
            date_to = st.date_input(
                "Date to",
                value=date.today(),
            )

        with col4:
            include_status = st.selectbox(
                "Include",
                options=[
                    "Approved and auto-approved",
                    "Approved only",
                    "Everything",
                ],
                index=0,
            )

    include_confidence = st.checkbox("Include confidence columns", value=True)

    st.divider()

    # == Load data =====================================
    df = get_extraction_output(
        doc_type=doc_type,
        date_from=date_from,
        date_to=date_to,
        include_status=include_status,
        include_confidence=include_confidence,
    )

    # == Preview header =================================
    header_left, header_right = st.columns([3, 1])

    with header_left:
        st.markdown(f"**Preview** &nbsp; {len(df)} rows")

    with header_right:
        if not df.empty:
            xlsx_bytes = to_excel_bytes(df)
            st.download_button(
                label="Download (.xlsx)",
                data=xlsx_bytes,
                file_name=f"slade_gorton_export_{datetime.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width='content',
            )
        else:
            st.button("Download (.xlsx)", disabled=True, width='content')

    # == Preview table ==================================
    if df.empty:
        st.info("No records match the selected filters.")
    else:
        st.dataframe(
            df,
            width='content',
            hide_index=True,
        )


render_export()