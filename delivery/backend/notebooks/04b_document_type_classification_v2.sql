-- ===========================================================
-- STEP 0 - SETUP
--
CREATE TRANSIENT TABLE IF NOT EXISTS PERMAFROST_POC.SPIKE.DOCUMENTS_CLASSIFIED (
    CHILD_DOC_ID    VARCHAR(36)   NOT NULL,
    DOC_ID          VARCHAR(36)   NOT NULL,
    DOC_TYPE        VARCHAR(100),
    PAGE_START      NUMBER        NOT NULL,
    PAGE_END        NUMBER        NOT NULL,
    CONFIDENCE      FLOAT,
    BOUNDARY_SIGNAL VARCHAR(500),
    CLASSIFIED_AT   TIMESTAMP_TZ  DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_SPIKE_DOCUMENTS_CLASSIFIED PRIMARY KEY (CHILD_DOC_ID)
);

CREATE TRANSIENT TABLE IF NOT EXISTS PERMAFROST_POC.SPIKE.DOCUMENTS_PAGES (
    DOC_ID                   VARCHAR(36)      NOT NULL,
    CHILD_DOC_ID             VARCHAR(36),
    PAGE_INDEX               NUMBER           NOT NULL,
    PAGE_NUMBER              NUMBER           NOT NULL,
    PAGE_CONTENT             VARCHAR(16777216) NOT NULL,
    PAGE_CONTENT_TRANSLATED  VARCHAR(16777216),
    EXTRACTED_AT             TIMESTAMP_TZ     DEFAULT CURRENT_TIMESTAMP(),
    CONSTRAINT PK_SPIKE_DOCUMENTS_PAGES PRIMARY KEY (DOC_ID, PAGE_INDEX)
);


-- Find the DOC_ID for the Cooke test file
SELECT DOC_ID, ORIGINAL_FILENAME, STATUS
FROM PERMAFROST_POC.INGEST.DOCUMENTS_INGESTED
ORDER BY RECEIVED_AT DESC
LIMIT 10;


-- ============================================================
-- STEP 1 - BUILD PAGE_SIGNALS
-- CLIENT-444 Spike
-- Runs AI_CLASSIFY and AI_FILTER on every unclassified page
-- in one set-based SQL statement.
-- Produces one row per page with PAGE_DOC_TYPE and IS_FIRST_PAGE.
-- ============================================================

CREATE OR REPLACE TRANSIENT TABLE PERMAFROST_POC.PROCESSING.PAGE_SIGNALS AS

WITH candidate_pages AS (
    SELECT
        p.DOC_ID,
        p.PAGE_INDEX,
        p.PAGE_NUMBER,
        COALESCE(p.PAGE_CONTENT_TRANSLATED, p.PAGE_CONTENT) AS page_text
    FROM PERMAFROST_POC.PROCESSING.DOCUMENTS_PAGES p
    WHERE p.DOC_ID IN (
        '11a297a0-071f-4ebf-81c4-411eaa5b9533',  -- PO# 4500315952 DRAFT INV,PL,BL.pdf (4 pages)
        'df83d7b7-6d59-4e6b-bbf5-04c62cfaaa18'   -- 146485 HC.pdf (3 pages)
    )
      AND COALESCE(p.PAGE_CONTENT_TRANSLATED, p.PAGE_CONTENT) IS NOT NULL
      AND TRIM(COALESCE(p.PAGE_CONTENT_TRANSLATED, p.PAGE_CONTENT)) != ''
    ORDER BY p.DOC_ID, p.PAGE_INDEX
    LIMIT 20
),

config AS (
    -- Load classify and boundary prompts once.
    SELECT
        MAX(CASE WHEN CONFIG_KEY = 'classify_model'
            THEN CONFIG_VALUE END) AS classify_model,
        MAX(CASE WHEN CONFIG_KEY = 'classify_prompt'
            THEN CONFIG_VALUE END) AS boundary_prompt
    FROM PERMAFROST_POC.CONFIG.PIPELINE_CONFIG
    WHERE CONFIG_KEY IN ('classify_model', 'classify_prompt')
)

SELECT
    cp.DOC_ID,
    cp.PAGE_INDEX,
    cp.PAGE_NUMBER,
