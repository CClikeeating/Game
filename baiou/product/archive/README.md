# Product Archive

This directory keeps product-side code that is useful for reference but is not part of the v0.3 release path.

- `legacy_web/`: old local Flask debug console. It can show dry-run output, screenshot understanding, and reference segments, so it must not be treated as the user-facing `/app` surface.

Current release entry points remain:

- API and admin: `baiou.product.api`
- User web page: `/app` served by `baiou.product.api.web_alpha`
- Mini program: `miniprogram/`

