import { h1, h2, h3, p, type Block } from '../blocks';

// One Q&A → an h3 question followed by a paragraph answer.
const qa = (q: string, a: string): Block[] => [h3(q), p(a)];

const blocks: Block[] = [
  h1('FAQ'),
  p('Fifty answers, grouped. Do not see yours? Contact your administrator with the `run_id`.'),

  h2('Product'),
  ...qa('1. What does the AP Exception Agent do?', 'It classifies invoice exceptions, routes them through deterministic rules, drafts the vendor/controller message, prioritizes the queue, and records an audit trail — with a human approving every action.'),
  ...qa('2. Does it pay invoices?', 'No. It triages and drafts. Releasing payment stays in your ERP/AP process; the agent never moves money.'),
  ...qa('3. Does it send messages automatically?', 'No. Every message is a **draft** until a human reviews and sends it. Sending is dry-run by default.'),
  ...qa('4. Is it a replacement for my ERP?', 'No — it is a triage layer on top. You feed it an exception export and act on its recommendations.'),
  ...qa('5. What invoice volumes does it handle?', 'Per-upload files up to 25 MB; throughput scales with the durable queue and multiple instances.'),
  ...qa('6. Can I try it without real data?', 'Yes — use the [sample data](/docs/sample-data) or the built-in sample queue.'),
  ...qa('7. What languages does it support?', 'The classifier reads English exception descriptions; the UI is English. Other languages depend on your configured AI provider.'),

  h2('Data & import'),
  ...qa('8. What file formats can I upload?', 'CSV and JSON, up to 25 MB.'),
  ...qa('9. What columns are required?', '`invoice_id`, `vendor_name`, `invoice_amount`, `exception_type`, `exception_description`, `days_outstanding`. See [File Import](/docs/file-import).'),
  ...qa('10. Do my headers have to match exactly?', 'No — common aliases are auto-mapped (e.g. `supplier` → `vendor_name`).'),
  ...qa('11. What happens to bad rows?', 'They are **quarantined** with a reason code; the rest of the file still processes. Download a rejection report to fix and re-upload.'),
  ...qa('12. Is there a CSV template?', 'Yes — **Download CSV template** in the console, or `GET /v1/upload/template.csv`.'),
  ...qa('13. Can I upload the same file twice?', 'Yes; each upload is a separate run. (Sends within a run are idempotent.)'),
  ...qa('14. How are currency values parsed?', 'Symbols and thousands separators are stripped; values must resolve to a number ≥ 0.'),
  ...qa('15. Is my spreadsheet safe from formula injection?', 'Yes — cells starting with `=`, `+`, `-`, `@` are neutralized.'),

  h2('AI & accuracy'),
  ...qa('16. Which AI models are used?', 'Anthropic Claude by default, with Google Gemini and Azure OpenAI as fallbacks; a deterministic mock mode if no key is set.'),
  ...qa('17. How accurate is the classification?', 'Each result carries a confidence score and rationale. Low-confidence items (< 0.60) auto-route to manual review.'),
  ...qa('18. Can the AI be wrong?', 'Yes — that is why a human approves. Confidence, rationale, and the deterministic rule trace make errors easy to catch.'),
  ...qa('19. Does the AI decide severity?', 'No. Severity is deterministic (thresholds). The AI suggestion is stored separately for drift monitoring only.'),
  ...qa('20. Can the AI be tricked by text in an invoice (prompt injection)?', 'User text is delimited and treated as data, and tool-use is forced — the model cannot emit free-form instructions in the pipeline.'),
  ...qa('21. Is my data used to train models?', 'The platform does not train models on your data. Provider data-use depends on your contract with the AI provider you configure.'),
  ...qa('22. What if the AI provider is down?', 'A per-call timeout bounds hung responses; affected rows are recorded as errors and the run continues. With no provider, mock mode keeps the pipeline running.'),
  ...qa('23. How do I monitor AI cost?', 'The `/metrics` endpoint reports AI token usage and an estimated cost.'),

  h2('Routing & resolution'),
  ...qa('24. How does it decide the resolution path?', 'A first-match-wins rule engine over a versioned policy — fully deterministic.'),
  ...qa('25. Can I change the rules and SLAs?', 'Yes — they are tunable per tenant. See [Resolution Paths](/docs/resolution-paths).'),
  ...qa('26. Why did a 6% price variance escalate instead of auto-approve?', 'Rules evaluate in order; a ≥ 5% variance matches the escalate rule before the auto-approve rule can apply.'),
  ...qa('27. Why is a duplicate not sent to the vendor?', 'Duplicates are **held for investigation** by design — to prevent tipping off or double-paying.'),
  ...qa('28. What is an SLA here?', 'The target resolution time attached to each path (e.g. 8 h for escalations).'),
  ...qa('29. Can two runs of the same file differ?', 'No — same input + same policy version = identical routing, severity, and priority.'),

  h2('Communications'),
  ...qa('30. What channels can it draft?', 'Vendor email, internal email, Slack, and finance notes.'),
  ...qa('31. What is dry-run mode?', 'The default safe mode: sending writes a preview file instead of contacting a real recipient.'),
  ...qa('32. How do I enable live sending?', 'Turn off dry-run and set a recipient-domain allow-list (and ideally a vendor master and daily cap). See [Administrator Guide](/docs/admin-guide).'),
  ...qa('33. Can I edit a draft before sending?', 'Yes — edits are flagged `is_edited_by_human` and recorded.'),
  ...qa('34. What if Slack is not configured?', 'Finance-note/Slack drafts fall back to email with a clear subject prefix.'),
  ...qa('35. What does a `skipped` send mean?', 'No recipient could be resolved, or the domain is not allow-listed.'),

  h2('Dashboards & priority'),
  ...qa('36. How is the priority score computed?', 'A weighted blend of amount, age, severity, path, and confidence. See [Severity & Priority](/docs/severity-priority).'),
  ...qa('37. Can I change the priority weights?', 'Yes — they are tunable per tenant.'),
  ...qa('38. What does "SLA at risk" mean?', 'The exception age is approaching or past its path SLA.'),
  ...qa('39. How is "suspended balance" calculated?', 'The summed value of open exceptions, partitioned by lifecycle state.'),
  ...qa('40. Where do vendor reliability scores come from?', 'Accumulated history per vendor across runs (duplicates, escalations, missing POs, etc.).'),

  h2('Security & compliance'),
  ...qa('41. How is access controlled?', 'Clerk JWT auth on every API route, with per-tenant scoping.'),
  ...qa('42. Can one customer see another data?', 'No — strict tenant isolation; cross-tenant reads return `404`.'),
  ...qa('43. Is there an audit log?', 'Yes — append-only per run, with model/prompt version and rule trace.'),
  ...qa('44. Is it SOX-friendly?', 'It supports key control objectives (authorization, traceability, completeness). See [Compliance & Audit](/docs/compliance).'),
  ...qa('45. Where is my data stored?', 'In your configured database/region. Secrets are never returned by the API.'),
  ...qa('46. Is data encrypted?', 'Use TLS in transit and your platform encryption-at-rest for the database.'),
  ...qa('47. How long is data kept?', 'Per your retention policy; audit events are append-only — export before purging.'),

  h2('Operations & billing'),
  ...qa('48. How do I integrate programmatically?', 'Use the REST [API](/docs/api-reference): submit a run, poll status, read results.'),
  ...qa('49. Are there webhooks?', 'Not today — poll run status or query `/metrics`.'),
  ...qa('50. What are the rate limits?', 'Default `240/minute` per client (`429` over the limit); configurable.'),
];

export default blocks;
