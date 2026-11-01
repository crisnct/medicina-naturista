# Deduplicating a product's safety messages

For each product in `products` you receive a numbered list of safety messages (`i`, `type`,
`text`, in English) already written about that same product. Your task is to group the
messages that express the same risk, nothing else. Do not rewrite, translate, add or remove
messages.

Two messages belong to the same group only if they describe the same risk for the same
substance, drug class, food, condition or group of people, with the same effect. The type
(`warning`, `contraindication`, `interaction`) does not matter: the same risk written under
different types is the same risk.

Never group messages:
- about different partners or conditions, even from the same broad class (for example
  anticoagulants and contraceptives, or pregnancy and children);
- with different effects for the same partner (for example reduced efficacy of a drug and
  serotonin syndrome);
- where one message is generic and the other names a specific partner, drug class or condition.
  A general message such as "may alter the metabolism of other drugs" never absorbs a message
  that names a specific drug or class (for example ciclosporin, digoxin, theophylline);
- when you are not sure they are the same risk. When in doubt, leave them separate.

Answer only with the strict JSON requested, without Markdown, explanations or extra fields:
an object with the key `products`, with one entry for each product received, in the same
order. Each entry has exactly `herb_id` (copied exactly from the request) and `groups`.
`groups` is a list of groups; a group is a list of at least two distinct numbers `i`. A number
appears in at most one group. Messages without a pair appear nowhere. If there are no
duplicates, `groups` is the empty list.
