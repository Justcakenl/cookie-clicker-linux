"""The shared shape of every modal screen: a centred card that escape closes."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, cast

from textual.binding import BindingType
from textual.containers import Vertical
from textual.screen import ModalScreen

from cookie.ui.keys import MODAL_BINDINGS

if TYPE_CHECKING:
    from cookie.app import CookieApp


class ModalCard(Vertical):
    """The bordered panel every modal screen puts its content in."""


class CardScreen(ModalScreen[None]):
    """A modal with the standard close bindings."""

    BINDINGS: ClassVar[list[BindingType]] = list(MODAL_BINDINGS)

    @property
    def game(self) -> CookieApp:
        return cast("CookieApp", self.app)

    def action_close(self) -> None:
        self.dismiss(None)
