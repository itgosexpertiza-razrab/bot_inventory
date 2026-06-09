from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from datetime import datetime
import sqlite3
import re
from aiogram.filters import StateFilter
from aiogram.types import FSInputFile
from .states import MoveFSM
from .keyboards import assets_list_kb, asset_card_kb, confirm_kb, history_kb
from .normalize import cab_match, norm_inv
from .excel_io import import_reference_xlsx, rebuild_current_from_reference_and_history, export_result_xlsx
import os
from pathlib import Path
from PIL import Image
from pyzbar.pyzbar import decode as zbar_decode
from .normalize import inv_candidates_from_barcode


router = Router()


async def safe_c_answer(c: CallbackQuery, *args, **kwargs):
    """
    Безопасный ответ на callback.
    Telegram иногда возвращает:
    Bad Request: query is too old...
    Тогда просто игнорируем.
    """
    try:
        await c.answer(*args, **kwargs)
    except Exception:
        pass


@router.callback_query(F.data.startswith("page:"))
async def page_cb(c: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    items = data.get("last_search", [])
    page = int(c.data.split(":")[1])
    await state.update_data(page=page)
    await c.message.edit_reply_markup(reply_markup=assets_list_kb(items, page=page))
    await safe_c_answer(c)


@router.callback_query(F.data.startswith("asset:"))
async def asset_cb(c: CallbackQuery, db: sqlite3.Connection):
    # ✅ отвечаем сразу (можно и в конце, но так надёжнее)
    await safe_c_answer(c)

    inv = c.data.split(":")[1]
    r = get_asset_by_inv(db, inv)
    if not r:
        await c.message.answer("❌ Не найдено.")
        return

    await c.message.answer(
        format_card(r),
        reply_markup=asset_card_kb(inv),
        parse_mode="HTML"
    )


# ⚠️ ВАЖНО: hist_cb должен быть на верхнем уровне файла (НЕ внутри asset_cb).
# Если у вас он случайно "уехал" отступами внутрь asset_cb — верните его на уровень router.
def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def get_asset_by_inv(db: sqlite3.Connection, inv: str) -> sqlite3.Row | None:
    inv = norm_inv(inv)
    if not inv:
        return None
    return db.execute("SELECT * FROM assets_current WHERE inventory_number = ?", (inv,)).fetchone()

@router.callback_query(F.data.startswith("hist:"))
async def hist_cb(c: CallbackQuery, db: sqlite3.Connection):
    inv = c.data.split(":")[1]

    cur = db.execute("""
        SELECT id, moved_at, initiator_username, initiator_tg_id,
               from_owner, from_cabinet, to_owner, to_cabinet
        FROM movements
        WHERE inventory_number = ?
        ORDER BY id DESC
        LIMIT 5
    """, (inv,))
    rows = cur.fetchall()

    if not rows:
        text = f"🕘 <b>История</b> по <code>{_esc(inv)}</code> пока пустая."
        await c.message.edit_text(text, reply_markup=history_kb(inv))
        await safe_c_answer(c)
        return

    parts = [f"🕘 <b>История</b> по <code>{_esc(inv)}</code> (последние {len(rows)}):"]

    for r in rows:
        who = r["initiator_username"] or ""
        who_id = r["initiator_tg_id"] or ""
        who_str = _esc(who) if who else "—"
        if who and not who.startswith("@"):
            who_str = "@" + who_str

        parts.append(
            "\n"
            f"🧾 <b>#{r['id']}</b> • <i>{_esc(r['moved_at'])}</i>\n"
            f"👤 <b>Владелец:</b> {_esc(r['from_owner'] or '—')} → <b>{_esc(r['to_owner'] or '—')}</b>\n"
            f"🏢 <b>Кабинет:</b> {_esc(r['from_cabinet'] or '—')} → <b>{_esc(r['to_cabinet'] or '—')}</b>\n"
            f"🔐 <b>Инициатор:</b> {who_str} <code>{_esc(str(who_id))}</code>"
        )


    await c.message.edit_text("\n".join(parts), reply_markup=history_kb(inv))
    await safe_c_answer(c)


@router.callback_query(F.data.startswith("back:"))
async def back_cb(c: CallbackQuery, db: sqlite3.Connection):
    inv = c.data.split(":")[1]
    r = db.execute("SELECT * FROM assets_current WHERE inventory_number = ?", (inv,)).fetchone()
    if not r:
        await safe_c_answer(c, "Не найдено", show_alert=True)
        return

    text = (
        f"📦 <b>{_esc(r['name'])}</b>\n"
        f"🔢 Инв: <code>{_esc(r['inventory_number'])}</code>\n"
        f"👤 Владелец: {_esc(r['owner'] or '—')}\n"
        f"🏢 Кабинет: {_esc(r['cabinet'] or '—')}\n"
        f"🧾 Серийный: {_esc(r['serial_number'] or '—')}"
    )
    await c.message.edit_text(text, reply_markup=asset_card_kb(inv))
    await safe_c_answer(c)


def is_inventory(s: str) -> bool:
    return bool(re.fullmatch(r"\d{5,10}", s.strip()))

def is_cab_query(s: str) -> bool:
    s = s.strip().lower()
    return bool(re.fullmatch(r"\d{1,4}", s)) or any(k in s for k in ["сервер", "конференц", "актов"])

def format_card(row: sqlite3.Row) -> str:
    return (
        f"📦 <b>{_esc(row['name'])}</b>\n"
        f"🔢 Инв: <code>{_esc(row['inventory_number'])}</code>\n"
        f"👤 Владелец: {_esc(row['owner'] or '-')}\n"
        f"🏢 Кабинет: {_esc(row['cabinet'] or '-')}\n"
        f"🧾 Серийный: {_esc(row['serial_number'] or '-')}"
    )


async def send_asset_cards(m: Message, rows: list[sqlite3.Row], *, limit: int = 20) -> None:
    total = len(rows)
    shown = rows[:limit]

    if total > limit:
        await m.answer(
            f"Найдено: {total}. Показываю первые {limit}. "
            "Уточните фамилию или добавьте имя, чтобы сузить поиск."
        )
    elif total > 1:
        await m.answer(f"Найдено: {total}.")

    for r in shown:
        await m.answer(
            format_card(r),
            reply_markup=asset_card_kb(r["inventory_number"]),
            parse_mode="HTML"
        )

@router.message(Command("start"))
async def start(m: Message):
    await m.answer(
        "Я бот учёта оборудования.\n"
        "Напишите инв. номер (например 007964), кабинет (405/серверная) или ФИО владельца.\n"
        "Команды: /reload_reference (админ), /export"
    )


@router.message(Command("ping"))
async def ping(m: Message):
    await m.answer("pong ✅")

@router.message(Command("paths"))
async def paths_cmd(m: Message, cfg):
    await m.answer(
        "DB_PATH: " + os.path.abspath(cfg.db_path) + "\n"
        "REFERENCE_XLSX: " + os.path.abspath(cfg.reference_xlsx) + "\n"
        "EXPORT_XLSX: " + os.path.abspath(cfg.export_xlsx)
    )




@router.message(Command("count"))
async def count_cmd(m: Message, db: sqlite3.Connection):
    a = db.execute("select count(*) as c from assets_current").fetchone()["c"]
    r = db.execute("select count(*) as c from assets_reference").fetchone()["c"]
    h = db.execute("select count(*) as c from movements").fetchone()["c"]
    await m.answer(f"assets_current={a}, assets_reference={r}, movements={h}")

@router.message(Command("peek"))
async def peek_cmd(m: Message, db: sqlite3.Connection):
    # пример: /peek 7960  или /peek Голубев
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await m.answer("Использование: /peek 7960  или  /peek Голубев")
        return
    q = parts[1].strip()

    # покажем что реально лежит в базе (поиск по вхождению)
    rows = db.execute("""
        SELECT inventory_number, owner, cabinet, length(inventory_number) as L
        FROM assets_current
        WHERE inventory_number LIKE ? OR owner LIKE ? OR name LIKE ?
        ORDER BY inventory_number
        LIMIT 10
    """, (f"%{q}%", f"%{q}%", f"%{q}%")).fetchall()

    if not rows:
        await m.answer("В базе по этому ключу тоже пусто (LIKE не нашёл).")
        return

    text = "Первые совпадения:\n" + "\n".join(
        [f"{r['inventory_number']} (len={r['L']}) | {r['owner'] or '-'} | {r['cabinet'] or '-'}" for r in rows]
    )
    await m.answer(text)
















@router.message(Command("myid"))
async def myid(m: Message):
    await m.answer(f"Ваш Telegram ID: {m.from_user.id}")

@router.message(Command("reload_reference"))
async def reload_ref(m: Message, state: FSMContext, db: sqlite3.Connection, cfg):
    if m.from_user.id not in cfg.admins:
        await m.answer("Нет прав (нужны админы).")
        return
    try:
        n = import_reference_xlsx(db, cfg.reference_xlsx)
        rebuild_current_from_reference_and_history(db)
        await m.answer(f"✅ Справочник перезагружен. Строк: {n}")
    except Exception as e:
        await m.answer(f"❌ Ошибка импорта: {e}")



@router.message(F.photo)
async def on_photo(m: Message, state: FSMContext, db: sqlite3.Connection, bot):
    # Берём самое большое фото
    photo = m.photo[-1]
    file = await bot.get_file(photo.file_id)

    # Скачаем во временный файл
    tmp_dir = Path("/tmp/inventory_bot")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    img_path = tmp_dir / f"{photo.file_unique_id}.jpg"

    await bot.download_file(file.file_path, destination=img_path)

    # Читаем штрихкод
    try:
        img = Image.open(img_path)
        codes = zbar_decode(img)
    except Exception as e:
        await m.answer(f"❌ Не удалось обработать фото: {e}")
        return

    if not codes:
        await m.answer("❌ Штрих-код не найден на фото. Попробуйте ближе/ровнее и без бликов.")
        return

    # Берём первый распознанный код
    raw = codes[0].data.decode("utf-8", errors="ignore").strip()

    cands = inv_candidates_from_barcode(raw)

    if not cands:
        await m.answer(f"❌ Прочитано: {raw}\nНе удалось выделить инвентарный номер.")
        return

    # пробуем найти первый кандидат, который есть в БД
    found = None
    found_inv = None
    for inv in cands:
        r = get_asset_by_inv(db, inv)
        if r:
            found = r
            found_inv = inv
            break

    if not found:
        await m.answer(f"🔎 Штрих-код: {raw}\nКандидаты: {', '.join(cands[:8])}\nНичего не найдено в справочнике.")
        return

    await m.answer(
        f"🔎 Штрих-код распознан → инв: {found_inv}\n\n" + format_card(found),
        reply_markup=asset_card_kb(found["inventory_number"]),
        parse_mode="HTML"
    )




@router.message(Command("export"))
async def export_cmd(m: Message, db: sqlite3.Connection, cfg):
    try:
        export_result_xlsx(db, cfg.export_xlsx)
        doc = FSInputFile(cfg.export_xlsx, filename="os_result.xlsx")
        await m.answer_document(doc)
    except Exception as e:
        await m.answer(f"❌ Ошибка экспорта: {e}")

@router.message(StateFilter(None), F.text)
async def on_text(m: Message, state: FSMContext, db: sqlite3.Connection):
    q = (m.text or "").strip()
    if not q:
        return

    q_cf = q.casefold()

    # 0) если чисто цифры — особая логика (кабинет / инвентарник)
    if q.isdigit():
        rows = db.execute(
            "SELECT * FROM assets_current WHERE inventory_number = ?",
            (norm_inv(q),)
        ).fetchall()

        # Если инвентарник не найден, короткие числа ищем как кабинет.
        if not rows and 1 <= len(q) <= 4:
            rows_all = db.execute("SELECT * FROM assets_current").fetchall()
            rows = [r for r in rows_all if cab_match(r["cabinet"], q)]

        if not rows:
            await m.answer("Ничего не найдено.")
            return

        # ✅ дедуп по inventory_number
        seen = set()
        dedup = []
        for r in rows:
            inv = r["inventory_number"]
            if inv in seen:
                continue
            seen.add(inv)
            dedup.append(r)
        rows = dedup

        if len(rows) == 1:
            r = rows[0]
            await m.answer(
                format_card(r),
                reply_markup=asset_card_kb(r["inventory_number"]),
                parse_mode="HTML"
            )
            return

        items = [
            (r["inventory_number"], f"{r['inventory_number']} • {r['name']} • {r['cabinet'] or '-'}")
            for r in rows
        ]
        await state.update_data(last_search=items, page=0)
        await m.answer(f"Найдено: {len(items)}. Выберите:", reply_markup=assets_list_kb(items, page=0))
        return

    # 1) сначала ищем по владельцу: фамилия/ФИО должны сразу отдавать карточки
    rows_all = db.execute("SELECT * FROM assets_current").fetchall()

    owner_rows = []
    for r in rows_all:
        owner = (r["owner"] or "").casefold()
        if q_cf in owner:
            owner_rows.append(r)

    if owner_rows:
        seen = set()
        dedup = []
        for r in owner_rows:
            inv = r["inventory_number"]
            if inv in seen:
                continue
            seen.add(inv)
            dedup.append(r)

        await send_asset_cards(m, dedup)
        return

    # 2) общий текстовый поиск (название/кабинет) — в Python, устойчиво к кириллице
    rows = []
    for r in rows_all:
        name = (r["name"] or "").casefold()
        cabinet = (r["cabinet"] or "").casefold()

        if q_cf in name or q_cf in cabinet:
            rows.append(r)

    if not rows:
        await m.answer("Ничего не найдено.")
        return

    # ✅ дедуп по inventory_number
    seen = set()
    dedup = []
    for r in rows:
        inv = r["inventory_number"]
        if inv in seen:
            continue
        seen.add(inv)
        dedup.append(r)
    rows = dedup[:50]  # ограничим, чтобы не спамить

    if len(rows) == 1:
        r = rows[0]
        await m.answer(
            format_card(r),
            reply_markup=asset_card_kb(r["inventory_number"]),
            parse_mode="HTML"
        )
        return

    items = [
        (r["inventory_number"], f"{r['inventory_number']} • {r['name']} • {r['cabinet'] or '-'}")
        for r in rows
    ]
    await state.update_data(last_search=items, page=0)
    await m.answer(f"Найдено: {len(items)}. Выберите:", reply_markup=assets_list_kb(items, page=0))


@router.message(Command("owners"))
async def owners_cmd(m: Message, db: sqlite3.Connection):
    rows = db.execute("""
        SELECT owner, count(*) as c
        FROM assets_current
        GROUP BY owner
        ORDER BY c DESC
        LIMIT 10
    """).fetchall()

    if not rows:
        await m.answer("В базе нет данных assets_current.")
        return

    text = "Топ владельцев в базе:\n" + "\n".join(
        [f"{(r['owner'] or '—')} — {r['c']}" for r in rows]
    )
    await m.answer(text)

# Перемещение — упрощённый MVP (только владелец+кабинет, дата сегодня)
@router.callback_query(F.data.startswith("move:"))
async def move_start(c: CallbackQuery, state: FSMContext):
    inv = c.data.split(":")[1]
    await state.clear()  # важно: чистим старое
    await state.update_data(inv=inv, new_owner=None, new_cabinet=None)
    await state.set_state(MoveFSM.move_owner)
    await c.message.answer("Введите нового владельца (ФИО) или `-` чтобы не менять:", parse_mode="Markdown")
    await safe_c_answer(c)

@router.message(MoveFSM.move_owner)
async def move_owner(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    await state.update_data(new_owner=None if t == "-" else t)
    await state.set_state(MoveFSM.move_cabinet)
    await m.answer("Введите новый кабинет (номер/серверная/конференц/актовый) или `-` чтобы не менять:", parse_mode="Markdown")

@router.message(MoveFSM.move_cabinet)
async def move_cab(m: Message, state: FSMContext):
    t = (m.text or "").strip()
    await state.update_data(new_cabinet=None if t == "-" else t)
    data = await state.get_data()
    if data.get("new_owner") is None and data.get("new_cabinet") is None:
        await state.clear()
        await m.answer("❌ Ничего не меняется (и владелец, и кабинет без изменений). Отмена.")
        return
    await state.set_state(MoveFSM.confirm)
    await m.answer("Подтвердить перемещение?", reply_markup=confirm_kb(data["inv"]))

@router.callback_query(F.data.startswith("cancel:"))
async def cancel_move(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.answer("Операция отменена.")
    await safe_c_answer(c)

@router.callback_query(F.data.startswith("confirm:"))
async def confirm_move(c: CallbackQuery, state: FSMContext, db: sqlite3.Connection):
    data = await state.get_data()
    inv_state = data.get("inv")
    inv_cb = c.data.split(":")[1]

    # Защита: подтверждаем только тот inv, который лежит в состоянии
    if not inv_state or inv_state != inv_cb:
        await safe_c_answer(c, "Сессия перемещения сбилась. Начните заново.", show_alert=True)
        await state.clear()
        return

    r = db.execute("SELECT * FROM assets_current WHERE inventory_number = ?", (inv_cb,)).fetchone()
    if not r:
        await c.message.answer("❌ Объект не найден.")
        await state.clear()
        await safe_c_answer(c)
        return

    from_owner, from_cab = r["owner"], r["cabinet"]
    new_owner = data.get("new_owner")
    new_cab = data.get("new_cabinet")

    to_owner = new_owner if new_owner is not None else from_owner
    to_cab = new_cab if new_cab is not None else from_cab

    moved_at = datetime.now().isoformat(timespec="seconds")

    db.execute("""
    INSERT INTO movements(moved_at, initiator_tg_id, initiator_username, initiator_name, inventory_number,
                            from_owner, from_cabinet, to_owner, to_cabinet, comment)
    VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        moved_at,
        c.from_user.id,
        c.from_user.username or "",
        c.from_user.full_name or "",
        inv_cb,
        from_owner, from_cab,
        to_owner, to_cab,
        None
    ))

    db.execute("""
      UPDATE assets_current
      SET owner = ?, cabinet = ?, updated_at = ?
      WHERE inventory_number = ?
    """, (to_owner, to_cab, moved_at, inv_cb))
    db.commit()

    # Считываем обновлённую запись и показываем её (чтобы вы точно видели, что поменялось)
    rr = db.execute("SELECT * FROM assets_current WHERE inventory_number = ?", (inv_cb,)).fetchone()
    await c.message.answer(
        "✅ Сохранено.\n"
        f"Было: {from_owner} / {from_cab}\n"
        f"Стало: {rr['owner']} / {rr['cabinet']}\n"
        f"Инв: {rr['inventory_number']}"
    )

    await state.clear()
    await safe_c_answer(c)
