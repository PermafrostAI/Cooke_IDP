import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from utils.constants import (
    settings,
    STATUS_AUTO_APPROVED,
    STATUS_IN_REVIEW,
    STATUS_DUPLICATE,
    STATUS_PIPELINE_UNAVAILABLE,
    PIPELINE_UNAVAILABLE_MSG,
)

@st.cache_resource(show_spinner=False)
def get_session():
    """
    Returns a Snowpark session using the active Snowflake connection.
    Cached as a shared resource across all viewers in the container runtime.
    """
    return st.connection("snowflake").session()


def _safe_query(sql: str) -> pd.DataFrame:
    """
    Wraps a Snowflake SQL query in try/except.
    Returns a dataframe on success.
    Raises RuntimeError with a plain message on failure.
    Page files catch RuntimeError and call st.error().
    """
    try:
        return session.sql(sql).to_pandas()
    except Exception as e:
        raise RuntimeError(
            f"A Snowflake query failed. Check your connection and try again. Detail: {e}"
        )


# == REVIEW QUEUE ======================================================================
@st.cache_data(ttl=30)
def get_review_queue() -> pd.DataFrame:
    """
    Returns all pending documents from REVIEW_QUEUE joined to classification metadata.
    Columns: DOC_ID, DOC_TYPE, SUPPLIER, FLAG_REASON, CONFIDENCE, CREATED_AT

    PLACEHOLDER: returns a hardcoded dataframe while pipeline tables are not yet available.
    Replace with _safe_query once REVIEW_QUEUE and documents_classified exist.
    """

    # --- PLACEHOLDER ---
    return pd.DataFrame([
        {
            "DOC_ID": "abc123def456",
            "DOC_TYPE": "Catch Certificate",
            "SUPPLIER": "Nordic Seafood AS",
            "FLAG_REASON": "Low confidence",
            "CONFIDENCE": 0.61,
            "CREATED_AT": datetime.now() - timedelta(hours=3),
        },
        {
            "DOC_ID": "789xyz000aaa",
            "DOC_TYPE": "Packing List",
            "SUPPLIER": "Pacific Star Fisheries",
            "FLAG_REASON": "Missing field",
            "CONFIDENCE": 0.74,
            "CREATED_AT": datetime.now() - timedelta(hours=1),
        },
    ])
    # --- END PLACEHOLDER ---

    # --- REAL QUERY (uncomment when tables exist) ---
    # return _safe_query(session, """
    #     SELECT
    #         rq.DOC_ID,
    #         dc.DOC_TYPE,
    #         dc.SUPPLIER,
    #         COALESCE(rq.FLAG_REASON, 'Unknown') AS FLAG_REASON,
    #         dec.COMPOSITE_CONFIDENCE AS CONFIDENCE,
    #         rq.CREATED_AT
    #     FROM PERMAFROST_POC.INGEST.REVIEW_QUEUE rq
    #     JOIN PERMAFROST_POC.INGEST.documents_classified dc
    #         ON rq.DOC_ID = dc.DOC_ID
    #     JOIN PERMAFROST_POC.INGEST.documents_extracted_confidence dec
    #         ON rq.DOC_ID = dec.DOC_ID
    #     WHERE rq.STATUS = 'PENDING'
    #     ORDER BY rq.CREATED_AT ASC
    # """)
    # --- END REAL QUERY ---

@st.cache_data(ttl=30)
def get_queue_summary() -> pd.DataFrame:
    """
    Returns summary counts for the metric cards on the review queue screen.
    Columns: AWAITING, OLDEST_HOURS, AVG_CONFIDENCE

    PLACEHOLDER: derives values from the placeholder dataframe.
    Replace with a direct SQL query once tables exist.
    """

    # --- PLACEHOLDER ---
    df = get_review_queue()
    if df.empty:
        return pd.DataFrame([{
            "AWAITING": 0,
            "OLDEST_HOURS": 0,
            "AVG_CONFIDENCE": 0.0,
        }])

    oldest_hours = (datetime.now() - df["CREATED_AT"].min()).seconds // 3600
    return pd.DataFrame([{
        "AWAITING": len(df),
        "OLDEST_HOURS": oldest_hours,
        "AVG_CONFIDENCE": round(df["CONFIDENCE"].mean() * 100, 1),
    }])
    # --- END PLACEHOLDER ---


