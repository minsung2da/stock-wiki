"""``get_decision_card`` — the decision-card read tool (Veto #13 payload default).

Thin wrapper over :func:`cards.store.get_active` (the Phase-2 store). The whole
point of the Veto #13 layering — designed back in Phase 2 — is that ``get_active``
returns the FULL typed ``DecisionCard`` (payload + ``body_md`` + ``status``), so
the ``view`` projection here is a **serialize-time exclude**, NOT a re-query:

- ``view="payload"`` (DEFAULT) → ``card.model_dump(mode="json", exclude={"body_md"})``.
  The body_md is dropped at serialize time so the default 10-card briefing session
  carries no full bodies (Veto #13 — "filter before context"). NO body_md key.
- ``view="both"`` → ``card.model_dump(mode="json")`` then ``body_md`` is replaced
  with its ``<untrusted>``-wrapped form + the card view carries no separate flag
  (the dict is returned as-is); the body is narrative so it gets the D-03 WRAP.

D-01: no active card for the corp is a NORMAL empty result —
``CardView(corp_code=..., found=False, card=None)``, never an error. Only a
malformed ``corp_code`` or an unknown ``view`` raises
:class:`~mcp_v2.errors.InvalidArgument`.

This module performs NO direct SQL — all DB access is delegated to
``cards.store.get_active`` (so the SC#3 AST guard finds no ``text()`` here).
"""

from __future__ import annotations

import re

from mcp.types import ToolAnnotations

from cards import store
from db.engine import get_engine

from .. import injection
from .._mcp import mcp
from ..errors import InvalidArgument
from ..models import CardView

__all__ = ["get_decision_card"]

_CORP_CODE_RE = re.compile(r"^[0-9]{8}$")
_VALID_VIEWS = ("payload", "both")


def get_decision_card(
    corp_code: str,
    latest: bool = True,
    view: str = "payload",
) -> CardView:
    """Return the latest active decision card for ``corp_code``.

    Args:
        corp_code: the 8-digit DART corp code.
        latest: only mode this phase — ``get_active`` already returns the latest
            active, non-superseded card. Accepted for forward-compat; non-latest
            history is out of scope (read it via the store's ``walk_supersedes``).
        view: ``"payload"`` (default, Veto #13 — body_md EXCLUDED) or ``"both"``
            (payload + ``<untrusted>``-wrapped body_md, D-03).

    Returns:
        :class:`CardView` — ``found=True`` with the projected card dict, or
        ``found=False, card=None`` when no active card exists (D-01 empty model).

    Raises:
        InvalidArgument: ``corp_code`` not 8 ASCII digits, or ``view`` not in
            {"payload", "both"}.
    """
    if not _CORP_CODE_RE.match(corp_code):
        raise InvalidArgument("corp_code must be 8 ASCII digits")
    if view not in _VALID_VIEWS:
        raise InvalidArgument("view must be 'payload' or 'both'")

    card = store.get_active(get_engine(), corp_code)
    if card is None:
        # D-01: no active card is a valid empty result, NOT an error.
        return CardView(corp_code=corp_code, found=False, card=None)

    if view == "payload":
        # Veto #13 default: drop body_md at serialize time — no re-query.
        data = card.model_dump(mode="json", exclude={"body_md"})
    else:  # view == "both"
        data = card.model_dump(mode="json")
        # body_md is narrative → WRAP+FLAG (D-03). The body is wrapped UNCHANGED;
        # detect() advisory flags are attached so a view='both' caller can see
        # whether the body tripped any injection markers.
        flags = [h["pattern_id"] for h in injection.detect(card.body_md)]
        data["body_md"] = injection.wrap_untrusted(card.body_md, "card", card.card_id)
        data["injection_suspected"] = bool(flags)
        data["injection_flags"] = flags

    return CardView(corp_code=corp_code, found=True, card=data)


# Register on the shared mcp via the call form (keeps get_decision_card a plain
# callable for in-process callers; see filing.py for the rationale).
mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))(get_decision_card)
