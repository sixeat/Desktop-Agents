import sys

from PyQt6.QtWidgets import QApplication

from config import PERSONAS_DIR
from core.agent import Agent
from core.agent_bus import AgentBus
from core.llm_client import OpenAICompatibleClient
from core.llm_settings import has_api_key, load_llm_settings, settings_to_client_kwargs
from ui.agent_manager import AgentManager
from ui.api_key_dialog import ApiKeyDialog


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


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not ensure_llm_configured():
        return

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
    bus.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
