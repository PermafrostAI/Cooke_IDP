WITH
-- 1. Assumptions
assumptions AS (
    SELECT
        2.00 AS usd_per_ai_credit,
        3.66 AS parse_credits_per_1k_pages,  -- AI_PARSE_DOCUMENT, layout mode
        1110 AS monthly_pages                -- 300 documents x 3.7 pages
),

rate_card AS (
    -- AI credits per 1M input tokens, per 1M output tokens
    SELECT *
    FROM
        VALUES
        ('claude-haiku-4-5', 0.60, 3.00),
        ('claude-sonnet-5', 1.20, 6.00),
        ('claude-sonnet-4-6', 1.80, 9.00)
            AS r (model_name, credits_per_m_in, credits_per_m_out)
),

-- 2. Token usage from LLM_USAGE (AI_COUNT_TOKENS on prompts and outputs)
llm_usage AS (
    SELECT
        pipeline_step,
        model_name,
        doc_id AS file_id,
        tokens_in,
        tokens_out
    FROM permafrost_poc.audit.llm_usage
),

-- 3. Billed pages per file, from the parse output.
doc_pages AS (
    SELECT
        doc_id,
        COALESCE(ARRAY_SIZE(v:pages), 1) AS pages
    FROM (
        SELECT
            doc_id,
            IFF(
                IS_VARCHAR(raw_extracted_value),
                TRY_PARSE_JSON(raw_extracted_value::VARCHAR),
                raw_extracted_value
            ) AS v
        FROM permafrost_poc.processing.documents_text
    )
),

file_scope AS (
    SELECT
        COUNT(DISTINCT doc_id) AS files_in_scope,
        SUM(pages) AS pages_in_scope
    FROM doc_pages
),

-- 4. AI_COMPLETE stages
llm_cost AS (
    SELECT
        u.pipeline_step,
        u.model_name,
        NULL::NUMBER AS pages,
        COUNT(*) AS calls,
        COUNT(DISTINCT u.file_id) AS files_logged,
        SUM(u.tokens_in) AS tokens_in,
        SUM(u.tokens_out) AS tokens_out,
        SUM(u.tokens_in) / 1e6 * MAX(r.credits_per_m_in)
        + SUM(u.tokens_out) / 1e6 * MAX(r.credits_per_m_out) AS credits
    FROM llm_usage AS u
    LEFT JOIN rate_card AS r ON u.model_name = r.model_name
    GROUP BY u.pipeline_step, u.model_name
),

-- 5. AI_PARSE_DOCUMENT, billed per page
parse_cost AS (
    SELECT
        'PARSE' AS pipeline_step,
        'AI_PARSE_DOCUMENT' AS model_name,
        NULL::NUMBER AS tokens_in,
        NULL::NUMBER AS tokens_out,
        COUNT(*) AS calls,
        COUNT(DISTINCT d.doc_id) AS files_logged,
        SUM(d.pages) AS pages,
        SUM(d.pages) / 1000 * MAX(p.parse_credits_per_1k_pages) AS credits
    FROM doc_pages AS d
    CROSS JOIN assumptions AS p
),

stages AS (
    SELECT
        pipeline_step,
        model_name,
        calls,
        files_logged,
        tokens_in,
        tokens_out,
        pages,
        credits
    FROM parse_cost
    UNION ALL
    SELECT
        pipeline_step,
        model_name,
        calls,
        files_logged,
        tokens_in,
        tokens_out,
        pages,
        credits
    FROM llm_cost
)

-- 6. Result
SELECT
    s.model_name,
    s.calls,
    s.files_logged,
    sc.files_in_scope,
    s.pages,
    s.tokens_in,
    s.tokens_out,
    s.credits,
    CASE s.pipeline_step
        WHEN 'PARSE' THEN '2. Parse'
        WHEN 'LANGUAGE_CHECK'
            THEN IFF(
                s.model_name = 'claude-haiku-4-5',
                '3a. Language screen (pass 1)',
                '3b. Language screen (pass 2)'
            )
        WHEN 'TRANSLATE' THEN '3c. Translation'
        WHEN 'CLASSIFY' THEN '4. Classification'
        WHEN 'EXTRACTION' THEN '5. Extraction'
        ELSE s.pipeline_step
    END AS stage_name,
    s.credits * p.usd_per_ai_credit AS usd,
    usd / NULLIF(sc.files_in_scope, 0) AS usd_per_file,
    usd / NULLIF(sc.pages_in_scope, 0) AS usd_per_page,
    usd_per_page * p.monthly_pages AS usd_monthly,
    RATIO_TO_REPORT(s.credits) OVER () AS share_of_cost
FROM stages AS s
CROSS JOIN file_scope AS sc
CROSS JOIN assumptions AS p
ORDER BY stage_name;
