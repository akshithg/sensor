# Linux kernel fixture provenance

These fixtures contain the body of `gnttab_dma_alloc_pages()` from the public Linux kernel source tree. They reproduce the exact before/after example named in the internship deck.

- `gnttab_dma_alloc_pages.before.c`: parent `fe8f65b018effbf473f53af3538d0c1878b8b329`
- `gnttab_dma_alloc_pages.after.c`: commit `e9ea0b30ada008f4e65933f449db6894832cb242`
- Upstream path: `drivers/xen/grant-table.c`
- Upstream repository: <https://github.com/torvalds/linux>
- Fix: <https://github.com/torvalds/linux/commit/e9ea0b30ada008f4e65933f449db6894832cb242>

The fixture source remains licensed under GPL-2.0-only, matching the upstream file's SPDX identifier. The complete upstream license text is included at `LICENSES/GPL-2.0`. `sensor_lite/demo_data.py` adds local type and API stubs only while parsing the isolated function with Clang; those stubs are not represented as kernel source.
