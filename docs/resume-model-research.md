# Resume models: research (October 2026)

Options for making resume scoring, "words to add" and job recommendations
better with small models that run on a normal CPU inside the API, with no paid
services. Licences and sizes were read from the Hugging Face API and PyPI on
22 October 2026; quality numbers come from the model cards. Sources are at the
end.

## Summary

- **Embedding model:** start with **bge-small-en-v1.5**. It's MIT-licensed, 33M parameters, 384 dimensions, and the best of the small English models on the published MTEB averages. Compare it against gte-small, e5-small-v2, all-MiniLM-L6-v2 and snowflake-arctic-embed-s on our own evaluation set before committing.
- **Runtime:** run models with **ONNX Runtime** (24 MB wheel) plus `tokenizers` (3.4 MB). Keep PyTorch (555 MB) out of the API; it's only needed in a separate training environment.
- **Rerank with explainable features first, not a neural reranker.** With a few hundred labels, a small weighted model over skills met, level, years, location and similarity is easier to explain and less likely to overfit. A cross-encoder (ms-marco-MiniLM-L6-v2, 23M, Apache-2.0) is a stage-5 option.
- **Job-specific models:** JobBERT-v2 and v3 (MIT) are strong for **job titles** but read only 64 tokens, so they suit a title-similarity feature, not whole resumes or postings.
- **Skill taxonomy:** build our own alias table, seeded from **O\*NET Technology Skills** (CC BY 4.0) and **ESCO** (free, EU attribution licence), plus the ~90 skills we already curate. **Lightcast Open Skills is out**: its API is now contract-only.
- **Public resume datasets: none qualify.** Every one either contains real people's CVs without stated consent, or has unclear provenance or a licence that doesn't permit this use. Our labelled set has to come from synthetic personas we write, people who explicitly opt in, and our own postings. Skill-annotated **job posting** datasets (SkillSpan, TechWolf's sets, all CC BY 4.0) are usable for checking skill extraction.
- **pgvector on Neon:** available (version 0.8.6 offered), and supports `halfvec` and HNSW. At 384 dimensions in `halfvec` that's about **2 KB per posting including the index**, roughly 120 MB for today's 58,885 postings.

## 1. Embedding models (bi-encoders)

All run on CPU. Scores are the MTEB English averages (56 tasks) from the model
cards, so they're comparable with each other. EmbeddingGemma reports a newer
MTEB version that isn't directly comparable.

| Model | Params | Dims | Max tokens | Licence | MTEB avg | Retrieval | Notes |
|---|---|---|---|---|---|---|---|
| BAAI/bge-small-en-v1.5 | 33.4M | 384 | 512 | MIT | 62.17 | 51.68 | Best small English model in these tables; 55M downloads |
| thenlper/gte-small | 33.4M | 384 | 512 | MIT | 61.36 | 49.46 | ~70 MB weights |
| intfloat/e5-small-v2 | 33.4M | 384 | 512 | MIT | 59.93 | 49.04 | Needs "query:" and "passage:" prefixes |
| sentence-transformers/all-MiniLM-L6-v2 | 22.7M | 384 | 256 trained (512 max) | Apache-2.0 | 56.26 | 41.95 | Fastest; weaker at retrieval |
| Snowflake/snowflake-arctic-embed-s | 33.2M | 384 | 512 | Apache-2.0 | n/a here | n/a | Retrieval-tuned; worth a run on our set |
| mixedbread-ai/mxbai-embed-xsmall-v1 | 24.1M | 384 | n/a | Apache-2.0 | n/a here | n/a | Newer small option |
| BAAI/bge-base-en-v1.5 | ~109M | 768 | 512 | MIT | 63.55 | 53.25 | +1.4 avg over small, at ~3× the cost |
| nomic-ai/nomic-embed-text-v1.5 | 137M | 768 (Matryoshka) | 8192 | Apache-2.0 | n/a here | n/a | Long inputs; larger |
| google/embeddinggemma-300m | 303M | 768 (to 128) | 2048 | **Gemma terms**, gated | 69.67 (MTEB Eng v2) | n/a | Strong, but 9× bigger, a custom licence with a prohibited-use policy, and no float16 |

**Why bge-small first:** it's the best published small model, MIT-licensed,
widely used, and has 384 dimensions, which keeps storage and transfer low.
Resumes and postings run to hundreds of words, so the 512-token limit means
embedding the parts that matter: title, requirements and skills for postings,
and summary, skills and recent roles for resumes. Whether it truncates well is
something to measure.

## 2. Rerankers (cross-encoders)

A cross-encoder reads the resume and the posting together and scores the
pair. It's more accurate than comparing two embeddings, and slower: one model
run per pair, so only for the top 50–200 candidates.

| Model | Params | Licence | Notes |
|---|---|---|---|
| cross-encoder/ms-marco-MiniLM-L6-v2 | 22.7M | Apache-2.0 | The standard small reranker; trained on web search, not jobs |
| jinaai/jina-reranker-v1-tiny-en | 33.0M | Apache-2.0 | Small |
| mixedbread-ai/mxbai-rerank-xsmall-v1 | 70.8M | Apache-2.0 | Middle option |
| BAAI/bge-reranker-base | 278M | MIT | Too slow for many pairs on CPU |
| BAAI/bge-reranker-v2-m3 | 568M | Apache-2.0 | Too big for this use |

None of these is trained on resume-to-job fit, and their scores can't explain
themselves. So the plan reranks with **explainable features** (skills met,
level, years, location, title similarity, ghost risk), and adds a
cross-encoder score as one more feature only if it measurably helps.

## 3. Job-specific models

| Model | What it is | Licence | Fit for us |
|---|---|---|---|
| TechWolf/JobBERT-v2 | Job-title encoder (all-mpnet-base-v2, trained on 5.58M title–skill pairs), 1024 dims, **64 tokens** | MIT | Good for title-to-title similarity ("Firmware Engineer Intern" vs "Embedded Software Intern"); too short for whole resumes |
| TechWolf/JobBERT-v3 | Multilingual version (278M) on 21M pairs, 64 tokens | MIT | Bigger and multilingual; not needed while postings are mostly English |
| TechWolf/ConTeXT-Skill-Extraction-base | 109M bi-encoder that links job-ad sentences to ESCO skills | **No licence listed** | Can't use until the licence is clear |
| SkillSpan-trained models | Skill-span taggers trained on SkillSpan | Dataset is CC BY 4.0; models vary | Reference for skill extraction; the dataset is useful for evaluation |

A published TalentCLEF study found JobBERT-v2 beat its base model on ranking
skills for job titles (nDCG 0.717 vs 0.666) even though it wasn't trained for
that task. That supports a JobBERT title-similarity feature. I didn't find a
published study of JobBERT on whole resumes.

## 4. Running models on a CPU

| Package | Wheel size (Linux, Python 3.12) | Needed for |
|---|---|---|
| onnxruntime 1.31 | **23.8 MB** | Running models in the API and at ingest |
| tokenizers 0.23 | 3.4 MB | Tokenising text for the model |
| numpy | 16.7 MB | Already installed |
| torch 2.14 | **554.6 MB** | Training only, in a separate environment |
| sentence-transformers 6.2 | 0.8 MB (needs torch) | Training only |
| fastembed 0.9 | 0.1 MB (needs onnxruntime) | Optional wrapper; we can do without it |

Model files are separate downloads: bge-small is about 130 MB in fp32 ONNX,
and roughly a quarter of that quantised to int8. I couldn't find a trustworthy
published CPU speed for bge-small. One study of a similar model on a laptop
CPU measured int8 ONNX at about 6 ms per query versus 25 ms in fp32, and
another found int8 can be slower on some CPUs. So **speed is measured on our
own API hardware in stage 4**, before choosing fp32 or int8.

## 5. Skill taxonomies

| Taxonomy | Size | Licence | Tech coverage | Verdict |
|---|---|---|---|---|
| **O\*NET Technology Skills** (USDOL/ETA) | ~31,000 occupation–technology rows; 168 "hot technologies" | **CC BY 4.0**, commercial use allowed with the required credit line | Named software and tools (MySQL, Kubernetes…), tied to occupations | **Use**: aliases, plus which skills go with which occupations |
| **ESCO** (European Commission) | ~13,939 skills, 3,039 occupations | Free download; EU content is CC BY 4.0 unless stated otherwise (check the download's notice) | Broad, but coverage of named frameworks and tools needs measuring | **Use**: broader skills and their related-skill links, after a coverage check against our postings |
| Lightcast Open Skills | ~34,000 skills, updated fortnightly | Terms depend on the licence requested; **API access is contract-based** | Very good for tech | **Out** (paid and contract-only) |
| Stack Overflow tags | Millions of tag uses | CC BY-SA (share-alike) | Excellent for tech | **Skip**: share-alike terms would pull our data in, and the dumps' terms of use have tightened |

**Recommendation:** a Ghostless skill file in the repo with one canonical name
per skill and its aliases ("Golang" → Go, "Postgres" → PostgreSQL), groups
(frontend, embedded…) and "related" links. Seed it from O\*NET and ESCO, keep
our current ~90 curated skills as the core, and grow it from what our postings
actually ask for. The required O\*NET attribution goes on the website's About
page.

## 6. Fine-tuning on our own data

- **Embedding model (bi-encoder):** train with MultipleNegativesRankingLoss on (anchor, positive) pairs. The other pairs in each batch act as negatives, so no explicit negatives are needed. Batch size matters most, and duplicates within a batch should be avoided. Practitioner guidance is **a few hundred to a few thousand pairs**, checked on a held-out set. We can make thousands of *weak* pairs from our own data with no human labels (a posting's title against its own requirements; duplicate postings), then check on human labels whether training helped.
- **Reranker (cross-encoder):** train with BinaryCrossEntropyLoss on labelled pairs. This needs real labels, and a few hundred pairs is a smoke test, not a model.
- **What 150–300 labels can support:** a small, explainable feature model (around 10 weights, fitted by logistic regression), plus honest evaluation. **Neural fine-tuning needs more:** roughly a thousand or more labelled pairs, or many feedback events from opted-in users. That's why fine-tuning is the last stage.
- **Hardware:** a 33M-parameter model can be fine-tuned on a CPU for thousands of pairs in hours. A GPU isn't needed at this scale.

## 7. Public datasets

Checked for licence **and** whether they contain real people's data without consent.

| Dataset | Contents | Licence | Personal data | Verdict |
|---|---|---|---|---|
| lang-uk/recruitment-dataset-candidate-profiles-english (Djinni) | 230K "anonymised" real CVs | MIT | Real people; no stated consent; sample CVs still include first names | **Don't use** |
| lang-uk/recruitment-dataset-job-descriptions-english (Djinni) | 150K job descriptions | MIT | Employer postings, not people | Usable for weak pairs if needed (Ukrainian IT market) |
| datasetmaster/resumes | Real and synthetic resumes mixed | MIT | "Anonymised CV submissions" of unstated origin | **Don't use** |
| ahmedheakl/resume-atlas | ~13K resumes | MIT | Source not stated; looks scraped from resume-template sites | **Don't use** |
| netsol/resume-score-details | 1,031 resumes with GPT-4o job descriptions and scores | "cc" (variant unstated) | Resume source unstated; labels come from GPT-4o | **Don't use** |
| cnamuangtoun/resume-job-description-fit | Resume–job pairs with fit labels | **None** | Unknown | **Don't use** |
| Kaggle "Resume Dataset" (LiveCareer) | ~2.4K resumes | CC0 claimed | Scraped from a resume site; real people | **Don't use** |
| jjzha/skillspan | 14.5K job-ad sentences with skill spans | CC BY 4.0 | Job ads only (the public parts) | **Use** to evaluate skill extraction |
| TechWolf/skill-extraction-tech | Tech job-ad sentences labelled with ESCO skills | CC BY 4.0 | Job ads | **Use** to evaluate skill extraction |
| TechWolf/Synthetic-ESCO-skill-sentences | 100K+ synthetic skill sentences | CC BY 4.0 | Synthetic | **Use** for weak training pairs |

**Consequence:** resume-side training and evaluation data comes from synthetic
personas we write, the founder's own labels, and later only users who opt in.
Real user resumes never go into the repo.

## 8. pgvector on Neon

Neon offers pgvector 0.8.6 (checked against the database), with `halfvec`
(16-bit, up to 4,000 dimensions) and HNSW indexes. Neon's docs say HNSW builds
need `maintenance_work_mem` (no more than 50–60% of the compute's memory).
At our size the index builds in seconds, so that's not a concern.

Note: Neon's current docs don't list a "Build" plan. This estimate uses your
figures: 5 GB storage, 25 GB transfer a month.

**Storage per posting (384 dimensions):**

| Part | `vector` (32-bit) | `halfvec` (16-bit) |
|---|---|---|
| Embedding value | 4 × 384 + 8 = 1,544 B | 2 × 384 + 8 = 776 B |
| Row overhead (job id, model version, header) | ~40 B | ~40 B |
| HNSW index (about 1–1.5× the raw vector, from a published measurement) | ~1.5–2.3 KB | ~0.8–1.2 KB |
| **Total** | **~3–4 KB** | **~1.6–2 KB** |

- **Today:** 58,885 postings ≈ **95–120 MB** with `halfvec`, against a 603 MB database. Room for growth to 150,000 postings (~300 MB).
- **Keeping it small:** embed open postings, and drop embeddings 30 days after a posting closes.
- **Transfer:** writing embeddings goes into Neon, not out. A recommendation query sends one vector (~0.8 KB) and gets back a few hundred ids (~3 KB). So embeddings add almost nothing to the monthly transfer, unlike reading descriptions.
- **Compute:** a nearest-neighbour query over ~50,000 rows is milliseconds with HNSW, and even a full scan is fine at this size.

## Sources

- Model licences and parameter counts: Hugging Face model API, e.g. [bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5), [gte-small](https://huggingface.co/thenlper/gte-small), [e5-small-v2](https://huggingface.co/intfloat/e5-small-v2), [all-MiniLM-L6-v2](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2), [snowflake-arctic-embed-s](https://huggingface.co/Snowflake/snowflake-arctic-embed-s), [embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m), [ms-marco-MiniLM-L6-v2](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2), [bge-reranker-base](https://huggingface.co/BAAI/bge-reranker-base), [mxbai-rerank-xsmall-v1](https://huggingface.co/mixedbread-ai/mxbai-rerank-xsmall-v1)
- MTEB tables: the [bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) and [gte-small](https://huggingface.co/thenlper/gte-small) model cards; EmbeddingGemma numbers from its [model card](https://huggingface.co/google/embeddinggemma-300m) and [DeepMind page](https://deepmind.google/models/gemma/embeddinggemma/)
- Job models: [JobBERT-v2](https://www.huggingface.co/TechWolf/JobBERT-v2), [JobBERT-v3](https://huggingface.co/TechWolf/JobBERT-v3), [ConTeXT-match paper](https://arxiv.org/abs/2505.24640v1), [Multilingual JobBERT / TalentCLEF](https://arxiv.org/pdf/2507.21609)
- Package sizes: PyPI JSON API for [onnxruntime](https://pypi.org/project/onnxruntime/), [torch](https://pypi.org/project/torch/), [tokenizers](https://pypi.org/project/tokenizers/), [sentence-transformers](https://pypi.org/project/sentence-transformers/), [fastembed](https://pypi.org/project/fastembed/)
- CPU speed caveats: [Efficient INT8 inference of small NLP models](https://arxiv.org/pdf/2608.18182), [Is INT8 portable?](https://arxiv.org/pdf/2609.16085), [domain-adaptive dense retrieval](https://arxiv.org/pdf/2602.00899)
- Taxonomies: [O\*NET database licence](https://www.onetcenter.org/license_db.html), [O\*NET Technology Skills](https://www.onetcenter.org/dictionary/25.3/mysql/technology_skills.html), [ESCO download](https://esco.ec.europa.eu/en/use-esco/download), [What is ESCO](https://esco.ec.europa.eu/en/about-esco/escopedia/escopedia/what-esco-and-how-use-it), [Europa copyright notice](https://esco.ec.europa.eu/en/copyright-notice-esco-skills-competences), [Lightcast Open Skills FAQ](https://lightcast.io/open-skills/faqs), [Lightcast taxonomy blog](https://lightcast.io/resources/blog/open-skills-taxonomy), [Stack Overflow data licence](https://stackoverflow.blog/2009/06/04/stack-overflow-creative-commons-data-dump/)
- Fine-tuning: [sbert.net MS MARCO training](https://www.sbert.net/examples/training/ms_marco/README.html), [cross-encoder losses](https://sbert.net/docs/package_reference/cross_encoder/losses.html), [Pinecone MNR guide](https://www.pinecone.io/learn/series/nlp/fine-tune-sentence-transformers-mnr/), [EnterpriseEM](https://arxiv.org/pdf/2406.00010)
- Datasets: Hugging Face cards for [Djinni CVs](https://huggingface.co/datasets/lang-uk/recruitment-dataset-candidate-profiles-english), [Djinni job descriptions](https://huggingface.co/datasets/lang-uk/recruitment-dataset-job-descriptions-english), [datasetmaster/resumes](https://huggingface.co/datasets/datasetmaster/resumes), [resume-atlas](https://huggingface.co/datasets/ahmedheakl/resume-atlas), [netsol/resume-score-details](https://huggingface.co/datasets/netsol/resume-score-details), [SkillSpan paper](https://aclanthology.org/2022.naacl-main.366) and [dataset](https://huggingface.co/datasets/jjzha/skillspan), [TechWolf skill-extraction-tech](https://huggingface.co/datasets/TechWolf/skill-extraction-tech)
- pgvector on Neon: [Neon pgvector docs](https://neon.com/docs/extensions/pgvector), [halfvec storage](https://neon.com/blog/dont-use-vector-use-halvec-instead-and-save-50-of-your-storage-cost), [HNSW size measurement](https://www.dbi-services.com/blog/pgvector-a-guide-for-dba-part-2-indexes-update-march-2026/), [AWS pgvector sizes](https://aws.amazon.com/blogs/database/load-vector-embeddings-up-to-67x-faster-with-pgvector-and-amazon-aurora), [Neon plans](https://neon.com/docs/introduction/plans)
