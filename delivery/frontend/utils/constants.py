from dataclasses import dataclass

@dataclass(frozen=True)
class _Settings:
    database: str = "PERMAFROST_POC"
    schema_name: str = "INGEST"
    processing_schema: str = "PROCESSING"
    stage_name: str = "RAW_DOCUMENTS_STAGE"
    stage_folder: str = "raw_files"
    confidence_threshold: float = 0.80

    @property
    def stage_path(self) -> str:
        return (
            f"@{self.database}.{self.schema_name}"
            f".{self.stage_name}/{self.stage_folder}"
        )

settings = _Settings()

# Pipeline status strings
STATUS_AUTO_APPROVED = "AUTO_APPROVED"
STATUS_IN_REVIEW = "IN_REVIEW"
STATUS_DUPLICATE = "DUPLICATE"
STATUS_FAILED = "FAILED"
STATUS_PIPELINE_UNAVAILABLE = "PIPELINE_UNAVAILABLE"

PIPELINE_UNAVAILABLE_MSG = (
    "The pipeline is not available. Your file was staged but could not "
    "be processed. Contact the pipeline team to trigger processing manually."
)

# Accepted file types for st.file_uploader
ACCEPTED_FILE_TYPES = [
    "pdf",
    "xlsx",
    "xls",
    "docx",
    "jpg",
    "jpeg",
    "png"
]

# Document types used across filter dropdowns
DOC_TYPES = [
    "All",
    "CATCH CERTIFICATE",
    "PACKING LIST",
    "HEALTH CERTIFICATE",
    "BILL OF LADING",
    "COMMERCIAL INVOICE",
    "COUNTRY OF ORIGIN CERT",
]

# Used in reclassification selectbox - excludes All and UNKNOWN
# Values are the raw Snowflake DOC_TYPE format
ASSIGNABLE_DOC_TYPES = [
    "catch_certificate",
    "packing_list",
    "health_certificate",
    "bill_of_lading",
    "commercial_invoice",
    "country_of_origin_cert",
]

# Display labels matching ASSIGNABLE_DOC_TYPES by index
ASSIGNABLE_DOC_TYPE_LABELS = [
    t.replace("_", " ").upper() for t in ASSIGNABLE_DOC_TYPES
]

# Flag reasons used in review queue filter
FLAG_REASONS = [
    "All",
    "Low confidence",
    "Missing field",
    "Unknown type",
    "Business rule"
]


# Export screen - gate and approval status values
EXPORT_GATE_RESULT_AUTO_APPROVED = "AUTO_APPROVED"
EXPORT_REVIEW_STATUS_APPROVED = "APPROVED"

# Export screen - filter options shown in the selectbox
EXPORT_STATUS_OPTIONS = {
    "Approved + auto-approved": [EXPORT_GATE_RESULT_AUTO_APPROVED, EXPORT_REVIEW_STATUS_APPROVED],
}

# Export screen - confidence column toggle options
EXPORT_CONFIDENCE_OPTIONS = ["Include", "Exclude"]

# Export screen - cache TTL in seconds
EXPORT_CACHE_TTL = 60
DOC_TYPE_CONFIG_CACHE_TTL = 600  # 10 minutes - config changes rarely



# == EXPORT SCREEN (CLIENT-448) ==============================================
# Fixed mapping from raw document type value to the backend export view.
# The query function only accepts view names found in this mapping, so
# dropdown text never goes into SQL.
# Packing list, bill of lading, and country of origin certificate are
# deferred to MVP.
_EXPORT_VIEW_PREFIX = f"{settings.database}.{settings.processing_schema}"

EXPORT_VIEW_BY_DOC_TYPE: dict[str, str] = {
    "commercial_invoice": f"{_EXPORT_VIEW_PREFIX}.VW_EXPORT_COMMERCIAL_INVOICE",
    "health_certificate": f"{_EXPORT_VIEW_PREFIX}.VW_EXPORT_HEALTH_CERTIFICATE",
    "catch_certificate": f"{_EXPORT_VIEW_PREFIX}.VW_EXPORT_CATCH_CERTIFICATE",
}

# Raw values, in display order.
EXPORT_DOC_TYPES: list[str] = list(EXPORT_VIEW_BY_DOC_TYPE.keys())

# Display labels, derived the same way as ASSIGNABLE_DOC_TYPE_LABELS.
EXPORT_DOC_TYPE_LABELS: list[str] = [
    t.replace("_", " ").upper() for t in EXPORT_DOC_TYPES
]

# Label for the option that exports every type in one workbook.
EXPORT_ALL_TYPES_LABEL: str = "ALL TYPES"

# View names the query function is allowed to read.
EXPORT_ALLOWED_VIEWS: frozenset[str] = frozenset(EXPORT_VIEW_BY_DOC_TYPE.values())

# Column in each export view that the date filter reads.
EXPORT_DATE_FILTER_COLUMN: str = "DOCUMENT_DATE_PARSED"

# Excel allows at most 31 characters in a sheet name.
EXCEL_SHEET_NAME_MAX_LENGTH: int = 31

# Columns left out of the preview and the download. They identify records
# inside the pipeline and mean nothing to a QA analyst. ORIGINAL_FILE_NAME
# stays so every row can be traced to its source file.
EXPORT_EXCLUDED_COLUMNS: tuple[str, ...] = ("CHILD_DOC_ID", "DOC_ID")

# Excel allows at most 32,767 characters in one cell.
EXCEL_CELL_MAX_LENGTH: int = 32767