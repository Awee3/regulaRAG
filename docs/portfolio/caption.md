# LinkedIn caption

RegulaRAG Indonesia is my first local RAG project. Ask a question in Indonesian and trace the answer to the official page.

The carousel walks through indexing, retrieval, and citation. E5 embeds passages during indexing and Qdrant Local stores the vectors. Hybrid search combines semantic rankings with BM25 keyword matches. Qwen3 1.7B selects source excerpts or abstains.

The migration preserved all 250 top-ten rankings across 50 questions and five configurations. On 15 answerable holdout questions, average Recall@5 was 65.0% for BM25 and 46.7% for hybrid with reranking. BM25 remains the default.

In the 10-prompt hybrid smoke test, seven prompts returned excerpts and three abstained. AI review found one wrong excerpt and one false abstention. Human validation is pending.

Read the migration evaluation on GitHub https://github.com/Awee3/regulaRAG/blob/codex/migrasi-qdrant/docs/quality_acceptance.md#migrasi-qdrant-local

#RAG #Qdrant #AIEngineering
