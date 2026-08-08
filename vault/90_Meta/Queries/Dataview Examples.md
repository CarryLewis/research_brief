---
title: Dataview Examples
type: meta
---

# Dataview — Research Workspace

```dataview
TABLE type, status, date
FROM "Concepts" OR "Projects" OR "Reflections" OR "Books"
WHERE graph != false
SORT file.mtime DESC
LIMIT 30
```

```dataview
TABLE period, date
FROM "Reports"
WHERE type = "report"
SORT date DESC
```
