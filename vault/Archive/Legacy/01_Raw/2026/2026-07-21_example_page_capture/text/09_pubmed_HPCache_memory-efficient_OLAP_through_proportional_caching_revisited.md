---
title: "HPCache: memory-efficient OLAP through proportional caching revisited."
type: raw-text
connector: pubmed
status: ready
created: 2026-07-21
tags:
  - type/raw-text
  - source/pubmed
  - topic/example_page_capture
keywords:
  - "example"
  - "page"
  - "capture"
url: "https://pubmed.ncbi.nlm.nih.gov/39678023/"
authors: "Hamish Nicholson, Periklis Chrysogelos, Anastasia Ailamaki"
published: 2024-01-01
---

# HPCache: memory-efficient OLAP through proportional caching revisited.

- 原文: https://pubmed.ncbi.nlm.nih.gov/39678023/

> [!quote] 原始文字
>
> HPCache: memory-efficient OLAP through proportional caching revisited.
> Journal: The VLDB journal : very large data bases : a publication of the VLDB Endowment
>
> Analytical engines rely on in-memory data caching to avoid storage accesses and provide timely responses by keeping the most frequently accessed data in memory. Purely frequency- and time-based caching decisions, however, are a proxy of the expected query execution speedup only when storage accesses are significantly slower than in-memory query processing. On the other hand, fast storage offers loading times that approach fully in-memory query response times, rendering purely frequency-based statistics incapable of capturing the impact of a caching decision on query execution. For example, caching the input of a frequent query that spends most of its time processing joins is less beneficial than caching a page for a slightly less frequent but scan-heavy query. Thus, existing caching policies waste valuable memory space to cache input data that offer little-to-no acceleration for analytics. This paper proposes HPCache, a buffer management policy that enables fast analytics on high-bandwidth storage by efficiently using the available in-memory space. HPCache caches data based on the speedup potential instead of relying on frequency-based statistics. We show that, with fast storage, the benefit of in-memory caching varies significantly across queries; therefore, we quantify the efficiency of caching decisions and formulate an optimization problem. We implement HPCache in Proteus and show that (i) estimating speedup potential improves memory space utilization, and (ii) simple runtime statistics suffice to infer speedup. We show that HPCache achieves up to a 1.75x speed-up over frequency-based caching policies by caching column proportions and automatically tuning them. Overall, HPCache enables efficient use of the in-memory space for input caching in the presence of fast storage, without requiring workload predictions.

## 关键词

example, page, capture
