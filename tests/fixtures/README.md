# Test fixtures

**Synthetic data only.** Per CLAUDE.md: never check in real client documents
or files containing real PII. Everything here is invented for unit testing.

If you add a fixture, double-check that:
- Names are obvious fakes (e.g. "Jane Doe", "John Q. Public").
- SSNs / EINs / account numbers are not real (use the 4xx-xx-xxxx range
  for SSNs to avoid Presidio's "obvious test number" filter on 123-xx-xxxx
  while still keeping them clearly synthetic).
- Email addresses are at example.com / example.org.