@st.cache_data(ttl=120)
def get_extracted_fields(doc_id: str) -> pd.DataFrame:
    """
    Returns extracted fields and per-field confidence for a document.
    Columns: FIELD_NAME, FIELD_VALUE, CONFIDENCE
    Cached for 120 seconds - field data does not change unless reprocessed.

    PLACEHOLDER: returns hardcoded fields while pipeline tables are not yet available.
    Replace with _safe_query once documents_extracted_confidence exists.
    """

    # --- PLACEHOLDER ---
    return pd.DataFrame([
        {"FIELD_NAME": "Vessel Name",       "FIELD_VALUE": "Nordic Star",  "CONFIDENCE": 0.91},
        {"FIELD_NAME": "Catch Date",        "FIELD_VALUE": "2026-07-14",   "CONFIDENCE": 0.58},
        {"FIELD_NAME": "Species",           "FIELD_VALUE": "Atlantic Cod", "CONFIDENCE": 0.88},
        {"FIELD_NAME": "Country of Origin", "FIELD_VALUE": "Norway",       "CONFIDENCE": 0.95},
        {"FIELD_NAME": "Certificate No",    "FIELD_VALUE": "",             "CONFIDENCE": 0.20},
    ])
    # --- END PLACEHOLDER ---

    # --- REAL QUERY (uncomment when tables exist) ---
    # return _safe_query(f"""
    #     SELECT FIELD_NAME, FIELD_VALUE, CONFIDENCE
    #     FROM PERMAFROST_POC.INGEST.documents_extracted_confidence
    #     WHERE DOC_ID = '{doc_id}'
    #     ORDER BY FIELD_NAME
    # """)
    # --- END REAL QUERY ---

def get_markdown_text(doc_id: str) -> str | None:
    """
    Returns the full document text for a document by concatenating all pages
    in page order from DOCUMENTS_PAGES.
    Uses PAGE_CONTENT_TRANSLATED where available, falls back to PAGE_CONTENT.
    Returns None if no pages exist yet for this document.
    """
    try:
        session = get_session()
        rows = session.sql(f"""
            SELECT
                PAGE_NUMBER,
                COALESCE(PAGE_CONTENT_TRANSLATED, PAGE_CONTENT) AS PAGE_TEXT
            FROM {settings.database}.{settings.processing_schema}.DOCUMENTS_PAGES
            WHERE DOC_ID = '{doc_id}'
            ORDER BY PAGE_INDEX ASC
        """).collect()

        if not rows:
            return None

        pages = [
            f"**Page {row['PAGE_NUMBER']}**\n\n{row['PAGE_TEXT']}"
            for row in rows
        ]
        return "\n\n---\n\n".join(pages)

    except Exception:
        return None


def get_staged_filenames() -> list[str]:
    """
    Returns a list of filenames already in the stage folder.
    Used for filename-based duplicate warning before staging a new file.
    Fails silently and returns an empty list if the stage is not accessible.
    The stage must have DIRECTORY = (ENABLE = TRUE).
    """
    try:
        session = get_session()
        rows = session.sql(f"""
                SELECT RELATIVE_PATH
                FROM DIRECTORY(@{settings.database}.{settings.schema_name}.{settings.stage_name})
                WHERE RELATIVE_PATH LIKE '{settings.stage_folder}/%'
            """).collect()
        return [row[0].split("/")[-1] for row in rows]
    except Exception:
        return []


def stage_file(file_bytes: bytes, filename: str) -> str:
    """
    Stages a file to the raw documents stage using put_stream.
    Returns the full staged path on success.
    Raises RuntimeError on failure.
    """
    try:
        import io
        session = get_session()
        stream = io.BytesIO(file_bytes)
        destination = f"{settings.stage_path}/{filename}"
        session.file.put_stream(
            stream,
            destination,
            auto_compress=False,
            overwrite=True
        )
        return destination 
    except Exception as e:
        raise RuntimeError(f"Failed to stage {filename}. Detail: {e}")


