# ClearPass API Schema Fixtures

These files document the field names and types returned by each ClearPass REST API
endpoint.  They contain **no actual values** — only field names and inferred types —
so they are safe to generate against a production appliance and commit to the repo.

## How to generate / refresh

```bash
python tools/capture_clearpass_responses.py \
    --url https://cppm.example.com \
    --client-id MY_CLIENT_ID \
    --client-secret MY_CLIENT_SECRET \
    [--no-verify-ssl]
```

Re-run after a ClearPass upgrade to pick up new or changed fields.

## File index

| File | Endpoint | Notes |
|------|----------|-------|
| `version.json` | `GET /api/server/version` | App version fields |
| `services_page.json` | `GET /api/config/service` | HAL collection — list-level item fields |
| `service_item.json` | `GET /api/config/service/{id}` | Full detail — includes rules_conditions, linked policy refs |
| `roles_page.json` | `GET /api/role` | HAL collection |
| `enforcement_profiles_page.json` | `GET /api/enforcement-profile` | HAL collection |
| `enforcement_policies_page.json` | `GET /api/enforcement-policy` | HAL collection |
| `enfpol_item.json` | `GET /api/enforcement-policy/{id}` | Full detail with rules |
| `role_mappings_page.json` | `GET /api/role-mapping` | HAL collection |
| `rm_item.json` | `GET /api/role-mapping/{id}` | Full detail with rules + conditions |
| `auth_methods_page.json` | `GET /api/auth-method` | HAL collection |
| `auth_sources_page.json` | `GET /api/auth-source` | HAL collection |
| `radius_dict_page.json` | `GET /api/radius-dictionary` | Nested vendor_name + attributes[] |
| `app_dict_page.json` | `GET /api/application-dictionary` | Flat or vendor_name:attribute format |
| `tacacs_dict_page.json` | `GET /api/tacacs-service-dictionary` | Same format as app_dict |

## Schema format

```json
{
  "_endpoint": "GET /api/config/service/{id}",
  "_description": "Single ClearPass service (full detail)",
  "response_type": "object",
  "fields": {
    "id": "string",
    "name": "string",
    "type": "string",
    "rules_conditions": {
      "_type": "array",
      "_item_fields": {
        "name": "string",
        "oper": "string",
        "type": "string",
        "value": "string"
      }
    }
  }
}
```

HAL collection files add:
- `hal_envelope_fields` — fields on the outer response object (e.g. `total`, `_links`)
- `total_items` — total count from the `total` field
- `page_size_fetched` — number of items in the captured page
- `item_fields` — merged field schema across all items in the page
