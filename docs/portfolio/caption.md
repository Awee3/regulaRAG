# LinkedIn caption

I’m building RegulaRAG Indonesia, my first RAG project, to explore official Indonesian personal data protection documents locally.

The engineering question: how can an answer make its evidence easy to inspect when the corpus contains both legislation and court rulings?

The pipeline extracts PDF chunks with page metadata, offers four retrieval modes, and uses BM25 for the demo. A single Qwen3 1.7B model selects excerpt IDs. The backend returns the original source text and validates citations.

This carousel shows a successful answer, source inspection, and abstention on an unsupported question. It also includes a failure: the system once rejected a question that had supporting evidence.

After development fixes, 12 of 13 cases passed AI review. These were earlier CPU runs, with no independent human validation or general accuracy estimate. The corpus remains limited, and PDF text extraction can lose words.

My main lesson: an authentic quotation still needs a relevance check against the original PDF. Original Indonesian evidence appears alongside English explanations. This is a document search aid, not legal advice.

Code and documentation: https://github.com/Awee3/regulaRAG

#RAG #AIEngineering #Portfolio
