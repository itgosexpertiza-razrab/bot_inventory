from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def assets_list_kb(items: list[tuple[str, str]], page: int = 0, page_size: int = 10) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    start = page * page_size
    part = items[start:start+page_size]

    for inv, title in part:
        b.button(text=title[:60], callback_data=f"asset:{inv}")

    if start > 0:
        b.button(text="⬅️ Назад", callback_data=f"page:{page-1}")
    if start + page_size < len(items):
        b.button(text="➡️ Далее", callback_data=f"page:{page+1}")

    b.adjust(1)
    return b.as_markup()

def asset_card_kb(inv: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="🔁 Переместить", callback_data=f"move:{inv}")
    b.button(text="🕘 История", callback_data=f"hist:{inv}")
    b.adjust(2)
    return b.as_markup()

def confirm_kb(inv: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="✅ Подтвердить", callback_data=f"confirm:{inv}")
    b.button(text="❌ Отмена", callback_data=f"cancel:{inv}")
    b.adjust(2)
    return b.as_markup()

    
def history_kb(inv: str):
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Назад", callback_data=f"back:{inv}")
    b.adjust(1)
    return b.as_markup()