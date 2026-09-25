# Final Report Generation Flow

**Input:** the user's health-problem description and the local hybrid index.

**Output:** recommendations displayed in the chat and a downloadable PDF report, with optional email delivery.

## 1. Accept the user's health-problem description — `on_message()`

- **1.1.** Resolve the current browser-tab session from the session cookie and Gradio session identifier.
- **1.2.** Trim the submitted message.
- **1.3.** Ignore an empty message.
- **1.4.** Reject a message that exceeds the configured maximum length.
- **1.5.** Acquire the session lock.
- **1.6.** Append the user's message to the chat history.
- **1.7.** Clear any previously generated report from the session.
- **1.8.** Replace the current health problem in the user profile with the new message.
- **1.9.** Set `auto_report_pending=True`.
- **1.10.** Append the “Preparing recommendations” status message to the chat.
- **1.11.** Return the updated chat history to the browser.

## 2. Trigger report generation — `on_auto_report()` and `on_report()`

- **2.1.** Gradio invokes `on_auto_report()` after the message-submission handler completes.
- **2.2.** Resolve the current session again.
- **2.3.** Acquire the session lock.
- **2.4.** Stop when no automatic report is pending.
- **2.5.** Set `auto_report_pending=False` so the same submission is processed only once.
- **2.6.** Call `on_report()`.
- **2.7.** Verify that the profile contains a health problem.
- **2.8.** Stop with a user-facing message when the profile is not ready for report generation.

## 3. Build the search-query set — `Retriever.collect()`

- **3.1.** Generate consultation queries from the current health profile.
- **3.2.** Stop retrieval when no usable query can be generated.
- **3.3.** Extract meaningful words from the complete health-problem text.
- **3.4.** Add the exact health-problem text as a priority query.
- **3.5.** Add a query made from the meaningful topic words.
- **3.6.** Add the remaining consultation queries derived from the profile.
- **3.7.** Create safety variants by appending contraindication, interaction, and warning terms to every base query.

## 4. Run hybrid retrieval for every query — `search.rank()`

- **4.1.** Read the embedding model and vector dimension from `data/hybrid_index/manifest.json`.
- **4.2.** Memory-map `data/hybrid_index/embeddings.npy`.
- **4.3.** Generate the E5 query vector with the `query: ` prefix.
- **4.4.** Normalize the query vector.
- **4.5.** Calculate semantic similarity against all document vectors.
- **4.6.** Retain the configured number of top semantic candidates.
- **4.7.** Convert the query into an SQLite FTS5 expression.
- **4.8.** Retrieve lexical candidates from `index.sqlite3`, ordered by BM25.
- **4.9.** Combine semantic and lexical ranks with Reciprocal Rank Fusion using `k=60`.
- **4.10.** Keep the configured number of top hybrid results.
- **4.11.** Load fragment text, source path, heading, and line range from SQLite.
- **4.12.** Return hybrid score, semantic similarity, lexical rank, and traceability metadata.

## 5. Filter, prioritize, and assemble evidence — `Retriever.collect()`

- **5.1.** For each search query, retain results that have a lexical rank and contain a meaningful query word.
- **5.2.** Retain safety-document results even when the regular lexical condition is not satisfied.
- **5.3.** Find additional fragments that directly cover the complete health problem.
- **5.4.** Find fragments from documents dedicated to the detected topic words.
- **5.5.** Add exact-topic fragments to the evidence first.
- **5.6.** Add dedicated-document fragments second.
- **5.7.** Add the remaining accepted query results in round-robin order across query batches.
- **5.8.** Deduplicate fragments by their `C<chunk_id>` evidence identifier.
- **5.9.** Stop after reaching the configured maximum evidence count.
- **5.10.** Expand each fragment with its semantic heading and nearby source context.
- **5.11.** Limit each evidence text to the configured evidence-context size.
- **5.12.** Store each evidence entry as an ID, source path with line range, and text.
- **5.13.** Return the ordered evidence inventory to `on_report()`.
- **5.14.** Stop report generation with a user-facing message when no evidence is found.

## 6. Prepare the evidence payload — `XAIClient.generate()`

- **6.1.** Log the total evidence count and character count.
- **6.2.** Convert the evidence dictionary into ordered entries containing `id`, `source`, and `text`.
- **6.3.** Serialize the evidence entries to estimate the request-context size.
- **6.4.** Keep every evidence entry unchanged when the serialized context is at most 2,400,000 characters.
- **6.5.** When the limit is exceeded, log the complete pre-compaction inventory.
- **6.6.** Calculate the text budget remaining after JSON metadata is accounted for.
- **6.7.** Reduce fragment texts proportionally while initially retaining at least 256 characters per entry.
- **6.8.** Continue trimming long entries evenly until the serialized evidence fits the hard limit.
- **6.9.** Preserve every evidence ID and source during compaction.
- **6.10.** Log the exact inventory sent to the AI and the number of characters removed from each fragment.
- **6.11.** Build the user prompt from the health profile and all admitted evidence entries.
- **6.12.** Load the report-generation system prompt from `ai/prompts/generate_report_system.md`.

