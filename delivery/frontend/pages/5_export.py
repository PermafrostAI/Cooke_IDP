import pandas as pd
import streamlit as st
from datetime import date, datetime
from utils.constants import (
    EXCEL_CELL_MAX_LENGTH,
    EXPORT_ALL_TYPES_LABEL,
    EXPORT_DOC_TYPE_LABELS,
    EXPORT_DOC_TYPES,
    EXPORT_VIEW_BY_DOC_TYPE,
)
from utils.helpers import to_excel_workbook_bytes
from utils.snowflake_client import (
    get_export_unreadable_date_count,
    get_extraction_output,
)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _longest_cell(frames: dict[str, pd.DataFrame]) -> int:
    """Returns the length of the longest text value across all dataframes."""
    longest = 0
    for df in frames.values():
        for col in df.columns:
            if df[col].dtype == object:
                lengths = df[col].dropna().astype(str).str.len()
                if not lengths.empty:
                    longest = max(longest, int(lengths.max()))
    return longest


def render_export():
    st.title("Export to Excel")
    st.caption(
        "Download extracted data as a spreadsheet for reporting. "
        "No Snowflake access is needed to use the file."
    )

    # == Filters ================================
    with st.container():
        col1, col2, col3 = st.columns(3)

        with col1:
            selected_label = st.selectbox(
                "Document type",
                options=[EXPORT_ALL_TYPES_LABEL] + EXPORT_DOC_TYPE_LABELS,
                index=0,
                key="export_doc_type",
            )

        with col2:
            date_from = st.date_input(
                "Date from",
                value=date(date.today().year, 1, 1),
                key="export_date_from",
            )

        with col3:
            date_to = st.date_input(
                "Date to",
                value=date.today(),
                key="export_date_to",
            )

        include_undated = st.checkbox(
            "Include documents with no readable document date",
            value=False,
            key="export_include_undated",
            help=(
                "These documents cannot be placed in a date range. Their "
                "received date is shown in the file instead."
            ),
        )

    st.caption(
        "Only approved documents are included. These are documents the "
        "system approved automatically and documents a reviewer approved. "
        "The date filter uses the document date."
    )

    if date_from > date_to:
        st.error("Date from must be on or before date to.")
        st.stop()

    if selected_label == EXPORT_ALL_TYPES_LABEL:
        selected_types = EXPORT_DOC_TYPES
    else:
        selected_types = [
            EXPORT_DOC_TYPES[EXPORT_DOC_TYPE_LABELS.index(selected_label)]
        ]

    st.divider()

    # == Load data =====================================
    # One dataframe per document type. The key is the Excel sheet name.
    frames: dict[str, pd.DataFrame] = {}
    unreadable_by_sheet: dict[str, int] = {}

    try:
        for doc_type in selected_types:
            view_name = EXPORT_VIEW_BY_DOC_TYPE[doc_type]
            sheet_name = doc_type.replace("_", " ").upper().capitalize()

            frames[sheet_name] = get_extraction_output(
                view_name, date_from, date_to, include_undated
            ).copy(deep=True)
            unreadable_by_sheet[sheet_name] = get_export_unreadable_date_count(
                view_name
            )
    except RuntimeError as e:
        st.error(str(e))
        st.stop()

    total_rows = sum(len(df) for df in frames.values())

    # == Documents with no readable date ===============
    total_unreadable = sum(unreadable_by_sheet.values())
    if total_unreadable > 0:
        if include_undated:
            message = (
                f"{total_unreadable} document(s) with no readable document "
                "date are included at the bottom of the table. Their "
                "document date is blank. See the received date column."
            )
        else:
            message = (
                f"{total_unreadable} document(s) have no readable document "
                "date and are not shown. Tick the box above to include them."
            )
        if len(frames) > 1:
            detail = ", ".join(
                f"{name}: {count}"
                for name, count in unreadable_by_sheet.items()
                if count > 0
            )
            message = f"{message} ({detail})"
        st.info(message)

    # == Build the Excel file ==========================
    xlsx_bytes = None
    if total_rows > 0:
        if _longest_cell(frames) > EXCEL_CELL_MAX_LENGTH:
            st.warning(
                "At least one cell holds more than 32,767 characters, which "
                "is the Excel limit. Excel may cut that text in the "
                "downloaded file. Check long list fields before you rely on "
                "the file."
            )
        try:
            xlsx_bytes = to_excel_workbook_bytes(frames)
        except Exception as e:
            st.error(f"The Excel file could not be built. Detail: {e}")

    # == Preview header =================================
    header_left, header_right = st.columns([3, 1])

    with header_left:
        if len(frames) > 1:
            st.markdown(
                f"**Preview** &nbsp; {total_rows} rows "
                f"across {len(frames)} document types"
            )
        else:
            st.markdown(f"**Preview** &nbsp; {total_rows} rows")

    with header_right:
        if xlsx_bytes is not None:
            st.download_button(
                label="Download (.xlsx)",
                data=xlsx_bytes,
                file_name=(
                    f"slade_gorton_export_{datetime.today().strftime('%Y%m%d')}.xlsx"
                ),
                mime=XLSX_MIME,
                key="export_download",
                width="content",
            )
        else:
            st.button(
                "Download (.xlsx)",
                disabled=True,
                key="export_download_disabled",
                width="content",
            )

    # == Preview table ==================================
    if total_rows == 0:
        st.info("No approved documents match the selected filters.")
        return

    if len(frames) == 1:
        only_df = next(iter(frames.values()))
        st.dataframe(only_df, width="stretch", hide_index=True)
    else:
        tabs = st.tabs([f"{name} ({len(df)})" for name, df in frames.items()])
        for tab, df in zip(tabs, frames.values()):
            with tab:
                if df.empty:
                    st.caption(
                        "No approved documents of this type match the "
                        "selected filters."
                    )
                else:
                    st.dataframe(df, width="stretch", hide_index=True)


render_export()