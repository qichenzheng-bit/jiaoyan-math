# Phone workspace refresh (V1)

- Mobile breakpoint remains 760px. Desktop layout and printing are unchanged by the new CSS.
- Chat and work use the same phone attachment sheet; desktop chat keeps its existing menu.
- Persistent work files are collapsed into a count; uploaded materials remain in the workspace, and the user can open the existing recognition panel independently.
- Existing uploaded PDFs support physical-page preview. DOCX layout preview renders local files before upload and authenticated stored originals, including tables, styles, images, headers, footers, explicit and saved page breaks. Complex Word pagination/font differences are possible; stored DOCX retains extracted-text fallback. Preview runs in a script-disabled iframe with no external network resources.
- File previews reuse bounded PDF rendering and safe Word extraction; no AI call or database migration is required.
- Regression checks: 320/360/390/430/760px, short landscape viewport, keyboard, file count expansion, direct delete, original comparison, desktop and print. Actual browser checks are performed in CI, not implied by this document.

- Mobile browser coverage includes every primary module entry, 393px and 360px, screenshots at 393px, and actual DOCX rendering before upload and after upload using a real OOXML fixture. These are synthetic browser tests, not physical-device inspection.