AI_CLASSIFY(
    cp.page_text,
    [
        {
            'label': 'COMMERCIAL_INVOICE',
            'description': 'Seller-issued document stating goods sold, unit prices, total amount, buyer, and seller details for a shipment.'
        },
        {
            'label': 'PACKING_LIST',
            'description': 'Lists individual packages in a shipment with weights, dimensions, and contents but no pricing information.'
        },
        {
            'label': 'BILL_OF_LADING',
            'description': 'Carrier-issued transport contract listing shipper, consignee, port of loading, port of discharge, and container details.'
        },
        {
            'label': 'HEALTH_CERTIFICATE',
            'description': 'Government or veterinary authority certificate confirming seafood products meet health and safety standards for import.'
        },
        {
            'label': 'CATCH_CERTIFICATE',
            'description': 'Fisheries authority document certifying the catch origin, vessel, fishing area, and species to prove legal harvest.'
        },
        {
            'label': 'CERTIFICATE_OF_ORIGIN',
            'description': 'Official document certifying the country where goods were produced or manufactured, used for customs and trade purposes.'
        },
        {
            'label': 'UNKNOWN',
            'description': 'Page does not clearly match any known document type, or is a freight, logistics, or shipping cost invoice.'
        }
    ],
    {
        'task_description': 'Classify this page from a seafood import shipping document packet into exactly one document type.',
        'examples': [
            {
                'input': 'FREIGHT INVOICE PO NO.: 4500315952 OCEAN FREIGHT AND LOCAL CHARGE IN VIETNAM BILL OF LADING NO.: EGLV235601016447 CONTAINER NO.: EMCU5617883 PAYMENT TERMS: 80% AGAINST B/L 20% AFTER FDA PASSAGE',
                'labels': ['UNKNOWN'],
                'explanation': 'This is a freight or logistics cost invoice from a carrier, not a commercial invoice for goods sold. It charges for shipping services, not seafood products.'
            },
            {
                'input': 'COMMERCIAL INVOICE SELLER: DALIAN HONGDAO MARINE PRODUCTS INVOICE NO: CI4500315737 SOLD TO: SLADE GORTON AND CO. INC DESCRIPTION: FROZEN PACIFIC COD FILLET UNIT PRICE USD 4.50/KG TOTAL AMOUNT USD 18000',
                'labels': ['COMMERCIAL_INVOICE'],
                'explanation': 'This is a commercial invoice for seafood goods sold, with product description, unit price, and total amount payable to the seller.'
            }
        ]
    }
):labels[0]::VARCHAR AS PAGE_DOC_TYPE,
    -- Concatenate the boundary prompt with the page text into
    -- one string. AI_FILTER takes a single input argument for text.
    AI_FILTER(
        CONCAT(
            'You are reviewing a page from a seafood import document packet. ',
            'Does this page appear to be the FIRST page of a new document? ',
            'Return TRUE if the page has a clear document start signal such as a document title, ',
            'header, reference number, invoice number, certificate number, or issuing authority at the top. ',
            'Return FALSE if this page is a continuation of the previous document, ',
            'for example a second page of an invoice, an additional page of a packing list, ',
            'or any page that continues from the previous page without a new document header. ',
            'Page content: ',
            cp.page_text
        )
    )                                   AS IS_FIRST_PAGE,
    cp.page_text                                 AS PAGE_TEXT
FROM candidate_pages cp
CROSS JOIN config cfg;


-- Step 1 Check
SELECT
    DOC_ID,
    PAGE_INDEX,
    PAGE_NUMBER,
    PAGE_DOC_TYPE,
    IS_FIRST_PAGE
FROM PERMAFROST_POC.PROCESSING.PAGE_SIGNALS
ORDER BY DOC_ID, PAGE_INDEX;

SELECT PAGE_INDEX, LEFT(PAGE_TEXT, 1000) AS content_preview
FROM PERMAFROST_POC.PROCESSING.PAGE_SIGNALS
WHERE DOC_ID = '11a297a0-071f-4ebf-81c4-411eaa5b9533'
AND PAGE_INDEX = 1;

select *
from permafrost_poc.ingest.documents_ingested
where doc_id = 'df83d7b7-6d59-4e6b-bbf5-04c62cfaaa18';

SELECT STATUS, COUNT(*) AS doc_count
FROM PERMAFROST_POC.INGEST.DOCUMENTS_INGESTED
GROUP BY STATUS;

SELECT COUNT(*) AS already_classified
FROM PERMAFROST_POC.PROCESSING.DOCUMENTS_CLASSIFIED;

SELECT CONFIG_KEY, CONFIG_VALUE
FROM PERMAFROST_POC.CONFIG.PIPELINE_CONFIG
WHERE CONFIG_KEY = 'classify_prompt';