def call_pipeline(staged_path: str) -> str:
    """
    Calls the pipeline entry point with the staged file path.
    In PoC this is SP_PROCESS_DOCUMENT. In MVP it may be a DAG trigger.
    The pipeline owns SHA-256 hashing, deduplication, and the documents table insert.

    Returns one of:
      AUTO_APPROVED        - all fields passed the confidence gate
      IN_REVIEW            - one or more fields flagged, document is in REVIEW_QUEUE
      DUPLICATE            - backend found matching FILE_HASH in documents table
      FAILED: <reason>     - unhandled exception in the pipeline
      PIPELINE_UNAVAILABLE - entry point could not be reached (frontend guardrail)

    Never raises. Always returns a string the page code can handle.
    """
    # --- STUB: remove when pipeline entry point is deployed ---
    import random 
    return random.choice([
        STATUS_AUTO_APPROVED,
        STATUS_IN_REVIEW,
        STATUS_DUPLICATE,
    ])
    # --- END STUB ---

    # --- REAL IMPLEMENTATION (uncomment when pipeline is ready) ---
    # try:
    #     session = get_session()
    #     rows = session.call("SP_PROCESS_DOCUMENT", staged_path)
    #     if hasattr(rows, "collect"):
    #         result = rows.collect()
    #         return result[0][0] if result else "UNKNOWN"
    #     return str(rows)
    # except Exception:
    #     return STATUS_PIPELINE_UNAVAILABLE
    # --- END REAL IMPLEMENTATION ---

def get_original_file_bytes(doc_id: str, filename: str) -> bytes | None:
    """
    Downloads the original staged file bytes for the reviewer to download.
    Returns None if the file is not found in the stage.
    """
    try:
        session = get_session()
        local_path = session.file.get_stream(
            f"{settings.stage_path}/{filename}"
        )
        return local_path.read()
    except Exception:
        return None



# == TEST / DEBUG ============================================

def get_document_text(doc_id: str) -> dict | None:
    """
    Returns extracted text and metadata for a document from DOCUMENTS_TEXT.
    Parses page content from RAW_EXTRACTED_VALUE VARIANT column.
    Returns None if no record exists for the given DOC_ID.
    """
    try:
        session = get_session()
        rows = session.sql(f"""
            SELECT
                DOC_ID,
                PAGE_COUNT,
                EXTRACTION_MODEL,
                EXTRACTED_AT,
                RAW_EXTRACTED_VALUE:metadata:pageCount::INTEGER AS PAGE_COUNT_RAW,
                RAW_EXTRACTED_VALUE:pages AS PAGES
            FROM PERMAFROST_POC.PROCESSING.DOCUMENTS_TEXT
            WHERE DOC_ID = '{doc_id}'
        """).collect()

        if not rows:
            return None

        row = rows[0]

        # Parse pages from the VARIANT column
        import json
        pages_raw = row["PAGES"]
        pages = []

        if pages_raw:
            pages_data = json.loads(pages_raw) if isinstance(pages_raw, str) else pages_raw
            for page in sorted(pages_data, key=lambda p: p.get("index", 0)):
                pages.append({
                    "index": page.get("index", 0),
                    "content": page.get("content", ""),
                })

        return {
            "doc_id":           row["DOC_ID"],
            "page_count":       row["PAGE_COUNT"],
            "extraction_model": row["EXTRACTION_MODEL"],
            "extracted_at":     row["EXTRACTED_AT"],
            "pages":            pages,
        }

    except Exception as e:
        raise RuntimeError(
            f"Failed to retrieve document text. Detail: {e}"
        )


def get_all_doc_ids() -> list[str]:
    """
    Returns all DOC_IDs from DOCUMENTS_TEXT for the test viewer dropdown.
    Fails silently and returns an empty list if the table is not yet populated.
    """
    try:
        session = get_session()
        rows = session.sql("""
            SELECT DOC_ID
            FROM PERMAFROST_POC.PROCESSING.DOCUMENTS_TEXT
            ORDER BY EXTRACTED_AT DESC
        """).collect()
        return [row["DOC_ID"] for row in rows]
    except Exception:
        return []


