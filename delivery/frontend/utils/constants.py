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
    "Catch Certifate",
    "Packing List",
    "Health Certificate",
    "Bill of Lading",
    "Commercial Invoice",
    "Country of Origin Cert",
]

# Flag reasons used in review queue filter
FLAG_REASONS = [
    "All",
    "Low confidence",
    "Missing field",
    "Unknown type",
    "Business rule"
]
