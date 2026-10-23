# from uuid import UUID

from rich.console import Console

# from domain.entities import Game, Player, User
from application.controllers.card_controller import CardController
from application.controllers.game_controller import GameController
from application.controllers.user_controller import UserController
from infrastructure.logging.logger import get_logger
from infrastructure.ui.console.handlers import ConsoleHandler

from infrastructure.ui.console.menu import print_menu
from infrastructure.ui.console.parser import parse_instruction
from infrastructure.ui.console.prompts import read_instruction
from infrastructure.ui.console.state import ConsoleState

logger = get_logger("ui.console")


class ConsoleApp:
    def __init__(
        self,
        game_controller: GameController,
        user_controller: UserController,
        card_controller: CardController,
    ) -> None:
        self._running = True
        self.state = ConsoleState()
        self.handler = ConsoleHandler(
            game_controller,
            user_controller,
            card_controller,
        )
        self.cnsl = Console()

    def run(self) -> None:
        logger.info("Console UI started")

        self.cnsl.print(print_menu())
        while self._running:
            raw = read_instruction(self.handler.cnsl)  # print(f"> {raw}")

            if not raw:
                logger.debug("Empty instruction received")
                continue

            try:
                logger.info(f"Raw instruction received: {raw}")
                instr = parse_instruction(raw)
                logger.info(f"Parsed instruction task: {instr.task}")
                if instr.task == "ext":
                    logger.info("Console UI exit requested")
                    self._running = False
                    continue
                self.cnsl.print(self.handler.dispatch(instr, self.state))
                logger.info("Instruction processed")
            except ValueError as exc:
                logger.error(f"Value error instr:'{raw}': {exc}")
                print(f"!>: {exc}")
            except Exception as exc:
                logger.error(f"Unexp err: {exc}")
                print(f"!> unexp err: {exc}")
