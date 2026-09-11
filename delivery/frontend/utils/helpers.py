import io
import pandas as pd
from utils.constants import settings


def confidence_label(score: float) -> str:
    """
    Returns a plain-language label for a confidence score.
    Used in the review queue and review detail screens.
    """
    if score >= 0.85:
        return f"{round(score * 100)}% - high"
    if score >= settings.confidence_threshold:
        return f"{round(score * 100)}% - check"
    return f"{round(score * 100)}% - low"


def is_low_confidence(score: float) -> bool:
    """
    Returns True if the score is below the configured confidence threshold.
    """
    return score < settings.confidence_threshold


def format_file_size(size_bytes: int) -> str:
    """
    Returns a human-readable file size string.
    Used on the upload screen alongside the filename
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{round(size_bytes / 1024, 1)} KB"
    return f"{round(size_bytes / (1024 * 1024), 1)} MB"


def df_to_xlsx(df: pd.DataFrame) -> bytes:
    """
    Converts a pandas dataframe to an in-memory Excel file.
    Returns bytes suitable for st.download_button.
    """
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    buf.seek(0)
    return buf.getvalue()

import markdown as md


def render_markdown_small(text: str) -> str:
    """
    Converts markdown text to HTML wrapped in a small font container.
    Used for rendering extracted document text without oversized headings.
    """
    html_content = md.markdown(text)
    return f"""
        <div style="font-size: 0.8rem; line-height: 1.6;">
            {html_content}
        </div>
    """