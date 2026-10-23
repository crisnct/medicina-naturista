# Architecture Diagrams

Use **XMind 8** to view the architecture diagrams in this folder.

Download the application from the [official XMind 8 download page](https://xmind.com/download/xmind8/), then open the `.xmind` files in XMind 8.

## Available Diagrams

- [chatbot-external-connections.xmind](chatbot-external-connections.xmind) — the chatbot's connections to external services.
- [final-report-generation.xmind](final-report-generation.xmind) — the final report generation flow.
- [fragment-search-and-scoring.xmind](fragment-search-and-scoring.xmind) — fragment search and scoring.
- [hybrid-index-generation.xmind](hybrid-index-generation.xmind) — the hybrid index generation flow.
- [message-classification-plan.xmind](message-classification-plan.xmind) — message classification and routing.
- [natural-product-condition-classification.xmind](natural-product-condition-classification.xmind) — product–condition source classification, local rules and Ollama, semantic cache, positive-only scoring and atomic ranking publication. Three sheets cover the execution overview, classification details, and contracts/edge cases; notes and attached source hashes document the local implementation reviewed on 2026-10-22.


The current asynchronous report flow is documented in [report-generation-background.xmind](report-generation-background.xmind), an XMind 8 workbook with separate sheets for HTTP admission/polling, job lifecycle and provider configuration. It supersedes the synchronous request lifetime in the earlier report diagram. Architecture diagrams for this project are maintained only in XMind 8 format.
