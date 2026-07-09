"""Jinja2 テンプレート共有インスタンスとフィルタ登録.

Starlette 1.x の ``TemplateResponse(request, name, context)`` 新シグネチャに対し、
ルータ側は ``TemplateResponse(name, {"request": request, ...})`` の記法で書けるよう
薄いラッパを提供する。
"""

from __future__ import annotations

from fastapi.templating import Jinja2Templates

from . import config
from .domain import AGE_BAND_LABELS, stars

_jinja = Jinja2Templates(directory=str(config.templates_dir()))

_jinja.env.filters["stars"] = stars
_jinja.env.globals["AGE_BAND_LABELS"] = AGE_BAND_LABELS
_jinja.env.globals["sex_label"] = lambda s: {"M": "男", "F": "女"}.get(s, "")


def fmt_num(v):
    if v is None:
        return ""
    try:
        f = float(v)
        return str(int(f)) if f.is_integer() else str(f)
    except (TypeError, ValueError):
        return str(v)


_jinja.env.filters["num"] = fmt_num


class _Templates:
    """``TemplateResponse(name, context)`` 記法を新 API に橋渡しするラッパ."""

    def __init__(self, jinja: Jinja2Templates):
        self._jinja = jinja

    @property
    def env(self):
        return self._jinja.env

    def TemplateResponse(self, name, context=None, **kwargs):
        context = context or {}
        request = context.get("request")
        return self._jinja.TemplateResponse(request, name, context, **kwargs)


templates = _Templates(_jinja)
