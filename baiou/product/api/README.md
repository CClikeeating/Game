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

Main config:

```text
baiou/config/product/miniprogram.json
```

SQLite defaults to:

```text
outputs/baiou/product/app.db
```
