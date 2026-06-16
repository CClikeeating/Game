# Baiou Miniprogram API

Start locally:

```powershell
python -m baiou.product.api.serve
```

Default URL:

```text
http://127.0.0.1:7871
```

The API keeps the product runtime unchanged and adds the first miniprogram product shell:

- user placeholder login
- conversations with independent background
- reply generation with recent conversation history
- staged image uploads for `wx.uploadFile`
- daily reply quota
- feedback records
- announcement and billing placeholders
- `/app` web alpha entry with access-code login

Main config:

```text
baiou/config/product/miniprogram.json
```

SQLite defaults to:

```text
outputs/baiou/product/app.db
```

## Web alpha

The user-facing browser alpha is served by the same Flask API:

```text
http://101.133.161.248/app
```

Recommended server-only environment variables:

```text
BAIOU_WEB_ACCESS_CODES=内测码
BAIOU_WEB_IP_DAILY_QUOTA=20
BAIOU_WEB_SITE_DAILY_QUOTA=500
BAIOU_MODE_UNIT_COSTS=bailian_rag_fast=1,bailian_rag_quality=2
BAIOU_TRUSTED_PROXY_IPS=127.0.0.1,::1
BAIOU_MINIPROGRAM_DEV_LOGIN=false
BAIOU_MINIPROGRAM_DEBUG=false
```

Do not put the access code, admin token, model keys, or WeChat secret in frontend source or tracked config files. For a stronger setup, store SHA-256 hashes in `BAIOU_WEB_ACCESS_CODE_HASHES` instead of plaintext access codes.

## Admin operations

`/admin` uses `Authorization: Bearer <BAIOU_ADMIN_TOKEN>`. Keep the token in the server environment or a secrets manager, not in tracked config.

The admin API can:

- view site quota used/remaining through `/api/v1/admin/stats`
- list users and recent masked login IPs through `/api/v1/admin/users`
- set or clear per-user quota overrides through `/api/v1/admin/users/<user_id>/quota`
- view today's IP usage through `/api/v1/admin/ip-usage`
