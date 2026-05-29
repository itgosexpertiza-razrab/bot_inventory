from aiogram.fsm.state import State, StatesGroup

class MoveFSM(StatesGroup):
    choosing_asset = State()
    move_owner = State()
    move_cabinet = State()
    move_date = State()
    confirm = State()