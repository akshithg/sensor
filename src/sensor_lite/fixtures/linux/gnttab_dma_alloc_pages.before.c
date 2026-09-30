// SPDX-License-Identifier: GPL-2.0-only
// Source: Linux drivers/xen/grant-table.c @ fe8f65b018ef
int gnttab_dma_alloc_pages(struct gnttab_dma_alloc_args *args)
{
	unsigned long pfn, start_pfn;
	size_t size;
	int i, ret;

	size = args->nr_pages << PAGE_SHIFT;
	if (args->coherent)
		args->vaddr = dma_alloc_coherent(args->dev, size,
						 &args->dev_bus_addr,
						 GFP_KERNEL | __GFP_NOWARN);
	else
		args->vaddr = dma_alloc_wc(args->dev, size,
					   &args->dev_bus_addr,
					   GFP_KERNEL | __GFP_NOWARN);
	if (!args->vaddr) {
		pr_debug("Failed to allocate DMA buffer of size %zu\n", size);
		return -ENOMEM;
	}

	start_pfn = __phys_to_pfn(args->dev_bus_addr);
	for (pfn = start_pfn, i = 0; pfn < start_pfn + args->nr_pages;
			pfn++, i++) {
		struct page *page = pfn_to_page(pfn);

		args->pages[i] = page;
		args->frames[i] = xen_page_to_gfn(page);
		xenmem_reservation_scrub_page(page);
	}

	xenmem_reservation_va_mapping_reset(args->nr_pages, args->pages);

	ret = xenmem_reservation_decrease(args->nr_pages, args->frames);
	if (ret != args->nr_pages) {
		pr_debug("Failed to decrease reservation for DMA buffer\n");
		ret = -EFAULT;
		goto fail;
	}

	ret = gnttab_pages_set_private(args->nr_pages, args->pages);
	if (ret < 0)
		goto fail;

	return 0;

fail:
	gnttab_dma_free_pages(args);
	return ret;
}

