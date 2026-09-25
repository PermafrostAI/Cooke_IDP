import streamlit as st
import pandas as pd
from datetime import date
from utils.snowflake_client import get_audit_search_results, get_audit_document_fields
from utils.helpers import to_excel_bytes

st.set_page_config(layout="wide")

CORTEX_SEARCH_AVAILABLE = True  # Set to True once CLIENT-387 is resolved


@st.dialog("Document fields", width="large")
def show_document_fields(doc_id: str):
    st.caption(f"Doc ID: {doc_id}")
    df = get_audit_document_fields(doc_id)
    if df.empty:
        st.info("No fields found for this document.")
    else:
        st.dataframe(df, width=True, hide_index=True)


def render_audit_search():
    st.markdown(
        "<h2 style='font-size:28px;font-weight:600;margin-bottom:4px'>Audit search</h2>",
        unsafe_allow_html=True,
    )
    st.markdown("""
    <style>
        /* Tighten vertical padding on column containers inside the results loop */
        [data-testid="column"] {
            padding-top: 4px !important;
            padding-bottom: 4px !important;
        }

        /* Reduce the gap between stVerticalBlock elements inside each row container */
        [data-testid="stVerticalBlock"] > [data-testid="stVerticalBlockBorderWrapper"] {
            margin-bottom: 0px !important;
        }

        /* Tighten the divider margin */
        hr {
            margin-top: 6px !important;
            margin-bottom: 6px !important;
        }

        /* Reduce default element container padding */
        [data-testid="stElementContainer"] {
            padding-top: 2px !important;
            padding-bottom: 2px !important;
        }
    </style>
""", unsafe_allow_html=True)
    st.caption(
        "Find any processed document to answer an FDA traceability request. "
        "Ask in plain English or use the filters below."
    )

    if not CORTEX_SEARCH_AVAILABLE:
        st.warning(
            "The Cortex Search index is not yet available. "
            "Natural language search is disabled until CLIENT-387 is resolved. "
            "You can still use the filters below to search by document type, supplier, country, and date range."
        )

    # == Search input ===============================================
    query_text = st.text_input(
        "Describe the document",
        placeholder="e.g. all health certificates for Chilean suppliers",
        disabled=not CORTEX_SEARCH_AVAILABLE,
    )

    # == Filters ====================================================
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        doc_type = st.selectbox(
            "Document type",
            options=[
                "Any",
                "Packing List",
                "Catch Certificate",
                "Health Certificate",
                "Bill of Lading",
                "Commercial Invoice",
                "Country of Origin Certificate",
            ],
            index=0,
        )

    with col2:
        supplier = st.selectbox(
            "Supplier",
            options=[
                "Any",
                "Nordic Seafood",
                "Mariscos del Sur",
                "Ocean Harvest",
                "Baltic Foods",
                "Pesca Austral",
                "Antarctic Seafoods",
            ],
            index=0,
        )

    with col3:
        country = st.selectbox(
            "Country",
            options=[
                "Any",
                "Chile",
                "Norway",
                "Spain",
                "Canada",
                "China",
            ],
            index=0,
        )

    with col4:
        date_from = st.date_input(
            "Date from",
            value=date(date.today().year, 1, 1),
        )

    with col5:
        date_to = st.date_input(
            "Date to",
            value=date.today(),
        )

    # == Search button ============================================
    search_clicked = st.button("Search", type="primary")

    st.divider()

    # == Results ==================================================
    if "audit_results" not in st.session_state:
        st.session_state["audit_results"] = pd.DataFrame()

    if search_clicked:
        st.session_state["audit_results"] = get_audit_search_results(
            query_text=query_text,
            doc_type=doc_type,
            supplier=supplier,
            country=country,
            date_from=date_from,
            date_to=date_to,
        )

    df = st.session_state["audit_results"]

    if df.empty and not search_clicked:
        st.info("Use the filters above and click Search to find documents.")
    elif df.empty:
        st.info("No documents match the selected filters.")
    else:
        result_left, result_right = st.columns([3, 1])

        with result_left:
            st.markdown(f"**{len(df)} documents found**")

        with result_right:
            xlsx_bytes = to_excel_bytes(df.drop(columns=["DOC_ID"], errors="ignore"))
            st.download_button(
                label="Export results (.xlsx)",
                data=xlsx_bytes,
                file_name=f"slade_gorton_audit_export_{date.today().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary",
                width="stretch",
            )

        h1, h2, h3, h4, h5, h6, h7 = st.columns([3, 2, 2.8, 1.5, 1.5, 2, 1])

        with h1:
            st.markdown("**Document**")
        with h2:
            st.markdown("**Type**")
        with h3:
            st.markdown("**Supplier**")
        with h4:
            st.markdown("**Country**")
        with h5:
            st.markdown("**Date**")
        with h6:
            st.markdown("**Lineage**")
        with h7:
            st.markdown("")
        st.divider()

        # == Results table with View button ============================
        for _, row in df.iterrows():
            with st.container():
                c1, c2, c3, c4, c5, c6, c7 = st.columns([3, 2, 2, 1.5, 1.5, 2, 1])
        
                with c1:
                    st.markdown(
                        f"**{row['FILENAME']}**"
                        f"<br><span style='font-size:11px;color:#6b6860'>{row.get('DESCRIPTION', '')}</span>"
                        f"<br><span style='font-size:10px;color:#9b9890'>{row['DOC_ID']}</span>",
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.write(row["DOC_TYPE"].replace("_", " ").title() if row["DOC_TYPE"] else "")
                with c3:
                    st.write(row["SUPPLIER"])
                with c4:
                    st.write(row["COUNTRY"])
                with c5:
                    st.write(str(row["DOC_DATE"]))
                with c6:
                    if row["LINEAGE"] == "AUTO_APPROVED":
                        st.markdown(
                            "<span style='background:#e4f2f2;color:#095858;padding:2px 8px;"
                            "font-size:12px;border-radius:4px;font-weight:500'>Auto-approved</span>",
                            unsafe_allow_html=True,
                        )
                    else:
                        st.markdown(
                            "<span style='background:#e4f2f2;color:#095858;padding:2px 8px;"
                            "font-size:12px;border-radius:4px;font-weight:500'>Reviewed</span>",
                            unsafe_allow_html=True,
                        )
                with c7:
                    if st.button("View", key=f"view_{row['DOC_ID']}"):
                        show_document_fields(row["DOC_ID"])
        
                st.divider()


render_audit_search()