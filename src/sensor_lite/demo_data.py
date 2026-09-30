"""Pinned Linux kernel history used by the SENSOR Lite browser demo."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from sensor_lite.analyzer import (
    analyze_source,
    build_change_graph,
    mine_patterns,
    score_against_patterns,
)

JsonObject = dict[str, Any]
PACKAGE_ROOT = Path(__file__).resolve().parent
FIXTURE_ROOT = PACKAGE_ROOT / "fixtures" / "linux"

_KERNEL_STUBS = """typedef unsigned long size_t;
typedef unsigned long dma_addr_t;
typedef unsigned long xen_pfn_t;
struct device { int unused; };
struct page { int unused; };
struct gnttab_dma_alloc_args {
    struct device *dev;
    int coherent;
    int nr_pages;
    struct page **pages;
    xen_pfn_t *frames;
    void *vaddr;
    dma_addr_t dev_bus_addr;
};
#define PAGE_SHIFT 12
#define INT_MAX 2147483647
#define ENOMEM 12
#define EFAULT 14
#define GFP_KERNEL 0
#define __GFP_NOWARN 0
#define pr_debug(...) ((void)0)
void *dma_alloc_coherent(struct device *, size_t, dma_addr_t *, int);
void *dma_alloc_wc(struct device *, size_t, dma_addr_t *, int);
unsigned long __phys_to_pfn(dma_addr_t);
struct page *pfn_to_page(unsigned long);
xen_pfn_t xen_page_to_gfn(struct page *);
void xenmem_reservation_scrub_page(struct page *);
void xenmem_reservation_va_mapping_reset(int, struct page **);
int xenmem_reservation_decrease(int, xen_pfn_t *);
int gnttab_pages_set_private(int, struct page **);
int gnttab_dma_free_pages(struct gnttab_dma_alloc_args *);

"""

_FIX_PATTERN: JsonObject = {
    "kind": "required-guard",
    "label": "validate nr_pages before PAGE_SHIFT",
    "contains": ["nr_pages", "PAGE_SHIFT"],
    "support": 1.0,
    "detail": (
        "The revision shifts nr_pages by PAGE_SHIFT without first bounding the value. "
        "The upstream fix adds a range guard to prevent integer overflow."
    ),
}


def prepare_kernel_source(source: str) -> str:
    """Add local declarations that let Clang parse the isolated kernel function."""
    source_without_comments = "\n".join(
        line for line in source.splitlines() if not line.startswith("//")
    )
    return _KERNEL_STUBS + source_without_comments


def _read_fixture(name: str) -> str:
    return (FIXTURE_ROOT / name).read_text(encoding="utf-8")


def build_demo() -> JsonObject:
    """Analyze the pinned kernel revisions and return the complete browser payload."""
    before_source = _read_fixture("gnttab_dma_alloc_pages.before.c")
    after_source = _read_fixture("gnttab_dma_alloc_pages.after.c")
    before_analysis = analyze_source(prepare_kernel_source(before_source))
    after_analysis = analyze_source(prepare_kernel_source(after_source))

    revision_specs: list[JsonObject] = [
        {
            "id": "9bdc7304f536",
            "date": "2018-07-20",
            "message": "allow DMA-capable grant buffers",
            "author": "Oleksandr Andrushchenko",
            "source": before_source,
            "analysis": before_analysis,
            "role": "introduced",
            "url": "https://github.com/torvalds/linux/commit/9bdc7304f536f3f77f0a69e7c3a8f5afda561a68",
        },
        {
            "id": "b3f7931f5c61",
            "date": "2019-11-07",
            "message": "switch gntdev to kvcalloc",
            "author": "Juergen Gross",
            "source": before_source,
            "analysis": before_analysis,
            "role": "enabler",
            "url": "https://github.com/torvalds/linux/commit/b3f7931f5c61ba39e81a5c958bf5d65ebb1838af",
        },
        {
            "id": "e9ea0b30ada0",
            "date": "2022-09-01",
            "message": "prevent integer overflow",
            "author": "Dan Carpenter",
            "source": after_source,
            "analysis": after_analysis,
            "role": "fix",
            "url": "https://github.com/torvalds/linux/commit/e9ea0b30ada008f4e65933f449db6894832cb242",
        },
    ]

    stable_patterns = mine_patterns([before_analysis, before_analysis])
    fix_patterns = [_FIX_PATTERN]
    for revision in revision_specs:
        analysis = revision["analysis"]
        revision["stable_score"] = score_against_patterns(analysis, stable_patterns)
        revision["fix_score"] = score_against_patterns(analysis, fix_patterns)

    return {
        "project": {
            "name": "linux / xen",
            "language": "C",
            "window": "Jul 2018 - Sep 2022",
            "commits": len(revision_specs),
            "files": 1,
            "upstream": "torvalds/linux",
        },
        "revisions": revision_specs,
        "patterns": {"stable": stable_patterns, "fix": fix_patterns},
        "change_graph": build_change_graph(before_analysis, after_analysis),
        "method": {
            "parser": "Clang JSON AST",
            "graph": "API actions, guards, data references",
            "miner": "history + fix-derived regularities",
        },
        "profile": "linux-gnttab",
    }