SELECT DOC_ID, PAGE_INDEX, LEFT(PAGE_TEXT, 500) AS content_preview
FROM PERMAFROST_POC.PROCESSING.PAGE_SIGNALS
ORDER BY DOC_ID, PAGE_INDEX;

SELECT DOC_ID, ORIGINAL_FILENAME, STATUS
FROM PERMAFROST_POC.INGEST.DOCUMENTS_INGESTED
ORDER BY RECEIVED_AT DESC
LIMIT 20;

SELECT
    d.DOC_ID,
    d.ORIGINAL_FILENAME,
    COUNT(p.PAGE_INDEX) AS page_count
FROM PERMAFROST_POC.INGEST.DOCUMENTS_INGESTED d
INNER JOIN PERMAFROST_POC.PROCESSING.DOCUMENTS_PAGES p
    ON d.DOC_ID = p.DOC_ID
WHERE d.DOC_ID IN (
    '78da3656-2ccf-4177-b201-24919ce25de9',  -- INVOICE&PACKING LIST
    '690b7109-2c9f-4bab-af55-24e2ad6505ab',  -- Invoice - PL
    '11a297a0-071f-4ebf-81c4-411eaa5b9533',  -- DRAFT INV,PL,BL
    'df83d7b7-6d59-4e6b-bbf5-04c62cfaaa18'   -- HC
)
GROUP BY d.DOC_ID, d.ORIGINAL_FILENAME
ORDER BY page_count DESC;



-- =====================================
-- STEP 2 BUILD PAGE_SEGMENT
-- =====================================

DROP TABLE IF EXISTS PERMAFROST_POC.PROCESSING.PAGE_SEGMENTS;

CREATE TRANSIENT TABLE PERMAFROST_POC.PROCESSING.PAGE_SEGMENTS AS

