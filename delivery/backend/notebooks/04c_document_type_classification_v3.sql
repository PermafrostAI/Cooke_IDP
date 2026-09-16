-- If the prompt is in the key-value config
SELECT CONFIG_KEY, CONFIG_VALUE
FROM PERMAFROST_POC.CONFIG.PIPELINE_CONFIG
ORDER BY CONFIG_KEY;


-- If the prompt is in the per-doc-type registry
SELECT DOC_TYPE, PROMPT_TEMPLATE, LLM_MODEL, IS_ACTIVE
FROM PERMAFROST_POC.CONFIG.DOC_TYPE_CONFIG
ORDER BY DOC_TYPE;


--============================================
-- STEP 1: Producing Page Signals
--============================================
CREATE OR REPLACE TRANSIENT TABLE PERMAFROST_POC.PROCESSING.PAGE_SIGNALS AS

WITH eligible_docs AS (
    -- All EXTRACTED documents not yet classified in the spike schema.
    SELECT d.DOC_ID
    FROM PERMAFROST_POC.INGEST.DOCUMENTS_INGESTED d
    WHERE 
        -- d.STATUS = 'EXTRACTED' AND 
        d.DOC_ID NOT IN (
          SELECT DISTINCT DOC_ID
          FROM PERMAFROST_POC.SPIKE.DOCUMENTS_CLASSIFIED
      )
),

candidate_pages AS (
    SELECT
        p.DOC_ID,
        p.PAGE_INDEX,
        p.PAGE_NUMBER,
        COALESCE(p.PAGE_CONTENT_TRANSLATED, p.PAGE_CONTENT) AS page_text
    FROM PERMAFROST_POC.PROCESSING.DOCUMENTS_PAGES p
    INNER JOIN eligible_docs e
        ON p.DOC_ID = e.DOC_ID
    WHERE COALESCE(p.PAGE_CONTENT_TRANSLATED, p.PAGE_CONTENT) IS NOT NULL
      AND TRIM(COALESCE(p.PAGE_CONTENT_TRANSLATED, p.PAGE_CONTENT)) != ''
    ORDER BY p.DOC_ID, p.PAGE_INDEX
),

classified AS (
    SELECT
        cp.DOC_ID,
        cp.PAGE_INDEX,
        cp.PAGE_NUMBER,
        cp.page_text,
        AI_COMPLETE(
            'claude-sonnet-5',
            CONCAT(
                'You are analysing a single page from a multi-page seafood import document packet. ',
                'Your job is to classify this page and determine whether it is the first page of a new document. ',
                'Two pages of the same document type are only the same segment if they are part of the same physical document. ',
                'If a new document of the same type starts (new certificate number, new issuing authority, new header, new reference), it must be a separate segment. ',
                'A continuation page (e.g. page 2 of a long invoice) belongs to the same segment as the previous page. ',
                'If uncertain whether this is a new document or a continuation, prefer treating it as a new document. ',
                'Freight, logistics, or shipping cost invoices must be classified as unknown, not commercial_invoice. ',
                'Choose doc_type from exactly this list: ',
                'health_certificate, commercial_invoice, packing_list, bill_of_lading, catch_certificate, country_of_origin_certificate, unknown. ',
                'Page content: ',
                cp.page_text
            ),
            response_format => {
                'type': 'json',
                'schema': {
                    'type': 'object',
                    'properties': {
                        'doc_type': {
                            'type': 'string'
                        },
                        'is_first_page': {
                            'type': 'boolean'
                        },
                        'confidence': {
                            'type': 'number'
                        },
                        'boundary_signal': {
                            'type': 'string'
                        }
                    },
                    'required': ['doc_type', 'is_first_page', 'confidence', 'boundary_signal']
                }
            }
        ) AS raw_result
    FROM candidate_pages cp
)

SELECT
    DOC_ID,
    PAGE_INDEX,
    PAGE_NUMBER,
    raw_result:doc_type::VARCHAR        AS PAGE_DOC_TYPE,
    raw_result:is_first_page::BOOLEAN   AS IS_FIRST_PAGE,
    raw_result:confidence::FLOAT        AS CONFIDENCE,
    raw_result:boundary_signal::VARCHAR AS PAGE_SIGNAL,
    page_text                           AS PAGE_TEXT
FROM classified;


-- Step 1 Spot check
SELECT
    DOC_ID,
    PAGE_INDEX,
    PAGE_NUMBER,
    PAGE_DOC_TYPE,
    IS_FIRST_PAGE,
    CONFIDENCE,
    PAGE_SIGNAL
FROM PERMAFROST_POC.PROCESSING.PAGE_SIGNALS
ORDER BY DOC_ID, PAGE_INDEX;



