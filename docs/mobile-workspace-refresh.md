# Phone workspace refresh (V1)

- Mobile breakpoint remains 760px. Desktop layout and printing are unchanged by the new CSS.
- Chat and work use the same phone attachment sheet; desktop chat keeps its existing menu.
- Persistent work files are collapsed into a count; uploaded materials remain in the workspace, and the user can open the existing recognition panel independently.
- Existing uploaded PDF files support physical-page preview and Word files support paragraph, formula and embedded-image preview. Word preview is not a replica of Word pagination. Pending local Word files still use the original-file fallback until uploaded.
- File previews reuse bounded PDF rendering and safe Word extraction; no AI call or database migration is required.
- Regression checks: 320/360/390/430/760px, short landscape viewport, keyboard, file count expansion, direct delete, original comparison, desktop and print. Actual browser checks are performed in CI, not implied by this document.
