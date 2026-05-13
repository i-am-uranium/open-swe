# Service Catalog Repo Resolution

Open SWE resolves Linear work to repositories using ordered evidence:

1. Explicit repo mentions in the request, for example `repo:clinikk/subscription-service`.
2. GitHub URLs in the request or issue context.
3. Service catalog labels, aliases, keywords, and repo groups.
4. Existing Linear team/project fallback.

Linear labels are only evidence. The source of truth is the versioned service catalog.

## Catalog Location

At runtime the app looks for:

- `/app/config/service-catalog.json`
- `/app/config/service-catalog.toml`
- `/workspace/open-swe/config/service-catalog.json`
- `/workspace/open-swe/config/service-catalog.toml`
- `config/service-catalog.json`
- `config/service-catalog.toml`

Use `config/service-catalog.example.json` as the starting schema.

## Example

```json
{
  "version": 1,
  "repos": [
    {
      "name": "subscription-service",
      "repo": "clinikk/subscription-service",
      "aliases": ["subscription", "membership card", "ola"],
      "linear_labels": ["subscription-service", "backend"]
    }
  ],
  "groups": [
    {
      "name": "ola-membership-card",
      "aliases": ["ola membership card"],
      "repos": ["clinikk/subscription-service", "clinikk/business-portal"]
    }
  ]
}
```

## TODO

- Add more Clinikk repos and aliases as we learn real Linear vocabulary.
- Add the infrastructure repo after it is available to the GitHub App.
- Add confidence scoring and require human confirmation for low-confidence inferred plans.
- Add service ownership metadata for Slack notifications and escalation.
- Add per-repo test command metadata so worker prompts can run the right checks.
