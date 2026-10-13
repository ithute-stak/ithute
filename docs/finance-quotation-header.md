# Ithute Finance quotation branding

The quotation PDF renderer now supports the supplied Ithute Solutions + iMail horizontal banner.
It preserves the existing document number, amounts, customer data, signature and footer.
The header is shown at the original image ratio (2048 × 600) at full A4 width.

## Install the approved artwork

The source image is a binary upload from the design review and is intentionally not
represented by a broken or fabricated placeholder in source control. Ship a real,
validated JPEG either at:

`apps/backend/app/assets/ithute_imail_quotation_header.jpg`

or by setting the backend environment variable:

`ITHUTE_QUOTATION_HEADER_PATH=/absolute/private/path/to/ithute_imail_quotation_header.jpg`

Provision this JPEG in every backend deployment image or persistent asset mount.
If it is missing or corrupt, quotation generation remains functional with the
existing branded vector fallback, but **it will not have the requested custom banner**.

Only quotation PDFs use this new header. Invoices, receipts and credit notes keep
their current headers. Do not send customer PDFs until the deployed banner is
visually confirmed and the PDF endpoint returns HTTP 200.

## Test

Generate /finance/documents/{id}/pdf for a quotation, inspect its first page and
verify the image, table, totals, validity date, authorized signature, and footer.
Check that the validity date is not earlier than the issue date before sending.
Run backend tests and repository CI before merging or deploying.
