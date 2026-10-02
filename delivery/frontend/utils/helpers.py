import io
import re
import pandas as pd
import math
import markdown as md
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows
from utils.constants import settings, EXCEL_SHEET_NAME_MAX_LENGTH


def confidence_label(score) -> str:
    if score is None:
        return "No score"
    try:
        score = float(score)
    except (ValueError, TypeError):
        return "No score"
    if math.isnan(score):
        return "No score"
    if score >= 0.85:
        return f"{round(score * 100)}% - high"
    if score >= settings.confidence_threshold:
        return f"{round(score * 100)}% - check"
    return f"{round(score * 100)}% - low"


def is_low_confidence(score) -> bool:
    if score is None:
        return True
    try:
        score = float(score)
    except (ValueError, TypeError):
        return True
    if math.isnan(score):
        return True
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


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    """
    Converts a dataframe to an in-memory .xlsx file and returns the raw bytes.
    Column headers are bolded. All columns are auto-sized to fit content.
    Dict-typed columns are dropped before writing to avoid openpyxl errors.
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Extracted Fields"

    # Drop any column where any value is a dict (e.g. Cortex Search score metadata)
    df = df[[
        col for col in df.columns
        if not df[col].apply(lambda x: isinstance(x, dict)).any()
    ]]

    header_font = Font(bold=True)
    header_fill = PatternFill(
        start_color="E4E4E4", end_color="E4E4E4", fill_type="solid"
    )

    for row_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), start=1):
        ws.append(row)
        if row_idx == 1:
            for cell in ws[row_idx]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

    for col in ws.columns:
        max_length = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in col
        )
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 4, 60)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read

# Characters that Excel does not allow in a sheet name.
_INVALID_SHEET_NAME_CHARS = re.compile(r"[\\/*?:\[\]]")


def _safe_sheet_name(name: str, used_names: set[str]) -> str:
    """
    Returns a sheet name that Excel accepts.
    Removes characters Excel forbids, cuts the name to
    EXCEL_SHEET_NAME_MAX_LENGTH characters, and adds a number at the end
    if the same name was already used. Excel compares names without
    regard to case, so used_names holds lower case names.
    """
    cleaned = _INVALID_SHEET_NAME_CHARS.sub(" ", name).strip().strip("'")
    cleaned = cleaned[:EXCEL_SHEET_NAME_MAX_LENGTH].strip() or "Sheet"

    candidate = cleaned
    counter = 2
    while candidate.lower() in used_names:
        suffix = f" {counter}"
        candidate = cleaned[: EXCEL_SHEET_NAME_MAX_LENGTH - len(suffix)] + suffix
        counter += 1

    used_names.add(candidate.lower())
    return candidate


def _write_df_to_sheet(ws, df: pd.DataFrame) -> None:
    """
    Writes a dataframe to an existing worksheet.
    Column headers are bold on a grey fill. Column widths fit the content
    up to a maximum of 60. Dict-typed columns are dropped before writing
    to avoid openpyxl errors. Missing values become empty cells.
    A dataframe with no rows still gets its header row.
    """
    df = df[[
        col for col in df.columns
        if not df[col].apply(lambda x: isinstance(x, dict)).any()
    ]]
    df = df.astype(object).where(df.notna(), None)

    header_font = Font(bold=True)
    header_fill = PatternFill(
        start_color="E4E4E4", end_color="E4E4E4", fill_type="solid"
    )

    for row_idx, row in enumerate(
        dataframe_to_rows(df, index=False, header=True), start=1
    ):
        ws.append(row)
        if row_idx == 1:
            for cell in ws[row_idx]:
                cell.font = header_font
                cell.fill = header_fill
                cell.alignment = Alignment(horizontal="center")

    for col in ws.columns:
        max_length = max(
            len(str(cell.value)) if cell.value is not None else 0
            for cell in col
        )
        ws.column_dimensions[col[0].column_letter].width = min(max_length + 4, 60)


def to_excel_workbook_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    """
    Converts several dataframes to one in-memory .xlsx file and returns
    the raw bytes. Each key in sheets becomes one sheet name and each
    value becomes the content of that sheet, in the order given.

    Sheet names are made safe for Excel: forbidden characters are removed,
    names are cut to 31 characters, and repeated names get a number.
    Raises ValueError if sheets is empty, because a workbook needs at
    least one sheet.
    """
    if not sheets:
        raise ValueError("At least one sheet is required to build a workbook.")

    wb = openpyxl.Workbook()
    wb.remove(wb.active)  # remove the empty default sheet

    used_names: set[str] = set()
    for requested_name, df in sheets.items():
        ws = wb.create_sheet(title=_safe_sheet_name(requested_name, used_names))
        _write_df_to_sheet(ws, df)

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


def is_low_confidence(score: float) -> bool:
    """
    Returns True if the score is below the configured confidence threshold.
    Returns True for None or NaN scores so they are flagged for review.
    """
    if score is None or (isinstance(score, float) and math.isnan(score)):
        return True
    return score < settings.confidence_threshold