def get_audit_search_results(
    query_text: str,
    doc_type: str,
    supplier: str,
    country: str,
    date_from,
    date_to,
) -> pd.DataFrame:
    """
    Placeholder data for the audit search screen.
    Replace with a real Cortex Search query once CLIENT-387 is resolved.
    """
    data = {
        "DOC_ID": [
            "doc_31aa02",
            "doc_55bd19",
            "doc_7c8e44",
            "doc_9f21a7",
        ],
        "FILENAME": [
            "health_cert_chile_0114.pdf",
            "health_cert_chile_0207.pdf",
            "health_cert_chile_0219.pdf",
            "health_cert_chile_0330.pdf",
        ],
        "DOC_TYPE": [
            "Health Certificate",
            "Health Certificate",
            "Health Certificate",
            "Health Certificate",
        ],
        "SUPPLIER": [
            "Pesca Austral",
            "Pesca Austral",
            "Antarctic Seafoods",
            "Pesca Austral",
        ],
        "COUNTRY": ["Chile", "Chile", "Chile", "Chile"],
        "DOC_DATE": ["2026-01-14", "2026-02-07", "2026-02-19", "2026-03-30"],
        "LINEAGE": [
            "AUTO_APPROVED",
            "REVIEWED",
            "AUTO_APPROVED",
            "REVIEWED",
        ],
    }

    df = pd.DataFrame(data)

    # Apply placeholder filters
    if doc_type != "Any":
        df = df[df["DOC_TYPE"] == doc_type]
    if supplier != "Any":
        df = df[df["SUPPLIER"] == supplier]
    if country != "Any":
        df = df[df["COUNTRY"] == country]

    return df.copy(deep=True)


def get_audit_document_fields(doc_id: str) -> pd.DataFrame:
    """
    Placeholder data for the View dialog on the audit search screen.
    Replace with a real Snowflake query against EXTRACTION_OUTPUT once
    the schema is confirmed by the pipeline team.
    """
    placeholder_fields = {
        "doc_31aa02": {
            "FIELD": [
                "Supplier",
                "Country of Origin",
                "Issue Date",
                "Certificate No.",
                "Product",
                "Lot No.",
                "Net Weight",
                "Issuing Authority",
            ],
            "VALUE": [
                "Pesca Austral S.A.",
                "Chile",
                "2026-01-14",
                "SERNAPESCA-2026-0041",
                "Frozen Atlantic Salmon Fillet",
                "L-3301",
                "2,400 kg",
                "SERNAPESCA",
            ],
            "CONFIDENCE": [0.97, 0.96, 0.95, 0.88, 0.92, 0.85, 0.91, 0.93],
            "STATUS": [
                "Auto-approved",
                "Auto-approved",
                "Auto-approved",
                "Auto-approved",
                "Auto-approved",
                "Auto-approved",
                "Auto-approved",
                "Auto-approved",
            ],
        }
    }

    fields = placeholder_fields.get(
        doc_id,
        {
            "FIELD": ["Supplier", "Doc Type", "Status"],
            "VALUE": ["Placeholder Supplier", "Health Certificate", "Auto-approved"],
            "CONFIDENCE": [0.90, 0.92, 0.95],
            "STATUS": ["Auto-approved", "Auto-approved", "Auto-approved"],
        },
    )

    return pd.DataFrame(fields).copy(deep=True)

    