-- ============================================
-- STEP 2: Document Segmentation
-- ============================================
CREATE OR REPLACE TRANSIENT TABLE PERMAFROST_POC.PROCESSING.PAGE_SEGMENTS AS

WITH boundary_flags AS (
    SELECT
        DOC_ID,
        PAGE_INDEX,
        PAGE_NUMBER,
        PAGE_DOC_TYPE,
        IS_FIRST_PAGE,
        CONFIDENCE,
        PAGE_SIGNAL,
        LAG(PAGE_DOC_TYPE) OVER (
            PARTITION BY DOC_ID
            ORDER BY PAGE_INDEX
        ) AS PREV_DOC_TYPE,
        CASE
            WHEN PAGE_DOC_TYPE != PREV_DOC_TYPE OR PREV_DOC_TYPE IS NULL THEN 1
            WHEN IS_FIRST_PAGE = TRUE THEN 1
            ELSE 0
        END AS IS_BOUNDARY
    FROM PERMAFROST_POC.PROCESSING.PAGE_SIGNALS
)

SELECT
    DOC_ID,
    PAGE_INDEX,
    PAGE_NUMBER,
    PAGE_DOC_TYPE,
    IS_FIRST_PAGE,
    CONFIDENCE,
    PAGE_SIGNAL,
    IS_BOUNDARY,
    SUM(IS_BOUNDARY) OVER (
        PARTITION BY DOC_ID
        ORDER BY PAGE_INDEX
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS SEGMENT_NUM
FROM boundary_flags;


-- Step 2 spot check
SELECT
    DOC_ID,
    PAGE_INDEX,
    PAGE_NUMBER,
    PAGE_DOC_TYPE,
    IS_FIRST_PAGE,
    CONFIDENCE,
    IS_BOUNDARY,
    SEGMENT_NUM
FROM PERMAFROST_POC.PROCESSING.PAGE_SEGMENTS
ORDER BY DOC_ID, PAGE_INDEX;




-- =============================================
-- STEP 3: Collapse per page
-- ============================================
CREATE OR REPLACE TRANSIENT TABLE PERMAFROST_POC.PROCESSING.SEGMENT_BOUNDARIES AS

SELECT
    DOC_ID,
    SEGMENT_NUM,
    PAGE_DOC_TYPE,
    MIN(PAGE_INDEX)   AS PAGE_INDEX_START,
    MAX(PAGE_INDEX)   AS PAGE_INDEX_END,
    MIN(PAGE_NUMBER)  AS PAGE_NUMBER_START,
    MAX(PAGE_NUMBER)  AS PAGE_NUMBER_END,
    COUNT(*)          AS PAGE_COUNT,
    -- Take the average confidence across all pages in the segment.
    -- This gives a more representative score than just the first page.
    AVG(CONFIDENCE)   AS CONFIDENCE
FROM PERMAFROST_POC.PROCESSING.PAGE_SEGMENTS
GROUP BY
    DOC_ID,
    SEGMENT_NUM,
    PAGE_DOC_TYPE
ORDER BY
    DOC_ID,
    SEGMENT_NUM;


-- Step 3 spot check
SELECT
    DOC_ID,
    SEGMENT_NUM,
    PAGE_DOC_TYPE,
    PAGE_INDEX_START,
    PAGE_INDEX_END,
    PAGE_NUMBER_START,
    PAGE_NUMBER_END,
    PAGE_COUNT,
    CONFIDENCE
FROM PERMAFROST_POC.PROCESSING.SEGMENT_BOUNDARIES
ORDER BY DOC_ID, SEGMENT_NUM;


-- ============================================
-- STEP 4: Assemble segment signals; UUID assignment
-- ============================================
CREATE OR REPLACE TRANSIENT TABLE PERMAFROST_POC.PROCESSING.SEGMENT_SIGNALS AS

SELECT
    sb.DOC_ID,
    sb.SEGMENT_NUM,
    sb.PAGE_DOC_TYPE,
    sb.PAGE_INDEX_START,
    sb.PAGE_INDEX_END,
    sb.PAGE_NUMBER_START,
    sb.PAGE_NUMBER_END,
    sb.CONFIDENCE,
    UUID_STRING()      AS CHILD_DOC_ID,
    ps.PAGE_SIGNAL     AS BOUNDARY_SIGNAL
FROM PERMAFROST_POC.PROCESSING.SEGMENT_BOUNDARIES sb
INNER JOIN PERMAFROST_POC.PROCESSING.PAGE_SIGNALS ps
    ON  ps.DOC_ID     = sb.DOC_ID
    AND ps.PAGE_INDEX = sb.PAGE_INDEX_START;


-- step 4 spot check
SELECT
    DOC_ID,
    SEGMENT_NUM,
    PAGE_DOC_TYPE,
    PAGE_INDEX_START,
    PAGE_INDEX_END,
    CHILD_DOC_ID,
    CONFIDENCE,
    BOUNDARY_SIGNAL
FROM PERMAFROST_POC.PROCESSING.SEGMENT_SIGNALS
ORDER BY DOC_ID, SEGMENT_NUM;



-- ============================================
-- STEP 5: Write final classified documents
-- ============================================
MERGE INTO PERMAFROST_POC.SPIKE.DOCUMENTS_CLASSIFIED AS target
USING (
    SELECT
        ss.CHILD_DOC_ID,
        ss.DOC_ID,
        UPPER(ss.PAGE_DOC_TYPE)  AS DOC_TYPE,
        ss.PAGE_NUMBER_START     AS PAGE_START,
        ss.PAGE_NUMBER_END       AS PAGE_END,
        ss.CONFIDENCE,
        ss.BOUNDARY_SIGNAL,
        CURRENT_TIMESTAMP()      AS CLASSIFIED_AT
    FROM PERMAFROST_POC.PROCESSING.SEGMENT_SIGNALS ss
) AS source
ON target.CHILD_DOC_ID = source.CHILD_DOC_ID
WHEN MATCHED THEN UPDATE SET
    target.DOC_ID          = source.DOC_ID,
    target.DOC_TYPE        = source.DOC_TYPE,
    target.PAGE_START      = source.PAGE_START,
    target.PAGE_END        = source.PAGE_END,
    target.CONFIDENCE      = source.CONFIDENCE,
    target.BOUNDARY_SIGNAL = source.BOUNDARY_SIGNAL,
    target.CLASSIFIED_AT   = source.CLASSIFIED_AT
WHEN NOT MATCHED THEN INSERT (
    CHILD_DOC_ID,
    DOC_ID,
    DOC_TYPE,
    PAGE_START,
    PAGE_END,
    CONFIDENCE,
    BOUNDARY_SIGNAL,
    CLASSIFIED_AT
) VALUES (
    source.CHILD_DOC_ID,
    source.DOC_ID,
    source.DOC_TYPE,
    source.PAGE_START,
    source.PAGE_END,
    source.CONFIDENCE,
    source.BOUNDARY_SIGNAL,
    source.CLASSIFIED_AT
);


-- ============================================
-- STEP 6: Update DOCUMENT_PAGES with child doc id
-- ============================================
INSERT INTO PERMAFROST_POC.SPIKE.DOCUMENTS_PAGES (
    DOC_ID,
    CHILD_DOC_ID,
    PAGE_INDEX,
    PAGE_NUMBER,
    PAGE_CONTENT,
    PAGE_CONTENT_TRANSLATED,
    EXTRACTED_AT
)
SELECT
    p.DOC_ID,
    NULL AS CHILD_DOC_ID,
    p.PAGE_INDEX,
    p.PAGE_NUMBER,
    p.PAGE_CONTENT,
    p.PAGE_CONTENT_TRANSLATED,
    p.EXTRACTED_AT
FROM PERMAFROST_POC.PROCESSING.DOCUMENTS_PAGES p
;

UPDATE PERMAFROST_POC.SPIKE.DOCUMENTS_PAGES AS p
SET p.CHILD_DOC_ID = dc.CHILD_DOC_ID
FROM PERMAFROST_POC.SPIKE.DOCUMENTS_CLASSIFIED AS dc
WHERE p.DOC_ID      = dc.DOC_ID
  AND p.PAGE_NUMBER BETWEEN dc.PAGE_START AND dc.PAGE_END;

-- step 5 and 6 spot check
SELECT CHILD_DOC_ID, DOC_ID, DOC_TYPE, PAGE_START, PAGE_END, CONFIDENCE, BOUNDARY_SIGNAL
FROM PERMAFROST_POC.SPIKE.DOCUMENTS_CLASSIFIED
ORDER BY DOC_ID, PAGE_START;

SELECT DOC_ID, CHILD_DOC_ID, PAGE_INDEX, PAGE_NUMBER
FROM PERMAFROST_POC.SPIKE.DOCUMENTS_PAGES
ORDER BY DOC_ID, PAGE_INDEX;



-- Truncate to reset
-- Clear both spike output tables
-- TRUNCATE TABLE PERMAFROST_POC.SPIKE.DOCUMENTS_CLASSIFIED;
-- TRUNCATE TABLE PERMAFROST_POC.SPIKE.DOCUMENTS_PAGES;