## 7. Request the structured report from xAI

- **7.1.** Read `GROK_API_KEY_MED` from the application settings.
- **7.2.** Stop with `AIUnavailable` when the API key is missing.
- **7.3.** Create one xAI Responses API request.
- **7.4.** Use the configured xAI model and reasoning effort.
- **7.5.** Send the system prompt and user payload as separate input messages.
- **7.6.** Request a JSON-object response.
- **7.7.** Set `max_output_tokens=20000`.
- **7.8.** Set `store=false`.
- **7.9.** Send the request to the configured `/responses` endpoint.
- **7.10.** Record HTTP status, duration, response size, and request ID in the logs.
- **7.11.** Convert HTTP or connection failures into a user-facing `AIUnavailable` error.

## 8. Parse and normalize the AI response

- **8.1.** Parse the HTTP response as JSON.
- **8.2.** Verify that the xAI response status is `completed`.
- **8.3.** Extract every `output_text` block from message outputs.
- **8.4.** Join the extracted text blocks.
- **8.5.** Parse the joined content as a JSON object.
- **8.6.** Reject an empty, incomplete, or non-object response.
- **8.7.** Initialize the five report sections:
  - **8.7.1.** `uz_intern` — internal use.
  - **8.7.2.** `nutritie` — nutrition.
  - **8.7.3.** `uz_extern` — external use.
  - **8.7.4.** `alte_recomandari` — other recommendations.
  - **8.7.5.** `atentionari` — warnings.
- **8.8.** Normalize nutrition into recipes, recommended, not recommended, forbidden, and other foods.
- **8.9.** Normalize recommendation text while preserving meaningful line breaks.
- **8.10.** Retain only string evidence IDs attached to each recommendation.
- **8.11.** Return the normalized section dictionary to `on_report()`.

## 9. Generate the PDF — `create_pdf()`

- **9.1.** Register the available report fonts.
- **9.2.** Build the report title and informational cover panel.
- **9.3.** Sort recommendation sections using their source coverage.
- **9.4.** Build a stable source-number index from recommendation evidence IDs.
- **9.5.** Render the five recommendation sections in the configured order.
- **9.6.** Render an explicit “no sufficiently relevant information” message for an empty section.
- **9.7.** Render nutrition with its dedicated recipe and food-category layout.
- **9.8.** Add inline source links to recommendations that have valid evidence IDs.
- **9.9.** Build the bibliography from the cited source paths and line ranges.
- **9.10.** Add links from recommendations to bibliography entries and back-links from bibliography entries.
- **9.11.** Add the medical-information notice and the configured visual styling.
- **9.12.** Build the document with ReportLab in memory.
- **9.13.** Return the completed PDF as bytes.

## 10. Store the report in the current session

- **10.1.** Store the PDF bytes in `session.report_bytes`.
- **10.2.** Generate a cryptographically random `report_id`.
- **10.3.** Associate the report ID with the current browser-tab session.
- **10.4.** Keep the report in process memory until the session is cleared, expires, or the application restarts.

## 11. Attempt email delivery — `send_report()`

- **11.1.** Load the Gmail OAuth configuration.
- **11.2.** Return `email_skipped` when email delivery is not configured.
- **11.3.** Build the email message and attach the generated PDF.
- **11.4.** Refresh the Google OAuth access token.
- **11.5.** Send the message through the Gmail API.
- **11.6.** Return `email_sent` after successful delivery.
- **11.7.** Log an email failure without deleting the already generated PDF.
- **11.8.** Continue the report flow even when email delivery fails.

## 12. Display and download the result

- **12.1.** Convert the normalized report sections into chat-friendly recommendation text.
- **12.2.** Append the recommendation text to the assistant chat history.
- **12.3.** Build a download URL containing the current `tab_id` and `report_id`.
- **12.4.** Return the updated chat history and download control to the browser.
- **12.5.** When the user requests the PDF, resolve the session from the browser cookie.
- **12.6.** Verify that the requested tab and report IDs belong to that session.
- **12.7.** Return HTTP 404 when the report does not belong to the current session or is no longer available.
- **12.8.** Return the PDF as an attachment with `Cache-Control: no-store` when validation succeeds.

## 13. Handle report-generation failures

- **13.1.** Show a specific user-facing message when the health problem is missing.
- **13.2.** Show a specific user-facing message when local retrieval returns no evidence.
- **13.3.** Show the `AIUnavailable` message when the AI service or its response is unavailable.
- **13.4.** Log the exception type, message, and traceback for unexpected failures.
- **13.5.** Show a generic report-generation failure message for unexpected errors.
- **13.6.** Treat email delivery as best-effort so an email failure does not invalidate the report.

## Final result

```text
User message
    -> session profile
    -> hybrid local retrieval
    -> prioritized evidence inventory
    -> one structured xAI request
    -> normalized recommendation sections
    -> in-memory PDF report
    -> chat response and secure download link
    -> optional Gmail delivery
```

This document complements the detailed technical diagram in `02-generare-raport-final.md` and explains the flow without Mermaid syntax or sequence-diagram complexity.