def get_extraction_output(
    doc_type: str,
    date_from,
    date_to,
    include_status: str,
    include_confidence: bool,
) -> pd.DataFrame:
    """
    Placeholder data for the export screen.
    Replace with a real Snowflake query once EXTRACTION_OUTPUT schema is confirmed.
    """
    data = {
        "DOC_ID": ["doc_b7d200", "doc_5f31cc", "doc_2b90fa", "doc_ac31d0"],
        "DOC_TYPE": ["Packing List", "Packing List", "Packing List", "Packing List"],
        "SUPPLIER": ["Mariscos del Sur", "Mariscos del Sur", "Baltic Foods", "Ocean Harvest"],
        "INVOICE_NO": ["MDS-2026-0091", "MDS-2026-0088", "BF-77120", "OH-5521"],
        "LOT_NO": ["L-4471", "L-4468", "L-9932", "L-1180"],
        "PRODUCT": [
            "Frozen Atlantic Salmon Fillet",
            "Frozen Cod Loin",
            "Smoked Herring",
            "Frozen Shrimp",
        ],
        "NET_WEIGHT": ["1,240 kg", "980 kg", "410 kg", "720 kg"],
        "CARTONS": [62, 49, 28, 36],
        "OVERALL_CONFIDENCE": [0.78, 0.95, 0.93, 0.90],
        "STATUS": ["APPROVED", "AUTO_APPROVED", "AUTO_APPROVED", "AUTO_APPROVED"],
        "EXTRACTED_AT": ["2026-07-14", "2026-07-12", "2026-07-10", "2026-07-09"],
    }

    confidence_cols = {
        "SUPPLIER_CONFIDENCE": [0.96, 0.97, 0.95, 0.93],
        "PRODUCT_CONFIDENCE": [0.74, 0.95, 0.92, 0.91],
        "NET_WEIGHT_CONFIDENCE": [0.61, 0.94, 0.93, 0.90],
        "LOT_NO_CONFIDENCE": [0.58, 0.96, 0.94, 0.89],
    }

    df = pd.DataFrame(data)

    if include_confidence:
        for col, values in confidence_cols.items():
            df[col] = values

    return df.copy(deep=True)


# @st.cache_data(ttl=60)
# def get_extraction_output(
#     doc_type: str,
#     date_from,
#     date_to,
#     include_status: str,
#     include_confidence: bool,
# ) -> pd.DataFrame:
#     """
#     Reads extracted field data from EXTRACTION_OUTPUT for the export screen.
#     Returns a placeholder dataframe until the pipeline team confirms the schema.
#     """
#     session = get_session()

#     # Status filter mapping
#     status_filter_map = {
#         "Approved and auto-approved": ("APPROVED", "AUTO_APPROVED"),
#         "Approved only": ("APPROVED",),
#         "Everything": None,
#     }
#     allowed_statuses = status_filter_map.get(include_status)

#     # Confidence columns to include or exclude
#     confidence_cols = """
#         ,eo.SUPPLIER_CONFIDENCE
#         ,eo.PRODUCT_CONFIDENCE
#         ,eo.NET_WEIGHT_CONFIDENCE
#         ,eo.LOT_NO_CONFIDENCE
#     """

#     try:
#         # Placeholder query - replace column names once EXTRACTION_OUTPUT
#         # schema is confirmed by the pipeline team.
#         query = f"""
#             SELECT
#                 eo.DOC_ID
#                 ,eo.DOC_TYPE
#                 ,eo.SUPPLIER
#                 ,eo.INVOICE_NO
#                 ,eo.LOT_NO
#                 ,eo.PRODUCT
#                 ,eo.NET_WEIGHT
#                 ,eo.CARTONS
#                 ,eo.OVERALL_CONFIDENCE
#                 ,eo.STATUS
#                 ,eo.EXTRACTED_AT
#                 {',' + confidence_cols.strip() if include_confidence else ''}
#             FROM {SETTINGS.database}.{SETTINGS.schema_name}.EXTRACTION_OUTPUT eo
#             WHERE eo.EXTRACTED_AT::DATE BETWEEN '{date_from}' AND '{date_to}'
#             {f"AND eo.DOC_TYPE = '{doc_type}'" if doc_type != 'All types' else ''}
#             {f"AND eo.STATUS IN ({', '.join(repr(s) for s in allowed_statuses)})" if allowed_statuses else ''}
#             ORDER BY eo.EXTRACTED_AT DESC
#         """
#         result = session.sql(query).to_pandas()
#         return result

#     except Exception as e:
#         st.error(f"Could not load extraction data. Error: {e}")
#         return pd.DataFrame()