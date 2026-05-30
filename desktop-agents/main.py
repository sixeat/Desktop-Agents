import argparse
import sys

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QInputDialog

from config import MAX_DESKTOP_AGENTS, MIN_DESKTOP_AGENTS, PERSONAS_DIR
from core.agent import Agent
from core.agent_bus import AgentBus
from core.chat_storage import ChatStorage
from core.explicit_memory import ExplicitMemoryStore
from core.llm_client import OpenAICompatibleClient
from core.llm_settings import has_api_key, load_llm_settings, settings_to_client_kwargs
from core.pet_registry import load_pet_configs, save_pet_configs
from ui.agent_manager import AgentManager
from ui.api_key_dialog import ApiKeyDialog
from ui.agent_edit_dialog import AgentEditDialog
from ui.pet_manager import PetManager


def load_group_persona_names() -> list[str]:
    persona_files = sorted(PERSONAS_DIR.glob("*.json"))
    persona_names = [path.stem for path in persona_files]
    non_default = [name for name in persona_names if name != "default"]
    return non_default or ["default"]


def ensure_llm_configured() -> bool:
    if has_api_key():
        return True
    dialog = ApiKeyDialog(first_run=True)
    return dialog.exec() == ApiKeyDialog.DialogCode.Accepted


def create_initial_pet_configs() -> list:
    count, ok = QInputDialog.getInt(
        None,
        "选择桌面 Agent 数量",
        f"请选择要出现在桌面的 Agent 数量（{MIN_DESKTOP_AGENTS}-{MAX_DESKTOP_AGENTS} 个）：",
        3,
        MIN_DESKTOP_AGENTS,
        MAX_DESKTOP_AGENTS,
        1,
    )
    if not ok:
        return []
    configs = []
    for index in range(count):
        dialog = AgentEditDialog()
        dialog.setWindowTitle(f"创建第 {index + 1}/{count} 个 Agent")
        if dialog.exec() != AgentEditDialog.DialogCode.Accepted or dialog.config is None:
            return []
        configs.append(dialog.config)
    return configs


def run_pet_mode(app: QApplication, open_manager: bool = False) -> bool:
    configs = load_pet_configs()
    if not configs:
        configs = create_initial_pet_configs()
        if not configs:
            return False
        save_pet_configs(configs)

    manager = PetManager(configs, chat_storage=ChatStorage(), explicit_memory=ExplicitMemoryStore())
    manager.create_widgets()
    manager.show_all()
    if open_manager:
        QTimer.singleShot(300, manager.show_agent_management)
    app.aboutToQuit.connect(manager.close)
    app.pet_manager = manager
    return True


def run_agent_mode(app: QApplication) -> bool:
    if not ensure_llm_configured():
        return False

    settings = load_llm_settings()
    client_kwargs = settings_to_client_kwargs(settings)
    agents = {
        persona_name: Agent(
            persona_name=persona_name,
            client=OpenAICompatibleClient(**client_kwargs),
        )
        for persona_name in load_group_persona_names()
    }

    bus = AgentBus()
    for agent_id, agent in agents.items():
        bus.register(agent_id, agent)

    manager = AgentManager(bus=bus, agents=agents)
    manager.create_widgets()
    manager.show_all()

    app.aboutToQuit.connect(bus.stop)
    app.aboutToQuit.connect(manager.close)
    app.agent_bus = bus
    app.agent_manager = manager
    bus.start()
    return True


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Desktop agents and pets")
    parser.add_argument("--mode", choices=["pets", "agents"], default="pets")
    parser.add_argument("--open-manager", action="store_true", help="Open Agent Management after startup")
    return parser.parse_args(argv[1:])


def main():
    args = parse_args(sys.argv)
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    started = run_agent_mode(app) if args.mode == "agents" else run_pet_mode(app, open_manager=args.open_manager)
    if not started:
        return

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
