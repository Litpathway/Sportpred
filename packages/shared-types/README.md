# API types

The authoritative schemas are Pydantic DTOs and the FastAPI OpenAPI endpoint at `/openapi.json`.
Frontend response types are in `apps/web/types/api.ts`. Regenerate from OpenAPI when extending the API:

```sh
npx openapi-typescript http://localhost:8000/openapi.json -o packages/shared-types/openapi.d.ts
```

The generator is optional and not a runtime dependency.