WITH boundary_flags AS (
    SELECT
        DOC_ID,
        PAGE_INDEX,
        PAGE_NUMBER,
        PAGE_DOC_TYPE,
        IS_FIRST_PAGE,
        -- Get the doc type of the previous page within the same document.
        LAG(PAGE_DOC_TYPE) OVER (
            PARTITION BY DOC_ID
            ORDER BY PAGE_INDEX
        ) AS PREV_DOC_TYPE,
        -- Mark a boundary when the type changes OR AI_FILTER says
        -- this is a new document start. PAGE_INDEX = 0 is always
        -- a boundary so we do not need to check it separately -
        -- LAG returns NULL for the first row which makes the
        -- type-change condition TRUE automatically.
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
    IS_BOUNDARY,
    -- Running sum of boundaries gives each segment a number.
    -- Pages in the same segment share the same SEGMENT_NUM.
    SUM(IS_BOUNDARY) OVER (
        PARTITION BY DOC_ID
        ORDER BY PAGE_INDEX
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS SEGMENT_NUM
FROM boundary_flags;

-- Step 2 check
SELECT
    DOC_ID,
    PAGE_INDEX,
    PAGE_NUMBER,
    PAGE_DOC_TYPE,
    IS_FIRST_PAGE,
    IS_BOUNDARY,
    SEGMENT_NUM
FROM PERMAFROST_POC.PROCESSING.PAGE_SEGMENTS
ORDER BY DOC_ID, PAGE_INDEX;


-- =========================================
-- STEP 3 - Build SEGMENT_BOUNDARIES
-- =========================================
DROP TABLE IF EXISTS PERMAFROST_POC.PROCESSING.SEGMENT_BOUNDARIES;

CREATE TRANSIENT TABLE PERMAFROST_POC.PROCESSING.SEGMENT_BOUNDARIES AS

SELECT
    DOC_ID,
    SEGMENT_NUM,
    PAGE_DOC_TYPE,
    MIN(PAGE_INDEX)  AS PAGE_INDEX_START,
    MAX(PAGE_INDEX)  AS PAGE_INDEX_END,
    MIN(PAGE_NUMBER) AS PAGE_NUMBER_START,
    MAX(PAGE_NUMBER) AS PAGE_NUMBER_END,
    COUNT(*)         AS PAGE_COUNT
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
    PAGE_COUNT
FROM PERMAFROST_POC.PROCESSING.SEGMENT_BOUNDARIES
ORDER BY DOC_ID, SEGMENT_NUM;



-- ==================================
-- STEP 4: Build SEGMENT_SIGNALS
-- ==================================
DROP TABLE IF EXISTS PERMAFROST_POC.PROCESSING.SEGMENT_SIGNALS;

CREATE TRANSIENT TABLE PERMAFROST_POC.PROCESSING.SEGMENT_SIGNALS AS

WITH first_pages AS (
    SELECT
        sb.DOC_ID,
        sb.SEGMENT_NUM,
        sb.PAGE_DOC_TYPE,
        sb.PAGE_INDEX_START,
        sb.PAGE_INDEX_END,
        sb.PAGE_NUMBER_START,
        sb.PAGE_NUMBER_END,
        ps.PAGE_TEXT
    FROM PERMAFROST_POC.PROCESSING.SEGMENT_BOUNDARIES sb
    INNER JOIN PERMAFROST_POC.PROCESSING.PAGE_SIGNALS ps
        ON  ps.DOC_ID     = sb.DOC_ID
        AND ps.PAGE_INDEX = sb.PAGE_INDEX_START
)

SELECT
    fp.DOC_ID,
    fp.SEGMENT_NUM,
    fp.PAGE_DOC_TYPE,
    fp.PAGE_INDEX_START,
    fp.PAGE_INDEX_END,
    fp.PAGE_NUMBER_START,
    fp.PAGE_NUMBER_END,
    UUID_STRING() AS CHILD_DOC_ID,
    AI_COMPLETE(
        'openai-gpt-5.4-mini',
        CONCAT(
            'In one sentence of 20 words or fewer, describe the key identifying signal on this page ',
            'that indicates what type of document it is. ',
            'For example: the document title, reference number, issuing authority, or header. ',
            'Page content: ',
            fp.PAGE_TEXT
        )
    ) AS BOUNDARY_SIGNAL
FROM first_pages fp;


-- Step 4 check
SELECT
    DOC_ID,
    SEGMENT_NUM,
    PAGE_DOC_TYPE,
    PAGE_INDEX_START,
    PAGE_INDEX_END,
    CHILD_DOC_ID,
    BOUNDARY_SIGNAL
FROM PERMAFROST_POC.PROCESSING.SEGMENT_SIGNALS
ORDER BY DOC_ID, SEGMENT_NUM;



-- == STEP 5 Merge into DOCUMENTS_CLASSIFIED

MERGE INTO PERMAFROST_POC.SPIKE.DOCUMENTS_CLASSIFIED AS target
USING (
    SELECT
        ss.CHILD_DOC_ID,
        ss.DOC_ID,
        ss.PAGE_DOC_TYPE       AS DOC_TYPE,
        ss.PAGE_NUMBER_START   AS PAGE_START,
        ss.PAGE_NUMBER_END     AS PAGE_END,
        NULL::FLOAT            AS CONFIDENCE,
        ss.BOUNDARY_SIGNAL,
        CURRENT_TIMESTAMP()    AS CLASSIFIED_AT
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


-- Step 5 spot check
SELECT
    CHILD_DOC_ID,
    DOC_ID,
    DOC_TYPE,
    PAGE_START,
    PAGE_END,
    CONFIDENCE,
    BOUNDARY_SIGNAL,
    CLASSIFIED_AT
FROM PERMAFROST_POC.SPIKE.DOCUMENTS_CLASSIFIED
ORDER BY DOC_ID, PAGE_START;




-- ===================================
-- STEP 6 Tag DOCUMENT_PAGES with CHILD_DOC_ID
--
-- First copy the source pages into the spike table.
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
WHERE p.DOC_ID IN (
    '11a297a0-071f-4ebf-81c4-411eaa5b9533',
    'df83d7b7-6d59-4e6b-bbf5-04c62cfaaa18'
);

-- Then update CHILD_DOC_ID on each page by joining to
-- DOCUMENTS_CLASSIFIED on the page number range.
UPDATE PERMAFROST_POC.SPIKE.DOCUMENTS_PAGES AS p
SET p.CHILD_DOC_ID = dc.CHILD_DOC_ID
FROM PERMAFROST_POC.SPIKE.DOCUMENTS_CLASSIFIED AS dc
WHERE p.DOC_ID      = dc.DOC_ID
  AND p.PAGE_NUMBER BETWEEN dc.PAGE_START AND dc.PAGE_END;


-- Step 6 spot check
SELECT
    DOC_ID,
    CHILD_DOC_ID,
    PAGE_INDEX,
    PAGE_NUMBER
FROM PERMAFROST_POC.SPIKE.DOCUMENTS_PAGES
ORDER BY DOC_ID, PAGE_INDEX;